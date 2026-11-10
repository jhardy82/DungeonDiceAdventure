"""Roll / keep / reroll, class scheduling, plan lock and action-speed order (AC-03, AC-04, AC-05, AC-07)."""

from __future__ import annotations

import pytest

from battle_dice import rng
from battle_dice.core import commands as cmd
from battle_dice.core import planning
from battle_dice.core.engine import run_until_input
from battle_dice.core.events import state_hash
from battle_dice.core.models import CombatPhase
from battle_dice.core.view import snapshot
from tests.conftest import (
    action,
    begin_hero,
    commit,
    content_with,
    events_of,
    finish_activation,
    last_event,
    make_ready,
    ok,
    rejected,
    reroll,
    resolve_hero,
    start,
    unit,
)

# --------------------------------------------------------------------------------------------
# Rolling (AC-03)
# --------------------------------------------------------------------------------------------


def test_fixed_seed_produces_the_pinned_dice_stream_in_die_id_order():
    seed = 77
    engine = start("scout", seed=seed)
    run_until_input(engine)  # Scout (speed 13) acts first
    assert engine.combat.phase == CombatPhase.HERO_ROLL
    ok(engine.do(cmd.ROLL_DICE))
    stream = rng.derive_stream(seed, "dice")
    expected = {"striker_d8": rng.bounded(stream, 8), "tools_d4": rng.bounded(stream, 4)}
    assert engine.combat.turn.rolled == expected
    rolled = events_of(engine, "dice_rolled")
    assert [e.delta["die_id"] for e in rolled] == ["striker_d8", "tools_d4"]
    assert all(e.rng_stream == "dice" for e in rolled)
    assert [e.rng_draw_index for e in rolled] == sorted(e.rng_draw_index for e in rolled)

    again = start("scout", seed=seed)
    run_until_input(again)
    ok(again.do(cmd.ROLL_DICE))
    assert again.combat.turn.rolled == expected


def test_snapshot_exposes_rolled_faces_and_full_distributions():
    engine = start("squire")
    begin_hero(engine, "h01", iron_d6=5, oath_d4=4)
    turn = snapshot(engine)["hero_turn"]
    assert [(d["die_id"], d["face"]["name"]) for d in turn["dice"]] == [("iron_d6", "Rally"), ("oath_d4", "Resolve")]
    assert [len(d["die"]["faces"]) for d in turn["dice"]] == [6, 4]
    assert turn["rerolls_remaining"] == 2 and turn["rerolls_total"] == 2


# --------------------------------------------------------------------------------------------
# Keep / reroll (AC-04)
# --------------------------------------------------------------------------------------------


def test_reroll_changes_only_unkept_dice_and_spends_exactly_one():
    engine = start("squire")
    begin_hero(engine, "h01", iron_d6=1, oath_d4=1)
    ok(engine.do(cmd.SET_KEPT_DICE, die_ids=["iron_d6"]))
    draws_before = engine.state.rng["dice"].draws
    ok(engine.do(cmd.REROLL_UNKEPT))  # real PCG draw for the single unkept d4
    turn = engine.combat.turn
    assert turn.rolled["iron_d6"] == 0  # kept die untouched
    assert turn.rerolls_remaining == 1 and turn.rerolls_used == 1
    assert engine.state.rng["dice"].draws == draws_before + 1  # a d4 never needs a rejection redraw
    rerolled = events_of(engine, "dice_rerolled")
    assert [e.delta["die_id"] for e in rerolled] == ["oath_d4"]
    assert rerolled[0].delta["rerolls_remaining"] == 1


def test_reroll_rerolls_all_unkept_dice_and_can_repeat_on_the_same_die():
    engine = start("squire")
    begin_hero(engine, "h01", iron_d6=6, oath_d4=1)
    ok(reroll(engine, iron_d6=3, oath_d4=2))
    assert engine.combat.turn.rolled == {"iron_d6": 2, "oath_d4": 1}
    ok(engine.do(cmd.SET_KEPT_DICE, die_ids=["oath_d4"]))
    ok(reroll(engine, iron_d6=5))
    assert engine.combat.turn.rolled == {"iron_d6": 4, "oath_d4": 1}
    assert engine.combat.turn.rerolls_remaining == 0


def test_a_kept_die_can_be_unkept_before_a_later_reroll():
    engine = start("squire")
    begin_hero(engine, "h01", iron_d6=1, oath_d4=1)
    ok(engine.do(cmd.SET_KEPT_DICE, die_ids=["iron_d6", "oath_d4"]))
    ok(engine.do(cmd.SET_KEPT_DICE, die_ids=[]))
    ok(reroll(engine, iron_d6=2, oath_d4=3))
    assert engine.combat.turn.rolled == {"iron_d6": 1, "oath_d4": 2}


