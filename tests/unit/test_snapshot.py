"""A saved hero enters a run with a build snapshot (Class Evolution Phase 4, step C; fixture CE-35).

Owner decision of 2026-11-11: with the gate on the party names saved heroes, and each hero's
complete build is written into the run's log, so a replay needs only the log. Without a snapshot
the ``StartRun`` command is the shipped one, which the case itself sends.
"""

from __future__ import annotations

import pytest

from battle_dice.content.vocations import VocationCatalog, load_vocation_catalog
from battle_dice.core import commands as cmd
from battle_dice.core.engine import Engine
from battle_dice.core.events import events_hash, state_hash
from battle_dice.core.replay import export_run, verify
from battle_dice.sim.policies import HeuristicPolicy, play_run
from tests.conftest import ok, packaged_content, rejected, unit
from tests.spec.test_class_evolution_rules import CASES


@pytest.fixture(scope="module")
def catalog() -> VocationCatalog:
    return load_vocation_catalog(packaged_content())


def entry(class_id: str, row: str, **hero) -> dict:
    return {"class_id": class_id, "row": row, "hero": hero} if hero else {"class_id": class_id, "row": row}


def start(catalog: VocationCatalog | None, *party: dict, seed: int = 3) -> Engine:
    engine = Engine(packaged_content(), catalog)
    ok(engine.do(cmd.START_RUN, seed=seed, party=list(party)))
    return engine


def test_ce35_the_shipped_start_command_is_unchanged_and_starts_every_party(catalog):
    case = CASES["CE-35"]
    assert "needs_design_decision" not in case and case["when"]["command"]["type"] == cmd.START_RUN
    params = case["when"]["command"]["params"]
    engine = Engine(packaged_content(), catalog)
    ok(engine.do(cmd.START_RUN, **params))
    assert engine.state.phase == case["then"]["state"]["run"]["phase"] == "battle"
    assert len(engine.state.party) == case["then"]["state"]["run"]["party_size"] == 5
    assert all(set(member) == {"id", "class_id", "row"} for member in engine.state.party)  # no snapshot, no hero id
    assert "heroes" not in engine.events[0].delta
    vocations = [engine.build(member["id"]).vocation_id for member in engine.state.party]
    assert vocations == ["squire", "squire", "scout", "scout", "scout"]  # one vocation each; two heroes may share one


def test_a_snapshot_gives_the_hero_its_own_name_stats_and_dice(catalog):
    engine = start(catalog,
                   entry("squire", "front", hero_id="hero_007", name="Brakka", stats={"max_hp": 15, "max_mana": 3, "speed": 8},
                         dice=["iron_d6", "vanguard_d4"], bench=["oath_d4"], skills=["scout_marksman"]),
                   entry("scout", "back"))
    saved, plain = unit(engine, "h01"), unit(engine, "h02")
    assert (saved.name, saved.max_hp, saved.hp, saved.speed) == ("Brakka", 15, 15, 8)  # one more health, and it starts with it
    assert saved.equipped_dice_ids == ["iron_d6", "vanguard_d4"] and engine.state.inventory["h01"] == ["oath_d4"]
    build = engine.build("h01")
    assert (build.hero_id, build.display_name, build.skills, build.vocation_id) == ("hero_007", "Brakka", ("scout_marksman",), "squire")
    assert plain.name == "Scout 2" and engine.build("h02").hero_id == ""
    assert engine.state.party == [{"id": "h01", "class_id": "squire", "row": "front", "hero_id": "hero_007"},
                                  {"id": "h02", "class_id": "scout", "row": "back"}]
    assert engine.events[0].delta["heroes"] == [{
        "id": "h01", "hero_id": "hero_007", "name": "Brakka", "vocation_id": "squire", "max_hp": 15, "max_mana": 3, "speed": 8,
        "dice": ["iron_d6", "vanguard_d4"], "bench": ["oath_d4"], "skills": ["scout_marksman"]}]


def test_a_snapshot_with_only_a_hero_id_is_the_vocation_as_it_is(catalog):
    engine = start(catalog, entry("guardian", "front", hero_id="hero_001"))
    base = catalog.build("guardian")
    hero = unit(engine, "h01")
    assert (hero.max_hp, hero.hp, hero.speed, hero.max_mana) == (base.max_hp, base.start_hp, base.speed, base.max_mana)
    assert hero.equipped_dice_ids == list(base.starting_dice) and hero.name == "Guardian 1"


def test_an_evolved_hero_may_bring_a_die_of_its_family(catalog):
    """Decision CE-18: a vocation may equip its own dice plus its family's. The career rules decide; the run can hold it."""
    engine = start(catalog, entry("guardian", "front", hero_id="hero_001", dice=["guardian_d6", "iron_d6"], bench=["guardian_d4"]))
    assert unit(engine, "h01").equipped_dice_ids == ["guardian_d6", "iron_d6"]
    assert play_run(engine, HeuristicPolicy()) in ("victory", "defeat")


