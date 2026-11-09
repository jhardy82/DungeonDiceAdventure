"""Action-gauge scheduler (section 6.1; AC-06)."""

from __future__ import annotations

from battle_dice.core import commands as cmd
from battle_dice.core import timeline
from battle_dice.core.engine import run_until_input
from battle_dice.core.models import STATE_DEFEATED, CombatPhase
from tests.conftest import add_status, down, events_of, ok, start, step, unit


def test_first_activation_follows_speed_accumulation():
    engine = start("squire")  # Squire speed 7 vs Goblin speed 10
    step(engine)
    assert engine.combat.timeline_tick == 10
    assert engine.combat.active_combatant_id == "b1_e01"
    assert unit(engine, "b1_e01").gauge == 0  # 100 - threshold
    assert unit(engine, "h01").gauge == 70
    advanced = events_of(engine, "timeline_advanced")[-1]
    assert advanced.delta["ticks"] == 10


def test_overflow_is_retained_after_activation():
    engine = start("scout")  # speed 13: 8 ticks -> 104
    step(engine)
    assert engine.combat.active_combatant_id == "h01"
    assert engine.combat.timeline_tick == 8
    assert unit(engine, "h01").gauge == 4


def test_tie_break_order_overflow_then_speed_then_initiative_then_id(content):
    balance = content.balance
    engine = start("squire", "apprentice", "scout")  # enemies: b1_e01, b1_e02 goblins, b1_e03 hex adept
    combat = engine.combat
    for c in combat.combatants.values():
        c.gauge = 0

    # 1. Largest readiness overflow wins, even against a faster combatant.
    unit(engine, "h01").gauge = 106
    unit(engine, "h03").gauge = 104
    assert timeline.select_ready(combat, balance).id == "h01"

    # 2. Equal overflow: highest current speed.
    unit(engine, "h01").gauge = 104
    assert timeline.select_ready(combat, balance).id == "h03"

    # 3. Equal overflow and speed: highest base initiative.
    unit(engine, "h01").speed = 13  # Squire initiative 5 < Scout initiative 6
    assert timeline.select_ready(combat, balance).id == "h03"
    unit(engine, "h01").base_initiative = 9
    assert timeline.select_ready(combat, balance).id == "h01"

    # 4. Everything equal: lowest lexicographic stable ID.
    for c in combat.combatants.values():
        c.gauge = 0
    unit(engine, "b1_e02").gauge = 100
    unit(engine, "b1_e01").gauge = 100
    assert timeline.select_ready(combat, balance).id == "b1_e01"


def test_already_ready_combatants_act_before_the_tick_advances():
    engine = start("squire", "scout")
    for c in engine.combat.combatants.values():
        c.gauge = 0
    unit(engine, "b1_e01").gauge = 100
    unit(engine, "b1_e02").gauge = 100
    tick_before = engine.combat.timeline_tick
    step(engine)
    assert engine.combat.active_combatant_id == "b1_e01"
    while len(events_of(engine, "activation_started")) < 2:
        run_until_input(engine)
        if engine.combat.phase in CombatPhase.STAGE_BY_WINDOW:
            ok(engine.do(cmd.SKIP_REACTION_STAGE))
    started = [e.actor_id for e in events_of(engine, "activation_started")]
    assert started[:2] == ["b1_e01", "b1_e02"]
    assert [e.tick for e in events_of(engine, "activation_started")[:2]] == [tick_before, tick_before]


def test_speed_is_clamped_to_the_legal_range(content):
    engine = start("squire")
    hero = unit(engine, "h01")
    hero.speed = 99
    assert timeline.current_speed(hero, content.balance) == 30
    hero.speed = -4
    assert timeline.current_speed(hero, content.balance) == 1
    hero.speed = 29
    add_status(engine, "h01", "speed_up", stacks=2)
    assert timeline.current_speed(hero, content.balance) == 30


def test_speed_change_alters_future_ticks_without_resetting_gauge(content):
    engine = start("squire")
    hero = unit(engine, "h01")
    hero.gauge = 41
    add_status(engine, "h01", "speed_up", stacks=2)
    assert hero.gauge == 41  # the modifier itself never touches accumulated gauge
    timeline.tick(engine.combat, content.balance)
    assert hero.gauge == 41 + 9


def test_downed_and_defeated_combatants_do_not_accumulate_or_act(content):
    engine = start("squire", "scout")
    down(engine, "h02")
    unit(engine, "b1_e02").state = STATE_DEFEATED
    unit(engine, "b1_e02").hp = 0
    unit(engine, "h02").gauge = 55
    for _ in range(3):
        timeline.tick(engine.combat, content.balance)
    assert unit(engine, "h02").gauge == 55
    assert unit(engine, "b1_e02").gauge == 0
    assert unit(engine, "h01").gauge == 21
    unit(engine, "h02").gauge = 500
    assert all(c.id != "h02" for c in timeline.ready_combatants(engine.combat, content.balance))


def test_forecast_matches_the_real_activation_order(content):
    engine = start("squire", "scout", seed=4)
    predicted = timeline.forecast(engine.combat, content.balance, 6)
    actual: list[str] = []
    while len(actual) < 6:
        run_until_input(engine)
        if engine.combat.phase == CombatPhase.HERO_ROLL:
            ok(engine.do(cmd.ROLL_DICE))
            ok(engine.do(cmd.SET_ACTION_PLAN, actions=[]))
            ok(engine.do(cmd.COMMIT_ACTION_PLAN))
        elif engine.combat.phase in CombatPhase.STAGE_BY_WINDOW:
            ok(engine.do(cmd.SKIP_REACTION_STAGE))
        actual = [e.actor_id for e in events_of(engine, "activation_started")]
    assert actual[:6] == predicted


def test_same_seed_and_inputs_give_the_same_activation_sequence():
    def sequence(seed: int) -> list[tuple[int, str]]:
        engine = start("squire", "apprentice", "scout", seed=seed)
        for _ in range(60):
            run_until_input(engine)
            if engine.finished() or engine.state.phase != "battle":
                break
            phase = engine.combat.phase
            if phase == CombatPhase.HERO_ROLL:
                ok(engine.do(cmd.ROLL_DICE))
                ok(engine.do(cmd.SET_ACTION_PLAN, actions=[]))
                ok(engine.do(cmd.COMMIT_ACTION_PLAN))
            else:
                ok(engine.do(cmd.SKIP_REACTION_STAGE))
        return [(e.tick, e.actor_id) for e in events_of(engine, "activation_started")]

    assert sequence(21) == sequence(21)
    assert len(sequence(21)) > 10
