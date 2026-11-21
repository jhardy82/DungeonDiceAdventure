"""The forecast shown to the player must equal what the engine then does (playtest finding 1).

Each test reads the forecast first, resolves the action through engine commands, and compares
the forecast with the amounts recorded in the event log.
"""

from __future__ import annotations

from battle_dice.core import commands as cmd
from battle_dice.core.engine import Engine
from battle_dice.core.events import EventType
from battle_dice.core.models import CombatPhase
from battle_dice.core.view import action_forecast, combat_log, describe_event, hero_turn_view, intent_view
from tests.conftest import (
    action,
    add_status,
    begin_enemy,
    begin_hero,
    captain_content,
    commit,
    enemies,
    events_of,
    finish_activation,
    force_slash,
    ok,
    packaged_content,
    skip_reactions,
    start,
    unit,
)


def die_forecast(engine: Engine, die_id: str) -> dict:
    turn = hero_turn_view(engine)
    assert turn is not None
    return next(d["forecast"] for d in turn["dice"] if d["die_id"] == die_id)


def intent_forecast(engine: Engine) -> dict:
    view = intent_view(engine)
    assert view is not None
    return view["forecast"]


def resolved(engine: Engine, kind: str) -> list[dict]:
    return [r for e in events_of(engine, EventType.ACTION_RESOLVED) for r in e.delta["results"] if r["type"] == kind]


def test_an_unmodified_action_has_no_note():
    engine = start("squire")
    begin_hero(engine, "h01", iron_d6=1, oath_d4=4)
    forecast = die_forecast(engine, "iron_d6")
    assert forecast["note"] == "" and forecast["damage"] == engine.die_for("h01", "iron_d6").faces[0].power
    assert die_forecast(engine, "oath_d4") == {"damage": None, "shield": None, "weaken": 0, "note": ""}


def test_a_weakened_attack_is_forecast_at_what_it_will_deal():
    engine = start("squire")
    add_status(engine, "h01", "weaken")
    begin_hero(engine, "h01", iron_d6=6, oath_d4=1)  # Blank and Jab
    forecast = die_forecast(engine, "oath_d4")
    assert forecast["damage"] == 0 and forecast["note"] == "deals 0 (Weaken -1)"
    commit(engine, action("oath_d4", enemies(engine)[0].id))
    finish_activation(engine)
    assert resolved(engine, "damage")[-1]["effective"] == forecast["damage"]


def test_the_steadfast_bonus_is_forecast_on_a_defense_die():
    engine = start("squire")
    begin_hero(engine, "h01", iron_d6=3, oath_d4=4)  # Guard
    forecast = die_forecast(engine, "iron_d6")
    printed = engine.die_for("h01", "iron_d6").faces[2].power
    assert forecast["shield"] == printed + 1 and forecast["note"] == f"+{printed + 1} shield (Steadfast +1)"
    commit(engine, action("iron_d6", "h01"))
    finish_activation(engine)
    assert unit(engine, "h01").shields == forecast["shield"]


def test_the_scout_combo_bonus_is_forecast_for_the_second_action_only():
    engine = start("scout")
    begin_hero(engine, "h01", striker_d8=4, tools_d4=1)  # Poison, then Quick Shot
    foe = enemies(engine)[0].id
    assert die_forecast(engine, "tools_d4")["note"] == ""  # alone, a Quick Shot is as printed
    plan = [action("striker_d8", foe), action("tools_d4", foe)]
    intents, problem = engine.preview_plan(plan)
    assert problem is None and [i.name for i in intents] == ["Poison", "Quick Shot"]
    hero = unit(engine, "h01")
    first = action_forecast(engine, hero, engine.intent_face(intents[0]), intents[0], unit(engine, foe), combo=False)
    second = action_forecast(engine, hero, engine.intent_face(intents[1]), intents[1], unit(engine, foe), combo=True)
    assert first["note"] == "" and second["note"] == "deals 2 (Exploit Opening +1)"
    commit(engine, *plan)
    finish_activation(engine)
    assert resolved(engine, "damage")[-1]["effective"] == second["damage"] == 2


def test_the_apprentice_corruption_bonus_is_forecast():
    engine = start("apprentice")
    hero = unit(engine, "h01")
    hero.corruption = engine.content.class_def("apprentice")["passive"]["threshold"]
    begin_hero(engine, "h01", arcane_d6=1, focus_d4=4)  # Arcane Bolt
    forecast = die_forecast(engine, "arcane_d6")
    printed = engine.die_for("h01", "arcane_d6").faces[0].power
    assert forecast["damage"] == printed + 1 and forecast["note"] == f"deals {printed + 1} (Arcane Resonance +1)"
    commit(engine, action("arcane_d6", enemies(engine)[0].id))
    finish_activation(engine)
    assert resolved(engine, "damage")[-1]["effective"] == forecast["damage"]


