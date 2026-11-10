"""Formation targeting, shields, statuses and resources (AC-08, AC-12)."""

from __future__ import annotations

from battle_dice.core import commands as cmd
from battle_dice.core import effects
from battle_dice.core.models import STATE_DEFEATED
from battle_dice.core.targeting import eligible_targets, protected_targets, resolve_targets
from battle_dice.core.view import snapshot
from tests.conftest import (
    action,
    add_status,
    begin_hero,
    down,
    enemy_acts,
    events_of,
    force_slash,
    last_event,
    ok,
    rejected,
    resolve_hero,
    start,
    unit,
)

# --------------------------------------------------------------------------------------------
# Formation (AC-08)
# --------------------------------------------------------------------------------------------


def test_melee_is_blocked_from_the_back_row_while_a_front_row_stands(content):
    engine = start("squire", "scout")  # b1_e01 goblin (front), b1_e02 hex adept (back)
    combat = engine.combat
    strike = content.die("iron_d6").faces[0]
    shot = content.die("striker_d8").faces[0]
    assert eligible_targets(combat, unit(engine, "h01"), strike) == ["b1_e01"]
    assert protected_targets(combat, unit(engine, "h01"), strike) == ["b1_e02"]
    assert eligible_targets(combat, unit(engine, "h02"), shot) == ["b1_e01", "b1_e02"]
    assert protected_targets(combat, unit(engine, "h02"), shot) == []

    unit(engine, "b1_e01").state = STATE_DEFEATED
    assert eligible_targets(combat, unit(engine, "h01"), strike) == ["b1_e02"]
    assert protected_targets(combat, unit(engine, "h01"), strike) == []


def test_enemy_melee_obeys_the_same_formation_rules():
    engine = start("squire", "scout")
    goblin = unit(engine, "b1_e01")
    slash = engine.enemy_action(goblin, "slash")
    assert eligible_targets(engine.combat, goblin, slash) == ["h01"]
    down(engine, "h01")  # a downed hero does not intercept melee
    assert eligible_targets(engine.combat, goblin, slash) == ["h02"]

    all_back = start("squire:back", "scout:back")
    goblin = unit(all_back, "b1_e01")
    assert eligible_targets(all_back.combat, goblin, all_back.enemy_action(goblin, "slash")) == ["h01", "h02"]


def test_ally_and_area_targeting_ignore_rows(content):
    engine = start("squire", "apprentice", "scout", content=None)
    combat = engine.combat
    squire = unit(engine, "h01")
    guard = content.die("iron_d6").faces[2]
    rally = content.die("iron_d6").faces[4]
    tend = content.die("bulwark_d4").faces[2]
    assert eligible_targets(combat, squire, guard) == ["h01", "h02", "h03"]
    down(engine, "h03")
    assert eligible_targets(combat, squire, guard) == ["h01", "h02"]
    assert eligible_targets(combat, squire, tend) == ["h01", "h02"]  # ordinary healing cannot revive
    assert eligible_targets(combat, squire, rally) == ["h01", "h02", "h03"]  # revival-tagged healing can


def test_blight_wave_targets_every_standing_hero(content):
    from tests.conftest import captain_content

    engine = start("squire", "apprentice", "scout", content=captain_content(3))
    captain = unit(engine, "b1_e01")
    wave = engine.enemy_action(captain, "blight_wave")
    assert eligible_targets(engine.combat, captain, wave) == ["h01", "h02", "h03"]
    down(engine, "h02")
    assert eligible_targets(engine.combat, captain, wave) == ["h01", "h03"]


def test_snapshot_explains_protected_back_row_targets():
    engine = start("squire", "scout")
    begin_hero(engine, "h01", iron_d6=1, oath_d4=1)
    die = snapshot(engine)["hero_turn"]["dice"][0]
    assert die["eligible_target_ids"] == ["b1_e01"] and die["protected_target_ids"] == ["b1_e02"]
    reason = rejected(engine.do(cmd.SET_ACTION_PLAN, actions=[action("iron_d6", "b1_e02")]), "protected")
    assert "front row" in reason


