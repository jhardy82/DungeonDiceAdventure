"""The optional third battle (Class Evolution Phase 4, step B).

Owner decision of 2026-11-11: the threat-4 fight is an optional third battle. A run started with
``StartRun``'s optional ``encounters`` asks the player after battle 2 whether to stop with a
victory or to fight on; losing the third battle is a defeat. A run started without it is the run
the game has always had, which the replay pin proves on every change.
"""

from __future__ import annotations

import dataclasses

import pytest

from battle_dice.content.vocations import VocationCatalog, load_catalog, load_vocation_catalog
from battle_dice.core import commands as cmd
from battle_dice.core.build import EncounterSource
from battle_dice.core.commands import CommandRejected
from battle_dice.core.engine import Engine
from battle_dice.core.events import EventType, events_hash, state_hash
from battle_dice.core.models import RunPhase
from battle_dice.core.replay import ReplayError, export_run, verify
from battle_dice.core.view import snapshot
from battle_dice.sim.policies import HeuristicPolicy, RandomPolicy, play_run
from tests.conftest import enemies, events_of, heroes, ok, packaged_content, rejected, unit, win_battle
from tests.integration.test_full_runs import play_checked

FIGHT = "training_04"
PARTY = [("squire", "front"), ("scout", "back"), ("apprentice", "back")]


@pytest.fixture(scope="module")
def catalog() -> VocationCatalog:
    return load_vocation_catalog(packaged_content())


def started(catalog: VocationCatalog | None, seed: int = 7, members: list[tuple[str, str]] | None = None,
            encounters: list[str] | None = None) -> Engine:
    engine = Engine(packaged_content(), catalog)
    params: dict = {"seed": seed, "party": [{"class_id": c, "row": r} for c, r in (members or PARTY)]}
    if encounters is not None:
        params["encounters"] = encounters
    ok(engine.do(cmd.START_RUN, **params))
    return engine


def at_the_decision(catalog: VocationCatalog, **kwargs) -> Engine:
    """A run that has won both shipped battles and now waits for: stop, or fight on."""
    engine = started(catalog, encounters=[FIGHT], **kwargs)
    win_battle(engine)
    offer = next(o for dice in engine.state.upgrade_offers.values() for die in dice.values() for o in die)
    ok(engine.do(cmd.CHOOSE_UPGRADE, hero_id=offer["hero_id"], die_id=offer["die_id"], offer_id=offer["offer_id"]))
    ok(engine.do(cmd.ADVANCE_PHASE))
    win_battle(engine)
    return engine


# --------------------------------------------------------------------------------------------
# The decision after battle 2
# --------------------------------------------------------------------------------------------


def test_the_catalog_is_an_encounter_source_and_the_engine_uses_it_by_default(catalog: VocationCatalog) -> None:
    as_object: object = catalog
    assert isinstance(as_object, EncounterSource)
    assert Engine(packaged_content(), catalog).encounters is catalog
    assert Engine(packaged_content()).encounters is None
    other = dataclasses.replace(catalog, version="other")
    assert Engine(packaged_content(), catalog, other).encounters is other


def test_after_battle_two_the_run_waits_for_stop_or_fight_on(catalog):
    engine = at_the_decision(catalog)
    state = engine.state
    assert state.phase == RunPhase.CONTINUE == "continue" and state.outcome is None and not engine.finished()
    assert engine.needs_input() and engine.offered_encounter() == FIGHT
    assert engine.permissible_commands() == [cmd.CONTINUE_RUN, cmd.END_RUN, cmd.SET_FORMATION]
    assert (engine.shipped_battle_count, engine.battle_count) == (2, 3)
    offered = events_of(engine, EventType.EXTRA_BATTLE_OFFERED)
    assert [e.delta for e in offered] == [{"battle": 3, "encounter_id": FIGHT}]
    # The party has recovered, by the same rule as after battle 1, before it decides.
    recoveries = events_of(engine, EventType.RECOVERY_APPLIED)
    assert len(recoveries) == 2 and engine.events.index(recoveries[1]) < engine.events.index(offered[0])
    assert all(h.standing and h.shields == 0 and h.mana == engine.build(h.id).max_mana for h in heroes(engine))
    # No second upgrade is offered.
    assert len(events_of(engine, EventType.UPGRADE_OFFERS_GENERATED)) == 1 and len(state.upgrades) == 1
    view = snapshot(engine)
    assert view["extra_battle"] == {"battle": 3, "encounter_id": FIGHT} and view["battle_count"] == 3
    assert view["run_phase"] == "continue" and view["permissible_commands"] == engine.permissible_commands()