@pytest.mark.parametrize(("hero", "reason"), [
    ({"hero_id": "hero_001", "stats": {"max_hp": 13}}, "max_hp 13 is below the 14 of a Squire"),
    ({"hero_id": "hero_001", "dice": ["iron_d6"]}, "takes 2 dice into a run, not 1"),
    ({"hero_id": "hero_001", "dice": ["iron_d6", "iron_d6"]}, "a die is listed twice"),
    ({"hero_id": "hero_001", "dice": ["iron_d6", "oath_d4"], "bench": ["oath_d4"]}, "a die is listed twice"),
    ({"hero_id": "hero_001", "dice": ["iron_d6", "guardian_d6"]}, "the die 'guardian_d6' does not exist for a Squire"),
    ({"hero_id": "hero_001", "dice": ["iron_d6", "dragon_d8"]}, "the die 'dragon_d8' does not exist for a Squire"),
])
def test_a_snapshot_the_run_cannot_hold_is_refused_and_nothing_starts(catalog, hero, reason):
    engine = Engine(packaged_content(), catalog)
    rejected(engine.do(cmd.START_RUN, seed=1, party=[{"class_id": "squire", "row": "front", "hero": hero}]), reason)
    assert not engine.started and engine._builds == {} and engine.events == []


@pytest.mark.parametrize(("hero", "reason"), [
    ("hero_001", "a hero snapshot is an object"),
    ({"name": "Nobody"}, "a hero snapshot is an object with hero_id"),
    ({"hero_id": "hero_001", "level": 9}, "a hero snapshot is an object"),
    ({"hero_id": ""}, "hero.hero_id must not be empty"),
    ({"hero_id": "hero_001", "stats": {"max_hp": "15"}}, "hero.stats may hold whole numbers"),
    ({"hero_id": "hero_001", "stats": {"rerolls": 5}}, "hero.stats may hold whole numbers for max_hp, max_mana, speed only"),
    ({"hero_id": "hero_001", "dice": "iron_d6"}, "hero.dice has the wrong type"),
    ({"hero_id": "hero_001", "skills": [1]}, "hero.skills must be a list of strings"),
])
def test_a_malformed_snapshot_is_refused_before_the_run_is_looked_at(catalog, hero, reason):
    engine = Engine(packaged_content(), catalog)
    rejected(engine.do(cmd.START_RUN, seed=1, party=[{"class_id": "squire", "row": "front", "hero": hero}]), reason)
    rejected(engine.do(cmd.START_RUN, seed=1, party=[{"class_id": "squire", "row": "front", "pet": "cat"}]), "list of {class_id, row} objects")


def test_the_same_saved_hero_cannot_be_in_the_party_twice(catalog):
    engine = Engine(packaged_content(), catalog)
    party = [entry("squire", "front", hero_id="hero_001"), entry("scout", "back", hero_id="hero_001")]
    rejected(engine.do(cmd.START_RUN, seed=1, party=party), "'hero_001' is in the party twice")
    assert not engine.started and engine._builds == {}


def test_a_run_with_snapshots_replays_from_its_record_alone(catalog):
    party = [entry("guardian", "front", hero_id="hero_001", name="Brakka", stats={"max_hp": 18}),
             entry("scout", "back", hero_id="hero_002", name="Wren", stats={"speed": 11})]
    engine = start(catalog, *party, seed=9)
    play_run(engine, HeuristicPolicy())
    record = export_run(engine)
    assert record["commands"][0]["params"]["party"] == party  # the snapshot is in the command log
    again = verify(packaged_content(), record)
    assert (events_hash(again.events), state_hash(again.state)) == (events_hash(engine.events), state_hash(engine.state))
    assert unit(again, "h01").name == "Brakka" and unit(again, "h01").max_hp == 18


def test_a_snapshot_of_a_shipped_class_needs_no_catalog(catalog):
    party = [entry("squire", "front", hero_id="hero_001", name="Brakka", stats={"max_hp": 15})]
    engine = start(None, *party)
    play_run(engine, HeuristicPolicy())
    record = export_run(engine)
    assert "vocation_catalog" not in record
    verify(packaged_content(), record)


def test_a_bonus_changes_the_run_and_no_snapshot_changes_nothing(catalog):
    plain = start(catalog, entry("squire", "front"), entry("scout", "back"))
    named = start(catalog, entry("squire", "front", hero_id="hero_001"), entry("scout", "back", hero_id="hero_002"))
    for engine in (plain, named):
        play_run(engine, HeuristicPolicy())
    # A snapshot that changes no number plays the same battles: the same commands and the same outcome.
    assert [c.type for c in plain.command_log] == [c.type for c in named.command_log]
    assert plain.state.outcome == named.state.outcome and plain.state.battle_records == named.state.battle_records
    assert state_hash(plain.state) != state_hash(named.state)  # the party entries carry the saved hero ids
