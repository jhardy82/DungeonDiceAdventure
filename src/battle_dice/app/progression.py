"""The link between a run and the saved careers of its heroes (Class Evolution Phase 4, step C).

The rules engine plays a run and knows nothing of saves. The career rules decide what a hero may
become and know nothing of battles. This module stands between them, and only the app uses it,
and only while the feature gate is on:

* it opens the save file and makes the profile on first use;
* it turns saved heroes into the party entries of ``StartRun``, each with its build snapshot;
* it tells the career rules that a run started, what each battle's result was (as one mastery
  award per hero), which phase the run is in, and that it ended.

Nothing here decides a rule. Every change goes through :class:`StoredCareerService`.
"""

from __future__ import annotations

import copy
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

from battle_dice.career.catalog import MASTERED_RANK, STAT_KEYS, CareerCatalog
from battle_dice.career.evidence import battle_events, challenge_evidence
from battle_dice.career.model import CareerState, EncounterResult, HeroRecord, Profile, saved_run_phase
from battle_dice.career.service import FINISHED_PHASES, CareerResult, career_tree_view
from battle_dice.career.store import SqliteProfileStore, StoredCareerService, utc_now
from battle_dice.content.loader import Content
from battle_dice.content.vocations import load_catalog
from battle_dice.core import commands as cmd
from battle_dice.core import skills as battle_skills
from battle_dice.core.engine import Engine
from battle_dice.core.events import EventType

Json = dict[str, Any]
PROFILE_ID = "profile_1"
SAVE_FILE = "profile.sqlite"
#: Mastery pace -> what every rank's points are divided by (``battle_dice.settings.PACES``).
PACES = {"normal": 1, "fast": 2, "very_fast": 4}
#: Start presets -> what the first hero (a Squire) has when the profile is made. Every preset but
#: ``fresh`` also recruits a Scout and an Apprentice, so a party of three is ready.
PRESETS = ("fresh", "squire_near_mastery", "guardian_unlocked", "guardian_mastered")


def with_pace(raw_catalog: Json, pace: str) -> Json:
    """The catalog with every rank's points divided by the pace (rounded up, still rising with each rank).

    Points per win stay 1 and 1: the save's award rows allow nothing else. A faster pace asks for
    fewer points instead. ``normal`` returns the catalog as it is.
    """
    divisor = PACES[pace]
    if divisor == 1:
        return raw_catalog
    tuned = copy.deepcopy(raw_catalog)
    for group, thresholds in tuned["mastery"]["rank_thresholds_by_group"].items():
        scaled = [0]
        for needed in thresholds[1:]:
            scaled.append(max(scaled[-1] + 1, math.ceil(needed / divisor)))
        tuned["mastery"]["rank_thresholds_by_group"][group] = scaled
    return tuned