def test_only_the_two_new_commands_and_a_formation_change_are_accepted_while_it_waits(catalog):
    engine = at_the_decision(catalog)
    rejected(engine.do(cmd.ADVANCE_PHASE), "fight on (ContinueRun) or to end the run")
    rejected(engine.do(cmd.ROLL_DICE), "No battle is in progress")
    rejected(engine.do(cmd.SWAP_DIE, hero_id="h01", out_die_id="oath_d4", in_die_id="vanguard_d4"), "between battles, after the mandatory upgrade")
    offer_hero = engine.state.upgrades[0]["hero_id"]
    rejected(engine.do(cmd.CHOOSE_UPGRADE, hero_id=offer_hero, die_id="x", offer_id="y"), "once, after winning Battle 1")
    assert unit(engine, "h02").row == "back"
    ok(engine.do(cmd.SET_FORMATION, hero_id="h02", row="front"))
    assert unit(engine, "h02").row == "front" and engine.state.phase == RunPhase.CONTINUE


def test_ending_the_run_is_a_victory_after_two_battles(catalog):
    engine = at_the_decision(catalog)
    ok(engine.do(cmd.END_RUN))
    state = engine.state
    assert (state.phase, state.outcome) == (RunPhase.VICTORY, "victory") and engine.finished()
    assert [r["battle"] for r in state.battle_records] == [1, 2]
    assert engine.events[-1].type == EventType.RUN_VICTORY and engine.events[-1].delta == {"battle": 2, "declined": FIGHT}
    assert engine.offered_encounter() is None and snapshot(engine)["extra_battle"] is None
    rejected(engine.do(cmd.CONTINUE_RUN), "No further battle is on offer")
    rejected(engine.do(cmd.END_RUN), "only while a further battle is on offer")


def test_fighting_on_starts_the_authored_encounter_for_this_party_size(catalog):
    engine = at_the_decision(catalog)
    hp_before = {h.id: h.hp for h in heroes(engine)}
    upgraded = dict(engine.state.die_overrides)
    ok(engine.do(cmd.CONTINUE_RUN))
    state, combat = engine.state, engine.combat
    assert state.phase == RunPhase.BATTLE and state.encounter_index == 2 and combat.encounter_id == FIGHT
    table = next(e for e in load_catalog()["encounters"] if e["id"] == FIGHT)["enemies"]["3"]
    foes = enemies(engine)
    assert sorted(f.id for f in foes) == ["b3_e01", "b3_e02", "b3_e03"]
    assert sorted((f.archetype_id, f.max_hp) for f in foes) == sorted((e["archetype"], e["overrides"]["max_hp"]) for e in table)
    assert all(f.hp == f.max_hp for f in foes)
    started_event = events_of(engine, EventType.BATTLE_STARTED)[-1]
    assert (started_event.delta["battle"], started_event.delta["encounter_id"]) == (3, FIGHT)
    # The heroes go in as they were after recovery, with the upgrade they chose.
    assert {h.id: h.hp for h in heroes(engine)} == hp_before and engine.state.die_overrides == upgraded
    assert snapshot(engine)["battle"] == 3 and snapshot(engine)["extra_battle"] is None


