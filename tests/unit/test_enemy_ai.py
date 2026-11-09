"""Enemy decision model and intent reveal (sections 7.1, 14.4; AC-10)."""

from __future__ import annotations

from battle_dice.core import enemy_ai
from battle_dice.core.models import CombatPhase
from battle_dice.core.view import snapshot
from tests.conftest import (
    add_status,
    begin_enemy,
    captain_content,
    force_slash,
    last_event,
    make_ready,
    start,
    step_to,
    unit,
)


def tiers(engine, enemy_id):
    evaluated = enemy_ai.evaluate_actions(engine, unit(engine, enemy_id))
    return {e["action_id"]: e["priority"] for e in evaluated}


def test_status_absent_on_target_outranks_plain_actions():
    engine = start("squire")
    assert tiers(engine, "b1_e01") == {"dirty_trick": 20, "slash": 10}
    add_status(engine, "h01", "weaken")
    assert tiers(engine, "b1_e01") == {"dirty_trick": 10, "slash": 10}


def test_unrefreshable_status_cap_makes_the_action_illegal():
    engine = start("squire")
    force_slash(engine, "h01")
    assert tiers(engine, "b1_e01") == {"slash": 10}
    unit(engine, "h01").instances_of("weaken")[0].remaining_target_activations = 1
    assert tiers(engine, "b1_e01") == {"dirty_trick": 10, "slash": 10}


def test_lethal_damage_gets_top_priority_after_shields_and_weaken():
    engine = start("squire")
    hero = unit(engine, "h01")
    hero.hp = 2
    assert tiers(engine, "b1_e01")["slash"] == 100
    hero.shields = 1  # 2 damage - 1 shield = 1 < 2 HP
    assert tiers(engine, "b1_e01")["slash"] == 10
    hero.shields = 0
    add_status(engine, "b1_e01", "weaken")  # the goblin's own Weaken lowers predicted damage
    assert tiers(engine, "b1_e01")["slash"] == 10


def test_weighted_choice_uses_stable_action_id_order():
    for roll, expected in ((0, "dirty_trick"), (1, "slash"), (2, "slash"), (3, "slash")):
        engine = start("squire")
        add_status(engine, "h01", "weaken")
        begin_enemy(engine, "b1_e01", action_roll=roll)
        record = last_event(engine, "intent_selected")
        assert record.delta["chosen"] == expected
        assert record.delta["tier"] == ["dirty_trick", "slash"] and record.delta["weight_total"] == 4
        assert record.rng_stream == "enemy:forced"


def test_lethal_tier_restricts_targets_to_those_it_would_down():
    engine = start("squire", "squire", "scout")  # two front-row Squires
    force_slash(engine, "h01")
    force_slash(engine, "h02")
    unit(engine, "h02").hp = 2
    begin_enemy(engine, "b1_e01")
    assert last_event(engine, "intent_selected").delta["tier_priority"] == 100
    assert engine.combat.committed_intent.committed_target_ids == ["h02"]


def test_damage_targets_maximise_hp_damage_then_low_hp_then_id():
    engine = start("squire", "squire", "scout")
    force_slash(engine, "h01")
    force_slash(engine, "h02")
    unit(engine, "h01").shields = 2  # fully absorbs a Slash
    begin_enemy(engine, "b1_e01")
    assert engine.combat.committed_intent.committed_target_ids == ["h02"]

    by_hp = start("squire", "squire", "scout")
    force_slash(by_hp, "h01")
    force_slash(by_hp, "h02")
    unit(by_hp, "h02").hp = 9
    begin_enemy(by_hp, "b1_e01")
    assert by_hp.combat.committed_intent.committed_target_ids == ["h02"]

    by_id = start("squire", "squire", "scout")
    force_slash(by_id, "h01")
    force_slash(by_id, "h02")
    begin_enemy(by_id, "b1_e01")
    assert by_id.combat.committed_intent.committed_target_ids == ["h01"]


def test_status_and_resource_targets_prefer_room_for_the_effect():
    engine = start("squire", "scout")  # hex adept is b1_e02
    add_status(engine, "h01", "poison")
    make_ready(engine, "b1_e02")
    step_to(engine, CombatPhase.REVEAL_INTENT)
    intent = engine.combat.committed_intent
    assert (intent.ability_id, intent.committed_target_ids) == ("poison_dart", ["h02"])  # h02 is not poisoned

    resource = start("squire", "scout")
    hex_adept = unit(resource, "b1_e02")
    mark = resource.enemy_action(hex_adept, "corrupt_mark")
    unit(resource, "h01").corruption = 6
    choice = {"face": mark, "targets": [unit(resource, "h01"), unit(resource, "h02")], "lethal": []}
    assert enemy_ai._choose_targets(resource, hex_adept, choice)[0] == ["h02"]


def test_war_cry_is_preferred_when_inactive_and_illegal_while_active():
    engine = start("squire", content=captain_content(1))
    assert tiers(engine, "b1_e01") == {"blight_wave": 10, "corrupt_mark": 10, "strike": 10, "war_cry": 20}
    add_status(engine, "b1_e01", "speed_up", stacks=2)
    assert "war_cry" not in tiers(engine, "b1_e01")


def test_ai_draws_only_from_the_enemy_stream_and_reveals_full_intent():
    engine = start("squire", seed=12)
    add_status(engine, "h01", "weaken")
    make_ready(engine, "b1_e01")
    before = {k: v.draws for k, v in engine.state.rng.items()}
    step_to(engine, CombatPhase.REVEAL_INTENT)
    after = {k: v.draws for k, v in engine.state.rng.items()}
    assert after["dice"] == before["dice"] and after["rewards"] == before["rewards"]
    assert after["enemy"] == before["enemy"] + 1
    step_to(engine, CombatPhase.GUARD_WINDOW)
    revealed = last_event(engine, "intent_revealed").delta
    assert set(revealed) >= {"name", "category", "power", "target_ids", "costs", "interruptible", "reactable", "effects"}
    assert revealed["target_ids"] == ["h01"] and revealed["interruptible"] is True
    view = snapshot(engine)["intent"]
    assert view["actor_id"] == "b1_e01" and view["target_names"] == ["Squire 1"] and view["reactable"]


def test_enemy_decisions_are_reproducible_for_a_seed():
    def choices(seed):
        engine = start("squire", "apprentice", "scout", seed=seed)
        picked = []
        for enemy_id in ("b1_e01", "b1_e02", "b1_e03", "b1_e01", "b1_e03"):
            begin_enemy(engine, enemy_id)
            intent = engine.combat.committed_intent
            picked.append((intent.ability_id, tuple(intent.committed_target_ids)))
            from tests.conftest import finish_activation, skip_reactions

            skip_reactions(engine)
            finish_activation(engine)
        return picked

    assert choices(8) == choices(8)
