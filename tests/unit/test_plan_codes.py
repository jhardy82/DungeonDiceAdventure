"""A refused action plan carries a machine-readable code beside its text.

Owner decision of 2026-11-11 (fixtures CE-29 and CE-30): the rules engine keeps the sentence it
shows the player and adds a code from ``docs/class_evolution/persistence/error_codes.json``.
The two fixtures name Champion dice, which the engine cannot build before wave 4, so this module
checks every code, and the two fixtures' situations, on the content that exists today.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from battle_dice.core import commands as cmd
from battle_dice.core import planning
from battle_dice.core.engine import Engine, run_until_input
from battle_dice.core.events import state_hash
from battle_dice.core.models import STATE_DOWNED
from battle_dice.core.targeting import protected_targets
from tests.conftest import action, begin_hero, down, enemies, make_ready, ok, packaged_content, start, unit

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = json.loads((ROOT / "docs" / "class_evolution" / "persistence" / "error_codes.json").read_text(encoding="utf-8"))

Plan = list[dict[str, Any]]


def squire_with(**faces: int) -> Engine:
    engine = start("squire")
    begin_hero(engine, "h01", **faces)
    return engine


def not_rolled() -> tuple[Engine, Plan]:
    engine = squire_with(iron_d6=1, oath_d4=1)
    return engine, [action("bulwark_d4", enemies(engine)[0].id)]  # the bench die: owned, not rolled


def used_twice() -> tuple[Engine, Plan]:
    engine = start("scout")
    begin_hero(engine, "h01", striker_d8=1, tools_d4=1)
    foe = enemies(engine)[0].id
    return engine, [action("striker_d8", foe), action("striker_d8", foe)]


def a_blank() -> tuple[Engine, Plan]:
    engine = squire_with(iron_d6=6, oath_d4=1)
    return engine, [action("iron_d6")]


def nothing_to_target() -> tuple[Engine, Plan]:
    engine = squire_with(iron_d6=1, oath_d4=1)
    foe = enemies(engine)[0]
    for enemy in enemies(engine):  # arranged: the battle would already be over
        enemy.hp, enemy.state = 0, STATE_DOWNED
    return engine, [action("iron_d6", foe.id)]


def two_targets() -> tuple[Engine, Plan]:
    engine = start("squire", "scout")
    begin_hero(engine, "h01", iron_d6=1, oath_d4=1)
    foes = [enemy.id for enemy in enemies(engine)]
    assert len(foes) >= 2
    return engine, [action("iron_d6", *foes[:2])]


def unknown_target() -> tuple[Engine, Plan]:
    engine = squire_with(iron_d6=1, oath_d4=1)
    return engine, [action("iron_d6", "nobody")]


def behind_the_front_row() -> tuple[Engine, Plan]:
    engine = start("squire", "scout")
    begin_hero(engine, "h01", iron_d6=1, oath_d4=1)
    strike = engine.die_for("h01", "iron_d6").faces[0]
    protected = protected_targets(engine.combat, unit(engine, "h01"), strike)
    assert protected, "this encounter must have a back row behind a standing front row"
    return engine, [action("iron_d6", protected[0])]


def guard_on_a_downed_ally() -> tuple[Engine, Plan]:
    engine = start("squire", "scout")
    begin_hero(engine, "h01", iron_d6=3, oath_d4=1)  # Guard: a defense face
    down(engine, "h02")
    return engine, [action("iron_d6", "h02")]


def strike_at_an_ally() -> tuple[Engine, Plan]:
    engine = start("squire", "scout")
    begin_hero(engine, "h01", iron_d6=1, oath_d4=1)
    return engine, [action("iron_d6", "h02")]


def two_actions_for_a_squire() -> tuple[Engine, Plan]:
    engine = squire_with(iron_d6=1, oath_d4=1)
    foe = enemies(engine)[0].id
    return engine, [action("iron_d6", foe), action("oath_d4", foe)]


def a_bolt_without_mana() -> tuple[Engine, Plan]:
    engine = start("apprentice")
    begin_hero(engine, "h01", arcane_d6=1, focus_d4=4)
    unit(engine, "h01").mana = 0
    return engine, [action("arcane_d6", enemies(engine)[0].id)]


SCENARIOS: dict[str, Callable[[], tuple[Engine, Plan]]] = {
    "DIE_NOT_ROLLED": not_rolled,
    "DIE_ALREADY_USED": used_twice,
    "FACE_NOT_AN_ACTION": a_blank,
    "NO_LEGAL_TARGET": nothing_to_target,
    "WRONG_TARGET_COUNT": two_targets,
    "TARGET_UNKNOWN": unknown_target,
    "TARGET_PROTECTED": behind_the_front_row,
    "TARGET_DOWNED": guard_on_a_downed_ally,
    "TARGET_NOT_LEGAL": strike_at_an_ally,
    "SCHEDULE_VIOLATION": two_actions_for_a_squire,
    "INSUFFICIENT_MANA": a_bolt_without_mana,
}


def refuse(engine: Engine, plan: Plan, code: str) -> Any:
    """Send the plan; it must be refused with ``code`` and its text, and nothing may change."""
    state, revision, events = state_hash(engine.state), engine.revision, len(engine.events)
    draws = {name: stream.draws for name, stream in engine.state.rng.items()}
    assert engine.check_plan(plan)[1:] != (None, None)  # the preview refuses it too
    preview_code = engine.check_plan(plan)[2]
    result = engine.do(cmd.SET_ACTION_PLAN, actions=plan)
    assert not result.accepted and result.code == code == preview_code, (result.code, result.reason)
    assert result.reason and result.reason == engine.check_plan(plan)[1]
    assert (state_hash(engine.state), engine.revision, len(engine.events)) == (state, revision, events)
    assert {name: stream.draws for name, stream in engine.state.rng.items()} == draws  # no random draw
    return result


def test_the_engine_and_the_registry_name_the_same_codes_in_the_same_order():
    in_registry = [entry["code"] for entry in REGISTRY["codes"] if entry["kind"] == "plan_rejection"]
    assert tuple(in_registry) == planning.PLAN_CODES == tuple(REGISTRY["plan_check_order"]["order"])
    assert set(SCENARIOS) == set(planning.PLAN_CODES), "every code needs a plan that raises it"
    for entry in REGISTRY["codes"]:
        if entry["kind"] == "plan_rejection":
            assert entry["raised_by"] == [cmd.SET_ACTION_PLAN, cmd.COMMIT_ACTION_PLAN]


@pytest.mark.parametrize("code", planning.PLAN_CODES)
def test_each_refusal_returns_its_code_and_changes_nothing(code: str):
    engine, plan = SCENARIOS[code]()
    refuse(engine, plan, code)


def test_a_plan_error_cannot_be_raised_with_an_unlisted_code():
    with pytest.raises(AssertionError):
        planning.PlanError("text", "NOT_A_CODE")


def test_a_self_targeted_face_refuses_another_target_as_a_wrong_count():
    engine = start("squire", "scout")
    begin_hero(engine, "h01", iron_d6=1, oath_d4=4)  # Resolve targets its user
    refuse(engine, [action("oath_d4", "h02")], "WRONG_TARGET_COUNT")
    refuse(engine, [action("iron_d6")], "WRONG_TARGET_COUNT")  # a single-target face with no target


def test_a_downed_enemy_is_refused_as_downed():
    engine = start("squire", "scout")
    begin_hero(engine, "h01", iron_d6=1, oath_d4=1)
    front = next(e for e in enemies(engine) if e.id not in protected_targets(
        engine.combat, unit(engine, "h01"), engine.die_for("h01", "iron_d6").faces[0]))
    front.hp, front.state = 0, STATE_DOWNED
    refuse(engine, [action("iron_d6", front.id)], "TARGET_DOWNED")


# --------------------------------------------------------------------------------------------
# The order of the checks
# --------------------------------------------------------------------------------------------


def test_the_first_failing_check_is_the_one_reported():
    # A target problem is found before the mana projection is made.
    engine, _ = a_bolt_without_mana()
    refuse(engine, [action("arcane_d6", "nobody")], "TARGET_UNKNOWN")
    # A die problem is found before the schedule is checked.
    engine = squire_with(iron_d6=1, oath_d4=1)
    foe = enemies(engine)[0].id
    refuse(engine, [action("iron_d6", foe), action("bulwark_d4", foe)], "DIE_NOT_ROLLED")
    # The schedule is checked before the mana projection.
    engine = start("apprentice")
    begin_hero(engine, "h01", arcane_d6=1, focus_d4=3)  # Arcane Bolt, then Ward: not Resource then cast
    unit(engine, "h01").mana = 0
    refuse(engine, [action("arcane_d6", enemies(engine)[0].id), action("focus_d4", "h01")], "SCHEDULE_VIOLATION")
    # Within one action: the die, then the face, then the target.
    engine = squire_with(iron_d6=6, oath_d4=1)
    refuse(engine, [action("iron_d6", "nobody")], "FACE_NOT_AN_ACTION")


# --------------------------------------------------------------------------------------------
# The situations of fixtures CE-29 and CE-30, on content that exists today
# --------------------------------------------------------------------------------------------


def test_ce30_a_heal_without_the_revival_tag_is_refused_on_a_downed_ally():
    engine = start("squire", "scout")
    unit(engine, "h01").equipped_dice_ids = ["bulwark_d4", "iron_d6"]  # arrange: the non-reviving Tend face
    begin_hero(engine, "h01", bulwark_d4=3, iron_d6=5)  # Tend and Rally
    down(engine, "h02")
    tend = engine.die_for("h01", "bulwark_d4").faces[2]
    assert tend.category == "healing" and "revival" not in tend.tags
    result = refuse(engine, [action("bulwark_d4", "h02")], "TARGET_DOWNED")
    assert "revival-capable" in result.reason
    assert unit(engine, "h02").state == STATE_DOWNED and unit(engine, "h02").hp == 0
    # The invariant of the case: a face with the revival tag may still target the downed hero.
    ok(engine.do(cmd.SET_ACTION_PLAN, actions=[action("iron_d6", "h02")]))


def test_ce30_mend_may_target_a_downed_hero_when_its_mana_is_there():
    engine = start("apprentice", "scout")
    begin_hero(engine, "h01", arcane_d6=3, focus_d4=4)  # Mend: revival tag, 2 mana
    down(engine, "h02")
    assert unit(engine, "h01").mana >= 2
    ok(engine.do(cmd.SET_ACTION_PLAN, actions=[action("arcane_d6", "h02")]))


def test_ce29_a_legal_target_and_too_little_mana_is_refused_for_the_mana():
    """The target check passes (Mend may revive), so the mana check is the one that fails."""
    engine = start("apprentice", "scout")
    begin_hero(engine, "h01", arcane_d6=3, focus_d4=4)
    down(engine, "h02")
    unit(engine, "h01").mana = 0
    result = refuse(engine, [action("arcane_d6", "h02")], "INSUFFICIENT_MANA")
    assert "needs 2 mana but only 0" in result.reason
    hero, ally = unit(engine, "h01"), unit(engine, "h02")
    assert hero.mana == 0  # mana never goes below zero
    assert ally.state == STATE_DOWNED and ally.hp == 0  # the downed hero is not revived


def test_gaining_mana_first_makes_the_same_cast_legal():
    engine = start("apprentice")
    begin_hero(engine, "h01", arcane_d6=1, focus_d4=1)  # Arcane Bolt and Channel
    unit(engine, "h01").mana = 0
    foe = enemies(engine)[0].id
    refuse(engine, [action("arcane_d6", foe)], "INSUFFICIENT_MANA")
    ok(engine.do(cmd.SET_ACTION_PLAN, actions=[action("focus_d4"), action("arcane_d6", foe)]))


# --------------------------------------------------------------------------------------------
# Commit, other refusals, and the shipped content
# --------------------------------------------------------------------------------------------


def test_commit_checks_the_plan_again_and_returns_the_same_codes():
    engine = start("apprentice")
    begin_hero(engine, "h01", arcane_d6=1, focus_d4=4)
    plan = [action("arcane_d6", enemies(engine)[0].id)]
    ok(engine.do(cmd.SET_ACTION_PLAN, actions=plan))
    unit(engine, "h01").mana = 0  # arranged: the state changed between setting and committing
    result = engine.do(cmd.COMMIT_ACTION_PLAN)
    assert not result.accepted and result.code == "INSUFFICIENT_MANA"


def test_a_legal_plan_and_a_refusal_that_is_not_about_a_plan_carry_no_code():
    engine = squire_with(iron_d6=1, oath_d4=1)
    plan = [action("iron_d6", enemies(engine)[0].id)]
    assert engine.check_plan(plan)[1:] == (None, None)
    assert ok(engine.do(cmd.SET_ACTION_PLAN, actions=plan)).code is None
    wrong_phase = engine.do(cmd.ROLL_DICE)
    assert not wrong_phase.accepted and wrong_phase.reason and wrong_phase.code is None
    fresh = Engine(packaged_content())
    assert fresh.check_plan(plan) == ([], "No hero is planning.", None)


def test_before_the_roll_the_preview_says_so_without_a_code():
    engine = start("squire")
    make_ready(engine, "h01")
    run_until_input(engine)
    assert engine.check_plan([action("iron_d6", enemies(engine)[0].id)]) == ([], "Roll the dice first.", None)
    assert engine.preview_plan([]) == ([], "Roll the dice first.")


def test_the_text_of_a_target_refusal_is_the_one_the_app_shows():
    engine, plan = strike_at_an_ally()
    hero, strike = unit(engine, "h01"), engine.die_for("h01", "iron_d6").faces[0]
    code, text = planning.target_refusal(engine, hero, strike, "h02")
    assert code == "TARGET_NOT_LEGAL" and text == planning.target_problem(engine, hero, strike, "h02")
    assert engine.do(cmd.SET_ACTION_PLAN, actions=plan).reason == text


def test_the_codes_are_the_same_on_the_shipped_content():
    engine = start("apprentice", "scout", content=packaged_content())
    begin_hero(engine, "h01", arcane_d6=3, focus_d4=4)
    down(engine, "h02")
    unit(engine, "h01").mana = 1
    refuse(engine, [action("arcane_d6", "h02")], "INSUFFICIENT_MANA")
    refuse(engine, [action("focus_d4", "h02")], "FACE_NOT_AN_ACTION")
