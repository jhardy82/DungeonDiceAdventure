"""Rules 1.2.0 (owner decisions D-36, D-37 and D-38; measurements in the decision log, sections 7.42 to 7.44).

Three changes to how a battle goes:

* an enemy never uses a status ability twice running;
* among equally good targets an enemy draws one, where the first hero of the party was taken before;
* a reaction stage that is passed over says why, for each hero whose reaction it could have been.

And one to the simulated player that measures the game: between plans that differ only in the ally they
help, it draws one.
"""

from __future__ import annotations

import collections

from battle_dice.core import enemy_ai
from battle_dice.core.events import EventType, state_hash
from battle_dice.core.models import CombatPhase, to_plain
from battle_dice.core.view import combat_log
from battle_dice.sim.policies import POLICY_VERSION, HeuristicPolicy
from tests.conftest import (
    action,
    add_status,
    begin_enemy,
    begin_hero,
    commit,
    down,
    enemies,
    enemy_acts,
    events_of,
    finish_activation,
    force_slash,
    last_event,
    packaged_content,
    skip_reactions,
    start,
    unit,
)


def tiers(engine, enemy_id):
    return {e["action_id"]: e["priority"] for e in enemy_ai.evaluate_actions(engine, unit(engine, enemy_id))}


# --------------------------------------------------------------------------------------------
# Never a status twice running
# --------------------------------------------------------------------------------------------


def test_after_a_status_ability_the_weights_decide():
    engine = start("squire", "scout")
    goblin = unit(engine, "b1_e01")
    assert goblin.last_category == "" and tiers(engine, "b1_e01") == {"dirty_trick": 20, "slash": 10}, "a fresh enemy prefers the status"
    goblin.last_category = "status"
    assert tiers(engine, "b1_e01") == {"dirty_trick": 10, "slash": 10}
    for other in ("attack", "resource", "defense"):
        goblin.last_category = other
        assert tiers(engine, "b1_e01")["dirty_trick"] == 20, other


def test_a_blow_that_brings_a_hero_down_still_comes_first():
    engine = start("squire")
    unit(engine, "b1_e01").last_category = "status"
    unit(engine, "h01").hp = 2
    assert tiers(engine, "b1_e01")["slash"] == 100


def test_the_engine_remembers_what_each_enemy_chose_last():
    engine = start("squire", "scout")
    first, second = enemies(engine)[0], enemies(engine)[1]
    enemy_acts(engine, first.id, action_roll=0)   # only Dirty Trick is in the top tier
    assert last_event(engine, "intent_selected").delta["chosen"] == "dirty_trick" and first.last_category == "status"
    assert second.last_category == "", "what one enemy did says nothing about another"
    # Next time a hero still has no Weaken, and yet both abilities are in one tier: the weights decide.
    assert any(hero.stacks_of("weaken") == 0 for hero in engine.combat.side("hero"))
    begin_enemy(engine, first.id, action_roll=1)  # 0 is Dirty Trick (weight 1), 1 to 3 are Slash (weight 3)
    selected = last_event(engine, "intent_selected")
    assert selected.delta["tier"] == ["dirty_trick", "slash"] and selected.delta["weight_total"] == 4
    assert selected.delta["chosen"] == "slash" and first.last_category == "attack"
    skip_reactions(engine)
    finish_activation(engine)
    assert tiers(engine, first.id).get("dirty_trick", 20) == 20, "after an attack the status comes first again, while a hero lacks it"


def test_what_an_enemy_chose_last_is_part_of_the_state_only_once_it_chose():
    engine = start("squire", "scout")
    before = state_hash(engine.state)
    assert "last_category" not in to_plain(unit(engine, "h01")) and "last_category" not in to_plain(unit(engine, "b1_e01"))
    unit(engine, "b1_e01").last_category = "status"
    assert to_plain(unit(engine, "b1_e01"))["last_category"] == "status" and state_hash(engine.state) != before


# --------------------------------------------------------------------------------------------
# A draw among equal targets
# --------------------------------------------------------------------------------------------


def test_a_status_goes_to_one_of_the_equal_heroes_by_a_draw():
    for drawn, expected in ((0, "h01"), (1, "h02"), (2, "h03")):
        engine = start("scout", "scout", "scout")
        begin_enemy(engine, "b1_e01", action_roll=0, target_roll=drawn)
        selected = last_event(engine, "intent_selected")
        assert selected.delta["chosen"] == "dirty_trick" and selected.delta["target_ids"] == [expected]
        assert selected.delta["target_draw"]["stream"] == "enemy:forced"


def test_no_draw_when_one_target_is_better():
    engine = start("scout", "scout", "scout")
    unit(engine, "h02").hp -= 1   # the most wounded of those without the status
    drawn_before = engine.state.rng["enemy"].draws
    begin_enemy(engine, "b1_e01", action_roll=0)
    selected = last_event(engine, "intent_selected")
    assert selected.delta["target_ids"] == ["h02"] and selected.delta["target_draw"] is None
    assert engine.state.rng["enemy"].draws == drawn_before, "the forced draw chose the ability; nothing else was drawn"


