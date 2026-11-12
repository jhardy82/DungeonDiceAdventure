"""The career rules: every change to a profile's progression goes through :class:`CareerService`.

It mirrors the rules engine's contract (``core/engine.py``):

* A client **command** is an envelope ``{type, command_id, state_revision, params}``. A rejected
  command returns exactly one code from ``docs/class_evolution/persistence/error_codes.json`` and
  changes nothing. A command id that was already accepted returns the stored result again.
* A **trusted event** (a mastery award, a discovery signal) comes from the game itself, not from a
  client, and is applied once per identity.
* Every change runs on a copy that replaces the state only on success, so a failure in the middle
  leaves nothing behind.

Phase 2 of Class Evolution keeps the state in memory. Nothing in the game calls this yet.
"""

from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass, field
from typing import Any

from battle_dice.career.catalog import MASTERED_RANK, SHOWN_STATS, STAT_KEYS, CareerCatalog
from battle_dice.career.model import (
    DISCOVERY_ORDER,
    ELIGIBLE,
    AwardRow,
    CareerState,
    DieInstance,
    DiscoveryRow,
    HeroRecord,
    MasteryRow,
    ProcessedCommand,
)
from battle_dice.content.loader import canonical_json

Json = dict[str, Any]

CLAIM = "ClaimVocation"
CHANGE = "ChangeVocation"
PREVIEW = "PreviewVocation"
EQUIP = "EquipInheritedSkill"
UNEQUIP = "UnequipInheritedSkill"
EQUIP_DIE = "EquipDie"
RECRUIT = "RecruitHero"
#: Owner decision of 2026-11-11 (D-27): heroes are recruited at party setup, free, up to this many.
ROSTER_LIMIT = 12
#: Run phases in which a run is over, so a new hero may be recruited and a new run started.
FINISHED_PHASES = ("victory", "defeat")
#: Commands that change the build a hero fights with.
BUILD_COMMANDS = (CHANGE, EQUIP, UNEQUIP, EQUIP_DIE)
#: Run phases in which the build is fixed: during a battle, and after the mandatory upgrade was chosen.
BUILD_LOCKED_PHASES = ("battle", "equipment")
#: What the career tree shows in place of a secret vocation the profile has not discovered.
UNDISCOVERED_LABEL = "???"
#: What a skill's ``transfer`` rule needs from the dice: a face of this category, or with this tag.
TRANSFER_NEEDS: dict[str, tuple[str, str]] = {
    "compatible_healing": ("category", "healing"),
    "compatible_melee": ("tag", "melee"),
    "compatible_ranged": ("tag", "ranged"),
}


def command_fingerprint(command_type: str, params: Json) -> str:
    """SHA-256 of the canonical command: what ``processed_command.command_sha256`` stores."""
    return hashlib.sha256(canonical_json({"type": command_type, "params": params}).encode("utf-8")).hexdigest()


class InjectedFault(RuntimeError):
    """Raised by a test-only fault point, to prove that a half-applied change leaves nothing behind."""


class _Reject(Exception):
    def __init__(self, code: str, details: Json | None = None):
        super().__init__(code)
        self.code, self.details = code, details


@dataclass
class CareerResult:
    result: str  # "accepted" or "rejected"
    duplicate: bool = False
    error_code: str | None = None
    error_details: Json | None = None
    events: list[Json] = field(default_factory=list)
    preview: Json | None = None

    @property
    def accepted(self) -> bool:
        return self.result == "accepted"


@dataclass
class _Route:
    route_id: str
    index: int
    unmet: list[Json]
    #: ``(item id, quantity, consumed on claim)``
    items: list[tuple[str, int, bool]]

    @property
    def cost(self) -> int:
        return sum(quantity for _, quantity, consume in self.items if consume)