class Progression:
    """One open save and the career of its profile."""

    def __init__(self, save_dir: Path | str, content: Content, raw_catalog: Json | None = None, clock: Callable[[], str] = utc_now,
                 mastery_pace: str = "normal", roster_limit: int | None = None, preset: str = "fresh"):
        if preset not in PRESETS:  # checked before any file is touched, so a wrong name leaves nothing behind
            raise ValueError(f"Unknown start preset '{preset}'.")
        if mastery_pace not in PACES:
            raise ValueError(f"Unknown mastery pace '{mastery_pace}'.")
        self.content, self._clock = content, clock
        self.mastery_pace = mastery_pace
        self.catalog = CareerCatalog(with_pace(raw_catalog if raw_catalog is not None else load_catalog(), mastery_pace), content)
        self.path = Path(save_dir) / SAVE_FILE
        self.store = SqliteProfileStore(self.path, self.catalog, clock)
        try:
            new_profile = PROFILE_ID not in self.store.profile_ids()
            if new_profile:
                self.store.import_state(CareerState(Profile(PROFILE_ID)))
            self.career = StoredCareerService(self.store, PROFILE_ID)
            if roster_limit is not None:
                self.career.service.roster_limit = roster_limit
            if new_profile:
                self._apply_preset(preset)
            else:  # the save may have been made at another pace: its ranks must agree with today's thresholds
                self.career.rederive_ranks(f"mastery pace {mastery_pace}")
        except BaseException:
            self.store.close()
            raise
        encounters = self.catalog.raw["encounters"]
        self._threat = {e["id"]: int(e["threat_rating"]) for e in encounters}
        self._shipped = {int(e["shipped_ref"]["battle"]): e["id"] for e in encounters if e["source"] == "shipped"}
        self._heroes: dict[str, str] = {}  # the run's hero id (h01) -> the saved hero id
        self._seen_events = 0
        #: What the last battles awarded, newest last; the screens show it.
        self.last_awards: list[Json] = []

    def _apply_preset(self, preset: str) -> None:
        """What a new profile starts with. Everything is done through the career rules and is in the event log."""
        if preset == "fresh":
            return
        for starting_class in ("squire", "scout", "apprentice"):
            if not self.recruit(starting_class).accepted:
                raise RuntimeError(f"The preset could not recruit a {starting_class}.")
        hero_id = next(iter(self.state.heroes))
        reason = f"demo preset {preset}"
        top = self.catalog.thresholds("squire")[-1]
        self.career.grant_mastery(hero_id, "squire", top - 1 if preset == "squire_near_mastery" else top, reason)
        if preset in ("guardian_unlocked", "guardian_mastered"):
            if not (self.claim(hero_id, "guardian").accepted and self.change(hero_id, "guardian").accepted):
                raise RuntimeError("The preset could not make the first hero a Guardian.")
        if preset == "guardian_mastered":
            self.career.grant_mastery(hero_id, "guardian", self.catalog.thresholds("guardian")[-1], reason)
            if not self.equip_skill(hero_id, battle_skills.FIELD_MEDIC).accepted:
                raise RuntimeError("The preset could not equip Field Medic.")

    def close(self) -> None:
        self.store.close()

    def __del__(self) -> None:
        # A save that was never closed by hand (a game object dropped without ``close``) is closed here,
        # so the file is not left held open. Closing twice is harmless.
        store = getattr(self, "store", None)
        if store is not None:
            store.close()

    # ----------------------------------------------------------------------------------------
    # The roster
    # ----------------------------------------------------------------------------------------

    @property
    def state(self) -> CareerState:
        return self.career.state

    def _command(self, command_type: str, hero: HeroRecord | None = None, **params: Any) -> CareerResult:
        """Send one career command. Its id is new for every accepted command, and the same after a refusal."""
        state = self.state
        if hero is not None:
            params["hero_id"] = hero.hero_id
        return self.career.submit({
            "type": command_type,
            "command_id": f"app:{state.next_event_seq}:{len(state.processed)}",
            "state_revision": hero.revision if hero is not None else 0,
            "params": params,
        })

    def recruit(self, starting_class: str) -> CareerResult:
        return self._command("RecruitHero", starting_class=starting_class)

    def claim(self, hero_id: str, vocation_id: str) -> CareerResult:
        return self._command("ClaimVocation", self.state.heroes[hero_id], target_vocation_id=vocation_id)

    def change(self, hero_id: str, vocation_id: str) -> CareerResult:
        return self._command("ChangeVocation", self.state.heroes[hero_id], target_vocation_id=vocation_id)

    def run_hero(self, hero_id: str) -> str | None:
        """The id a saved hero fights under in the current run (``h01``), or ``None`` when it is not in it."""
        return next((run_id for run_id, saved in self._heroes.items() if saved == hero_id), None)

    def change_in_run(self, engine: Engine, hero_id: str, vocation_id: str) -> tuple[CareerResult, str | None]:
        """A hero takes another vocation while a run is under way (fixture CE-19).

        The career rules decide first (they allow it between a battle's recovery and the upgrade).
        When the hero is fighting in the run, the run follows with the hero's new build snapshot.
        Returns the career's answer and, when the run refused, its reason; the hero is then put
        back to what it was, so the save and the run never disagree.
        """
        previous = self.state.heroes[hero_id].active_vocation_id
        result = self.change(hero_id, vocation_id)
        fighter = self.run_hero(hero_id)
        if not result.accepted or fighter is None or previous == vocation_id:
            return result, None
        sent = engine.do(cmd.CHANGE_VOCATION, hero_id=fighter, class_id=vocation_id, hero=self.snapshot(hero_id))
        if not sent.accepted:
            self.change(hero_id, previous)
            return result, sent.reason or "The run refused the change."
        self.sync(engine)
        return result, None

    def preview(self, hero_id: str, vocation_id: str) -> CareerResult:
        return self._command("PreviewVocation", self.state.heroes[hero_id], target_vocation_id=vocation_id)

    def tree(self, hero_id: str) -> Json:
        return career_tree_view(self.career.service, hero_id)

    # ----------------------------------------------------------------------------------------
    # Skills
    # ----------------------------------------------------------------------------------------

    def skills(self, hero_id: str) -> Json:
        """The skills a hero has learned, which are equipped, and for each other one why it can or cannot be."""
        hero, service = self.state.heroes[hero_id], self.career.service
        capacity = self.catalog.inheritance_capacity(hero.active_vocation_id)
        used = service.capacity_used(hero)
        slot_of = {skill_id: slot for slot, skill_id in hero.equipped_skills.items()}
        rows = []
        for skill_id in hero.learned_skills:
            skill = self.catalog.skills[skill_id]
            cost = service.skill_cost(hero, skill_id)
            in_battle = skill_id in battle_skills.KNOWN
            problem = None
            if skill_id in slot_of:
                pass  # equipped: it can always be taken off (outside a run)
            elif not in_battle:
                problem = "Not in this version yet: the rules of battle do not know this skill."
            elif skill["transfer"] == "active_only":
                problem = "This skill only works for the vocation that teaches it."
            elif not service.skill_has_a_face(hero, skill_id):
                problem = "None of this hero's dice has a face the skill can work on."
            elif used + cost > capacity:
                problem = f"Needs {cost} capacity; {capacity - used} of {capacity} is free."
            rows.append({
                "skill_id": skill_id,
                "name": str(skill["name"]),
                "summary": str(skill["summary"]),
                "taught_by": self.catalog.name(self.catalog.skill_origin[skill_id][0]),
                "cost": cost,
                "equipped": skill_id in slot_of,
                "slot_index": slot_of.get(skill_id),
                "in_battle": in_battle,
                "problem": problem,
            })
        return {"capacity": capacity, "used": used, "vocation_name": self.catalog.name(hero.active_vocation_id), "rows": rows}

    def equip_skill(self, hero_id: str, skill_id: str) -> CareerResult:
        """Equip a learned skill in the hero's first free slot."""
        hero = self.state.heroes[hero_id]
        slot = next(index for index in range(len(hero.equipped_skills) + 1) if index not in hero.equipped_skills)
        return self._command("EquipInheritedSkill", hero, skill_id=skill_id, slot_index=slot)

    def unequip_skill(self, hero_id: str, skill_id: str) -> CareerResult:
        hero = self.state.heroes[hero_id]
        slot = next((slot for slot, equipped in hero.equipped_skills.items() if equipped == skill_id), -1)
        return self._command("UnequipInheritedSkill", hero, slot_index=slot)

    def roster(self) -> list[Json]:
        """Every saved hero, as the party setup shows it."""
        rows = []
        for hero in self.state.heroes.values():
            vocation_id = hero.active_vocation_id
            mastery = hero.mastery[vocation_id]
            thresholds = self.catalog.thresholds(vocation_id)
            rows.append({
                "hero_id": hero.hero_id,
                "name": hero.display_name or hero.hero_id,
                "vocation_id": vocation_id,
                "vocation_name": self.catalog.name(vocation_id),
                "rank": mastery.rank,
                "points": mastery.points,
                "points_for_next_rank": None if mastery.rank >= MASTERED_RANK else thresholds[mastery.rank],
                "mastered": mastery.rank >= MASTERED_RANK,
                "unlocked_vocations": list(hero.unlocked_vocations),
            })
        return rows

    # ----------------------------------------------------------------------------------------
    # A run
    # ----------------------------------------------------------------------------------------

    def extra_encounters(self) -> list[str]:
        """The encounters a run may add after the shipped battles: the authored ones, easiest first."""
        authored = [e for e in self.catalog.raw["encounters"] if e["source"] == "authored"]
        return [e["id"] for e in sorted(authored, key=lambda e: (e["threat_rating"], e["id"]))]

    def next_run_id(self, seed: int) -> str:
        """A run id no run of this save has used: the save refuses to start the same run twice."""
        return f"run-{self.store.run_count(PROFILE_ID) + 1:04d}-{seed}"

    def snapshot(self, hero_id: str) -> Json:
        """A saved hero's build for a run: what the party entry's ``hero`` carries (fixture CE-35)."""
        hero = self.state.heroes[hero_id]
        vocation_id = hero.active_vocation_id
        stats = self.career.service.effective_stats(hero, vocation_id)
        equipped = sorted((die for die in hero.dice if die.location == "equipped"), key=lambda die: die.slot_index or 0)
        snapshot: Json = {
            "hero_id": hero.hero_id,
            "name": hero.display_name or hero.hero_id,
            "stats": {name: stats[name] for name in STAT_KEYS},
            "skills": [hero.equipped_skills[slot] for slot in sorted(hero.equipped_skills)],
        }
        if hero.dice:  # the hero's dice are tracked: the run uses exactly these
            snapshot["dice"] = [die.definition_id for die in equipped]
            snapshot["bench"] = [die.definition_id for die in hero.dice if die.location != "equipped"]
        return snapshot

    def party_entry(self, hero_id: str, row: str) -> Json:
        return {"class_id": self.state.heroes[hero_id].active_vocation_id, "row": row, "hero": self.snapshot(hero_id)}

    def abandon_run(self) -> None:
        """The player left a run unfinished: the save records it as a defeat. Nothing happens when no run is open."""
        run = self.state.run
        if run is not None and run.phase not in FINISHED_PHASES:
            self.career.end_run(run.run_id, "defeat")

    def run_started(self, engine: Engine) -> None:
        """Call once ``StartRun`` was accepted. A run left unfinished in the save is closed as a defeat first."""
        self.abandon_run()
        self.career.begin_run(engine.state.run_id)
        self._heroes = {member["id"]: member["hero_id"] for member in engine.state.party if "hero_id" in member}
        self._seen_events = 0
        self.last_awards = []
        self.sync(engine)

    def sync(self, engine: Engine) -> list[Json]:
        """Hand over what happened since the last call. Returns the awards of battles that ended meanwhile."""
        run = self.state.run
        if run is None or run.run_id != engine.state.run_id or run.phase in FINISHED_PHASES:
            return []
        new_awards: list[Json] = []
        events = engine.events
        for event in events[self._seen_events:]:
            if event.type in (EventType.BATTLE_WON, EventType.BATTLE_LOST):
                new_awards += self._award_battle(engine, int(event.delta["battle"]), event.type == EventType.BATTLE_WON)
        self._seen_events = len(events)
        self.last_awards += new_awards
        state = engine.state
        if engine.finished():
            assert state.outcome is not None
            self.career.end_run(run.run_id, state.outcome)
        else:
            self.career.report_run(saved_run_phase(state.phase), state.revision)
        return new_awards

    def _award_battle(self, engine: Engine, battle: int, won: bool) -> list[Json]:
        events = battle_events(engine.events, battle)
        encounter_id = self._shipped.get(battle) or str(events[0].delta["encounter_id"])
        outcome = "victory" if won else "defeat"
        self.state.encounter = EncounterResult(encounter_id, self._threat[encounter_id], True, outcome)
        evidence = challenge_evidence(events)
        report = []
        for run_hero, hero_id in self._heroes.items():
            hero = self.state.heroes[hero_id]
            vocation_id = engine.build(run_hero).vocation_id
            challenge_id = str(self.catalog.vocations[vocation_id]["bonus_challenge_id"])
            row = hero.mastery[vocation_id]
            before = (row.rank, row.points, list(hero.learned_skills))
            result = self.career.award_mastery({
                "type": "AwardEncounterMastery", "run_id": engine.state.run_id, "encounter_id": encounter_id, "hero_id": hero_id,
                "vocation_id": vocation_id, "deployed_at_encounter_start": True, "challenge_id": challenge_id,
                "challenge_evidence_count": evidence.get(run_hero, {}).get(challenge_id, 0),
            })
            row = self.state.heroes[hero_id].mastery[vocation_id]
            award = next((a for a in reversed(self.state.awards) if a.identity == (engine.state.run_id, encounter_id, hero_id, vocation_id)), None)
            report.append({
                "battle": battle, "encounter_id": encounter_id, "threat_rating": self._threat[encounter_id], "outcome": outcome,
                "hero_id": hero_id, "name": hero.display_name or hero_id, "vocation_id": vocation_id,
                "base_points": award.base_points if award else 0,
                "challenge_points": award.challenge_points if award else 0,
                "denial_reason": award.denial_reason if award else ("ALREADY_MASTERED" if before[0] >= MASTERED_RANK else None),
                "rank_before": before[0], "rank_after": row.rank, "points_after": row.points,
                "skills_learned": [str(self.catalog.skills[s]["name"]) for s in self.state.heroes[hero_id].learned_skills if s not in before[2]],
                "duplicate": result.duplicate,
            })
        return report
