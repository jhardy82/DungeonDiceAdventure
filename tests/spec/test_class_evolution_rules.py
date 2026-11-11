"""The acceptance fixtures, executed against the career rules (Class Evolution Phase 2).

``docs/class_evolution/fixtures/acceptance_fixtures.json`` states each case as: given this state,
when this one command or trusted event is applied, then this result and state. This module loads
the given state into :class:`battle_dice.career.service.CareerService`, applies the step and checks
what the case lists. It follows the conventions written in the fixtures file itself.

Every one of the 40 cases is either run here or named in ``NOT_RUN_HERE`` with the phase that
will run it, so no case can drop out unnoticed.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from battle_dice.career.catalog import CareerCatalog
from battle_dice.career.model import (
    AwardRow,
    CareerState,
    CombatSnapshot,
    DieInstance,
    DiscoveryRow,
    EncounterResult,
    HeroRecord,
    MasteryRow,
    ProcessedCommand,
    Profile,
    RunInfo,
)
from battle_dice.career.service import CareerResult, CareerService, InjectedFault, state_view
from battle_dice.content.vocations import load_catalog
from tests.conftest import packaged_content

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = json.loads((ROOT / "docs" / "class_evolution" / "fixtures" / "acceptance_fixtures.json").read_text(encoding="utf-8"))
CASES = {case["id"]: case for case in FIXTURES["cases"]}

#: The cases the career rules decide on their own.
RUN_HERE = [
    "CE-02", "CE-03", "CE-04", "CE-05", "CE-06", "CE-07", "CE-08", "CE-10", "CE-11", "CE-12", "CE-13", "CE-14", "CE-15",
    "CE-16", "CE-17", "CE-18", "CE-20", "CE-21", "CE-22", "CE-23", "CE-24", "CE-26", "CE-27", "CE-28", "CE-33", "CE-37", "CE-38",
    "CE-39",
]
#: Every other case, and where it is checked or will be.
NOT_RUN_HERE = {
    "CE-01": "the replay pin and tests/unit/test_vocations.py (gate off)",
    "CE-09": "needs a decision; the career-tree view is Phase 4",
    "CE-19": "the rules engine and owned dice together: Phase 4",
    "CE-25": "saved run upgrades: Phase 3",
    "CE-29": "needs a decision; a rules-engine case",
    "CE-30": "needs a decision; a rules-engine case",
    "CE-31": "needs a decision; a rules-engine case",
    "CE-32": "needs a decision (what every hash covers)",
    "CE-34": "loading a save: Phase 3",
    "CE-35": "StartRun with saved heroes and build snapshots: Phase 4",
    "CE-36": "the catalog validator: tests/spec/test_class_evolution_catalog.py",
    "CE-40": "tests/integration/test_class_evolution_runs.py (gate on, starting classes: byte for byte)",
}
#: Lists a case states in full; every other list is matched entry by entry on its id.
COMPLETE_LISTS = {"unlocked_vocations", "equipped_skills", "item_consumptions", "quests_completed", "mastery_award_events",
                  "processed_commands"}
ID_KEYS = ("hero_id", "vocation_id", "item_id", "die_instance_id")


@pytest.fixture(scope="module")
def catalog() -> CareerCatalog:
    return CareerCatalog(load_catalog(), packaged_content())


# --------------------------------------------------------------------------------------------
# given -> state
# --------------------------------------------------------------------------------------------


def load_state(given: dict[str, Any], catalog: CareerCatalog) -> CareerState:
    raw_profile = given["profile"]
    profile = Profile(
        raw_profile["profile_id"],
        discovery={
            row["vocation_id"]: DiscoveryRow(row["vocation_id"], row["discovery_state"], row.get("clue_count", 0))
            for row in raw_profile.get("discovery", [])
        },
        items={row["item_id"]: row["quantity"] for row in raw_profile.get("items", [])},
        item_consumptions=copy.deepcopy(raw_profile.get("item_consumptions", [])),
        quests_completed=copy.deepcopy(raw_profile.get("quests_completed", [])),
    )
    state = CareerState(profile)
    for raw in given.get("heroes", []):
        # Convention: a mastery row (rank 1, 0 points) for every unlocked vocation unless the case says otherwise.
        mastery = {vocation_id: MasteryRow(vocation_id) for vocation_id in raw["unlocked_vocations"]}
        for row in raw.get("mastery", []):
            mastery[row["vocation_id"]] = MasteryRow(row["vocation_id"], row["rank"], row["points"])
        learned = raw.get("learned_skills")
        if learned is None:
            learned = [skill for vocation_id, row in mastery.items() for skill in catalog.skills_learned_by(vocation_id, row.rank)]
        hero = HeroRecord(
            hero_id=raw["hero_id"],
            active_vocation_id=raw["active_vocation_id"],
            eligibility_state=raw["eligibility_state"],
            revision=raw["revision"],
            unlocked_vocations=list(raw["unlocked_vocations"]),
            mastery=mastery,
            learned_skills=list(learned),
            equipped_skills={entry["slot_index"]: entry["skill_id"] for entry in raw.get("equipped_skills", [])},
            dice=[DieInstance(**die) for die in raw.get("dice", [])],
            combat=CombatSnapshot(**raw["combat"]) if "combat" in raw else None,
        )
        state.heroes[hero.hero_id] = hero
    if given.get("run"):
        state.run = RunInfo(**given["run"])
    if "encounter" in given:
        state.encounter = EncounterResult(**given["encounter"])
    state.awards = [AwardRow(**row) for row in given.get("mastery_award_events", [])]
    for done in given.get("processed_commands", []):
        state.processed[done["command_id"]] = ProcessedCommand(done["command_id"], done["type"], {"result": done["result"]})
    earlier = [int(c["claim_event"].rsplit(":", 1)[1]) for c in profile.item_consumptions if ":" in str(c.get("claim_event"))]
    state.next_event_seq = max(earlier, default=-1) + 1
    return state


def check_the_given_state_is_consistent(case: dict[str, Any], service: CareerService) -> None:
    """Numbers a case states about its own starting point must be the ones the rules derive."""
    for raw in case["given"].get("heroes", []):
        hero = service.state.heroes[raw["hero_id"]]
        if "permanent_stat_bonus" in raw:
            assert service.permanent_stat_bonus(hero) == raw["permanent_stat_bonus"], case["id"]
        if "inheritance_capacity_used" in raw:
            assert service.capacity_used(hero) == raw["inheritance_capacity_used"], case["id"]
        if "inheritance_capacity_max" in raw:
            assert service.catalog.inheritance_capacity(hero.active_vocation_id) == raw["inheritance_capacity_max"], case["id"]
        for row in hero.mastery.values():
            assert service.catalog.rank_for(row.vocation_id, row.points) == row.rank, (case["id"], row)


# --------------------------------------------------------------------------------------------
# when -> result, and the comparison with then
# --------------------------------------------------------------------------------------------


def apply(service: CareerService, step: dict[str, Any]) -> CareerResult:
    if "command" in step:
        return service.submit(copy.deepcopy(step["command"]))
    event = step["event"]
    if event["type"] == "AwardEncounterMastery":
        return service.award_mastery(event)
    assert event["type"] == "ApplyDiscoverySignal", event["type"]
    return service.apply_discovery_signal(event)


def assert_matches(expected: Any, actual: Any, where: str, key: str = "") -> None:
    if isinstance(expected, dict):
        assert isinstance(actual, dict), where
        for name, value in expected.items():
            assert name in actual, f"{where}.{name} is missing"
            assert_matches(value, actual[name], f"{where}.{name}", name)
    elif isinstance(expected, list):
        assert isinstance(actual, list), where
        id_key = next((name for name in ID_KEYS if expected and isinstance(expected[0], dict) and name in expected[0]), None)
        if key in COMPLETE_LISTS or (expected and isinstance(expected[0], dict) and id_key is None):
            # Stated in full, or its entries carry no id to match on (a preview's blocked_by and routes).
            assert len(actual) == len(expected), f"{where}: expected exactly {expected}, got {actual}"
            for index, (want, got) in enumerate(zip(expected, actual, strict=True)):
                assert_matches(want, got, f"{where}[{index}]")
        elif id_key is not None:
            by_id = {entry[id_key]: entry for entry in actual}
            for want in expected:
                assert want[id_key] in by_id, f"{where}: no entry with {id_key} {want[id_key]}"
                assert_matches(want, by_id[want[id_key]], f"{where}[{want[id_key]}]")
        else:
            assert sorted(actual) == sorted(expected), where
    else:
        assert actual == expected, f"{where}: expected {expected!r}, got {actual!r}"


def assert_outcome(expected: dict[str, Any], result: CareerResult, service: CareerService, where: str) -> None:
    assert result.result == expected["result"], f"{where}: {result}"
    if "duplicate" in expected:
        assert result.duplicate is expected["duplicate"], where
    assert result.error_code == expected.get("error_code"), f"{where}: {result}"
    if "error_details" in expected:
        assert result.error_details == expected["error_details"], where
    if "events" in expected:  # complete and ordered
        assert len(result.events) == len(expected["events"]), f"{where}: events {result.events}"
        for index, (want, got) in enumerate(zip(expected["events"], result.events, strict=True)):
            assert_matches(want, got, f"{where}.events[{index}]")
    state = copy.deepcopy(expected.get("state", {}))
    for consumption in state.get("profile", {}).get("item_consumptions", []):
        if consumption.get("claim_event") == "events[0]":  # convention: the id of the first event of this step
            consumption["claim_event"] = result.events[0]["event_id"]
    preview = state.pop("preview", None)
    if preview is not None:
        assert_matches(preview, result.preview, f"{where}.preview")
    assert_matches(state, state_view(service), f"{where}.state")


@pytest.mark.parametrize("case_id", RUN_HERE)
def test_acceptance_fixture(case_id: str, catalog: CareerCatalog) -> None:
    case = CASES[case_id]
    assert "needs_design_decision" not in case, "a case that still needs a decision cannot be a test"
    service = CareerService(catalog, load_state(case["given"], catalog))
    check_the_given_state_is_consistent(case, service)

    for number, step in enumerate(case["given"].get("history", []), start=1):
        where = f"{case_id}.history[{number}]"
        if step["outcome"] == "aborted":  # it failed inside its transaction and was rolled back
            before = state_view(service)
            service.fault = {"after": step["fault_injection"]["after"]}
            with pytest.raises(InjectedFault):
                apply(service, step)
            assert state_view(service) == before, f"{where}: an aborted step left something behind"
        else:
            result = apply(service, step)
            assert result.accepted and result.duplicate is step.get("duplicate", False), f"{where}: {result}"
        assert_matches(step.get("state_after", {}), state_view(service), f"{where}.state_after")

    before = state_view(service)
    events_before = len(service.state.events)
    result = apply(service, case["when"])
    assert_outcome(case["then"], result, service, case_id)
    if result.result == "rejected" or result.duplicate:
        # A rejected result changes nothing: no row, no revision, no event. Neither does a replay.
        assert state_view(service) == before and len(service.state.events) == events_before, case_id


def test_every_case_is_either_run_here_or_accounted_for() -> None:
    assert sorted([*RUN_HERE, *NOT_RUN_HERE]) == sorted(CASES), "a fixture is neither run nor explained"
    assert not set(RUN_HERE) & set(NOT_RUN_HERE)
    still_open = {case_id for case_id, case in CASES.items() if "needs_design_decision" in case}
    assert still_open <= set(NOT_RUN_HERE)
    assert len(RUN_HERE) == 28