def test_resolve_targets_fallback_rules(content):
    engine = start("squire", "squire", "apprentice", "scout", "scout")  # 3 goblins (front), 2 hex adepts (back)
    combat = engine.combat
    scout = unit(engine, "h04")
    shot = content.die("striker_d8").faces[0]
    unit(engine, "b1_e01").state = STATE_DEFEATED
    unit(engine, "b1_e03").hp = 3
    unit(engine, "b1_e04").hp = 1  # lowest HP%, but in the other row
    resolution = resolve_targets(combat, scout, shot, ["b1_e01"])
    assert (resolution.retargeted_from, resolution.retargeted_to) == ("b1_e01", "b1_e03")  # same row, lowest HP%
    unit(engine, "b1_e03").hp = 6
    assert resolve_targets(combat, scout, shot, ["b1_e01"]).targets == ["b1_e02"]  # tie -> stable ID
    for enemy_id in ("b1_e02", "b1_e03"):
        unit(engine, enemy_id).state = STATE_DEFEATED
    assert resolve_targets(combat, scout, shot, ["b1_e01"]).targets == ["b1_e04"]  # other row, lowest HP%
    for enemy_id in ("b1_e04", "b1_e05"):
        unit(engine, enemy_id).state = STATE_DEFEATED
    cancelled = resolve_targets(combat, scout, shot, ["b1_e01"])
    assert cancelled.cancelled and cancelled.targets == []


# --------------------------------------------------------------------------------------------
# Shields (AC-12)
# --------------------------------------------------------------------------------------------


def test_shields_absorb_first_and_excess_passes_through():
    engine = start("squire")
    force_slash(engine, "h01")
    hero = unit(engine, "h01")
    hero.shields = 3
    enemy_acts(engine, "b1_e01")
    assert (hero.shields, hero.hp) == (1, 14)
    result = last_event(engine, "action_resolved").delta["results"][0]
    assert (result["damage"], result["absorbed"], result["hp_damage"]) == (2, 2, 0)
    enemy_acts(engine, "b1_e01")
    assert (hero.shields, hero.hp) == (0, 13)
    result = last_event(engine, "action_resolved").delta["results"][0]
    assert (result["absorbed"], result["hp_damage"]) == (1, 1)


def test_shields_persist_across_activations_until_consumed():
    engine = start("squire")
    begin_hero(engine, "h01", iron_d6=3, oath_d4=1)
    resolve_hero(engine, action("iron_d6", "h01"))
    assert unit(engine, "h01").shields == 4
    begin_hero(engine, "h01", iron_d6=6, oath_d4=1)
    resolve_hero(engine)
    assert unit(engine, "h01").shields == 4  # no decay


def test_shield_cap_and_steadfast():
    engine = start("squire", "scout")
    squire, scout = unit(engine, "h01"), unit(engine, "h02")
    begin_hero(engine, "h01", iron_d6=3, oath_d4=1)
    resolve_hero(engine, action("iron_d6", "h02"))
    assert scout.shields == 4  # Guard on an ally: 3 + 1 Steadfast (rules 1.1.0: any target)
    assert last_event(engine, "action_resolved").delta["results"][0]["bonus"] == 1
    begin_hero(engine, "h01", iron_d6=3, oath_d4=2)
    resolve_hero(engine, action("oath_d4", "h02"))
    assert scout.shields == 7  # Brace on an ally: 2 + 1 Steadfast
    begin_hero(engine, "h01", iron_d6=3, oath_d4=1)
    resolve_hero(engine, action("iron_d6", "h01"))
    assert squire.shields == 4  # Guard on self: +1 Steadfast
    assert last_event(engine, "action_resolved").delta["results"][0]["bonus"] == 1
    squire.shields = 11
    begin_hero(engine, "h01", iron_d6=3, oath_d4=1)
    resolve_hero(engine, action("iron_d6", "h01"))
    assert squire.shields == 12  # capped; the excess is lost


