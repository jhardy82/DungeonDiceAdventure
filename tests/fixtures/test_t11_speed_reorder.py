"""T11_speed_reorder: an immediate speed change alters scheduling without resetting gauge."""

from battle_dice.core import timeline
from battle_dice.core.models import CombatPhase
from tests.conftest import (
    add_status,
    begin_enemy,
    captain_content,
    enemy_acts,
    events_of,
    finish_activation,
    last_event,
    start,
    step,
    unit,
)


def test_t11_war_cry_changes_speed_immediately_and_keeps_gauge():
    engine = start("squire", content=captain_content(1))
    captain = unit(engine, "b1_e01")
    balance = engine.content.balance
    begin_enemy(engine, "b1_e01", action_roll=0)
    assert engine.combat.committed_intent.name == "War Cry" and engine.combat.phase == CombatPhase.ENEMY_RESOLVE
    unit(engine, "h01").gauge = 63
    gauges_before = {c.id: c.gauge for c in engine.combat.sorted_combatants()}
    step(engine)  # War Cry resolves mid-activation
    assert timeline.current_speed(captain, balance) == 11
    assert {c.id: c.gauge for c in engine.combat.sorted_combatants()} == gauges_before  # no gauge reset
    finish_activation(engine)
    # Applied during its own activation, so that activation does not consume a duration count.
    assert captain.instances_of("speed_up")[0].remaining_target_activations == 2
    timeline.tick(engine.combat, balance)
    assert captain.gauge == gauges_before["b1_e01"] + 11


def test_t11_speed_up_lasts_two_further_activations_then_expires():
    engine = start("squire", content=captain_content(1))
    captain = unit(engine, "b1_e01")
    enemy_acts(engine, "b1_e01", action_roll=0)
    assert captain.stacks_of("speed_up") == 2
    enemy_acts(engine, "b1_e01")
    assert captain.instances_of("speed_up")[0].remaining_target_activations == 1
    assert [e.delta["speed"] for e in events_of(engine, "activation_started") if e.actor_id == "b1_e01"] == [9, 11]
    enemy_acts(engine, "b1_e01")
    assert captain.stacks_of("speed_up") == 0
    assert last_event(engine, "status_expired").delta["status"] == "speed_up"
    assert timeline.current_speed(captain, engine.content.balance) == 9


def test_t11_speed_change_reorders_the_forecast():
    engine = start("squire", "scout", content=captain_content(2))
    balance = engine.content.balance
    unit(engine, "h01").gauge, unit(engine, "h02").gauge, unit(engine, "b1_e01").gauge = 0, 10, 20
    before = timeline.forecast(engine.combat, balance, 8)
    add_status(engine, "b1_e01", "speed_up", stacks=2)
    after = timeline.forecast(engine.combat, balance, 8)
    assert before != after
    assert after.count("b1_e01") >= before.count("b1_e01")
    assert unit(engine, "b1_e01").gauge == 20