def test_no_reroll_is_applied_when_none_remain():
    engine = start("squire")
    begin_hero(engine, "h01", iron_d6=1, oath_d4=1)
    ok(reroll(engine, iron_d6=1, oath_d4=1))
    ok(reroll(engine, iron_d6=1, oath_d4=1))
    before = (state_hash(engine.state), len(engine.events))
    rejected(engine.do(cmd.REROLL_UNKEPT), "no rerolls remaining")
    assert (state_hash(engine.state), len(engine.events)) == before


def test_no_reroll_is_spent_when_every_die_is_kept():
    engine = start("squire")
    begin_hero(engine, "h01", iron_d6=1, oath_d4=1)
    ok(engine.do(cmd.SET_KEPT_DICE, die_ids=["iron_d6", "oath_d4"]))
    rejected(engine.do(cmd.REROLL_UNKEPT), "nothing to reroll")
    assert engine.combat.turn.rerolls_remaining == 2


def test_keep_rejects_unknown_or_duplicate_dice():
    engine = start("squire")
    begin_hero(engine, "h01", iron_d6=1, oath_d4=1)
    rejected(engine.do(cmd.SET_KEPT_DICE, die_ids=["focus_d4"]), "not rolled")
    rejected(engine.do(cmd.SET_KEPT_DICE, die_ids=["iron_d6", "iron_d6"]), "only once")


def test_rerolls_reset_each_activation_and_do_not_carry_over():
    engine = start("squire")
    begin_hero(engine, "h01", iron_d6=6, oath_d4=1)
    ok(reroll(engine, iron_d6=6, oath_d4=1))
    resolve_hero(engine)  # pass with one reroll unused
    begin_hero(engine, "h01", iron_d6=1, oath_d4=1)
    assert engine.combat.turn.rerolls_remaining == 2
    assert engine.combat.turn.kept == []


# --------------------------------------------------------------------------------------------
# Class scheduling (AC-05)
# --------------------------------------------------------------------------------------------


def test_squire_single_commitment_allows_one_action_and_discards_the_rest():
    engine = start("squire")
    begin_hero(engine, "h01", iron_d6=1, oath_d4=1)
    rejected(
        engine.do(cmd.SET_ACTION_PLAN, actions=[action("iron_d6", "b1_e01"), action("oath_d4", "b1_e01")]),
        "at most 1 action",
    )
    commit(engine, action("iron_d6", "b1_e01"))
    assert last_event(engine, "plan_committed").delta["discarded_dice"] == ["oath_d4"]
    finish_activation(engine)
    assert unit(engine, "b1_e01").hp == 4  # exactly one Strike resolved
    begin_hero(engine, "h01", iron_d6=6, oath_d4=1)
    assert set(engine.combat.turn.rolled) == {"iron_d6", "oath_d4"}  # nothing carried over


def test_apprentice_channel_and_cast_requires_resource_then_other():
    engine = start("apprentice")
    begin_hero(engine, "h01", arcane_d6=1, focus_d4=1)  # Arcane Bolt + Channel
    ok(engine.do(cmd.SET_ACTION_PLAN, actions=[action("arcane_d6", "b1_e01"), action("focus_d4")]))
    assert [a.name for a in engine.combat.turn.plan] == ["Channel", "Arcane Bolt"]  # dependency beats list order

    begin_other = start("apprentice")
    begin_hero(begin_other, "h01", arcane_d6=1, focus_d4=3)  # Arcane Bolt + Ward (no Resource)
    rejected(
        begin_other.do(cmd.SET_ACTION_PLAN, actions=[action("arcane_d6", "b1_e01"), action("focus_d4", "h01")]),
        "only allowed as resource first",
    )
    ok(begin_other.do(cmd.SET_ACTION_PLAN, actions=[action("focus_d4", "h01")]))

    double_resource = start("apprentice")
    begin_hero(double_resource, "h01", arcane_d6=5, focus_d4=1)  # Cleanse + Channel
    rejected(
        double_resource.do(cmd.SET_ACTION_PLAN, actions=[action("arcane_d6"), action("focus_d4")]),
        "only allowed as resource first",
    )