# --------------------------------------------------------------------------------------------
# Weaken and Poison (AC-12)
# --------------------------------------------------------------------------------------------


def test_weaken_reduces_attack_damage_only_with_minimum_zero():
    engine = start("squire")
    add_status(engine, "h01", "weaken")
    begin_hero(engine, "h01", iron_d6=1, oath_d4=1)
    resolve_hero(engine, action("iron_d6", "b1_e01"))
    assert unit(engine, "b1_e01").hp == 5  # 2 - 1
    add_status(engine, "h01", "weaken")
    begin_hero(engine, "h01", iron_d6=1, oath_d4=1)
    resolve_hero(engine, action("oath_d4", "b1_e01"))
    assert unit(engine, "b1_e01").hp == 5  # 1 - 2 -> 0, never negative
    assert last_event(engine, "action_resolved").delta["results"][0]["effective"] == 0

    shielding = start("squire")
    add_status(shielding, "h01", "weaken")
    add_status(shielding, "h01", "weaken")
    begin_hero(shielding, "h01", iron_d6=3, oath_d4=4)
    resolve_hero(shielding, action("iron_d6", "h01"))
    assert unit(shielding, "h01").shields == 4  # shielding is not reduced by Weaken


def test_weaken_and_poison_stack_caps_refresh_the_oldest(content):
    engine = start("squire")
    hero, goblin = unit(engine, "h01"), unit(engine, "b1_e01")
    for _ in range(2):
        effects.apply_status(engine, hero, goblin, "weaken", 1, 2)
    assert goblin.stacks_of("weaken") == 2
    first, second = goblin.instances_of("weaken")
    assert effects.status_unrefreshable(engine, goblin, "weaken", 2)
    assert effects.apply_status(engine, hero, goblin, "weaken", 1, 2)[0]["result"] == "no_change"
    first.remaining_target_activations = 1
    assert not effects.status_unrefreshable(engine, goblin, "weaken", 2)
    assert effects.apply_status(engine, hero, goblin, "weaken", 1, 2)[0] == {"status": "weaken", "result": "refreshed", "id": first.id}
    assert goblin.stacks_of("weaken") == 2 and first.remaining_target_activations == 2
    assert [s.id for s in goblin.instances_of("weaken")] == [second.id, first.id]  # refreshed stack is now newest

    for _ in range(5):
        effects.apply_status(engine, hero, goblin, "poison", 1, 2)
    assert goblin.stacks_of("poison") == content.status_cap("poison") == 3


def test_poison_ticks_at_activation_start_bypassing_shields_for_two_activations():
    engine = start("scout")
    goblin = unit(engine, "b1_e01")
    goblin.shields = 5
    begin_hero(engine, "h01", striker_d8=4, tools_d4=4)
    resolve_hero(engine, action("striker_d8", "b1_e01"))
    assert goblin.stacks_of("poison") == 1 and goblin.hp == 6
    enemy_acts(engine, "b1_e01")
    assert (goblin.hp, goblin.shields) == (5, 5)
    assert goblin.instances_of("poison")[0].remaining_target_activations == 1
    enemy_acts(engine, "b1_e01")
    assert goblin.hp == 4 and goblin.stacks_of("poison") == 0
    assert last_event(engine, "status_expired").delta["status"] == "poison"
    enemy_acts(engine, "b1_e01")
    assert goblin.hp == 4
    assert len(events_of(engine, "poison_tick")) == 2


# --------------------------------------------------------------------------------------------
# Mana, corruption, healing (AC-12)
# --------------------------------------------------------------------------------------------


def test_mana_is_clamped_and_does_not_regenerate_on_activation():
    engine = start("squire")
    hero = unit(engine, "h01")
    assert (hero.mana, hero.max_mana) == (2, 3)
    begin_hero(engine, "h01", iron_d6=6, oath_d4=4)
    assert hero.mana == 2  # no automatic regeneration at activation start
    resolve_hero(engine, action("oath_d4"))
    assert hero.mana == 3
    begin_hero(engine, "h01", iron_d6=6, oath_d4=4)
    resolve_hero(engine, action("oath_d4"))
    assert hero.mana == 3  # clamped to the class maximum
    assert last_event(engine, "action_resolved").delta["results"][0]["gained"] == 0


