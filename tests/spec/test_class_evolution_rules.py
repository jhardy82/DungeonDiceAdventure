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
from battle_dice.career.service import (
    UNDISCOVERED_LABEL,
    CareerResult,
    CareerService,
    InjectedFault,
    career_tree_view,
    state_view,
)
from battle_dice.content import vocations
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
#: Cases this module runs with a test of their own, because their step is not a career command.
RUN_HERE_BY_NAME = ["CE-09", "CE-36"]
#: Cases another module runs, and where.
RUN_ELSEWHERE = {
    "CE-01": "the replay pin and tests/unit/test_vocations.py (gate off)",
    "CE-19": "tests/integration/test_vocation_change_in_run.py (the change before the upgrade, the upgrade on the new die, "
             "that die locked against a swap; the engine names dice by definition, not by instance)",
    "CE-25": "tests/spec/test_class_evolution_store.py (saved run upgrades)",
    "CE-32": "tests/spec/test_class_evolution_determinism.py (a recorded session, replayed with different clocks)",
    "CE-34": "tests/spec/test_class_evolution_store.py (a save of another catalog version)",
    "CE-35": "tests/unit/test_snapshot.py (the shipped start command, and saved heroes with build snapshots)",
    "CE-40": "tests/integration/test_class_evolution_runs.py (gate on, starting classes: byte for byte)",
}
#: Cases no test can run yet, and what each waits for. Their rules are decided unless the text says otherwise.
NOT_EXECUTABLE_YET = {
    "CE-29": "names Champion dice (wave 4) and an inherited skill in battle (Phase 4); "
             "its code and situation are tested on today's content in tests/unit/test_plan_codes.py",
    "CE-30": "names Champion dice (wave 4); its code and situation are tested on today's content in tests/unit/test_plan_codes.py",
    "CE-31": "still needs a decision: what Duelist's Parry does in the engine (wave 3)",
}
NOT_RUN_HERE = {**RUN_ELSEWHERE, **NOT_EXECUTABLE_YET}
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


# --------------------------------------------------------------------------------------------
# CE-09: the career tree shows an undiscovered secret as an anonymous entry
# --------------------------------------------------------------------------------------------


def test_ce09_a_hidden_secret_is_an_anonymous_entry_that_leaks_nothing(catalog: CareerCatalog) -> None:
    case = CASES["CE-09"]
    assert "needs_design_decision" not in case and case["when"]["event"]["type"] == "BuildCareerTreeView"
    service = CareerService(catalog, load_state(case["given"], catalog))
    before = state_view(service)
    view = career_tree_view(service, case["when"]["event"]["hero_id"])
    assert state_view(service) == before and not service.state.events, "building a view changes nothing"

    expected = case["then"]["state"]["view_model"]["career_tree"]
    entries = view["career_tree"]["entries"]
    listed = [entry["vocation_id"] for entry in entries if entry["kind"] == "vocation"]
    assert sorted(listed) == sorted(expected["listed_vocation_ids"]) and len(listed) == 12
    anonymous = [{key: value for key, value in entry.items() if key != "kind"} for entry in entries if entry["kind"] != "vocation"]
    assert anonymous == expected["anonymous_entries"] == [{"label": UNDISCOVERED_LABEL}] * 2
    assert entries[-2:] == [{"kind": "undiscovered", "label": UNDISCOVERED_LABEL}] * 2, "the anonymous entries come last"
    assert not set(expected["absent_vocation_ids"]) & set(listed)
    text = json.dumps(view, ensure_ascii=False)
    for forbidden in expected["forbidden_strings"]:
        assert forbidden not in text, f"the view leaks {forbidden!r}"
    # Every string that could give a secret away is on the case's list: ids, names, items, quests and clues.
    for vocation_id in expected["absent_vocation_ids"]:
        secret = catalog.vocations[vocation_id]
        assert {vocation_id, secret["name"], secret["discovery"]["clue"]} <= set(expected["forbidden_strings"])


