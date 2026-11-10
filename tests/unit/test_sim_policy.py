"""The scripted "informed player" used for balance measurement and smoke runs (``sim/policies.py``).

Rolls are forced, so each decision is checked on a position whose right answer does not depend on
how the score weights are tuned: one option is strictly better than every other.
"""

from __future__ import annotations

from typing import Any

import pytest

from battle_dice.core import commands as cmd
from battle_dice.core import progression
from battle_dice.core.engine import Engine
from battle_dice.core.events import EventType, events_hash, state_hash
from battle_dice.core.models import CombatPhase, RunPhase
from battle_dice.sim.policies import POLICY_VERSION, HeuristicPolicy, play_run
from tests.conftest import (
    add_status,
    begin_enemy,
    begin_hero,
    enemies,
    events_of,
    force_slash,
    packaged_content,
    start,
    unit,
)


def variant(**switches: bool | float) -> HeuristicPolicy:
    """The player with some of its parts switched off."""
    return type("Variant", (HeuristicPolicy,), switches)()


def version_1() -> HeuristicPolicy:
    return variant(lookahead=False, real_amounts=False, value_upgrades=False, shield_weight=1.0)


def settle(engine: Engine, hero_id: str) -> None:
    """Arrange: full shields and mana, so Guard, Brace and Resolve are worth nothing to this hero."""
    hero = unit(engine, hero_id)
    hero.shields = engine.content.balance["shield"]["cap"]
    hero.mana = hero.max_mana


def planned(engine: Engine) -> list[tuple[str, list[str]]]:
    turn = engine.combat.turn
    assert turn is not None
    return [(intent.name, intent.committed_target_ids) for intent in turn.plan]


# --------------------------------------------------------------------------------------------
# Keep or reroll
# --------------------------------------------------------------------------------------------


def test_a_usable_face_is_kept_when_no_reroll_can_beat_it():
    """The version 1 player threw this roll away: a weakened Strike scored under its keep threshold."""
    engine = start("squire")
    settle(engine, "h01")
    add_status(engine, "h01", "weaken")
    begin_hero(engine, "h01", iron_d6=1, oath_d4=4)  # Strike (1 damage while weakened) and Resolve (mana is full)
    HeuristicPolicy().act(engine)
    assert engine.combat.phase == CombatPhase.ACTION_PLAN
    assert engine.combat.turn.rerolls_used == 0
    assert planned(engine) == [("Strike", [enemies(engine)[0].id])]

    old = start("squire")
    settle(old, "h01")
    add_status(old, "h01", "weaken")
    begin_hero(old, "h01", iron_d6=1, oath_d4=4)
    version_1().act(old)
    assert old.combat.turn.rerolls_used == 1 and old.combat.turn.kept == []


def test_the_useful_die_is_kept_and_only_the_other_is_rerolled():
    engine = start("squire")
    settle(engine, "h01")
    begin_hero(engine, "h01", iron_d6=6, oath_d4=1)  # Blank and Jab
    policy = HeuristicPolicy()
    engine.force_draws("dice", [0])  # the reroll of the Iron d6 comes up Strike
    policy.act(engine)
    turn = engine.combat.turn
    assert turn.kept == ["oath_d4"] and turn.rerolls_used == 1
    assert turn.rolled == {"iron_d6": 0, "oath_d4": 0}
    policy.act(engine)  # Strike beats Jab and nothing on the Oath d4 can beat Strike: stop here
    assert engine.combat.phase == CombatPhase.ACTION_PLAN and engine.combat.turn.rerolls_used == 1
    assert planned(engine) == [("Strike", [enemies(engine)[0].id])]


def test_a_roll_with_nothing_useful_is_rerolled_and_passed_only_when_rerolls_run_out():
    engine = start("squire")
    settle(engine, "h01")
    begin_hero(engine, "h01", iron_d6=6, oath_d4=4)  # Blank and Resolve at full mana
    policy = HeuristicPolicy()
    engine.force_draws("dice", [5, 3])
    policy.act(engine)
    assert engine.combat.turn.rerolls_used == 1 and engine.combat.turn.kept == []
    engine.force_draws("dice", [5, 3])
    policy.act(engine)
    assert engine.combat.turn.rerolls_remaining == 0
    policy.act(engine)
    assert engine.combat.phase == CombatPhase.ACTION_PLAN and planned(engine) == []


def test_a_finishing_blow_is_taken_at_once():
    engine = start("squire")
    foe = enemies(engine)[0]
    foe.hp = 1
    begin_hero(engine, "h01", iron_d6=6, oath_d4=1)  # Blank and Jab: the Jab ends the battle
    HeuristicPolicy().act(engine)
    assert engine.combat.turn.rerolls_used == 0 and planned(engine) == [("Jab", [foe.id])]


@pytest.mark.parametrize("party", [("squire",), ("apprentice",), ("scout",), ("squire", "apprentice", "scout")])
def test_looking_ahead_changes_nothing_in_the_engine(party):
    """Scoring rolls that have not happened must not touch state, events or any random stream."""
    engine = start(*party, seed=7, content=packaged_content())
    policy = HeuristicPolicy()
    while engine.combat.phase != CombatPhase.KEEP_REROLL:
        if engine.needs_input():
            policy.act(engine)
        else:
            assert engine.do(cmd.ADVANCE_PHASE).accepted
    hero, turn = engine._active_hero()
    before = (state_hash(engine.state), events_hash(engine.events), len(engine.command_log), engine.revision)
    keep, plan = policy._choose_keep(engine, hero, turn)
    assert (state_hash(engine.state), events_hash(engine.events), len(engine.command_log), engine.revision) == before
    assert set(keep) <= set(turn.rolled) and all(a["die_id"] in turn.rolled for a in plan)