def test_scout_exploit_combo_requires_status_then_attack():
    engine = start("scout")
    begin_hero(engine, "h01", striker_d8=4, tools_d4=1)  # Poison + Quick Shot
    ok(engine.do(cmd.SET_ACTION_PLAN, actions=[action("tools_d4", "b1_e01"), action("striker_d8", "b1_e01")]))
    assert [a.category for a in engine.combat.turn.plan] == ["status", "attack"]

    two_attacks = start("scout")
    begin_hero(two_attacks, "h01", striker_d8=1, tools_d4=1)
    rejected(
        two_attacks.do(cmd.SET_ACTION_PLAN, actions=[action("striker_d8", "b1_e01"), action("tools_d4", "b1_e01")]),
        "only allowed as status first, then attack",
    )

    status_defense = start("scout")
    begin_hero(status_defense, "h01", striker_d8=4, tools_d4=3)
    rejected(
        status_defense.do(cmd.SET_ACTION_PLAN, actions=[action("striker_d8", "b1_e01"), action("tools_d4", "h01")]),
        "only allowed as status first, then attack",
    )


def test_plan_validation_rejects_illegal_dice_and_targets():
    engine = start("squire", "scout")  # enemies: goblin (front) b1_e01, hex adept (back) b1_e02
    begin_hero(engine, "h01", iron_d6=6, oath_d4=1)
    rejected(engine.do(cmd.SET_ACTION_PLAN, actions=[action("iron_d6")]), "non-action")
    rejected(engine.do(cmd.SET_ACTION_PLAN, actions=[action("focus_d4", "h01")]), "has not been rolled")
    rejected(engine.do(cmd.SET_ACTION_PLAN, actions=[action("oath_d4")]), "exactly one target")
    rejected(engine.do(cmd.SET_ACTION_PLAN, actions=[action("oath_d4", "b1_e01", "b1_e02")]), "exactly one target")
    rejected(engine.do(cmd.SET_ACTION_PLAN, actions=[action("oath_d4", "b1_e02")]), "protected")
    rejected(engine.do(cmd.SET_ACTION_PLAN, actions=[action("oath_d4", "h02")]), "not a legal target")
    rejected(engine.do(cmd.SET_ACTION_PLAN, actions=[action("oath_d4", "nobody")]), "unknown target")
    rejected(
        engine.do(cmd.SET_ACTION_PLAN, actions=[action("oath_d4", "b1_e01"), action("oath_d4", "b1_e01")]),
        "already supplies another action",
    )
    assert engine.combat.phase == CombatPhase.KEEP_REROLL  # nothing was accepted


def test_mana_is_projected_in_resolution_order():
    engine = start("apprentice")
    unit(engine, "h01").mana = 0
    begin_hero(engine, "h01", arcane_d6=1, focus_d4=1)
    rejected(engine.do(cmd.SET_ACTION_PLAN, actions=[action("arcane_d6", "b1_e01")]), "needs 1 mana but only 0")
    ok(engine.do(cmd.SET_ACTION_PLAN, actions=[action("arcane_d6", "b1_e01"), action("focus_d4")]))

    mend = start("apprentice")
    unit(mend, "h01").mana = 1
    begin_hero(mend, "h01", arcane_d6=3, focus_d4=3)  # Mend costs 2, no channel available
    rejected(mend.do(cmd.SET_ACTION_PLAN, actions=[action("arcane_d6", "h01")]), "needs 2 mana")
    options = {d["die_id"]: d for d in snapshot(mend)["hero_turn"]["dice"]}
    assert options["arcane_d6"]["usable_alone"] is False and "Needs 2 mana" in options["arcane_d6"]["reason"]


def test_plan_is_editable_until_confirmed_then_locked():
    engine = start("squire")
    begin_hero(engine, "h01", iron_d6=1, oath_d4=1)
    ok(engine.do(cmd.SET_ACTION_PLAN, actions=[action("iron_d6", "b1_e01")]))
    ok(engine.do(cmd.SET_ACTION_PLAN, actions=[action("oath_d4", "b1_e01")]))  # edit before confirming
    rejected(engine.do(cmd.REROLL_UNKEPT), "not allowed during")  # planning ends rerolling
    ok(engine.do(cmd.COMMIT_ACTION_PLAN))
    committed = last_event(engine, "plan_committed").delta
    assert [a["die_id"] for a in committed["actions"]] == ["oath_d4"]
    assert committed["actions"][0]["committed_target_ids"] == ["b1_e01"]
    rejected(engine.do(cmd.SET_ACTION_PLAN, actions=[action("iron_d6", "b1_e01")]), "not allowed during")
    rejected(engine.do(cmd.COMMIT_ACTION_PLAN), "not allowed during")
    finish_activation(engine)
    assert unit(engine, "b1_e01").hp == 5  # the Jab, not the Strike