class CareerService:
    def __init__(self, catalog: CareerCatalog, state: CareerState):
        self.catalog = catalog
        self.state = state
        #: How many heroes a profile may hold. A setting of the demo; the default is the owner's decision.
        self.roster_limit = ROSTER_LIMIT
        #: Test-only: ``{"after": step}`` makes the next change fail right after that step.
        self.fault: Json | None = None

    # ----------------------------------------------------------------------------------------
    # Entry points
    # ----------------------------------------------------------------------------------------

    def submit(self, command: Json) -> CareerResult:
        """Apply one client command."""
        command_type, command_id = command["type"], command["command_id"]
        params: Json = command.get("params", {})
        handlers = {CLAIM: self._claim, CHANGE: self._change, PREVIEW: self._preview, EQUIP: self._equip, UNEQUIP: self._unequip,
                    EQUIP_DIE: self._equip_die}
        handler = handlers.get(command_type)
        if handler is None and command_type != RECRUIT:
            raise ValueError(f"Unknown career command '{command_type}'.")
        fingerprint = command_fingerprint(command_type, params)
        seen = self.state.processed.get(command_id)
        if seen is not None:
            if seen.type == command_type and seen.fingerprint in (None, fingerprint):
                return CareerResult(seen.result.get("result", "accepted"), duplicate=True)  # the replay result
            return CareerResult("rejected", error_code="COMMAND_ID_REUSED")

        def change() -> Json | None:
            if handler is None:  # RecruitHero: there is no hero yet to check
                self._recruit(params)
                return None
            hero = self._checked_hero(command_type, command, params)
            return handler(hero, params)

        result = self._transaction(change)
        if result.accepted and command_type != PREVIEW:  # a preview is a pure read and is not recorded
            self.state.processed[command_id] = ProcessedCommand(command_id, command_type, {"result": "accepted"}, fingerprint)
        return result

    def award_mastery(self, event: Json) -> CareerResult:
        """Trusted event ``AwardEncounterMastery``: at most one award per run, encounter, hero and vocation."""
        return self._transaction(lambda: self._award(event), duplicate_if=self._award_exists(event))

    def apply_discovery_signal(self, event: Json) -> CareerResult:
        """Trusted event ``ApplyDiscoverySignal``: discovery only ever moves forward."""
        return self._transaction(lambda: self._discover(event["signal"]))

    def grant_mastery(self, hero_id: str, vocation_id: str, points: int, reason: str) -> CareerResult:
        """Trusted event: set a hero's mastery points of an unlocked vocation (a demo start preset does this).

        It is written to the event log like every other change, with its reason, so a save always
        says which of its mastery was earned and which was handed out.
        """
        def change() -> None:
            hero = self.state.heroes[hero_id]
            row = hero.mastery[vocation_id]
            top = self.catalog.thresholds(vocation_id)[-1]
            row.points = max(0, min(int(points), top))
            row.rank = self.catalog.rank_for(vocation_id, row.points)
            hero.revision += 1
            self._emit("MasteryGranted", hero_id=hero_id, vocation_id=vocation_id, points_after=row.points, rank_after=row.rank, reason=reason)
            self._learn(hero, vocation_id, row.rank)

        return self._transaction(change)

    def rederive_ranks(self, reason: str) -> CareerResult:
        """Trusted event: make every rank agree with its points under the catalog's thresholds.

        Needed when the thresholds changed (the demo's mastery pace). Nothing happens, and no event is
        written, when every rank already agrees. A rank never takes a learned skill away.
        """
        def change() -> None:
            changed = []
            for hero in self.state.heroes.values():
                for vocation_id, row in hero.mastery.items():
                    rank = self.catalog.rank_for(vocation_id, row.points)
                    if rank != row.rank:
                        changed.append({"hero_id": hero.hero_id, "vocation_id": vocation_id, "from": row.rank, "to": rank})
                        row.rank = rank
                        hero.revision += 1
                        self._learn(hero, vocation_id, rank)
            if changed:
                self._emit("RanksRederived", reason=reason, changes=changed)

        return self._transaction(change)

    def _learn(self, hero: HeroRecord, vocation_id: str, rank: int) -> None:
        for skill_id in self.catalog.skills_learned_by(vocation_id, rank):
            if skill_id not in hero.learned_skills:
                hero.learned_skills.append(skill_id)
                self._emit("SkillLearned", hero_id=hero.hero_id, skill_id=skill_id, vocation_id=vocation_id)

    def _transaction(self, change: Any, duplicate_if: bool = False) -> CareerResult:
        if duplicate_if:
            return CareerResult("accepted", duplicate=True)
        backup = copy.deepcopy(self.state)
        first_new_event = len(self.state.events)
        try:
            preview = change()
        except _Reject as rejection:
            self.state = backup
            return CareerResult("rejected", error_code=rejection.code, error_details=rejection.details)
        except Exception:
            self.state = backup
            raise
        return CareerResult("accepted", events=self.state.events[first_new_event:], preview=preview)

    # ----------------------------------------------------------------------------------------
    # Checks every command shares, in the registry's check order
    # ----------------------------------------------------------------------------------------

    def _checked_hero(self, command_type: str, command: Json, params: Json) -> HeroRecord:
        if params.get("catalog_version") not in (None, self.catalog.version):
            raise _Reject("CONTENT_MIGRATION_REQUIRED")
        hero = self.state.heroes.get(params["hero_id"])
        if hero is None:
            raise ValueError(f"Unknown hero '{params['hero_id']}'.")
        if command_type == PREVIEW:
            return hero
        if command["state_revision"] != hero.revision:
            raise _Reject("REVISION_CONFLICT")
        run = self.state.run
        if run is not None:
            locked = BUILD_LOCKED_PHASES if command_type in BUILD_COMMANDS else ("battle",)
            if run.phase in locked:
                raise _Reject("PHASE_LOCKED")
        if command_type in (CLAIM, CHANGE) and hero.eligibility_state != ELIGIBLE:
            raise _Reject("HERO_NOT_ELIGIBLE")
        if command_type == CHANGE and params.get("vocation_slot", "primary") != "primary":
            raise _Reject("UNSUPPORTED_SECONDARY_VOCATION")
        return hero

    # ----------------------------------------------------------------------------------------
    # Discovery, prerequisites and stats (pure reads)
    # ----------------------------------------------------------------------------------------

    def discovery_state(self, vocation_id: str) -> str:
        row = self.state.profile.discovery.get(vocation_id)
        if row is not None:
            return row.state
        return "discovered" if self.catalog.is_public(vocation_id) else "hidden"

    def routes(self, hero: HeroRecord, vocation_id: str) -> list[_Route]:
        """Each unlock route of the vocation with what this hero still lacks."""
        return [
            _Route(route_id, index, *self._conditions(hero, node))
            for index, (route_id, node) in enumerate(self.catalog.routes[vocation_id].items())
        ]

    def _conditions(self, hero: HeroRecord, node: Json) -> tuple[list[Json], list[tuple[str, int, bool]]]:
        unmet: list[Json] = []
        items: list[tuple[str, int, bool]] = []
        if "all" in node:
            for child in node["all"]:
                child_unmet, child_items = self._conditions(hero, child)
                unmet += child_unmet
                items += child_items
        elif "any" in node:  # an alternative inside a route: the one with the least still open stands for the group
            unmet, items = min((self._conditions(hero, child) for child in node["any"]), key=lambda found: (len(found[0]), len(found[1])))
        elif "mastered" in node:
            rank = hero.rank(node["mastered"])
            if rank < MASTERED_RANK:
                unmet.append({"op": "MASTERY_AT_LEAST", "vocation_id": node["mastered"], "rank": MASTERED_RANK, "current_rank": rank})
        elif "mastered_count" in node:
            group, minimum = node["mastered_count"]["group"], node["mastered_count"]["minimum"]
            count = sum(1 for v in self.catalog.vocations if self.catalog.group(v) == group and hero.rank(v) >= MASTERED_RANK)
            if count < minimum:
                unmet.append({"op": "MASTERED_COUNT_AT_LEAST", "group": group, "minimum": minimum, "current_count": count})
        elif "quest" in node:
            if not self._quest_complete(hero, node["quest"]):
                unmet.append({"op": "QUEST_COMPLETE", "quest_id": node["quest"]})
        elif "item" in node:
            items.append((node["item"], int(node.get("quantity", 1)), bool(node.get("consume", False))))
        return unmet, items

    def _quest_complete(self, hero: HeroRecord, quest_id: str) -> bool:
        return any(
            done["quest_id"] == quest_id and (done.get("qualifier_scope") == "profile" or done.get("qualifier_id") == hero.hero_id)
            for done in self.state.profile.quests_completed
        )

    def _claim_route(self, hero: HeroRecord, vocation_id: str) -> _Route:
        """The route a claim would use, or the rejection it would get."""
        routes = self.routes(hero, vocation_id)
        ready = [route for route in routes if not route.unmet]
        if not ready:
            raise _Reject("PREREQUISITE_UNMET", {"routes": [{"route_id": r.route_id, "unmet": r.unmet} for r in routes]})
        held = self.state.profile.items
        affordable = [r for r in ready if all(held.get(item, 0) >= quantity for item, quantity, _ in r.items)]
        if not affordable:
            item, quantity, _ = next(i for i in ready[0].items if held.get(i[0], 0) < i[1])
            raise _Reject("ITEM_INSUFFICIENT", {"item_id": item, "quantity_required": quantity, "quantity_held": held.get(item, 0)})
        return min(affordable, key=lambda route: (route.cost, route.index))  # the cheapest satisfied route

    def requested_stat_bonus(self, hero: HeroRecord) -> dict[str, int]:
        """What the hero's mastered vocations grant, before the caps."""
        total = dict.fromkeys(STAT_KEYS, 0)
        for vocation_id, vocation in self.catalog.vocations.items():
            if hero.rank(vocation_id) >= MASTERED_RANK:
                for reward in vocation["mastery_rewards"]:
                    total[reward["stat"]] += reward["amount"]
        return total

    def permanent_stat_bonus(self, hero: HeroRecord) -> dict[str, int]:
        requested = self.requested_stat_bonus(hero)
        return {stat: min(requested[stat], self.catalog.stat_caps[stat]) for stat in STAT_KEYS}

    def effective_stats(self, hero: HeroRecord, vocation_id: str) -> dict[str, int]:
        stats = self.catalog.base_stats(vocation_id)
        for stat, amount in self.permanent_stat_bonus(hero).items():
            stats[stat] += amount
        return stats

    # ----------------------------------------------------------------------------------------
    # Skills (pure reads)
    # ----------------------------------------------------------------------------------------

    def skill_cost(self, hero: HeroRecord, skill_id: str, vocation_id: str | None = None) -> int:
        """A skill is free while the vocation that teaches it is active; elsewhere it costs its capacity."""
        active = vocation_id or hero.active_vocation_id
        origin = self.catalog.skill_origin.get(skill_id, (None, 0))[0]
        return 0 if origin == active else int(self.catalog.skills[skill_id]["capacity_cost"])

    def capacity_used(self, hero: HeroRecord, equipped: dict[int, str] | None = None, vocation_id: str | None = None) -> int:
        chosen = hero.equipped_skills if equipped is None else equipped
        return sum(self.skill_cost(hero, skill_id, vocation_id) for skill_id in set(chosen.values()))

    def _equipped_dice(self, hero: HeroRecord, vocation_id: str) -> list[str]:
        owned = [die.definition_id for die in hero.dice if die.location == "equipped"]
        return owned or self.catalog.starting_dice(vocation_id)

    def skill_has_a_face(self, hero: HeroRecord, skill_id: str, vocation_id: str | None = None) -> bool:
        need = TRANSFER_NEEDS.get(self.catalog.skills[skill_id]["transfer"])
        if need is None:
            return True
        kind, wanted = need
        active = vocation_id or hero.active_vocation_id
        faces = [face for die_id in self._equipped_dice(hero, active) for face in self.catalog.die_faces(die_id)]
        return any(category == wanted if kind == "category" else wanted in tags for category, tags in faces)

    # ----------------------------------------------------------------------------------------
    # Command handlers
    # ----------------------------------------------------------------------------------------

    def _recruit(self, params: Json) -> None:
        """A new hero of a starting class. It has every starting class unlocked, as all heroes do."""
        if params.get("catalog_version") not in (None, self.catalog.version):
            raise _Reject("CONTENT_MIGRATION_REQUIRED")
        starting = self.catalog.starting_classes()
        vocation_id = params["starting_class"]
        if vocation_id not in starting:
            raise ValueError(f"'{vocation_id}' is not a starting class; a hero is recruited as one of {', '.join(starting)}.")
        run = self.state.run
        if run is not None and run.phase not in FINISHED_PHASES:
            raise _Reject("PHASE_LOCKED")  # heroes are recruited at party setup, not inside a run
        heroes = self.state.heroes
        if len(heroes) >= self.roster_limit:
            raise _Reject("ROSTER_FULL", {"roster_limit": self.roster_limit, "heroes": len(heroes)})
        number = max((int(h.rsplit("_", 1)[1]) for h in heroes if h.startswith("hero_") and h.rsplit("_", 1)[1].isdigit()), default=0) + 1
        hero_id = f"hero_{number:03d}"
        name = f"{self.catalog.name(vocation_id)} {number}"
        hero = HeroRecord(hero_id, vocation_id, origin_vocation_id=vocation_id, display_name=name)
        heroes[hero_id] = hero
        self._emit("HeroRecruited", hero_id=hero_id, vocation_id=vocation_id, display_name=name)
        for unlocked in starting:
            self._emit("VocationClaimed", hero_id=hero_id, vocation_id=unlocked, route_id="route_0", consumed_items=[])
            hero.unlocked_vocations.append(unlocked)
            hero.unlock_routes[unlocked] = "route_0"
            hero.mastery[unlocked] = MasteryRow(unlocked)
            for skill_id in self.catalog.skills_learned_by(unlocked, 1):
                hero.learned_skills.append(skill_id)

    def _require_discovered(self, vocation_id: str) -> None:
        if vocation_id not in self.catalog.vocations or self.discovery_state(vocation_id) != "discovered":
            raise _Reject("NOT_DISCOVERED")  # no detail: nothing about the vocation may leak

    def _claim(self, hero: HeroRecord, params: Json) -> None:
        target = params["target_vocation_id"]
        self._require_discovered(target)
        if target in hero.unlocked_vocations:
            return  # already claimed: accepted, and nothing changes
        route = self._claim_route(hero, target)
        profile = self.state.profile
        consumed: list[Json] = [{"item_id": item, "quantity": quantity} for item, quantity, consume in route.items if consume]
        for item, quantity, consume in route.items:
            if consume:
                profile.items[item] -= quantity
        self._step("item_decrement")
        event = self._emit("VocationClaimed", hero_id=hero.hero_id, vocation_id=target, route_id=route.route_id, consumed_items=consumed)
        self._step("event_insert")
        hero.unlocked_vocations.append(target)
        hero.unlock_routes[target] = route.route_id
        hero.mastery.setdefault(target, MasteryRow(target))
        self._step("unlock_insert")
        for entry in consumed:
            profile.item_consumptions.append({"hero_id": hero.hero_id, **entry, "claim_event": event["event_id"]})
        self._step("consumption_insert")
        hero.revision += 1

    def _change(self, hero: HeroRecord, params: Json) -> None:
        target = params["target_vocation_id"]
        if target not in hero.unlocked_vocations:
            raise _Reject("PREREQUISITE_UNMET", {"vocation_id": target, "unlocked_for_hero": False})
        previous = hero.active_vocation_id
        if target == previous:
            return  # already active: accepted, and nothing changes
        if hero.combat is not None:
            self._convert_combat(hero, target)
        hero.active_vocation_id = target
        extra: Json = {}
        if hero.dice:  # the hero's dice are tracked: the new vocation's own dice take the slots
            extra["displaced_dice_ids"] = self._equip_starting_dice(hero, target)
        dropped = self._drop_skills_that_no_longer_fit(hero)
        if dropped:
            extra["unequipped_skills"] = dropped
        hero.revision += 1
        self._emit("VocationChanged", hero_id=hero.hero_id, **{"from": previous, "to": target}, **extra)

    def _equip_starting_dice(self, hero: HeroRecord, vocation_id: str) -> list[str]:
        """Bench what is equipped and equip the vocation's own starting dice. Returns the ids that left a slot.

        A die the hero does not own yet is added: a vocation always comes with its starting dice.
        The benched dice stay owned, and the family's can be put back with ``EquipDie``.
        """
        displaced = [die for die in sorted(hero.dice, key=lambda d: (d.slot_index is None, d.slot_index)) if die.location == "equipped"]
        for die in displaced:
            die.location, die.slot_index = "bench", None
        for slot, definition_id in enumerate(self.catalog.starting_dice(vocation_id)):
            mine = next((d for d in hero.dice if d.definition_id == definition_id and d.location == "bench"), None)
            if mine is None:
                owned = sum(1 for d in hero.dice if d.definition_id == definition_id)
                mine = DieInstance(f"{hero.hero_id}-{definition_id}-{owned + 1}", definition_id, "bench")
                hero.dice.append(mine)
            mine.location, mine.slot_index = "equipped", slot
        return [die.die_instance_id for die in displaced if die.location == "bench"]

    def _equip_die(self, hero: HeroRecord, params: Json) -> None:
        """Put an owned die into a slot. The die that was there goes to the bench."""
        slot = int(params["slot_index"])
        die = next((d for d in hero.dice if d.die_instance_id == params["die_instance_id"]), None)
        capacity = len(self.catalog.starting_dice(hero.active_vocation_id))
        if die is None or not 0 <= slot < capacity or not self.catalog.may_equip(hero.active_vocation_id, die.definition_id):
            raise _Reject("INCOMPATIBLE_DIE", {"die_instance_id": params["die_instance_id"], "vocation_id": hero.active_vocation_id})
        if die.location == "equipped" and die.slot_index == slot:
            return  # already there: accepted, and nothing changes
        previous = next((d for d in hero.dice if d.location == "equipped" and d.slot_index == slot), None)
        if previous is not None:  # the two dice trade places
            previous.location, previous.slot_index = die.location, die.slot_index
        die.location, die.slot_index = "equipped", slot
        dropped = self._drop_skills_that_no_longer_fit(hero)
        hero.revision += 1
        extra = {"unequipped_skills": dropped} if dropped else {}
        self._emit("DieEquipped", hero_id=hero.hero_id, die_instance_id=die.die_instance_id, slot_index=slot,
                   displaced_die_id=previous.die_instance_id if previous is not None else None, **extra)

    def _convert_combat(self, hero: HeroRecord, target: str) -> None:
        """``current' = ceil(current * new_max / old_max)``, clamped. A hero at 0 HP stays down: a change never revives."""
        combat = hero.combat
        assert combat is not None
        new = self.effective_stats(hero, target)

        def scaled(current: int, old_max: int, new_max: int) -> int:
            if current <= 0 or old_max <= 0:
                return 0
            return min(new_max, -((-current * new_max) // old_max))

        combat.hp, combat.max_hp = scaled(combat.hp, combat.max_hp, new["max_hp"]), new["max_hp"]
        if combat.mana is not None and combat.max_mana is not None:
            combat.mana, combat.max_mana = scaled(combat.mana, combat.max_mana, new["max_mana"]), new["max_mana"]
        if combat.corruption is not None:
            combat.corruption = min(combat.corruption, new["max_corruption"])

    def _drop_skills_that_no_longer_fit(self, hero: HeroRecord) -> list[str]:
        """After a change of vocation, keep skills in slot order while they have a face and fit the new capacity."""
        capacity = self.catalog.inheritance_capacity(hero.active_vocation_id)
        kept: dict[int, str] = {}
        dropped: list[str] = []
        for slot in sorted(hero.equipped_skills):
            skill_id = hero.equipped_skills[slot]
            trial = {**kept, slot: skill_id}
            if self.skill_has_a_face(hero, skill_id) and self.capacity_used(hero, trial) <= capacity:
                kept = trial
            else:
                dropped.append(skill_id)
        hero.equipped_skills = kept
        return dropped

    def _equip(self, hero: HeroRecord, params: Json) -> None:
        skill_id, slot = params["skill_id"], int(params["slot_index"])
        if skill_id not in self.catalog.skills:
            raise ValueError(f"Unknown skill '{skill_id}'.")
        skill = self.catalog.skills[skill_id]
        native_only = skill["transfer"] == "active_only"
        if skill_id not in hero.learned_skills or native_only:
            raise _Reject("PREREQUISITE_UNMET", {"skill_id": skill_id, "learned": skill_id in hero.learned_skills, "transfer": skill["transfer"]})
        if not self.skill_has_a_face(hero, skill_id):
            raise _Reject("NO_LEGAL_FACE")
        wanted = {s: k for s, k in hero.equipped_skills.items() if k != skill_id}
        wanted[slot] = skill_id
        capacity = self.catalog.inheritance_capacity(hero.active_vocation_id)
        requested = self.capacity_used(hero, wanted)
        if requested > capacity:
            details = {"capacity_max": capacity, "capacity_used": self.capacity_used(hero), "capacity_requested": requested}
            raise _Reject("CAPACITY_EXCEEDED", details)
        if wanted == hero.equipped_skills:
            return  # already equipped there: accepted, and nothing changes
        hero.equipped_skills = wanted
        hero.revision += 1
        self._emit("SkillEquipped", hero_id=hero.hero_id, skill_id=skill_id, slot_index=slot)

    def _unequip(self, hero: HeroRecord, params: Json) -> None:
        slot = int(params["slot_index"])
        skill_id = hero.equipped_skills.pop(slot, None)
        if skill_id is None:
            return  # nothing in that slot: accepted, and nothing changes
        hero.revision += 1
        self._emit("SkillUnequipped", hero_id=hero.hero_id, skill_id=skill_id, slot_index=slot)

    def _preview(self, hero: HeroRecord, params: Json) -> Json:
        target = params["target_vocation_id"]
        self._require_discovered(target)
        unlocked = target in hero.unlocked_vocations
        blocked_by: list[Json] = []
        if not unlocked:
            if hero.eligibility_state != ELIGIBLE:
                blocked_by.append({"error_code": "HERO_NOT_ELIGIBLE"})
            else:
                try:
                    self._claim_route(hero, target)
                except _Reject as rejection:
                    blocked_by.append({"error_code": rejection.code, **(rejection.details or {})})
        return {
            "target_vocation_id": target,
            "discovered": True,
            "unlocked_for_hero": unlocked,
            "eligible_to_claim": not unlocked and not blocked_by,
            "blocked_by": blocked_by,
            "requested_stat_bonus": self.requested_stat_bonus(hero),
            "permanent_stat_bonus": self.permanent_stat_bonus(hero),
            "effective_stats": {name: self.effective_stats(hero, target)[name] for name in SHOWN_STATS},
            "inheritance_capacity_max": self.catalog.inheritance_capacity(target),
        }

    # ----------------------------------------------------------------------------------------
    # Trusted events
    # ----------------------------------------------------------------------------------------

    def _award_exists(self, event: Json) -> bool:
        identity = (event["run_id"], event["encounter_id"], event["hero_id"], event["vocation_id"])
        return any(row.identity == identity for row in self.state.awards)

    def _award(self, event: Json) -> None:
        encounter = self.state.encounter
        if encounter is None or encounter.encounter_id != event["encounter_id"]:
            raise ValueError("A mastery award needs the result of the encounter it names.")
        hero = self.state.heroes[event["hero_id"]]
        vocation_id = event["vocation_id"]
        row = hero.mastery.get(vocation_id)
        if row is None:
            raise ValueError(f"{hero.hero_id} has not unlocked '{vocation_id}'.")
        if not event.get("deployed_at_encounter_start", True) or not encounter.mastery_eligible:
            return  # not this hero's encounter, or one that never awards mastery: nothing is recorded
        if row.rank >= MASTERED_RANK:
            return  # a mastered vocation earns nothing more, and no row is written for it

        def record(base: int, challenge: int, denial: str | None) -> None:
            self.state.awards.append(
                AwardRow(event["run_id"], encounter.encounter_id, hero.hero_id, vocation_id, base, challenge, encounter.threat_rating, denial)
            )

        if encounter.outcome != "victory":
            record(0, 0, "ENCOUNTER_NOT_WON")
            return
        if encounter.threat_rating < self.catalog.threat_floor(vocation_id, row.rank):
            record(0, 0, "UNDER_THREAT_CAP")  # anti-farming: the bonus is subordinate to eligibility
            return
        rules = self.catalog.raw["mastery"]
        top = self.catalog.thresholds(vocation_id)[-1]
        base = min(int(rules["points_per_eligible_win"]), top - row.points)
        met = event.get("challenge_evidence_count", 0) >= 1 and event.get("challenge_id") == self.catalog.vocations[vocation_id]["bonus_challenge_id"]
        challenge = min(int(rules["challenge_bonus_per_encounter"]), top - row.points - base) if met else 0
        record(base, challenge, None)
        before = row.rank
        row.points += base + challenge
        row.rank = self.catalog.rank_for(vocation_id, row.points)
        hero.revision += 1
        self._emit("MasteryAwarded", hero_id=hero.hero_id, vocation_id=vocation_id, base_points=base,
                   challenge_points=challenge, points_after=row.points, rank_after=row.rank)
        for skill_id in self.catalog.skills_learned_by(vocation_id, row.rank):
            if skill_id not in hero.learned_skills and before < self.catalog.skill_origin[skill_id][1]:
                hero.learned_skills.append(skill_id)
                self._emit("SkillLearned", hero_id=hero.hero_id, skill_id=skill_id, vocation_id=vocation_id)

    def _discover(self, signal: str) -> None:
        for name, vocation_id, leads_to in self.catalog.discovery_signals():
            if name != signal:
                continue
            profile = self.state.profile
            row = profile.discovery.get(vocation_id)
            if row is None:
                row = profile.discovery[vocation_id] = DiscoveryRow(vocation_id)
            counted = signal not in row.signals_seen
            if counted:
                row.signals_seen.append(signal)
                row.clue_count += 1
            if DISCOVERY_ORDER.index(leads_to) > DISCOVERY_ORDER.index(row.state):  # only forward
                previous, row.state = row.state, leads_to
                self._emit("DiscoveryChanged", vocation_id=vocation_id, **{"from": previous, "to": leads_to}, signal=signal)
            elif counted:
                # A new clue that shows nothing new is still logged: the log is what remembers which clues were counted.
                self._emit("DiscoveryClueCounted", vocation_id=vocation_id, signal=signal)

    # ----------------------------------------------------------------------------------------
    # Events and fault points
    # ----------------------------------------------------------------------------------------

    def _emit(self, event_type: str, **payload: Any) -> Json:
        state = self.state
        event = {"type": event_type, "event_id": f"{state.profile.profile_id}:{state.next_event_seq}", "event_seq": state.next_event_seq, **payload}
        state.next_event_seq += 1
        state.events.append(event)
        return event

    def _step(self, name: str) -> None:
        if self.fault is not None and self.fault.get("after") == name:
            self.fault = None
            raise InjectedFault(f"fault injected after '{name}'")


# --------------------------------------------------------------------------------------------
# The state in the shape the acceptance fixtures use
# --------------------------------------------------------------------------------------------


def state_view(service: CareerService) -> Json:
    """The whole career state as plain data, in the vocabulary of ``acceptance_fixtures.json``."""
    state = service.state
    heroes = []
    for hero in state.heroes.values():
        entry: Json = {
            "hero_id": hero.hero_id,
            "eligibility_state": hero.eligibility_state,
            "active_vocation_id": hero.active_vocation_id,
            "revision": hero.revision,
            "unlocked_vocations": list(hero.unlocked_vocations),
            "unlocks": [{"vocation_id": v, "unlock_route_id": r} for v, r in hero.unlock_routes.items()],
            "mastery": [{"vocation_id": m.vocation_id, "rank": m.rank, "points": m.points} for m in hero.mastery.values()],
            "learned_skills": list(hero.learned_skills),
            "equipped_skills": [{"slot_index": slot, "skill_id": hero.equipped_skills[slot]} for slot in sorted(hero.equipped_skills)],
            "inheritance_capacity_max": service.catalog.inheritance_capacity(hero.active_vocation_id),
            "inheritance_capacity_used": service.capacity_used(hero),
            "permanent_stat_bonus": service.permanent_stat_bonus(hero),
            "dice": [{key: value for key, value in vars(die).items() if value is not None} for die in hero.dice],
            "owned_dice_count": len(hero.dice),
        }
        if hero.combat is not None:
            entry["combat"] = {key: value for key, value in vars(hero.combat).items() if value is not None}
        heroes.append(entry)
    profile = state.profile
    return {
        "profile": {
            "profile_id": profile.profile_id,
            "discovery": [{"vocation_id": d.vocation_id, "discovery_state": d.state, "clue_count": d.clue_count} for d in profile.discovery.values()],
            "items": [{"item_id": item, "quantity": quantity} for item, quantity in profile.items.items()],
            "item_consumptions": copy.deepcopy(profile.item_consumptions),
            "quests_completed": copy.deepcopy(profile.quests_completed),
        },
        "heroes": heroes,
        "run": None if state.run is None else vars(state.run).copy(),
        "mastery_award_events": [vars(row).copy() for row in state.awards],
        "processed_commands": [{"command_id": p.command_id, "type": p.type, "result": p.result["result"]} for p in state.processed.values()],
    }


# --------------------------------------------------------------------------------------------
# The career tree, as a player may see it
# --------------------------------------------------------------------------------------------


def career_tree_view(service: CareerService, hero_id: str) -> Json:
    """The career tree of one hero, holding only what its player may know.

    Owner decision of 2026-11-11 (fixture CE-09): a secret vocation the profile has not discovered
    is an anonymous entry, not a missing one, so the player can see that something is still to be
    found.

    * A discovered vocation is listed in full, in catalog order.
    * A **hinted** secret is an entry with the label ``???`` and its clue. It has no id, name,
      group or requirement.
    * A **hidden** secret is an entry with the label ``???`` and nothing else. Every hidden entry
      is identical, and they come last, so neither content nor position says which secret it is.

    Building the view reads the state and changes nothing.
    """
    hero = service.state.heroes[hero_id]
    catalog = service.catalog
    listed: list[Json] = []
    hinted: list[Json] = []
    hidden: list[Json] = []
    for vocation_id in catalog.vocations:
        state = service.discovery_state(vocation_id)
        if state == "discovered":
            rank = hero.rank(vocation_id)
            listed.append({
                "kind": "vocation",
                "vocation_id": vocation_id,
                "name": catalog.name(vocation_id),
                "group": catalog.group(vocation_id),
                "unlocked": vocation_id in hero.unlocked_vocations,
                "active": vocation_id == hero.active_vocation_id,
                "rank": rank,
                "mastered": rank >= MASTERED_RANK,
            })
        elif state == "hinted":
            hinted.append({"kind": "undiscovered", "label": UNDISCOVERED_LABEL, "clue": catalog.clue(vocation_id)})
        else:
            hidden.append({"kind": "undiscovered", "label": UNDISCOVERED_LABEL})
    return {"career_tree": {"hero_id": hero_id, "entries": [*listed, *hinted, *hidden]}}
