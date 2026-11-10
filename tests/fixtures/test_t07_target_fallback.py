"""T07_target_fallback: frontline protection during offensive auto-retarget; invalid Heal/Defense cancels."""

from battle_dice.core.models import STATE_DEFEATED, CombatPhase
from tests.conftest import (
    action,
    begin_hero,
    commit,
    down,
    events_of,
    finish_activation,
    last_event,
    start,
    step,
    step_to,
    unit,
)


def _defeat(engine, enemy_id):
    enemy = unit(engine, enemy_id)
    enemy.hp = 0
    enemy.state = STATE_DEFEATED


def test_t07_melee_retarget_respects_the_front_row():
    engine = start("squire", "apprentice", "scout")  # goblins b1_e01, b1_e02 (front); hex adept b1_e03 (back)
    begin_hero(engine, "h01", iron_d6=1, oath_d4=1)
    commit(engine, action("iron_d6", "b1_e01"))
    _defeat(engine, "b1_e01")  # arrange: the committed target is gone before resolution
    unit(engine, "b1_e03").hp = 1  # lowest HP%, but protected by the standing front row
    finish_activation(engine)
    retarget = last_event(engine, "action_retargeted").delta
    assert (retarget["from"], retarget["to"]) == ("b1_e01", "b1_e02")
    assert unit(engine, "b1_e02").hp == 4 and unit(engine, "b1_e03").hp == 1


def test_t07_ranged_retarget_prefers_same_row_then_low_hp_then_id():
    engine = start("squire", "squire", "apprentice", "scout", "scout")  # 3 goblins front, 2 hex adepts back
    begin_hero(engine, "h04", striker_d8=1, tools_d4=4)
    commit(engine, action("striker_d8", "b1_e01"))
    _defeat(engine, "b1_e01")
    unit(engine, "b1_e03").hp = 3
    unit(engine, "b1_e04").hp = 1
    finish_activation(engine)
    assert last_event(engine, "action_retargeted").delta["to"] == "b1_e03"  # same row beats lower HP% elsewhere
    assert unit(engine, "b1_e03").hp == 1

    other_row = start("squire", "scout")  # goblin front, hex adept back
    begin_hero(other_row, "h02", striker_d8=1, tools_d4=4)
    commit(other_row, action("striker_d8", "b1_e01"))
    _defeat(other_row, "b1_e01")
    finish_activation(other_row)
    assert last_event(other_row, "action_retargeted").delta["to"] == "b1_e02"
    assert unit(other_row, "b1_e02").hp == 5


def test_t07_offensive_action_cancels_when_no_legal_target_remains():
    engine = start("apprentice")
    hero = unit(engine, "h01")
    begin_hero(engine, "h01", arcane_d6=1, focus_d4=1)
    commit(engine, action("focus_d4"), action("arcane_d6", "b1_e01"))
    step_to(engine, CombatPhase.ACTION_RESOLVE)
    step(engine)  # Channel
    mana_after_channel, corruption = hero.mana, hero.corruption
    _defeat(engine, "b1_e01")
    step(engine)  # Arcane Bolt has nobody to hit
    cancelled = last_event(engine, "action_cancelled").delta
    assert cancelled["reason"] == "no legal target remains" and cancelled["cost_spent"] == 0
    hero = unit(engine, "h01")
    assert hero.corruption == corruption  # no rider effect
    assert events_of(engine, "action_retargeted") == []
    assert mana_after_channel == 5


def test_t07_invalid_defense_and_healing_targets_cancel_without_cost():
    guard = start("squire", "scout")
    begin_hero(guard, "h01", iron_d6=3, oath_d4=1)
    commit(guard, action("iron_d6", "h02"))
    down(guard, "h02")
    finish_activation(guard)
    cancelled = last_event(guard, "action_cancelled").delta
    assert cancelled["name"] == "Guard" and cancelled["cost_spent"] == 0
    assert unit(guard, "h02").shields == 0 and events_of(guard, "action_retargeted") == []

    heal = start("squire", "scout")
    unit(heal, "h01").equipped_dice_ids = ["bulwark_d4", "iron_d6"]  # arrange: the non-reviving Tend face
    unit(heal, "h02").hp = 4
    begin_hero(heal, "h01", bulwark_d4=3, iron_d6=6)
    commit(heal, action("bulwark_d4", "h02"))
    down(heal, "h02")
    finish_activation(heal)
    assert last_event(heal, "action_cancelled").delta["name"] == "Tend"
    assert unit(heal, "h02").state == "downed" and unit(heal, "h01").mana == 2


def test_t07_revival_capable_heal_stays_legal_when_its_target_goes_down():
    engine = start("squire", "scout")
    unit(engine, "h02").hp = 4
    begin_hero(engine, "h01", iron_d6=5, oath_d4=1)
    commit(engine, action("iron_d6", "h02"))
    down(engine, "h02")
    finish_activation(engine)
    assert events_of(engine, "action_cancelled") == []
    assert (unit(engine, "h02").state, unit(engine, "h02").hp, unit(engine, "h01").mana) == ("standing", 2, 1)