def test_ce09_the_entry_of_a_listed_vocation_says_what_the_hero_has_reached(catalog: CareerCatalog) -> None:
    service = CareerService(catalog, load_state(CASES["CE-09"]["given"], catalog))
    hero = service.state.heroes["hero_001"]
    hero.mastery["squire"] = MasteryRow("squire", 8, 14)
    hero.mastery["apprentice"] = MasteryRow("apprentice", 7, 10)  # one rank short of mastery
    by_id = {e["vocation_id"]: e for e in career_tree_view(service, "hero_001")["career_tree"]["entries"] if e["kind"] == "vocation"}
    assert list(by_id) == [v for v in catalog.vocations if catalog.is_public(v)], "listed in catalog order"
    assert by_id["squire"] == {"kind": "vocation", "vocation_id": "squire", "name": "Squire", "group": "novice",
                               "unlocked": True, "active": True, "rank": 8, "mastered": True}
    assert by_id["scout"]["unlocked"] and not by_id["scout"]["active"] and by_id["scout"]["rank"] == 1
    assert (by_id["apprentice"]["rank"], by_id["apprentice"]["mastered"]) == (7, False)
    assert by_id["guardian"] == {"kind": "vocation", "vocation_id": "guardian", "name": "Guardian", "group": "advanced",
                                 "unlocked": False, "active": False, "rank": 0, "mastered": False}


def test_ce09_a_hint_shows_the_clue_only_and_a_discovery_shows_the_vocation(catalog: CareerCatalog) -> None:
    service = CareerService(catalog, load_state(CASES["CE-09"]["given"], catalog))
    assert service.apply_discovery_signal({"type": "ApplyDiscoverySignal", "signal": "quest_hint:crooked_mirror"}).accepted
    entries = career_tree_view(service, "hero_001")["career_tree"]["entries"]
    clue = catalog.vocations["trickster"]["discovery"]["clue"]
    # The hinted secret comes before the hidden one, whatever their order in the catalog.
    assert entries[-2:] == [{"kind": "undiscovered", "label": UNDISCOVERED_LABEL, "clue": clue},
                            {"kind": "undiscovered", "label": UNDISCOVERED_LABEL}]
    text = json.dumps(entries, ensure_ascii=False)
    for secret in ("trickster", "Trickster", "jester_mask", "crooked_mirror", "secret_sidegrade", "dragon_knight", "Dragon Knight"):
        assert secret not in text

    assert service.apply_discovery_signal({"type": "ApplyDiscoverySignal", "signal": "item_found:jester_mask"}).accepted
    entries = career_tree_view(service, "hero_001")["career_tree"]["entries"]
    assert [e for e in entries if e.get("vocation_id") == "trickster"] == [
        {"kind": "vocation", "vocation_id": "trickster", "name": "Trickster", "group": "secret_sidegrade",
         "unlocked": False, "active": False, "rank": 0, "mastered": False}]
    assert entries[-1] == {"kind": "undiscovered", "label": UNDISCOVERED_LABEL} and len(entries) == 14
    assert "Dragon Knight" not in json.dumps(entries)


# --------------------------------------------------------------------------------------------
# CE-36: a rank no available encounter can train is reported by the catalog validator
# --------------------------------------------------------------------------------------------


