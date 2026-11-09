"""T08_poison_lethal: Poison bypasses shield and downs/defeats at actor start."""

from battle_dice.core.engine import run_until_input
from battle_dice.core.models import RunPhase
from tests.conftest import add_status, events_of, last_event, make_ready, start, unit


def test_t08_poison_defeats_a_shielded_enemy_before_it_acts():
    engine = start("squire", "scout")
    goblin = unit(engine, "b1_e01")
    goblin.hp, goblin.shields = 1, 5
    add_status(engine, "b1_e01", "poison")
    make_ready(engine, "b1_e01")
    intents_before = len(events_of(engine, "intent_selected"))
    run_until_input(engine)
    assert goblin.state == "defeated" and goblin.shields == 5
    assert last_event(engine, "poison_tick").delta["hp_damage"] == 1
    assert last_event(engine, "combatant_defeated").delta["id"] == "b1_e01"
    acted = [e for e in events_of(engine, "intent_selected")[intents_before:] if e.actor_id == "b1_e01"]
    assert acted == []  # removed before choosing an action
    assert engine.state.phase == RunPhase.BATTLE  # the hex adept is still standing


def test_t08_poison_downs_a_shielded_hero_who_then_does_not_roll():
    engine = start("squire", "scout")
    squire = unit(engine, "h01")
    squire.hp, squire.shields = 1, 3
    add_status(engine, "h01", "poison")
    make_ready(engine, "h01")
    run_until_input(engine)
    assert squire.state == "downed" and squire.shields == 3
    assert last_event(engine, "combatant_downed").delta["id"] == "h01"
    assert [e for e in events_of(engine, "dice_rolled") if e.actor_id == "h01"] == []
    ended = [e for e in events_of(engine, "activation_ended") if e.actor_id == "h01"]
    assert ended[-1].delta["reason"] == "removed at activation start"
    assert squire.instances_of("poison")[0].remaining_target_activations == 2  # downed heroes do not tick durations
    assert engine.combat.active_combatant_id != "h01"


def test_t08_poison_on_the_last_enemy_wins_and_on_the_last_hero_loses():
    win = start("squire")
    unit(win, "b1_e01").hp = 1
    add_status(win, "b1_e01", "poison")
    make_ready(win, "b1_e01")
    run_until_input(win)
    assert win.state.phase == RunPhase.UPGRADE and win.combat.outcome == "victory"

    lose = start("squire")
    unit(lose, "h01").hp = 1
    add_status(lose, "h01", "poison")
    make_ready(lose, "h01")
    run_until_input(lose)
    assert lose.state.phase == RunPhase.DEFEAT and lose.state.outcome == "defeat"
