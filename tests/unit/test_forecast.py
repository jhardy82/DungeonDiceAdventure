"""The forecast shown to the player must equal what the engine then does (playtest finding 1).

Each test reads the forecast first, resolves the action through engine commands, and compares
the forecast with the amounts recorded in the event log.
"""

from __future__ import annotations

from battle_dice.core import commands as cmd
from battle_dice.core.engine import Engine
from battle_dice.core.events import EventType
from battle_dice.core.models import CombatPhase
from battle_dice.core.view import action_forecast, hero_turn_view, intent_view
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