def test_a_weakened_enemy_intent_is_forecast():
    engine = start("squire")
    force_slash(engine)
    goblin = enemies(engine)[0]
    add_status(engine, goblin.id, "weaken")
    begin_enemy(engine, goblin.id)
    forecast = intent_forecast(engine)
    committed = engine.combat.committed_intent
    assert committed is not None
    printed = engine.intent_face(committed).power
    assert forecast["weaken"] == 1 and forecast["damage"] == printed - 1
    skip_reactions(engine)
    finish_activation(engine)
    assert resolved(engine, "damage")[-1]["effective"] == forecast["damage"]


def test_a_resisted_disrupt_is_forecast_on_the_enemy_intent():
    engine = start("scout", content=captain_content(1))
    captain = enemies(engine)[0]
    for _ in range(40):  # find a Strike: the elite-resistant, interruptible attack
        begin_enemy(engine, captain.id)
        if engine.combat.committed_intent.name == "Strike" and engine.combat.phase == CombatPhase.INTERRUPT_WINDOW:
            break
        skip_reactions(engine)
        finish_activation(engine)
        unit(engine, "h01").hp = unit(engine, "h01").max_hp
        unit(engine, "h01").mana = unit(engine, "h01").max_mana
    else:
        raise AssertionError("the captain never used Strike with Disrupt available")
    before = intent_forecast(engine)["damage"]
    ok(engine.do(cmd.USE_REACTION, hero_id="h01", target_id=None))
    after = intent_forecast(engine)
    assert after["damage"] == max(0, before - 2) and "Disrupt -2" in after["note"]
    skip_reactions(engine)
    finish_activation(engine)
    assert resolved(engine, "damage")[-1]["effective"] == after["damage"]


# --------------------------------------------------------------------------------------------
# Playtest of 2026-11-21 (D1, D14): modifiers that cancel out, and amounts cut by a maximum
# --------------------------------------------------------------------------------------------


def planned(engine: Engine, *actions: dict) -> list[dict]:
    """The forecast of each action of a plan, in the order it resolves, as the plan panel computes it."""
    intents, problem = engine.preview_plan(list(actions))
    assert problem is None
    hero = unit(engine, engine.combat.turn.hero_id)
    opening = engine.build(hero.id).schedule.opening_categories
    out = []
    for position, intent in enumerate(intents):
        target = unit(engine, intent.committed_target_ids[0]) if intent.committed_target_ids else hero
        combo = len(intents) == 2 and position == 1 and intents[0].category in opening
        out.append(action_forecast(engine, hero, engine.intent_face(intent), intent, target, combo))
    return out


def test_modifiers_that_cancel_each_other_out_are_still_named():
    """Found by three playtesters: a weakened Scout's combo shot. The amount is the printed one, and the player is told why."""
    engine = start("scout")
    add_status(engine, "h01", "weaken")
    begin_hero(engine, "h01", striker_d8=4, tools_d4=1)  # Poison, then Quick Shot (1 damage)
    foe = enemies(engine)[0].id
    assert die_forecast(engine, "tools_d4")["note"] == "deals 0 (Weaken -1)"  # alone, the shot loses to Weaken
    plan = [action("striker_d8", foe), action("tools_d4", foe)]
    second = planned(engine, *plan)[1]
    assert second["damage"] == 1 and second["note"] == "deals 1 (Exploit Opening +1, Weaken -1)"
    commit(engine, *plan)
    finish_activation(engine)
    assert resolved(engine, "damage")[-1]["effective"] == 1


def test_a_heal_larger_than_the_missing_health_is_forecast_at_what_it_will_heal():
    engine = start("apprentice", "squire")
    squire = unit(engine, "h02")
    squire.hp = squire.max_hp - 1
    begin_hero(engine, "h01", arcane_d6=3, focus_d4=4)  # Mend: heal 3
    # On the die card the ally is not chosen yet (two could be healed): no amount is promised there.
    assert die_forecast(engine, "arcane_d6")["note"] == ""
    forecast = planned(engine, action("arcane_d6", "h02"))[0]
    assert forecast["note"] == f"heals 1 ({squire.name} is at {squire.hp}/{squire.max_hp} HP)"
    commit(engine, action("arcane_d6", "h02"))
    finish_activation(engine)
    assert resolved(engine, "heal")[-1]["healed"] == 1


def test_a_heal_on_the_only_possible_target_is_forecast_on_the_die_card_too():
    engine = start("apprentice")
    hero = unit(engine, "h01")
    hero.hp = hero.max_hp - 2
    begin_hero(engine, "h01", arcane_d6=3, focus_d4=4)
    assert die_forecast(engine, "arcane_d6")["note"] == f"heals 2 ({hero.name} is at {hero.hp}/{hero.max_hp} HP)"
    hero.hp = hero.max_hp
    assert die_forecast(engine, "arcane_d6")["note"] in ("", f"heals 0 ({hero.name} is at full health)")
    hero.hp = hero.max_hp - 3
    assert die_forecast(engine, "arcane_d6")["note"] == ""  # all of it is used: as printed