def test_explicit_pass_and_no_legal_action():
    engine = start("apprentice")
    begin_hero(engine, "h01", arcane_d6=6, focus_d4=4)  # two Blanks
    turn = snapshot(engine)["hero_turn"]
    assert turn["has_legal_action"] is False
    assert [d["reason"] for d in turn["dice"]] == ["Blank: no action.", "Blank: no action."]
    resolve_hero(engine)
    assert last_event(engine, "hero_passed").actor_id == "h01"
    assert unit(engine, "b1_e01").hp == 6

    passing = start("squire")
    begin_hero(passing, "h01", iron_d6=1, oath_d4=1)  # legal actions exist, player passes anyway
    assert snapshot(passing)["hero_turn"]["has_legal_action"] is True
    resolve_hero(passing)
    assert last_event(passing, "hero_passed").actor_id == "h01"


# --------------------------------------------------------------------------------------------
# Action speed (AC-07)
# --------------------------------------------------------------------------------------------


def _free_content():
    def mutate(documents):
        documents["classes"]["classes"]["squire"]["scheduling"] = {
            "policy": "free", "label": "Free Actions", "max_actions": 2, "summary": "Test-only policy.",
        }

    return content_with(mutate)


def test_higher_action_speed_resolves_first_without_a_class_dependency():
    engine = start("squire", content=_free_content())
    begin_hero(engine, "h01", iron_d6=1, oath_d4=2)  # Strike (AS 1) + Brace (AS 2)
    ok(engine.do(cmd.SET_ACTION_PLAN, actions=[action("iron_d6", "b1_e01"), action("oath_d4", "h01")]))
    assert [(a.name, a.action_speed) for a in engine.combat.turn.plan] == [("Brace", 2), ("Strike", 1)]


@pytest.mark.parametrize("order", [("iron_d6", "oath_d4"), ("oath_d4", "iron_d6")])
def test_equal_action_speed_uses_the_players_tie_order(order):
    engine = start("squire", content=_free_content())
    begin_hero(engine, "h01", iron_d6=1, oath_d4=1)  # Strike (AS 1) + Jab (AS 1)
    resolve_hero(engine, *[action(die, "b1_e01") for die in order])
    resolved = [e.delta["name"] for e in events_of(engine, "action_resolved")]
    assert resolved == (["Strike", "Jab"] if order[0] == "iron_d6" else ["Jab", "Strike"])


def test_action_speed_does_not_touch_the_global_gauge():
    gauges = []
    for faces in ({"iron_d6": 3, "oath_d4": 4}, {"iron_d6": 1, "oath_d4": 1}):  # speeds (2, 3) versus (1, 1)
        engine = start("squire", content=_free_content())
        begin_hero(engine, "h01", **faces)
        plan = [action("iron_d6", "h01" if faces["iron_d6"] == 3 else "b1_e01")]
        plan.append(action("oath_d4") if faces["oath_d4"] == 4 else action("oath_d4", "b1_e01"))
        resolve_hero(engine, *plan)
        gauges.append({c.id: c.gauge for c in engine.combat.sorted_combatants()})
    assert gauges[0] == gauges[1] == {"b1_e01": 0, "h01": 0}


def test_order_actions_unit(content):
    iron, oath = content.die("iron_d6"), content.die("oath_d4")
    free = {"policy": "free", "label": "Free", "max_actions": 3, "summary": ""}
    strike, guard, resolve_face = iron.faces[0], iron.faces[2], oath.faces[3]
    assert planning.order_actions([(strike, 0), (guard, 1), (resolve_face, 2)], free) == [2, 1, 0]
    assert planning.order_actions([(strike, 1), (oath.faces[0], 0)], free) == [1, 0]
    scout = content.class_def("scout")["scheduling"]
    striker = content.die("striker_d8")
    # Status (AS 2) then Attack (AS 1) is class-defined; it holds even if speeds were reversed.
    assert planning.order_actions([(striker.faces[0], 0), (striker.faces[3], 1)], scout) == [1, 0]


def test_unselected_results_never_carry_to_a_later_activation():
    engine = start("scout")
    begin_hero(engine, "h01", striker_d8=4, tools_d4=1)
    resolve_hero(engine, action("striker_d8", "b1_e01"))
    assert engine.combat.turn is None
    make_ready(engine, "h01")
    run_until_input(engine)
    assert engine.combat.turn is not None
    assert engine.combat.turn.rolled == {} and engine.combat.phase == CombatPhase.HERO_ROLL