def test_ce36_an_advanced_vocation_cannot_reach_rank_8_on_the_available_encounters() -> None:
    case = CASES["CE-36"]
    assert "needs_design_decision" not in case and case["when"]["event"]["type"] == "ValidateCatalog"
    raw = load_catalog()
    (override,) = case["given"]["catalog"]["overrides"]
    assert override["path"] == "encounter_pool"
    expected, pool = case["then"]["error_details"], override["value"]
    assert case["then"]["result"] == "rejected" and case["then"]["error_code"] in vocations.CONTENT_VALIDATION_CODES

    shipped_only = [e["id"] for e in raw["encounters"] if e["source"] == "shipped"]
    for available in (pool, shipped_only):  # the case's pool, and the shipped battles alone
        details = vocations.training_dead_end_details(raw, available)
        advanced = [entry for entry in details if entry["vocation_group"] == expected["vocation_group"]]
        assert advanced and all({key: entry[key] for key in expected} == expected for entry in advanced), advanced
        assert {entry["vocation_id"] for entry in advanced} == {v["id"] for v in raw["vocations"] if v["group"] == "advanced"}
        assert vocations.available_threat(raw, available) == expected["max_available_threat"] == 3
    # Every dead end on the case's pool, as (rank, threat that rank needs), group by group.
    by_vocation: dict[str, list[tuple[int, int]]] = {}
    for entry in vocations.training_dead_end_details(raw, pool):
        by_vocation.setdefault(entry["vocation_id"], []).append((entry["rank"], entry["required_threat"]))
    assert by_vocation == {
        **{v["id"]: [(7, 4)] for v in raw["vocations"] if v["group"] == "advanced"},
        **{v["id"]: [(1, 4), (2, 4), (3, 4), (4, 5), (5, 5), (6, 5), (7, 5)] for v in raw["vocations"]
           if v["group"] in ("capstone", "secret_prestige")},
        "trickster": [(6, 4), (7, 4)],
    }, "a starting class has no dead end; the others have exactly these"
    # The decision: only encounters marked shipped count, at the catalog's ratings.
    shipped = {e["id"]: e["threat_rating"] for e in raw["encounters"] if e["source"] == "shipped"}
    assert shipped == {"training_01": 1, "training_03": 3} and set(shipped) <= set(pool)
    # With a threat 4 encounter available the dead end is gone. Phase 4 authored that encounter, and an
    # authored encounter counts as available like a shipped one: so the catalog as it stands has no such dead end.
    assert not [e for e in vocations.training_dead_end_details(raw, [*pool, "training_04"]) if e["vocation_group"] == "advanced"]
    assert vocations.available_threat(raw) == 4 and vocations.PLAYABLE_SOURCES == ("shipped", "authored")
    assert not [e for e in vocations.training_dead_end_details(raw) if e["vocation_group"] == "advanced"]
    assert vocations.problems_only(vocations.validate(raw, packaged_content(), wave=1)) == []
    # Taken away again, the validator prints exactly this case's dead end for the first wave.
    without = json.loads(json.dumps(raw))
    fight = next(e for e in without["encounters"] if e["id"] == "training_04")
    del fight["enemies"]
    fight["source"] = "to_author"
    lines = vocations.problems_only(vocations.validate(without, packaged_content(), wave=1))
    assert lines == [f"{case['then']['error_code']} guardian rank {expected['rank']}"]
    assert vocations.available_threat(raw, []) == -1


def test_every_case_is_run_or_accounted_for() -> None:
    assert sorted([*RUN_HERE, *RUN_HERE_BY_NAME, *NOT_RUN_HERE]) == sorted(CASES), "a fixture is neither run nor explained"
    assert len({*RUN_HERE, *RUN_HERE_BY_NAME, *NOT_RUN_HERE}) == len(CASES) == 40, "a fixture is listed twice"
    still_open = {case_id for case_id, case in CASES.items() if "needs_design_decision" in case}
    assert still_open == {"CE-31"} and still_open <= set(NOT_EXECUTABLE_YET)
    assert len(RUN_HERE) == 28 and len(RUN_ELSEWHERE) == 7 and len(NOT_EXECUTABLE_YET) == 3
    for case_id, where in RUN_ELSEWHERE.items():
        named = [word for word in where.replace("(", " ").split() if word.startswith("tests/")]
        assert named and all((ROOT / path).is_file() for path in named), f"{case_id}: {where}"