def test_corruption_is_clamped_and_cleansed():
    engine = start("apprentice")
    hero = unit(engine, "h01")
    assert effects.gain_corruption(hero, 9) == 5 and hero.corruption == 6
    assert effects.remove_corruption(hero, 2) == 2 and hero.corruption == 4
    begin_hero(engine, "h01", arcane_d6=5, focus_d4=4)
    resolve_hero(engine, action("arcane_d6"))
    assert hero.corruption == 2
    hero.corruption = 1
    begin_hero(engine, "h01", arcane_d6=5, focus_d4=4)
    resolve_hero(engine, action("arcane_d6"))
    assert hero.corruption == 0  # "up to 2"


def test_healing_caps_at_max_hp_and_full_hp_ally_is_a_legal_target():
    engine = start("squire")
    hero = unit(engine, "h01")
    hero.hp = 13
    begin_hero(engine, "h01", iron_d6=5, oath_d4=1)
    resolve_hero(engine, action("iron_d6", "h01"))
    assert (hero.hp, hero.shields, hero.mana) == (14, 0, 1)  # overheal is discarded, never becomes shield
    begin_hero(engine, "h01", iron_d6=5, oath_d4=1)
    ok(engine.do(cmd.SET_ACTION_PLAN, actions=[action("iron_d6", "h01")]))  # full HP is still legal
    ok(engine.do(cmd.COMMIT_ACTION_PLAN))


def test_steadfast_applies_only_to_the_squires_defense_die_actions():
    # Another class shielding an ally gets no bonus.
    engine = start("squire", "scout")
    begin_hero(engine, "h02", striker_d8=8, tools_d4=3)
    resolve_hero(engine, action("tools_d4", "h01"))
    assert unit(engine, "h01").shields == 2
    assert last_event(engine, "action_resolved").delta["results"][0]["bonus"] == 0

    # The Squire's non-Defense die faces are unaffected: Rally still heals exactly 2.
    healing = start("squire", "scout")
    unit(healing, "h02").hp = 5
    begin_hero(healing, "h01", iron_d6=5, oath_d4=1)
    resolve_hero(healing, action("iron_d6", "h02"))
    assert (unit(healing, "h02").hp, unit(healing, "h02").shields) == (7, 0)

    # The Interpose reaction is not a die action, so it grants exactly 2 shield.
    from battle_dice.core import commands as cmd
    from tests.conftest import begin_enemy

    reaction = start("squire", "scout")
    force_slash(reaction)
    begin_enemy(reaction, "b1_e01")
    ok(reaction.do(cmd.USE_REACTION, hero_id="h01", target_id="h01"))
    assert unit(reaction, "h01").shields == 2


def test_dirty_trick_is_ranged_while_slash_stays_melee():
    engine = start("squire", "scout")  # Squire front, Scout back
    goblin = unit(engine, "b1_e01")
    trick, slash = engine.enemy_action(goblin, "dirty_trick"), engine.enemy_action(goblin, "slash")
    assert (trick.range_type, slash.range_type) == ("ranged", "melee")
    assert eligible_targets(engine.combat, goblin, trick) == ["h01", "h02"]  # reaches the back row
    assert protected_targets(engine.combat, goblin, trick) == []
    assert eligible_targets(engine.combat, goblin, slash) == ["h01"]  # melee still stops at the front row

    # With the front-row Squire already Weakened, the Goblin's setup action goes to the back-row Scout.
    add_status(engine, "h01", "weaken")
    enemy_acts(engine, "b1_e01")
    assert last_event(engine, "action_resolved").delta["name"] == "Dirty Trick"
    assert unit(engine, "h02").stacks_of("weaken") == 1
