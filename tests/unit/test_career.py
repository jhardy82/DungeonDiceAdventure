"""The career rules beyond what the acceptance fixtures pin (``career/service.py``).

``tests/spec/test_class_evolution_rules.py`` runs the fixtures. These tests cover the behaviour
the fixtures leave open; where a rule here is this project's own reading of the design, the test
name says "by this build's rule" and the decision log lists it.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from battle_dice.career.catalog import CareerCatalog, signal_name
from battle_dice.career.model import (
    CareerState,
    CombatSnapshot,
    EncounterResult,
    HeroRecord,
    MasteryRow,
    Profile,
    RunInfo,
)
from battle_dice.career.service import CareerService, InjectedFault, state_view
from battle_dice.content.vocations import load_catalog
from tests.conftest import packaged_content

NOVICES = ["squire", "apprentice", "scout"]
MASTERED = {"novice": 14, "advanced": 24, "capstone": 35}


@pytest.fixture(scope="module")
def catalog() -> CareerCatalog:
    return CareerCatalog(load_catalog(), packaged_content())


def service_with(catalog: CareerCatalog, mastered: tuple[str, ...] = (), unlocked: tuple[str, ...] = (), active: str = "squire",
                 items: dict[str, int] | None = None, run_phase: str | None = None, **hero_fields: Any) -> CareerService:
    """One eligible hero at revision 3 with the given mastered and unlocked vocations."""
    owned = [*NOVICES, *[v for v in (*mastered, *unlocked) if v not in NOVICES]]
    mastery = {v: MasteryRow(v) for v in owned}
    for vocation_id in mastered:
        mastery[vocation_id] = MasteryRow(vocation_id, 8, MASTERED[catalog.group(vocation_id)])
    learned = [skill for v, row in mastery.items() for skill in catalog.skills_learned_by(v, row.rank)]
    hero = HeroRecord("hero_001", active, revision=3, unlocked_vocations=owned, mastery=mastery, learned_skills=learned, **hero_fields)
    state = CareerState(Profile("profile_demo", items=dict(items or {})), heroes={"hero_001": hero})
    if run_phase is not None:
        state.run = RunInfo("run_0001", run_phase, 40)
    return CareerService(catalog, state)


def command(service: CareerService, command_type: str, number: int = 1, revision: int | None = None, **params: Any) -> dict[str, Any]:
    hero = service.state.heroes["hero_001"]
    return {
        "type": command_type,
        "command_id": f"cmd-{number}",
        "state_revision": hero.revision if revision is None else revision,
        "params": {"profile_id": "profile_demo", "hero_id": "hero_001", "catalog_version": service.catalog.version, **params},
    }


def hero_of(service: CareerService) -> HeroRecord:
    return service.state.heroes["hero_001"]


# --------------------------------------------------------------------------------------------
# The command envelope
# --------------------------------------------------------------------------------------------


def test_a_command_id_reused_for_a_different_command_is_rejected(catalog):
    service = service_with(catalog, mastered=("squire", "scout"))
    assert service.submit(command(service, "ClaimVocation", target_vocation_id="guardian")).accepted
    before = state_view(service)
    again = service.submit(command(service, "ClaimVocation", target_vocation_id="ranger"))  # same id, other params
    assert (again.result, again.error_code) == ("rejected", "COMMAND_ID_REUSED") and state_view(service) == before
    other_type = service.submit(command(service, "ChangeVocation", target_vocation_id="guardian"))  # same id, other type
    assert other_type.error_code == "COMMAND_ID_REUSED"


def test_a_stale_revision_is_a_conflict_but_a_preview_never_is_and_is_not_recorded(catalog):
    service = service_with(catalog, mastered=("squire",))
    stale = service.submit(command(service, "ClaimVocation", revision=2, target_vocation_id="guardian"))
    assert stale.error_code == "REVISION_CONFLICT" and "guardian" not in hero_of(service).unlocked_vocations
    preview = service.submit(command(service, "PreviewVocation", revision=0, target_vocation_id="guardian"))
    assert preview.accepted and preview.preview is not None
    assert preview.preview["eligible_to_claim"] is True and preview.preview["blocked_by"] == []
    assert service.state.processed == {} and hero_of(service).revision == 3


def test_an_unknown_catalog_version_needs_a_migration(catalog):
    service = service_with(catalog, mastered=("squire",))
    old = command(service, "ClaimVocation", target_vocation_id="guardian")
    old["params"]["catalog_version"] = "1.2.1"
    assert service.submit(old).error_code == "CONTENT_MIGRATION_REQUIRED"


def test_when_several_conditions_fail_the_first_in_the_check_order_is_reported(catalog):
    """Registry check order: revision, phase, hero eligibility, second slot, discovery, prerequisite."""
    service = service_with(catalog, run_phase="battle", eligibility_state="guest")
    everything_wrong = command(service, "ChangeVocation", revision=1, target_vocation_id="trickster", vocation_slot="secondary")
    assert service.submit(everything_wrong).error_code == "REVISION_CONFLICT"
    everything_wrong["state_revision"] = 3
    assert service.submit(everything_wrong).error_code == "PHASE_LOCKED"
    service.state.run = None
    assert service.submit(everything_wrong).error_code == "HERO_NOT_ELIGIBLE"
    hero_of(service).eligibility_state = "eligible"
    assert service.submit(everything_wrong).error_code == "UNSUPPORTED_SECONDARY_VOCATION"
    del everything_wrong["params"]["vocation_slot"]
    assert service.submit(everything_wrong).error_code == "PREREQUISITE_UNMET"


def test_an_unknown_command_or_hero_is_a_programming_error(catalog):
    service = service_with(catalog)
    with pytest.raises(ValueError, match="Unknown career command"):
        service.submit(command(service, "GrantEverything"))
    stranger = command(service, "PreviewVocation", target_vocation_id="guardian")
    stranger["params"]["hero_id"] = "hero_404"
    with pytest.raises(ValueError, match="Unknown hero"):
        service.submit(stranger)


# --------------------------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------------------------


def test_public_vocations_are_discovered_from_the_start_and_secret_ones_are_hidden(catalog):
    service = service_with(catalog)
    assert [service.discovery_state(v) for v in ("squire", "guardian", "hero")] == ["discovered"] * 3
    assert [service.discovery_state(v) for v in ("trickster", "dragon_knight")] == ["hidden"] * 2


@pytest.mark.parametrize("command_type", ["ClaimVocation", "PreviewVocation"])
def test_a_vocation_that_is_not_discovered_gives_nothing_away(catalog, command_type):
    service = service_with(catalog, mastered=("scout", "apprentice"), items={"jester_mask": 1})
    for target in ("trickster", "no_such_vocation"):
        result = service.submit(command(service, command_type, target_vocation_id=target))
        assert (result.result, result.error_code, result.error_details, result.preview) == ("rejected", "NOT_DISCOVERED", None, None)
    service.apply_discovery_signal({"signal": "quest_hint:crooked_mirror"})  # hinted is still not discovered
    assert service.submit(command(service, command_type, target_vocation_id="trickster")).error_code == "NOT_DISCOVERED"


def test_discovery_only_moves_forward_and_each_distinct_clue_counts_once(catalog):
    """Owner decision of 2026-11-11 (fixture CE-10)."""
    service = service_with(catalog)
    hint = service.apply_discovery_signal({"signal": "quest_hint:crooked_mirror"})
    assert [(e["type"], e["from"], e["to"]) for e in hint.events] == [("DiscoveryChanged", "hidden", "hinted")]
    found = service.apply_discovery_signal({"signal": "item_found:jester_mask"})
    assert [(e["from"], e["to"]) for e in found.events] == [("hinted", "discovered")]
    row = service.state.profile.discovery["trickster"]
    assert (row.state, row.clue_count) == ("discovered", 2)

    weaker_again = service.apply_discovery_signal({"signal": "quest_hint:crooked_mirror"})  # a repeat of a weaker clue
    assert weaker_again.accepted and weaker_again.events == [] and (row.state, row.clue_count) == ("discovered", 2)
    third = service.apply_discovery_signal({"signal": "quest_complete:crooked_mirror"})  # new clue, same state
    assert [(e["type"], e["signal"]) for e in third.events] == [("DiscoveryClueCounted", "quest_complete:crooked_mirror")]
    assert service.state.profile.discovery["trickster"].clue_count == 3
    nothing = service.apply_discovery_signal({"signal": "item_found:rubber_duck"})
    assert nothing.accepted and nothing.events == [] and list(service.state.profile.discovery) == ["trickster"]


def test_a_preview_for_a_guest_says_the_hero_is_not_eligible(catalog):
    service = service_with(catalog, mastered=("squire",), eligibility_state="guest")
    preview = service.submit(command(service, "PreviewVocation", target_vocation_id="guardian")).preview
    assert preview is not None
    assert (preview["eligible_to_claim"], preview["blocked_by"]) == (False, [{"error_code": "HERO_NOT_ELIGIBLE"}])
    own = service.submit(command(service, "PreviewVocation", 2, target_vocation_id="squire")).preview
    assert own is not None and (own["unlocked_for_hero"], own["eligible_to_claim"], own["blocked_by"]) == (True, False, [])


def test_a_weaker_clue_after_a_stronger_one_does_not_hide_what_was_shown(catalog):
    service = service_with(catalog)
    service.apply_discovery_signal({"signal": "item_found:drake_scale"})
    later = service.apply_discovery_signal({"signal": "mastery_rank:spellblade:4"})
    row = service.state.profile.discovery["dragon_knight"]
    assert [e["type"] for e in later.events] == ["DiscoveryClueCounted"] and (row.state, row.clue_count) == ("discovered", 2)
    names = {signal_name(entry) for v in catalog.raw["vocations"] for entry in v.get("discovery", {}).get("signals", [])}
    assert {"mastery_rank:spellblade:4", "item_found:drake_scale", "quest_hint:crooked_mirror"} <= names


# --------------------------------------------------------------------------------------------
# Claims
# --------------------------------------------------------------------------------------------


def test_the_item_route_is_used_when_it_is_the_only_one_satisfied_and_refused_without_the_item(catalog):
    service = service_with(catalog, mastered=("apprentice",), items={"jester_mask": 1})
    service.apply_discovery_signal({"signal": "item_found:jester_mask"})
    claimed = service.submit(command(service, "ClaimVocation", target_vocation_id="trickster"))
    assert claimed.accepted and claimed.events[-1]["route_id"] == "route_1"
    assert service.state.profile.items == {"jester_mask": 0} and hero_of(service).unlock_routes == {"trickster": "route_1"}
    assert service.state.profile.item_consumptions == [
        {"hero_id": "hero_001", "item_id": "jester_mask", "quantity": 1, "claim_event": claimed.events[-1]["event_id"]}
    ]

    poor = service_with(catalog, mastered=("apprentice",))
    poor.apply_discovery_signal({"signal": "item_found:jester_mask"})
    refused = poor.submit(command(poor, "ClaimVocation", target_vocation_id="trickster"))
    assert refused.error_code == "ITEM_INSUFFICIENT"
    assert refused.error_details == {"item_id": "jester_mask", "quantity_required": 1, "quantity_held": 0}


def test_three_mastered_advanced_vocations_are_counted_for_the_heros_second_route(catalog):
    service = service_with(catalog, mastered=("squire", "scout", "guardian", "ranger"))
    refused = service.submit(command(service, "ClaimVocation", target_vocation_id="hero"))
    assert refused.error_details is not None
    second = refused.error_details["routes"][1]
    assert second["route_id"] == "route_1" and second["unmet"] == [
        {"op": "MASTERED_COUNT_AT_LEAST", "group": "advanced", "minimum": 3, "current_count": 2},
        {"op": "QUEST_COMPLETE", "quest_id": "trial_of_the_hero"},
    ]
    first = refused.error_details["routes"][0]["unmet"]
    assert [(u["vocation_id"], u["current_rank"]) for u in first] == [("champion", 0), ("archmage", 0)]


def test_a_quest_completed_by_another_hero_does_not_count_for_a_hero_scoped_quest(catalog):
    service = service_with(catalog, mastered=("squire", "scout", "apprentice", "guardian", "ranger", "arcanist"))
    service.state.profile.quests_completed.append({"quest_id": "trial_of_the_hero", "qualifier_scope": "hero", "qualifier_id": "hero_002"})
    assert service.submit(command(service, "ClaimVocation", target_vocation_id="hero")).error_code == "PREREQUISITE_UNMET"
    service.state.profile.quests_completed.append({"quest_id": "trial_of_the_hero", "qualifier_scope": "hero", "qualifier_id": "hero_001"})
    claimed = service.submit(command(service, "ClaimVocation", number=2, target_vocation_id="hero"))
    assert claimed.accepted and claimed.events[0]["route_id"] == "route_1"


def test_an_alternative_inside_a_route_stands_for_its_easiest_branch(catalog):
    """No shipped route nests an ``any``; the rule is exercised on a copy of the catalog."""
    raw = copy.deepcopy(catalog.raw)
    guardian = next(v for v in raw["vocations"] if v["id"] == "guardian")
    guardian["prerequisite"] = {"all": [{"mastered": "squire"}, {"any": [{"mastered": "scout"}, {"mastered": "apprentice"}]}]}
    nested = CareerCatalog(raw, packaged_content())
    assert list(nested.routes["guardian"]) == ["route_0"]
    allowed = service_with(nested, mastered=("squire", "apprentice"))
    assert allowed.submit(command(allowed, "ClaimVocation", target_vocation_id="guardian")).accepted
    refused = service_with(nested, mastered=("squire",))
    result = refused.submit(command(refused, "ClaimVocation", target_vocation_id="guardian"))
    assert result.error_details == {"routes": [{"route_id": "route_0", "unmet": [
        {"op": "MASTERY_AT_LEAST", "vocation_id": "scout", "rank": 8, "current_rank": 1}]}]}


def test_claiming_a_vocation_twice_changes_nothing_by_this_builds_rule(catalog):
    service = service_with(catalog, mastered=("squire",))
    assert service.submit(command(service, "ClaimVocation", 1, target_vocation_id="guardian")).accepted
    before = state_view(service)
    again = service.submit(command(service, "ClaimVocation", 2, target_vocation_id="guardian"))
    after = state_view(service)
    assert again.accepted and again.events == [] and after["heroes"] == before["heroes"] and after["profile"] == before["profile"]


@pytest.mark.parametrize("step", ["item_decrement", "event_insert", "unlock_insert", "consumption_insert"])
def test_a_failure_at_any_step_of_a_claim_leaves_nothing_behind(catalog, step):
    service = service_with(catalog, mastered=("squire", "apprentice", "spellblade"), items={"drake_scale": 1})
    service.apply_discovery_signal({"signal": "item_found:drake_scale"})
    before, events = state_view(service), len(service.state.events)
    service.fault = {"after": step}
    claim = command(service, "ClaimVocation", target_vocation_id="dragon_knight")
    with pytest.raises(InjectedFault):
        service.submit(claim)
    assert state_view(service) == before and len(service.state.events) == events and service.state.next_event_seq == events
    assert service.submit(claim).accepted, "the same command id succeeds once the fault is gone"
    assert service.state.profile.items == {"drake_scale": 0}


# --------------------------------------------------------------------------------------------
# Changing vocation
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("phase", "change", "claim"),
    [(None, True, True), ("upgrade", True, True), ("victory", True, True), ("defeat", True, True),
     ("equipment", False, True), ("battle", False, False)],
)
def test_when_the_build_may_change_inside_a_run(catalog, phase, change, claim):
    """Owner decision of 2026-11-11: after recovery and before the mandatory upgrade; never in battle or after the upgrade."""
    service = service_with(catalog, mastered=("squire",), unlocked=("guardian",), run_phase=phase)
    changed = service.submit(command(service, "ChangeVocation", 1, target_vocation_id="guardian"))
    assert changed.accepted is change and (changed.error_code is None) is change
    assert change or changed.error_code == "PHASE_LOCKED"
    claimed = service.submit(command(service, "ClaimVocation", 2, target_vocation_id="ranger"))
    assert (claimed.error_code == "PHASE_LOCKED") is not claim
    equip = service.submit(command(service, "EquipInheritedSkill", 3, skill_id="squire_anchor", slot_index=0))
    assert equip.accepted is change


def test_changing_to_a_vocation_that_was_not_claimed_is_refused_and_to_the_active_one_changes_nothing(catalog):
    service = service_with(catalog, mastered=("squire",))
    refused = service.submit(command(service, "ChangeVocation", 1, target_vocation_id="guardian"))
    assert refused.error_code == "PREREQUISITE_UNMET" and refused.error_details == {"vocation_id": "guardian", "unlocked_for_hero": False}
    same = service.submit(command(service, "ChangeVocation", 2, target_vocation_id="squire"))
    assert same.accepted and same.events == [] and hero_of(service).revision == 3


def test_a_change_never_revives_and_keeps_corruption_within_the_new_maximum(catalog):
    raw = copy.deepcopy(catalog.raw)
    next(v for v in raw["vocations"] if v["id"] == "guardian")["max_corruption"] = 4  # no authored vocation has a lower cap
    tighter = CareerCatalog(raw, packaged_content())
    downed = service_with(tighter, mastered=("squire",), unlocked=("guardian",), run_phase="upgrade",
                          combat=CombatSnapshot(hp=0, max_hp=15, mana=2, max_mana=3, corruption=5, state="downed"))
    assert downed.submit(command(downed, "ChangeVocation", target_vocation_id="guardian")).accepted
    combat = hero_of(downed).combat
    assert (combat.hp, combat.max_hp, combat.state) == (0, 18, "downed"), "a hero at 0 HP stays at 0 HP and downed"
    assert combat.corruption == 4, "corruption is kept, capped at the new maximum"

    shrinking = service_with(catalog, mastered=("squire", "apprentice"), unlocked=("guardian",), active="guardian", run_phase="upgrade",
                             combat=CombatSnapshot(hp=18, max_hp=18, mana=3, max_mana=4, corruption=6))
    assert shrinking.submit(command(shrinking, "ChangeVocation", target_vocation_id="apprentice")).accepted
    combat = hero_of(shrinking).combat
    apprentice = shrinking.effective_stats(hero_of(shrinking), "apprentice")
    assert (combat.hp, combat.max_hp) == (apprentice["max_hp"], apprentice["max_hp"]), "full health stays full"
    assert (apprentice["max_hp"], apprentice["max_mana"]) == (13, 7), "12 and 6 shipped, +1 each for the mastered Squire and Apprentice"
    assert (combat.mana, combat.max_mana) == (6, 7), "3 of 4 becomes ceil(3 * 7 / 4) = 6 of 7"
    assert combat.corruption == 6


# --------------------------------------------------------------------------------------------
# Inherited skills
# --------------------------------------------------------------------------------------------


def test_equipping_moving_and_unequipping_a_skill(catalog):
    service = service_with(catalog, mastered=("squire", "scout"), unlocked=("guardian",), active="guardian")
    hero = hero_of(service)
    assert hero.learned_skills == ["squire_anchor", "scout_marksman"] and service.capacity_used(hero) == 0
    first = service.submit(command(service, "EquipInheritedSkill", 1, skill_id="squire_anchor", slot_index=0))
    assert [(e["type"], e["skill_id"], e["slot_index"]) for e in first.events] == [("SkillEquipped", "squire_anchor", 0)]
    assert service.submit(command(service, "EquipInheritedSkill", 2, skill_id="scout_marksman", slot_index=1)).accepted
    assert (hero.equipped_skills, service.capacity_used(hero), hero.revision) == ({0: "squire_anchor", 1: "scout_marksman"}, 3, 5)

    moved = service.submit(command(service, "EquipInheritedSkill", 3, skill_id="squire_anchor", slot_index=2))
    assert moved.accepted and hero.equipped_skills == {1: "scout_marksman", 2: "squire_anchor"}, "a skill is equipped once"
    same = service.submit(command(service, "EquipInheritedSkill", 4, skill_id="squire_anchor", slot_index=2))
    assert same.accepted and same.events == [] and hero.revision == 6

    gone = service.submit(command(service, "UnequipInheritedSkill", 5, slot_index=1))
    assert [(e["type"], e["skill_id"]) for e in gone.events] == [("SkillUnequipped", "scout_marksman")]
    empty = service.submit(command(service, "UnequipInheritedSkill", 6, slot_index=1))
    assert empty.accepted and empty.events == [] and hero.equipped_skills == {2: "squire_anchor"} and hero.revision == 7


def test_a_skill_is_free_while_the_vocation_that_teaches_it_is_active(catalog):
    """v0.1 section 6.4: native and capacity-free only while its originating vocation is active."""
    service = service_with(catalog, mastered=("squire",))
    hero = hero_of(service)
    assert service.skill_cost(hero, "squire_anchor") == 0 and service.skill_cost(hero, "squire_anchor", "guardian") == 1
    assert service.submit(command(service, "EquipInheritedSkill", skill_id="squire_anchor", slot_index=0)).accepted
    assert service.capacity_used(hero) == 0 and catalog.inheritance_capacity("squire") == 2


def test_a_skill_that_was_not_learned_or_is_native_only_cannot_be_equipped_by_this_builds_rule(catalog):
    service = service_with(catalog, mastered=("squire", "scout"), unlocked=("guardian", "duelist", "champion"), active="guardian")
    unlearned = service.submit(command(service, "EquipInheritedSkill", 1, skill_id="guardian_field_medic", slot_index=0))
    assert unlearned.error_code == "PREREQUISITE_UNMET" and unlearned.error_details is not None
    assert unlearned.error_details["learned"] is False
    hero_of(service).learned_skills.append("champion_guard")
    native = service.submit(command(service, "EquipInheritedSkill", 2, skill_id="champion_guard", slot_index=0))
    assert native.error_code == "PREREQUISITE_UNMET" and native.error_details is not None
    assert native.error_details["transfer"] == "active_only"
    with pytest.raises(ValueError, match="Unknown skill"):
        service.submit(command(service, "EquipInheritedSkill", 3, skill_id="omniscience", slot_index=0))


def test_a_skill_tied_to_melee_or_ranged_faces_needs_such_a_face(catalog):
    service = service_with(catalog, mastered=("scout", "ranger"), active="squire")
    assert "ranger_mark" in hero_of(service).learned_skills
    assert service.submit(command(service, "EquipInheritedSkill", 1, skill_id="ranger_mark", slot_index=0)).error_code == "NO_LEGAL_FACE"
    assert service.submit(command(service, "ChangeVocation", 2, target_vocation_id="scout")).accepted
    assert service.submit(command(service, "EquipInheritedSkill", 3, skill_id="ranger_mark", slot_index=0)).accepted


def test_a_change_of_vocation_drops_the_skills_that_no_longer_fit(catalog):
    service = service_with(catalog, mastered=("squire", "scout", "apprentice"), unlocked=("guardian",), active="guardian")
    for number, (skill, slot) in enumerate([("squire_anchor", 0), ("scout_marksman", 1)], start=1):
        assert service.submit(command(service, "EquipInheritedSkill", number, skill_id=skill, slot_index=slot)).accepted
    changed = service.submit(command(service, "ChangeVocation", 9, target_vocation_id="apprentice"))  # capacity 2
    hero = hero_of(service)
    assert changed.events[0]["unequipped_skills"] == ["scout_marksman"] and hero.equipped_skills == {0: "squire_anchor"}
    assert service.capacity_used(hero) == 1 <= catalog.inheritance_capacity("apprentice")
    back = service.submit(command(service, "ChangeVocation", 10, target_vocation_id="guardian"))
    assert "unequipped_skills" not in back.events[0]


# --------------------------------------------------------------------------------------------
# Mastery awards
# --------------------------------------------------------------------------------------------


def award(service: CareerService, vocation_id: str, threat: int = 3, outcome: str = "victory", evidence: int = 0,
          challenge: str | None = None, encounter_id: str = "training_03", eligible: bool = True, deployed: bool = True) -> Any:
    service.state.encounter = EncounterResult(encounter_id, threat, eligible, outcome)
    return service.award_mastery({
        "type": "AwardEncounterMastery", "run_id": "run_0001", "encounter_id": encounter_id, "hero_id": "hero_001",
        "vocation_id": vocation_id, "deployed_at_encounter_start": deployed,
        "challenge_id": challenge or catalog_challenge(service, vocation_id), "challenge_evidence_count": evidence,
    })


def catalog_challenge(service: CareerService, vocation_id: str) -> str:
    return str(service.catalog.vocations[vocation_id]["bonus_challenge_id"])


def test_a_skill_is_learned_when_its_rank_is_reached(catalog):
    service = service_with(catalog)
    hero = hero_of(service)
    hero.mastery["squire"] = MasteryRow("squire", 3, 2)
    hero.learned_skills.clear()
    result = award(service, "squire", evidence=0)
    assert [e["type"] for e in result.events] == ["MasteryAwarded", "SkillLearned"]
    assert hero.mastery["squire"].rank == 4 and hero.learned_skills == ["squire_anchor"] and hero.revision == 4
    again = award(service, "squire", encounter_id="training_03b")
    assert [e["type"] for e in again.events] == ["MasteryAwarded"], "a skill is learned once"


def test_points_stop_at_the_last_threshold_and_a_mastered_vocation_earns_nothing(catalog):
    service = service_with(catalog)
    hero = hero_of(service)
    hero.mastery["squire"] = MasteryRow("squire", 7, 13)
    last = award(service, "squire", evidence=1)
    assert (last.events[0]["base_points"], last.events[0]["challenge_points"], last.events[0]["points_after"]) == (1, 0, 14)
    assert hero.mastery["squire"].rank == 8
    more = award(service, "squire", evidence=1, encounter_id="training_03b")
    assert more.accepted and more.events == [] and len(service.state.awards) == 1, "no row for a mastered vocation"


def test_the_bonus_needs_the_vocations_own_challenge(catalog):
    service = service_with(catalog)
    result = award(service, "squire", evidence=3, challenge="block_and_counter")
    assert (result.events[0]["base_points"], result.events[0]["challenge_points"]) == (1, 0)


def test_an_award_for_a_hero_that_was_not_deployed_or_an_ineligible_encounter_records_nothing(catalog):
    service = service_with(catalog)
    assert award(service, "squire", deployed=False).events == [] and service.state.awards == []
    assert award(service, "squire", eligible=False).events == [] and service.state.awards == []
    assert hero_of(service).mastery["squire"].points == 0 and hero_of(service).revision == 3


def test_an_award_must_name_the_encounter_that_ended_and_a_vocation_the_hero_has(catalog):
    service = service_with(catalog)
    service.state.encounter = EncounterResult("training_01", 1, True, "victory")
    event = {"run_id": "run_0001", "encounter_id": "training_03", "hero_id": "hero_001", "vocation_id": "squire"}
    with pytest.raises(ValueError, match="needs the result of the encounter"):
        service.award_mastery(event)
    with pytest.raises(ValueError, match="has not unlocked 'guardian'"):
        service.award_mastery({**event, "encounter_id": "training_01", "vocation_id": "guardian"})
    assert service.state.awards == []


# --------------------------------------------------------------------------------------------
# Catalog questions and the state view
# --------------------------------------------------------------------------------------------


def test_novice_numbers_come_from_the_shipped_classes(catalog):
    shipped = packaged_content().class_def("squire")
    assert catalog.base_stats("squire") == {name: shipped[name] for name in ("max_hp", "max_mana", "speed", "base_initiative", "max_corruption")}
    assert catalog.starting_dice("squire") == shipped["starting_dice"] and catalog.starting_dice("ranger") == ["ranger_d8", "ranger_d4"]
    assert [catalog.rank_for("squire", points) for points in (0, 1, 2, 4, 14, 99)] == [1, 2, 3, 4, 8, 8]
    assert (catalog.threat_floor("guardian", 1), catalog.threat_floor("guardian", 7), catalog.threat_floor("champion", 1)) == (2, 4, 4)
    assert {category for category, _ in catalog.die_faces("iron_d6")} >= {"attack", "defense", "healing"}


def test_the_state_view_is_plain_data_in_the_fixture_vocabulary(catalog):
    service = service_with(catalog, mastered=("squire",), run_phase="upgrade", combat=CombatSnapshot(hp=9, max_hp=15))
    view = state_view(service)
    assert set(view) == {"profile", "heroes", "run", "mastery_award_events", "processed_commands"}
    hero = view["heroes"][0]
    assert hero["permanent_stat_bonus"] == {"max_hp": 1, "max_mana": 0, "speed": 0} and hero["inheritance_capacity_max"] == 2
    assert hero["combat"] == {"hp": 9, "max_hp": 15, "state": "standing"} and view["run"]["phase"] == "upgrade"
    assert copy.deepcopy(view) == view


def test_the_game_does_not_load_the_career_package_yet():
    """Phase 2 is rules only: nothing a player runs may depend on them until they are wired in behind the gate."""
    import os
    import subprocess
    import sys

    code = (
        "import sys, tempfile\n"
        "import battle_dice.__main__, battle_dice.ui.app, battle_dice.sim.runner, battle_dice.replay_cli\n"
        "from battle_dice.app.controller import AppController\n"
        "import pathlib\n"
        "base = pathlib.Path(tempfile.mkdtemp())\n"
        "c = AppController(fixed_seed=1, log_dir=base / 'logs', features=['class_evolution_v1'])\n"
        "c.new_run(); c.add_hero('scout'); c.begin_run()\n"
        "saves = [p.name for p in base.rglob('*.sqlite*')]\n"
        "print(sorted(name for name in sys.modules if name.startswith('battle_dice.career')), saves)\n"
    )
    env = {**os.environ, "SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy"}
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=120, check=True)
    assert done.stdout.strip().splitlines()[-1] == "[] []", "no career module is loaded and no save file is created"


# --------------------------------------------------------------------------------------------
# Dice: a vocation may equip its own dice, plus its family's (owner decision of 2026-11-11)
# --------------------------------------------------------------------------------------------


def test_which_dice_a_vocation_may_equip(catalog):
    assert catalog.family("squire") is None and catalog.family("guardian") == "squire" and catalog.family("ranger") == "scout"
    assert catalog.own_dice("squire") == ["iron_d6", "oath_d4", "vanguard_d4"]
    # A Guardian: its own dice and the Squire's, nobody else's.
    assert all(catalog.may_equip("guardian", die) for die in ("guardian_d6", "guardian_d4", "iron_d6", "oath_d4", "vanguard_d4"))
    assert not any(catalog.may_equip("guardian", die) for die in ("striker_d8", "arcane_d6", "ranger_d8", "duelist_d6"))
    # A starting class: only its own. The family rule does not run backwards.
    assert not catalog.may_equip("squire", "guardian_d6") and not catalog.may_equip("scout", "ranger_d8")
    # A capstone's family is the starting class, not the vocations in between.
    assert catalog.may_equip("champion", "iron_d6") and not catalog.may_equip("champion", "guardian_d6")


def dice_hero(catalog: CareerCatalog) -> CareerService:
    from battle_dice.career.model import DieInstance

    dice = [DieInstance("hero_001-iron_d6-1", "iron_d6", "equipped", 0), DieInstance("hero_001-oath_d4-1", "oath_d4", "equipped", 1),
            DieInstance("hero_001-striker_d8-1", "striker_d8", "bench")]
    return service_with(catalog, mastered=("squire",), unlocked=("guardian",), dice=dice)


def test_a_change_of_vocation_equips_its_own_dice_and_a_family_die_can_be_put_back(catalog):
    service = dice_hero(catalog)
    hero = hero_of(service)
    changed = service.submit(command(service, "ChangeVocation", 1, target_vocation_id="guardian"))
    assert changed.events[0]["displaced_dice_ids"] == ["hero_001-iron_d6-1", "hero_001-oath_d4-1"]
    equipped = {d.slot_index: d.definition_id for d in hero.dice if d.location == "equipped"}
    assert equipped == {0: "guardian_d6", 1: "guardian_d4"} and len(hero.dice) == 5, "the Guardian's dice came with the vocation"

    back = service.submit(command(service, "EquipDie", 2, die_instance_id="hero_001-iron_d6-1", slot_index=0))
    assert back.accepted and back.events[0]["type"] == "DieEquipped" and back.events[0]["displaced_die_id"] == "hero_001-guardian_d6-1"
    equipped = {d.slot_index: d.definition_id for d in hero.dice if d.location == "equipped"}
    assert equipped == {0: "iron_d6", 1: "guardian_d4"}, "a family die may be put back"
    assert next(d for d in hero.dice if d.definition_id == "guardian_d6").location == "bench"

    same = service.submit(command(service, "EquipDie", 3, die_instance_id="hero_001-iron_d6-1", slot_index=0))
    assert same.accepted and same.events == [] and hero.revision == 5


@pytest.mark.parametrize(
    ("die_instance_id", "slot"),
    [("hero_001-striker_d8-1", 0), ("hero_001-no_such_die-1", 0), ("hero_001-iron_d6-1", 2), ("hero_001-iron_d6-1", -1)],
)
def test_a_die_of_another_vocation_an_unknown_die_or_a_slot_that_does_not_exist_is_refused(catalog, die_instance_id, slot):
    service = dice_hero(catalog)
    assert service.submit(command(service, "ChangeVocation", 1, target_vocation_id="guardian")).accepted
    before = state_view(service)
    refused = service.submit(command(service, "EquipDie", 2, die_instance_id=die_instance_id, slot_index=slot))
    assert refused.error_code == "INCOMPATIBLE_DIE" and state_view(service) == before
    assert refused.error_details == {"die_instance_id": die_instance_id, "vocation_id": "guardian"}


def test_two_equipped_dice_trade_places_and_a_die_swap_can_cost_a_skill_its_face(catalog):
    service = dice_hero(catalog)
    hero = hero_of(service)
    swapped = service.submit(command(service, "EquipDie", 1, die_instance_id="hero_001-oath_d4-1", slot_index=0))
    assert swapped.accepted and {d.definition_id: d.slot_index for d in hero.dice if d.location == "equipped"} == {"oath_d4": 0, "iron_d6": 1}

    # Field Medic needs a Healing face. Of the dice a Guardian may equip, only the Guardian d6 and the Iron d6 have one.
    medic = service_with(catalog, mastered=("squire", "guardian"), active="squire", dice=list(dice_hero(catalog).state.heroes["hero_001"].dice))
    assert medic.submit(command(medic, "ChangeVocation", 1, target_vocation_id="guardian")).accepted
    assert medic.submit(command(medic, "EquipInheritedSkill", 2, skill_id="guardian_field_medic", slot_index=0)).accepted
    assert medic.submit(command(medic, "EquipDie", 3, die_instance_id="hero_001-oath_d4-1", slot_index=0)).accepted
    equipped = sorted(d.definition_id for d in hero_of(medic).dice if d.location == "equipped")
    assert equipped == ["guardian_d4", "oath_d4"], "neither has a Healing face"
    assert medic.state.events[-1]["unequipped_skills"] == ["guardian_field_medic"] and hero_of(medic).equipped_skills == {}
    assert "guardian_field_medic" in hero_of(medic).learned_skills, "the skill stays learned"
    refused = medic.submit(command(medic, "EquipInheritedSkill", 4, skill_id="guardian_field_medic", slot_index=0))
    assert refused.error_code == "NO_LEGAL_FACE"


def test_die_changes_are_locked_like_every_other_build_change(catalog):
    service = dice_hero(catalog)
    service.state.run = RunInfo("run_0001", "battle", 12)
    locked = service.submit(command(service, "EquipDie", 1, die_instance_id="hero_001-oath_d4-1", slot_index=0))
    assert locked.error_code == "PHASE_LOCKED"