def test_a_lone_hero_is_never_drawn_for():
    engine = start("squire")
    drawn_before = engine.state.rng["enemy"].draws
    begin_enemy(engine, "b1_e01")
    assert last_event(engine, "intent_selected").delta["target_draw"] is None
    assert engine.state.rng["enemy"].draws == drawn_before + 1, "one draw: the ability"


def test_the_place_in_the_party_no_longer_decides_who_is_attacked_first():
    """Over many runs of the same party, the first enemy action falls on each of three equal heroes."""
    first_targets: collections.Counter[str] = collections.Counter()
    for seed in range(1, 61):
        engine = start("scout", "scout", "scout", seed=seed)
        begin_enemy(engine, enemies(engine)[0].id)
        first_targets[last_event(engine, "intent_selected").delta["target_ids"][0]] += 1
    assert set(first_targets) == {"h01", "h02", "h03"} and min(first_targets.values()) >= 10, first_targets


def test_an_enemy_whose_target_is_gone_draws_among_the_equal_ones_that_are_left():
    engine = start("squire", "squire", "squire")
    force_slash(engine)
    begin_enemy(engine, "b1_e01", action_roll=0, target_roll=0)
    assert engine.combat.committed_intent.committed_target_ids == ["h01"]
    down(engine, "h01")                         # gone before the blow lands
    skip_reactions(engine)
    engine.force_draws("enemy", [1])            # of h02 and h03, the second
    drawn_before = engine.state.rng["enemy"].draws
    finish_activation(engine)
    moved = last_event(engine, "action_retargeted")
    assert (moved.delta["from"], moved.delta["to"]) == ("h01", "h03")
    assert moved.delta["rule"] == "same row, then lowest HP percentage, then a draw"
    assert (moved.rng_stream, moved.rng_draw_index) == ("enemy:forced", drawn_before), "the event says which draw decided it"
    assert unit(engine, "h03").hp < unit(engine, "h03").max_hp and unit(engine, "h02").hp == unit(engine, "h02").max_hp


def test_one_target_left_is_taken_without_a_draw():
    engine = start("squire", "squire")
    force_slash(engine)
    begin_enemy(engine, "b1_e01", action_roll=0, target_roll=0)
    down(engine, "h01")
    skip_reactions(engine)
    drawn_before = engine.state.rng["enemy"].draws
    finish_activation(engine)
    moved = last_event(engine, "action_retargeted")
    assert moved.delta["to"] == "h02" and moved.delta["rule"] == "same row, then lowest HP percentage, then stable ID"
    assert moved.rng_stream is None and engine.state.rng["enemy"].draws == drawn_before


def test_a_heros_own_new_target_is_still_the_first_of_the_equal_enemies():
    """The draw is for enemies choosing among heroes. A hero whose target is gone keeps the stated rule."""
    engine = start("scout", "scout", "scout", "scout", "scout", content=packaged_content())
    goblins = [foe for foe in enemies(engine) if foe.archetype_id == "goblin"]
    assert [foe.id for foe in goblins] == ["b1_e01", "b1_e02", "b1_e03"] and len({(foe.row, foe.hp, foe.max_hp) for foe in goblins}) == 1
    begin_hero(engine, "h01", striker_d8=1, tools_d4=1)
    commit(engine, action("striker_d8", "b1_e01"))
    goblins[0].hp, goblins[0].state = 0, "defeated"   # gone before the blow lands; the other two are equally good
    drawn_before = engine.state.rng["enemy"].draws
    finish_activation(engine)
    moved = last_event(engine, "action_retargeted")
    assert (moved.delta["from"], moved.delta["to"]) == ("b1_e01", "b1_e02")
    assert moved.delta["rule"] == "same row, then lowest HP percentage, then stable ID" and moved.rng_stream is None
    assert goblins[1].hp < goblins[1].max_hp and goblins[2].hp == goblins[2].max_hp
    assert engine.state.rng["enemy"].draws == drawn_before


# --------------------------------------------------------------------------------------------
# Why no hero could react
# --------------------------------------------------------------------------------------------


def test_a_passed_stage_records_the_reason_for_each_hero_whose_reaction_it_is():
    engine = start("squire", "apprentice", content=packaged_content())
    force_slash(engine)
    unit(engine, "h01").mana = 0          # Interpose costs 1 mana
    unit(engine, "h02").mana = unit(engine, "h02").max_mana  # Grounding would change nothing: full mana, no corruption
    enemy_acts(engine, enemies(engine)[0].id)
    passed = {event.delta["stage"]: event.delta for event in events_of(engine, EventType.REACTION_STAGE_SKIPPED)}
    assert passed["guard"]["heroes"] == [{"hero_id": "h01", "reason": "Needs 1 mana (has 0)."}]
    assert passed["resource"]["heroes"] == [{"hero_id": "h02", "reason": "No resource change is possible."}]
    assert passed["interrupt"]["heroes"] == [], "no hero of this party has a reaction for that stage"
    assert all(delta["reason"] == "no eligible reaction" for delta in passed.values())
    line = next(text for text in combat_log(engine) if text.startswith("No hero could react"))
    assert line == "No hero could react to this enemy action. Squire 1: Needs 1 mana (has 0). Apprentice 2: No resource change is possible."