def test_winning_the_third_battle_is_the_victory(catalog):
    engine = at_the_decision(catalog)
    ok(engine.do(cmd.CONTINUE_RUN))
    win_battle(engine)
    state = engine.state
    assert (state.phase, state.outcome) == (RunPhase.VICTORY, "victory")
    assert [(r["battle"], r["outcome"]) for r in state.battle_records] == [(1, "victory"), (2, "victory"), (3, "victory")]
    assert engine.events[-1].delta == {"battle": 3} and [e.type for e in engine.events[-2:]] == ["battle_won", "run_victory"]


def test_losing_the_third_battle_is_a_defeat(catalog):
    engine = at_the_decision(catalog)
    ok(engine.do(cmd.CONTINUE_RUN))
    for hero in heroes(engine):  # arranged: a party that cannot survive
        hero.hp, hero.shields, hero.mana = 1, 0, 0
    assert play_run(engine, HeuristicPolicy()) == "defeat"
    state = engine.state
    assert (state.phase, state.outcome) == (RunPhase.DEFEAT, "defeat")
    assert [(r["battle"], r["outcome"]) for r in state.battle_records] == [(1, "victory"), (2, "victory"), (3, "defeat")]
    assert [e.type for e in engine.events[-2:]] == ["battle_lost", "run_defeat"]


# --------------------------------------------------------------------------------------------
# Starting such a run
# --------------------------------------------------------------------------------------------


def test_run_started_names_the_extra_encounters_and_pins_the_catalog(catalog):
    engine = started(catalog, encounters=[FIGHT])
    delta = engine.events[0].delta
    assert delta["encounters"] == [FIGHT]
    # Every hero is a shipped class; the catalog is pinned all the same, because its encounter may be fought.
    assert delta["vocation_catalog"] == {"version": catalog.version, "sha256": catalog.sha256} == engine.vocation_catalog_pin
    plain = started(catalog)
    assert "encounters" not in plain.events[0].delta and "vocation_catalog" not in plain.events[0].delta
    assert plain.battle_count == 2 and plain.vocation_catalog_pin is None


@pytest.mark.parametrize(("catalog_on", "encounters", "reason"), [
    (False, [FIGHT], "no encounters beyond the shipped battles"),
    (True, ["nowhere"], "Unknown encounter 'nowhere'"),
    (True, ["training_05"], "its enemies have not been authored"),
    (True, ["training_01"], "it is a shipped battle of every run"),
    (True, [FIGHT, FIGHT], "only once"),
])
def test_a_start_with_an_encounter_that_cannot_be_played_is_refused_and_nothing_starts(catalog, catalog_on, encounters, reason):
    engine = Engine(packaged_content(), catalog if catalog_on else None)
    result = engine.do(cmd.START_RUN, seed=1, party=[{"class_id": "squire", "row": "front"}], encounters=encounters)
    rejected(result, reason)
    assert not engine.started and engine.events == [] and engine._extra_encounters == [] and engine._builds == {}
    ok(engine.do(cmd.START_RUN, seed=1, party=[{"class_id": "squire", "row": "front"}]))  # the engine is still usable
    assert engine.battle_count == 2


def test_a_start_that_fails_late_leaves_no_encounters_behind(catalog, monkeypatch):
    """Arranged: the start is refused after its encounters were noted. The engine must forget them."""
    engine = Engine(packaged_content(), catalog)
    real = engine._build_combat

    def refuse(*args, **kwargs):
        raise CommandRejected("arranged refusal")

    monkeypatch.setattr(engine, "_build_combat", refuse)
    rejected(engine.do(cmd.START_RUN, seed=1, party=[{"class_id": "squire", "row": "front"}], encounters=[FIGHT]), "arranged refusal")
    assert not engine.started and engine._extra_encounters == [] and engine._builds == {} and engine.events == []
    monkeypatch.setattr(engine, "_build_combat", real)
    ok(engine.do(cmd.START_RUN, seed=1, party=[{"class_id": "squire", "row": "front"}]))
    assert engine.battle_count == 2 and engine.vocation_catalog_pin is None  # a plain run, with nothing left over


