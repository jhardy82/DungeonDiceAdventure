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
from battle_dice.core.engine import Engine
from battle_dice.core.events import EventType

Json = dict[str, Any]
PROFILE_ID = "profile_1"
SAVE_FILE = "profile.sqlite"


class Progression:
    """One open save and the career of its profile."""

    def __init__(self, save_dir: Path | str, content: Content, raw_catalog: Json | None = None, clock: Callable[[], str] = utc_now):
        self.catalog = CareerCatalog(raw_catalog if raw_catalog is not None else load_catalog(), content)
        self.path = Path(save_dir) / SAVE_FILE
        self.store = SqliteProfileStore(self.path, self.catalog, clock)
        try:
            if PROFILE_ID not in self.store.profile_ids():
                self.store.import_state(CareerState(Profile(PROFILE_ID)))
            self.career = StoredCareerService(self.store, PROFILE_ID)
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

    def close(self) -> None:
        self.store.close()

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

    def preview(self, hero_id: str, vocation_id: str) -> CareerResult:
        return self._command("PreviewVocation", self.state.heroes[hero_id], target_vocation_id=vocation_id)

    def tree(self, hero_id: str) -> Json:
        return career_tree_view(self.career.service, hero_id)

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

    def run_started(self, engine: Engine) -> None:
        """Call once ``StartRun`` was accepted. A run left unfinished in the save is closed as a defeat first."""
        run = self.state.run
        if run is not None and run.phase not in FINISHED_PHASES:
            self.career.end_run(run.run_id, "defeat")  # abandoned: the player left it
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
                "skills_learned": [s for s in self.state.heroes[hero_id].learned_skills if s not in before[2]],
                "duplicate": result.duplicate,
            })
        return report
