"""The scripted personas used for scenario-based playtesting (``docs/PLAYTEST.md``).

Each persona must differ from the informed player in exactly the habit its name says, or the
comparison between them measures nothing.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from battle_dice.core import commands as cmd
from battle_dice.core.engine import Engine
from battle_dice.core.events import EventType
from battle_dice.core.models import CombatPhase
from battle_dice.sim.personas import PERSONAS, make_persona
from tests.conftest import begin_hero, enemies, events_of, packaged_content, party_spec, start

ROOT = Path(__file__).resolve().parents[2]


def play(persona: str, *party: str, seed: int = 3) -> Engine:
    engine = Engine(packaged_content())
    assert engine.do(cmd.START_RUN, seed=seed, party=party_spec(*party)).accepted
    policy = make_persona(persona, seed)
    while not engine.finished():
        if engine.needs_input():
            policy.act(engine)
        else:
            assert engine.do(cmd.ADVANCE_PHASE).accepted
    return engine


@pytest.mark.parametrize("persona", sorted(PERSONAS))
def test_every_persona_plays_a_whole_run_and_is_deterministic(persona):
    first, second = play(persona, "squire", "scout"), play(persona, "squire", "scout")
    assert first.state.outcome in ("victory", "defeat")
    assert [e.type for e in first.events] == [e.type for e in second.events]


def test_the_newcomer_never_rerolls_never_reacts_and_takes_one_action():
    engine = play("newcomer", "squire", "apprentice", "scout")
    assert not events_of(engine, EventType.DICE_REROLLED) and not events_of(engine, EventType.REACTION_USED)
    assert all(len(e.delta["actions"]) <= 1 for e in events_of(engine, EventType.PLAN_COMMITTED))


def test_single_habit_personas_change_only_their_habit():
    assert not events_of(play("no_reroll", "squire", "scout"), EventType.DICE_REROLLED)
    quiet = play("no_reaction", "squire", "scout")
    assert not events_of(quiet, EventType.REACTION_USED) and events_of(quiet, EventType.DICE_REROLLED)
    assert events_of(play("informed", "squire", "scout"), EventType.REACTION_USED)


def test_attacker_and_defender_disagree_on_the_same_roll():
    chosen = {}
    for persona in ("attacker", "defender"):
        engine = start("squire")
        begin_hero(engine, "h01", iron_d6=3, oath_d4=1)  # Guard and Jab; the Squire takes one action
        engine.combat.turn.rerolls_remaining = 0
        make_persona(persona, 0).act(engine)
        assert engine.combat.phase == CombatPhase.ACTION_PLAN
        chosen[persona] = [intent.name for intent in engine.combat.turn.plan]
    assert chosen == {"attacker": ["Jab"], "defender": ["Guard"]}


def test_the_gambler_keeps_only_a_die_showing_its_best_face():
    engine = start("squire")
    begin_hero(engine, "h01", iron_d6=1, oath_d4=1)  # Strike is not the Iron d6's best face by value; Jab is not the Oath d4's
    policy = make_persona("gambler", 0)
    hero = engine.combat.combatants["h01"]
    best = {
        die_id: max(range(len(faces)), key=lambda i, f=faces: policy._face_value(engine, hero, f[i]))
        for die_id in hero.equipped_dice_ids
        for faces in [engine.die_for("h01", die_id).faces]
    }
    policy.act(engine)
    turn = engine.combat.turn
    assert turn.rerolls_used == 1
    assert set(turn.kept) == {d for d in ("iron_d6", "oath_d4") if best[d] == 0}


def test_the_random_target_persona_only_ever_picks_legal_targets():
    engine = play("random_target", "squire", "apprentice", "scout")
    assert engine.state.outcome in ("victory", "defeat")  # an illegal target would have raised PolicyError
    assert len(enemies(engine)) >= 1


def test_the_bench_swapper_swaps_a_die_in_before_battle_2():
    for seed in range(1, 12):
        engine = play("bench_swapper", "squire", "apprentice", "scout", seed=seed)
        if engine.state.encounter_index == 1:
            swaps = events_of(engine, EventType.DIE_SWAPPED)
            assert swaps, "Battle 2 was reached without any bench die swapped in"
            assert {e.delta["out_die_id"] for e in swaps} <= {"oath_d4", "focus_d4", "tools_d4"}  # never the main die
            return
    pytest.fail("no seed reached Battle 2")


def test_the_playtest_tool_measures_a_run_from_its_event_log():
    spec = importlib.util.spec_from_file_location("playtest_scenarios", ROOT / "tools" / "playtest_scenarios.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    runs = [tool.play(None, "informed", [("squire", "front"), ("scout", "back")], seed) for seed in (1, 2)]
    summary = tool.summarise(runs)
    assert summary["runs"] == 2 and 0 <= summary["win_rate"] <= 100
    assert all(r["hero_activations"] > 0 and r["decisions"] >= r["hero_activations"] for r in runs)
    assert all(r["reactions"] <= r["reaction_windows"] for r in runs)
    assert set(tool.PARTIES) == {"solo squire", "solo apprentice", "solo scout", "trio", "four", "five"}