def test_the_encounters_parameter_must_be_a_list_of_names(catalog):
    engine = Engine(packaged_content(), catalog)
    result = engine.do(cmd.START_RUN, seed=1, party=[{"class_id": "squire", "row": "front"}], encounters=FIGHT)
    rejected(result, "StartRun.encounters must be a list of strings")
    empty = started(catalog, encounters=[])  # an empty list is the plain run
    assert empty.battle_count == 2 and "encounters" not in empty.events[0].delta


def test_a_run_without_extra_encounters_never_sees_the_decision(catalog):
    engine = started(catalog)
    assert play_run(engine, HeuristicPolicy()) in ("victory", "defeat")
    assert not events_of(engine, EventType.EXTRA_BATTLE_OFFERED) and len(engine.state.battle_records) <= 2
    rejected(engine.do(cmd.CONTINUE_RUN), "No further battle is on offer")  # a finished run offers nothing either
    fresh = started(catalog)
    rejected(fresh.do(cmd.CONTINUE_RUN), "No further battle is on offer")
    rejected(fresh.do(cmd.END_RUN), "only while a further battle is on offer")


# --------------------------------------------------------------------------------------------
# Whole runs, replay, and the simulated players
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(10))
def test_runs_with_the_third_battle_play_to_an_outcome_with_every_invariant_held(catalog, seed):
    sizes = [[("guardian", "front")], PARTY[:2], PARTY, [*PARTY, ("guardian", "front")], [*PARTY, ("guardian", "front"), ("ranger", "back")]]
    policy = HeuristicPolicy() if seed % 2 == 0 else RandomPolicy(seed)
    engine = started(catalog, seed=seed, members=sizes[seed % 5], encounters=[FIGHT])
    outcome = play_checked(engine, policy)
    records = engine.state.battle_records
    assert outcome in ("victory", "defeat") and 1 <= len(records) <= 3
    if len(records) == 3:
        assert engine.combat.encounter_id == FIGHT and records[2]["outcome"] == outcome


def test_a_run_with_the_third_battle_replays_exactly_from_its_record(catalog):
    engine = started(catalog, seed=1, encounters=[FIGHT])
    play_run(engine, HeuristicPolicy())
    assert len(engine.state.battle_records) == 3, "this seed fights the third battle"
    record = export_run(engine)
    assert record["commands"][0]["params"]["encounters"] == [FIGHT]
    assert record["vocation_catalog"] == {"version": catalog.version, "sha256": catalog.sha256}
    again = verify(packaged_content(), record)  # the packaged catalog is loaded for it
    assert (events_hash(again.events), state_hash(again.state)) == (events_hash(engine.events), state_hash(engine.state))
    changed = dataclasses.replace(catalog, sha256="0" * 64)
    with pytest.raises(ReplayError, match="vocation catalog differs"):
        verify(packaged_content(), record, changed)


def test_the_simulated_player_stops_or_fights_on_as_it_is_told(catalog):
    stopping = started(catalog, seed=1, encounters=[FIGHT])
    assert play_run(stopping, HeuristicPolicy(fight_on=False)) == "victory"
    assert len(stopping.state.battle_records) == 2 and stopping.command_log[-1].type == cmd.END_RUN
    going = started(catalog, seed=1, encounters=[FIGHT])
    play_run(going, HeuristicPolicy())
    assert len(going.state.battle_records) == 3 and cmd.CONTINUE_RUN in [c.type for c in going.command_log]
    # Up to the decision the two runs are the same run.
    shared = len(stopping.command_log) - 1
    assert [c.type for c in going.command_log[:shared]] == [c.type for c in stopping.command_log[:shared]]


def test_a_rejected_decision_changes_nothing(catalog):
    engine = at_the_decision(catalog)
    before = state_hash(engine.state), engine.revision, len(engine.events)
    draws = {name: stream.draws for name, stream in engine.state.rng.items()}
    rejected(engine.do(cmd.ADVANCE_PHASE))
    rejected(engine.do(cmd.SET_FORMATION, hero_id="h09", row="front"), "Unknown hero")
    assert (state_hash(engine.state), engine.revision, len(engine.events)) == before
    assert {name: stream.draws for name, stream in engine.state.rng.items()} == draws
