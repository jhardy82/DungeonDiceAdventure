"""T15_terminal_edges: final standing hero downed, last enemy defeated, simultaneous terminal precedence."""

from battle_dice.core import commands as cmd
from battle_dice.core import terminal
from battle_dice.core.models import STATE_DEFEATED, RunPhase
from tests.conftest import (
    action,
    begin_hero,
    down,
    enemy_acts,
    events_of,
    force_slash,
    ok,
    rejected,
    resolve_hero,
    start,
    unit,
    win_battle,
)


def test_t15_final_standing_hero_downed_ends_the_run():
    engine = start("squire")
    force_slash(engine, "h01")
    unit(engine, "h01").hp = 2
    enemy_acts(engine, "b1_e01")
    assert unit(engine, "h01").state == "downed"
    assert (engine.combat.outcome, engine.state.phase, engine.state.outcome) == ("defeat", RunPhase.DEFEAT, "defeat")
    assert [e.type for e in engine.events[-3:]] == ["combatant_downed", "battle_lost", "run_defeat"]
    assert engine.finished() and engine.permissible_commands() == []
    rejected(engine.do(cmd.ADVANCE_PHASE), "run is over")
    rejected(engine.do(cmd.ROLL_DICE), "no battle is in progress")


def test_t15_run_continues_while_any_hero_stands_and_fails_when_none_can_revive():
    engine = start("squire", "apprentice")  # both classes own a revival face
    force_slash(engine, "h01")
    unit(engine, "h01").hp = 2
    enemy_acts(engine, "b1_e01")
    assert unit(engine, "h01").state == "downed" and engine.state.phase == RunPhase.BATTLE
    assert engine.combat.outcome is None

    unit(engine, "h02").hp = 3
    unit(engine, "h02").shields = 0
    enemy_acts(engine, "b1_e02", action_roll=None)  # Hex Adept: Shadow Bolt is lethal -> priority 100
    assert unit(engine, "h02").state == "downed"
    assert engine.state.outcome == "defeat"  # no standing caster, so no legal revival remains
    assert terminal.legal_revival_pending(engine.combat) is False


def test_t15_last_enemy_defeated_wins_each_battle():
    engine = start("squire")
    win_battle(engine)
    assert (engine.combat.outcome, engine.state.phase, engine.state.outcome) == ("victory", RunPhase.UPGRADE, None)
    offer = engine.state.upgrade_offers["h01"]["iron_d6"][0]
    ok(engine.do(cmd.CHOOSE_UPGRADE, hero_id="h01", die_id="iron_d6", offer_id=offer["offer_id"]))
    ok(engine.do(cmd.ADVANCE_PHASE))
    win_battle(engine)
    assert (engine.state.phase, engine.state.outcome) == (RunPhase.VICTORY, "victory")
    assert [e.type for e in engine.events[-2:]] == ["battle_won", "run_victory"]
    assert [r["outcome"] for r in engine.state.battle_records] == ["victory", "victory"]


def test_t15_defeat_in_battle_two_ends_the_run():
    engine = start("squire")
    win_battle(engine)
    offer = engine.state.upgrade_offers["h01"]["iron_d6"][0]
    ok(engine.do(cmd.CHOOSE_UPGRADE, hero_id="h01", die_id="iron_d6", offer_id=offer["offer_id"]))
    ok(engine.do(cmd.ADVANCE_PHASE))
    unit(engine, "h01").hp = 1
    from tests.conftest import add_status

    add_status(engine, "b2_e01", "speed_up", stacks=2)  # War Cry unavailable; Strike is lethal -> priority 100
    enemy_acts(engine, "b2_e01")
    assert (engine.state.phase, engine.state.encounter_index) == (RunPhase.DEFEAT, 1)
    assert [r["outcome"] for r in engine.state.battle_records] == ["victory", "defeat"]


def test_t15_simultaneous_elimination_resolves_as_defeat():
    engine = start("squire", "scout")
    assert terminal.evaluate(engine.combat) is None
    for enemy in engine.combat.side("enemy"):
        enemy.hp, enemy.state = 0, STATE_DEFEATED
    assert terminal.evaluate(engine.combat) == "victory"
    down(engine, "h01")
    assert terminal.evaluate(engine.combat) == "victory"  # one hero still stands
    down(engine, "h02")
    assert terminal.evaluate(engine.combat) == "defeat"  # nobody stands on either side: defeat takes priority


def test_t15_victory_is_evaluated_after_each_atomic_effect_before_later_cleanup():
    engine = start("apprentice")
    hero = unit(engine, "h01")
    hero.corruption, hero.hp = 4, 1
    unit(engine, "b1_e01").hp = 3
    begin_hero(engine, "h01", arcane_d6=1, focus_d4=4)
    resolve_hero(engine, action("arcane_d6", "b1_e01"))
    # The kill ends the battle immediately: the end-of-activation backlash (corruption 5) never fires.
    assert engine.combat.outcome == "victory" and events_of(engine, "corruption_backlash") == []
    assert unit(engine, "h01").state == "standing" and unit(engine, "h01").corruption == 5