def test_the_reasons_of_one_enemy_action_are_not_repeated_under_the_next():
    engine = start("squire", "apprentice", content=packaged_content())
    unit(engine, "h01").mana = 0
    unit(engine, "h02").mana = unit(engine, "h02").max_mana
    for _ in range(2):
        force_slash(engine)
        enemy_acts(engine, enemies(engine)[0].id)
    lines = [text for text in combat_log(engine) if text.startswith("No hero could react")]
    assert lines == ["No hero could react to this enemy action. Squire 1: Needs 1 mana (has 0). Apprentice 2: No resource change is possible."] * 2


def test_a_stage_the_player_skips_has_no_reasons():
    engine = start("squire", content=packaged_content())
    force_slash(engine)
    begin_enemy(engine, enemies(engine)[0].id)
    assert engine.combat.phase == CombatPhase.GUARD_WINDOW
    skip_reactions(engine)
    skipped = [event.delta for event in events_of(engine, EventType.REACTION_STAGE_SKIPPED) if event.delta["stage"] == "guard"]
    assert skipped == [{"stage": "guard", "reason": "skipped by player"}]


# --------------------------------------------------------------------------------------------
# The simulated player: no favourite among allies
# --------------------------------------------------------------------------------------------


def test_between_two_allies_that_are_equally_worth_helping_the_player_draws():
    """It took the first before, so the first hero of a party got every such shield (decision log 7.43)."""
    assert POLICY_VERSION == 3
    helped: collections.Counter[str] = collections.Counter()
    for seed in range(1, 41):
        engine = start("squire", "scout", "scout", seed=seed)
        begin_hero(engine, "h01", iron_d6=3, oath_d4=2)   # Guard and Brace: a shield for an ally, twice
        hero, turn = engine._active_hero()
        policy = HeuristicPolicy()
        plan, score = policy._best_plan(engine, hero, turn)
        again, _ = HeuristicPolicy()._best_plan(engine, hero, turn)
        assert plan == again and score > 0, "the same moment of the same run gives the same plan"
        for step in plan:
            helped.update(step["target_ids"])
    scouts = helped["h02"] + helped["h03"]
    assert scouts >= 20, helped
    assert min(helped["h02"], helped["h03"]) >= scouts * 0.3, f"neither Scout is the favourite: {dict(helped)}"


def test_only_the_ally_may_differ_for_a_draw():
    engine = start("squire", "scout", "scout")
    same = HeuristicPolicy._only_the_ally_differs
    foe_a, foe_b = (foe.id for foe in enemies(engine)[:2])
    one = [{"die_id": "iron_d6", "target_ids": ["h02"]}, {"die_id": "oath_d4", "target_ids": [foe_a]}]
    assert same(engine, one, [{"die_id": "iron_d6", "target_ids": ["h03"]}, {"die_id": "oath_d4", "target_ids": [foe_a]}])
    assert not same(engine, one, [{"die_id": "iron_d6", "target_ids": ["h02"]}, {"die_id": "oath_d4", "target_ids": [foe_b]}]), "another enemy: no draw"
    assert not same(engine, one, [{"die_id": "iron_d6", "target_ids": ["h03"]}, {"die_id": "oath_d4", "target_ids": [foe_b]}])
    assert not same(engine, one, list(one)), "the same plan is not another plan"
    assert not same(engine, one, [{"die_id": "oath_d4", "target_ids": [foe_a]}, {"die_id": "iron_d6", "target_ids": ["h03"]}]), "another order"
    assert not same(engine, one, one[:1])


def test_the_player_still_stays_on_one_enemy():
    """Equal plans that hit different enemies are not drawn between: scattering the attacks loses battles."""
    chosen: collections.Counter[tuple[str, ...]] = collections.Counter()
    for seed in range(1, 21):
        engine = start("scout", "scout", seed=seed)
        for foe in enemies(engine):
            foe.hp, foe.shields = foe.max_hp, 0
        add_status(engine, "h01", "weaken", remaining=1, stacks=0)
        begin_hero(engine, "h01", striker_d8=1, tools_d4=1)
        hero, turn = engine._active_hero()
        plan, _ = HeuristicPolicy()._best_plan(engine, hero, turn)
        chosen[tuple(target for step in plan for target in step["target_ids"])] += 1
    assert len(chosen) == 1, f"the same enemies every time: {dict(chosen)}"
