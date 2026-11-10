"""T06_interrupt_resistance: basic ability cancelled; elite action downgraded rather than cancelled."""

from battle_dice.core import commands as cmd
from battle_dice.core import reactions
from battle_dice.core.models import CombatPhase
from tests.conftest import (
    add_status,
    begin_enemy,
    captain_content,
    finish_activation,
    force_slash,
    last_event,
    ok,
    start,
    unit,
)

STRIKE, CORRUPT_MARK, BLIGHT_WAVE = 2, 1, 0  # rolls inside the tier [blight_wave 1, corrupt_mark 1, strike 3]


def _elite(*party):
    engine = start(*party, content=captain_content(len(party)))
    add_status(engine, "b1_e01", "speed_up", stacks=2)  # War Cry active -> illegal -> plain priority tier
    return engine


def _to_interrupt(engine):
    while engine.combat.phase != CombatPhase.INTERRUPT_WINDOW:
        ok(engine.do(cmd.SKIP_REACTION_STAGE))


def test_t06_basic_ability_is_cancelled():
    engine = start("squire", "scout")
    force_slash(engine, "h01")
    begin_enemy(engine, "b1_e01")
    _to_interrupt(engine)
    assert reactions.stage_options(engine, "interrupt")[0]["expected"] == "Cancel Slash."
    ok(engine.do(cmd.USE_REACTION, hero_id="h02"))
    finish_activation(engine)
    assert unit(engine, "h01").hp == 14 and unit(engine, "h02").mana == 1
    assert last_event(engine, "intent_cancelled").delta["by"] == "h02"


def test_t06_elite_strike_is_weakened_by_two_not_cancelled():
    engine = _elite("squire", "scout")
    begin_enemy(engine, "b1_e01", action_roll=STRIKE)
    intent = engine.combat.committed_intent
    assert intent.name == "Strike" and "elite_resistant" in intent.tags
    _to_interrupt(engine)
    assert "Resisted" in reactions.stage_options(engine, "interrupt")[0]["expected"]
    ok(engine.do(cmd.USE_REACTION, hero_id="h02"))
    assert not intent.cancelled and intent.damage_reduction == 2
    assert last_event(engine, "intent_weakened").delta["damage_reduction"] == 2
    finish_activation(engine)
    result = last_event(engine, "action_resolved").delta["results"][0]
    assert (result["base"], result["mitigation"], result["effective"]) == (3, 2, 1)
    assert unit(engine, "h01").hp == 13
    assert unit(engine, "h02").mana == 1 and unit(engine, "h02").reaction_charges == 0


def test_t06_elite_resource_and_area_effects_are_reduced_with_a_floor_of_zero():
    mark = _elite("squire", "scout")
    begin_enemy(mark, "b1_e01", action_roll=CORRUPT_MARK)
    assert mark.combat.committed_intent.name == "Corrupt Mark"
    _to_interrupt(mark)
    ok(mark.do(cmd.USE_REACTION, hero_id="h02"))
    assert mark.combat.committed_intent.magnitude_reduction == 1
    finish_activation(mark)
    assert [h.corruption for h in mark.combat.side("hero")] == [0, 0]  # +1 corruption reduced to 0

    wave = _elite("squire", "scout")
    begin_enemy(wave, "b1_e01", action_roll=BLIGHT_WAVE)
    _to_interrupt(wave)
    ok(wave.do(cmd.USE_REACTION, hero_id="h02"))
    finish_activation(wave)
    assert [h.hp for h in wave.combat.side("hero")] == [14, 10]  # 1 damage - 2 -> 0


def test_t06_without_a_reaction_the_elite_action_lands_in_full():
    engine = _elite("squire", "scout")
    begin_enemy(engine, "b1_e01", action_roll=STRIKE)
    while engine.combat.phase in CombatPhase.STAGE_BY_WINDOW:
        ok(engine.do(cmd.SKIP_REACTION_STAGE))
    finish_activation(engine)
    assert unit(engine, "h01").hp == 11


def test_t06_two_scouts_can_each_weaken_the_same_elite_intent():
    engine = _elite("squire", "scout", "scout")
    begin_enemy(engine, "b1_e01", action_roll=STRIKE)
    _to_interrupt(engine)
    ok(engine.do(cmd.USE_REACTION, hero_id="h02"))
    assert engine.combat.phase == CombatPhase.INTERRUPT_WINDOW  # the other Scout may still react
    ok(engine.do(cmd.USE_REACTION, hero_id="h03"))
    finish_activation(engine)
    assert unit(engine, "h01").hp == 14  # 3 - 4 -> 0