def test_the_player_is_deterministic():
    def run() -> tuple[str, str, int]:
        engine = start("squire", "apprentice", "scout", seed=11, content=packaged_content())
        outcome = play_run(engine, HeuristicPolicy())
        return outcome, events_hash(engine.events), len(engine.command_log)

    assert run() == run()
    assert HeuristicPolicy.version == POLICY_VERSION == 2


# --------------------------------------------------------------------------------------------
# Scoring uses the engine's amounts
# --------------------------------------------------------------------------------------------


def best_score(policy: HeuristicPolicy, engine: Engine) -> float:
    hero, turn = engine._active_hero()
    return policy._best_plan(engine, hero, turn)[1]


def test_guard_is_valued_with_the_steadfast_bonus_and_other_classes_get_none():
    squire = start("squire")
    unit(squire, "h01").mana = unit(squire, "h01").max_mana
    begin_hero(squire, "h01", iron_d6=3, oath_d4=4)  # Guard 3; Resolve is worth nothing at full mana
    bonus = squire.content.class_def("squire")["passive"]["amount"]
    with_bonus, without = best_score(HeuristicPolicy(), squire), best_score(variant(real_amounts=False), squire)
    assert with_bonus == pytest.approx(without * (3 + bonus) / 3) and with_bonus > without

    apprentice = start("apprentice")
    unit(apprentice, "h01").mana = unit(apprentice, "h01").max_mana
    begin_hero(apprentice, "h01", arcane_d6=6, focus_d4=3)  # Blank and Ward
    assert best_score(HeuristicPolicy(), apprentice) == pytest.approx(best_score(variant(real_amounts=False), apprentice))


def test_the_scout_combo_bonus_is_counted_for_status_then_attack():
    engine = start("scout")
    begin_hero(engine, "h01", striker_d8=4, tools_d4=1)  # Poison, then Quick Shot
    bonus = engine.content.class_def("scout")["passive"]["amount"]
    assert best_score(HeuristicPolicy(), engine) == pytest.approx(best_score(variant(real_amounts=False), engine) + bonus)


def test_two_attacks_are_not_both_credited_with_the_same_kill():
    """Apprentice: Channel then Arcane Bolt is legal; the plan's value counts one kill, once."""
    engine = start("scout", "scout")
    first, second = enemies(engine)[0], enemies(engine)[1]
    first.hp, second.hp = 1, 9
    add_status(engine, "h01", "weaken")  # Quick Shot now deals 0 before the combo bonus
    begin_hero(engine, "h01", striker_d8=4, tools_d4=1)  # Poison, then Quick Shot (1 with the combo bonus)
    policy = HeuristicPolicy()
    hero, turn = engine._active_hero()
    plan, _ = policy._best_plan(engine, hero, turn)
    by_die = {a["die_id"]: a["target_ids"] for a in plan}
    assert by_die["tools_d4"] == [first.id]  # the shot finishes the 1 HP enemy
    assert by_die["striker_d8"] == [second.id]  # so the poison goes to the one that will still be standing


# --------------------------------------------------------------------------------------------
# Reactions (the version 1 rule, kept: see decision log 7.6)
# --------------------------------------------------------------------------------------------


def test_an_eligible_reaction_is_always_taken_on_the_most_pressed_target():
    engine = start("squire", "apprentice")
    unit(engine, "h02").mana = unit(engine, "h02").max_mana  # Grounding has nothing to change
    force_slash(engine)
    goblin = next(e for e in enemies(engine) if e.archetype_id == "goblin")
    begin_enemy(engine, goblin.id)
    policy = HeuristicPolicy()
    while engine.combat.phase in CombatPhase.STAGE_BY_WINDOW:
        policy.act(engine)
    used = [(e.delta["reaction"], e.delta["target_ids"]) for e in events_of(engine, EventType.REACTION_USED)]
    assert used == [("interpose", ["h01"])]


# --------------------------------------------------------------------------------------------
# Upgrades
# --------------------------------------------------------------------------------------------


def test_the_upgrade_that_adds_the_most_is_chosen_whatever_its_kind():
    engine = start("squire", content=packaged_content())
    policy = HeuristicPolicy()
    while engine.state.phase != RunPhase.UPGRADE:
        assert not engine.finished(), "the seeded run should reach the upgrade screen"
        if engine.needs_input():
            policy.act(engine)
        else:
            assert engine.do(cmd.ADVANCE_PHASE).accepted
    hero = unit(engine, "h01")
    offers = [o for dice in engine.state.upgrade_offers["h01"].values() for o in dice]

    def gain(offer: dict[str, Any]) -> float:
        size = engine.die_for("h01", offer["die_id"]).size
        before = policy._face_value(engine, hero, progression.face_from_plain(offer["before"]))
        after = policy._face_value(engine, hero, progression.face_from_plain(offer["after"]))
        return (after - before) / size

    best = max(offers, key=lambda o: (gain(o), o["offer_id"]))
    assert gain(best) > 0
    policy.act(engine)
    chosen = events_of(engine, EventType.UPGRADE_APPLIED)[-1].delta["offer_id"]
    assert gain(next(o for o in offers if o["offer_id"] == chosen)) == pytest.approx(gain(best))