def test_mana_gained_above_the_maximum_is_forecast_at_what_will_be_gained():
    engine = start("apprentice")
    hero = unit(engine, "h01")
    hero.mana = hero.max_mana - 1
    begin_hero(engine, "h01", arcane_d6=6, focus_d4=1)  # Channel: +2 mana
    forecast = die_forecast(engine, "focus_d4")
    assert forecast["note"] == f"+1 mana ({hero.name} has {hero.mana} of at most {hero.max_mana})"
    commit(engine, action("focus_d4"))
    finish_activation(engine)
    assert resolved(engine, "gain_mana")[-1]["gained"] == 1


def test_the_mana_forecast_counts_from_the_mana_the_plan_has_left():
    """A later action of a plan starts from the mana the earlier ones leave, not from the mana of now."""
    engine = start("apprentice")
    hero = unit(engine, "h01")
    hero.mana = hero.max_mana
    begin_hero(engine, "h01", arcane_d6=6, focus_d4=1)
    intents, _ = engine.preview_plan([action("focus_d4")])
    face = engine.intent_face(intents[0])
    assert action_forecast(engine, hero, face, intents[0], hero)["note"] == f"+0 mana ({hero.name} has {hero.max_mana} of at most {hero.max_mana})"
    assert action_forecast(engine, hero, face, intents[0], hero, mana=hero.max_mana - 2)["note"] == ""
    assert action_forecast(engine, hero, face, intents[0], hero, mana=hero.max_mana - 1)["note"].startswith("+1 mana")


def test_a_shield_above_the_maximum_is_forecast_at_what_will_be_gained():
    engine = start("squire")
    hero = unit(engine, "h01")
    cap = engine.content.balance["shield"]["cap"]
    hero.shields = cap - 2
    begin_hero(engine, "h01", iron_d6=3, oath_d4=4)  # Guard: 3, and Steadfast adds 1
    forecast = die_forecast(engine, "iron_d6")
    assert forecast["shield"] == 2 and forecast["note"] == f"+2 shield (Steadfast +1, {hero.name} has {cap - 2} of at most {cap})"
    commit(engine, action("iron_d6", "h01"))
    finish_activation(engine)
    assert resolved(engine, "shield")[-1]["gained"] == 2 and hero.shields == cap


# --------------------------------------------------------------------------------------------
# Playtest of 2026-11-21 (D10, D15): the combat log
# --------------------------------------------------------------------------------------------


def test_the_log_says_when_a_hit_was_larger_than_the_health_that_was_left():
    engine = start("squire", content=packaged_content())  # the shipped Strike: 3 damage
    foe = enemies(engine)[0]
    foe.hp = 1
    begin_hero(engine, "h01", iron_d6=1, oath_d4=4)  # Strike
    strike = engine.die_for("h01", "iron_d6").faces[0].power
    assert strike >= 3
    commit(engine, action("iron_d6", foe.id))
    finish_activation(engine)
    line = next(line for line in reversed(combat_log(engine)) if " uses Strike" in line)
    assert f"{foe.name} takes 1 damage [{strike} base, {strike - 1} more than its health]" in line
    # A weakened hit: every number of the line is accounted for (the tester's "takes 1 damage [3 base, -1 Weaken]").
    engine = start("squire", content=packaged_content())  # the shipped Strike: 3 damage
    foe = enemies(engine)[0]
    foe.hp = 1
    add_status(engine, "h01", "weaken")
    begin_hero(engine, "h01", iron_d6=1, oath_d4=4)
    commit(engine, action("iron_d6", foe.id))
    finish_activation(engine)
    line = next(line for line in reversed(combat_log(engine)) if " uses Strike" in line)
    assert f"takes 1 damage [{strike} base, -1 Weaken, {strike - 2} more than its health]" in line


def test_a_hit_that_fits_the_health_has_no_such_remark():
    engine = start("squire")
    foe = enemies(engine)[0]
    foe.shields = 1
    begin_hero(engine, "h01", iron_d6=1, oath_d4=4)
    strike = engine.die_for("h01", "iron_d6").faces[0].power
    assert foe.hp > strike
    commit(engine, action("iron_d6", foe.id))
    finish_activation(engine)
    line = next(line for line in reversed(combat_log(engine)) if " uses Strike" in line)
    assert line.endswith(f"{foe.name} takes {strike - 1} damage, 1 absorbed by shield.")


def test_the_log_credits_a_bonus_to_the_passive_that_gave_it():
    engine = start("squire")
    begin_hero(engine, "h01", iron_d6=3, oath_d4=4)  # Guard
    commit(engine, action("iron_d6", "h01"))
    finish_activation(engine)
    assert any("gains 4 shield (incl. +1 Steadfast)" in line for line in combat_log(engine))
    event = events_of(engine, EventType.ACTION_RESOLVED)[-1]
    names = {"h01": "Aldric"}
    assert "(incl. +1 Bulwark)" in str(describe_event(event, names, None, {"h01": "Bulwark"}))
    assert "(incl. +1 bonus)" in str(describe_event(event, names))  # the passive is not known: no name is made up
