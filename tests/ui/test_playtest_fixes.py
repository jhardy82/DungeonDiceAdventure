"""Fixes for what the team of playtesters found on 2026-11-21 (docs/PLAYTEST_TEAM_2026-11-21.md).

Each test names the finding it closes. The tests go through the real screens: they press the keys
a player presses and read the texts the screen draws.
"""

from __future__ import annotations

import pygame
import pytest

from battle_dice.app.controller import FALLBACK_TEXT
from battle_dice.core.engine import Engine
from battle_dice.core.events import EventType
from battle_dice.core.models import STATE_DEFEATED
from battle_dice.ui import screens, toolkit
from tests.conftest import add_status, down, enemies, events_of, force_slash, unit
from tests.ui.test_ui_flow import Play, record_text

#: Fonts of very different widths, as other machines have them. () is pygame's own font.
FONTS = [("dejavusans",), (), ("liberationmono",), ("dejavuserif",)]


def engine_of(play: Play) -> Engine:
    engine = play.ctrl.engine
    assert engine is not None
    return engine


def redraw(play: Play, monkeypatch) -> tuple[list[str], list[str]]:
    """Every text of the next frame, and the texts that had to be shortened in it."""
    drawn, shortened = record_text(monkeypatch)
    play.app.frame(0)
    return drawn, shortened


def plan_die(play: Play, number: int, target: int = 1) -> None:
    """Plan a die as a player does: its number, then the number of a target when one is asked for."""
    play.key((pygame.K_1, pygame.K_2)[number - 1])
    if play.ctrl.targeting_die is not None:
        play.key((pygame.K_1, pygame.K_2, pygame.K_3)[target - 1])


# --------------------------------------------------------------------------------------------
# D1: the die card of a planned combo
# --------------------------------------------------------------------------------------------


def test_the_die_card_of_a_planned_combo_shows_the_plans_prediction(tmp_path, monkeypatch):
    play = Play(tmp_path, ["scout"])
    play.begin()
    play.to_roll_prompt()
    add_status(engine_of(play), "h01", "weaken")
    play.roll_faces(striker_d8=4, tools_d4=1)  # Poison, then Quick Shot: the Scout's combo
    drawn, _ = redraw(play, monkeypatch)
    assert drawn.count("Now deals 0 (Weaken -1)") == 1, "alone, the shot loses its 1 damage to Weaken"
    plan_die(play, 1)
    plan_die(play, 2)
    assert play.ctrl.confirm_problem() is None
    drawn, _ = redraw(play, monkeypatch)
    # Once on the die card and once in the plan: the two can no longer disagree.
    assert drawn.count("Now deals 1 (Exploit Opening +1, Weaken -1)") == 2
    assert "Now deals 0 (Weaken -1)" not in drawn
    damage_before = len([r for e in events_of(engine_of(play), EventType.ACTION_RESOLVED) for r in e.delta["results"] if r["type"] == "damage"])
    play.key(pygame.K_RETURN)
    play.to_input()
    dealt = [r for e in events_of(engine_of(play), EventType.ACTION_RESOLVED) for r in e.delta["results"] if r["type"] == "damage"]
    assert dealt[damage_before]["effective"] == 1


def test_a_die_in_a_plan_that_is_not_legal_keeps_its_own_prediction(tmp_path, monkeypatch):
    play = Play(tmp_path, ["squire"])
    play.begin()
    play.to_roll_prompt()
    unit(engine_of(play), "h01").status_instances.clear()
    play.roll_faces(iron_d6=3, oath_d4=1)  # Guard and Jab: a Squire may plan one action only
    foe = enemies(engine_of(play))[0].id
    play.ctrl.draft = [{"die_id": "iron_d6", "target_ids": ["h01"]}, {"die_id": "oath_d4", "target_ids": [foe]}]
    assert play.ctrl.plan_preview()["problem"]
    drawn, _ = redraw(play, monkeypatch)
    # The plan cannot say what the Guard will give while it is not legal; the die card still can.
    assert "Now +4 shield (Steadfast +1)" in drawn


# --------------------------------------------------------------------------------------------
# M1: corruption backlash is predicted and explained
# --------------------------------------------------------------------------------------------


def backlash_events(play: Play) -> list:
    return events_of(engine_of(play), EventType.CORRUPTION_BACKLASH)


def test_the_plan_predicts_the_health_lost_to_corruption(tmp_path, monkeypatch):
    play = Play(tmp_path, ["apprentice"])
    play.begin()
    play.to_roll_prompt()
    hero = unit(engine_of(play), "h01")
    rule = play.ctrl.content.balance["corruption"]
    hero.corruption = rule["backlash_threshold"]
    play.roll_faces(arcane_d6=6, focus_d4=4)  # two blanks: nothing to plan
    line = f"Corruption {hero.corruption}: -{rule['backlash_damage']} HP when this activation ends."
    assert play.ctrl.plan_preview()["backlash"] == line
    drawn, shortened = redraw(play, monkeypatch)
    assert line in drawn and line not in shortened
    health, before = hero.hp, len(backlash_events(play))
    play.ctrl.settings.confirm_pass = False
    play.key(pygame.K_p)
    play.to_input()
    assert len(backlash_events(play)) == before + 1 and hero.hp == health - rule["backlash_damage"]


def test_a_plan_that_takes_the_corruption_below_the_threshold_predicts_no_loss(tmp_path, monkeypatch):
    play = Play(tmp_path, ["apprentice"])
    play.begin()
    play.to_roll_prompt()
    hero = unit(engine_of(play), "h01")
    hero.corruption = play.ctrl.content.balance["corruption"]["backlash_threshold"]
    play.roll_faces(arcane_d6=5, focus_d4=4)  # Cleanse: the Apprentice loses 2 corruption
    assert play.ctrl.plan_preview()["backlash"], "before the plan the loss is predicted"
    plan_die(play, 1)
    assert play.ctrl.confirm_problem() is None and play.ctrl.plan_preview()["backlash"] == ""
    drawn, _ = redraw(play, monkeypatch)
    assert not any(text.startswith("Corruption ") and "when this activation ends" in text for text in drawn)
    health, before = hero.hp, len(backlash_events(play))
    play.key(pygame.K_RETURN)
    play.to_input()
    assert len(backlash_events(play)) == before and hero.hp == health


def test_a_plan_that_raises_the_corruption_to_the_threshold_predicts_the_loss(tmp_path):
    play = Play(tmp_path, ["apprentice"])
    play.begin()
    play.to_roll_prompt()
    hero = unit(engine_of(play), "h01")
    threshold = play.ctrl.content.balance["corruption"]["backlash_threshold"]
    hero.corruption, hero.mana = threshold - 1, hero.max_mana
    play.roll_faces(arcane_d6=1, focus_d4=4)  # Arcane Bolt: the caster gains 1 corruption
    assert play.ctrl.plan_preview()["backlash"] == ""
    plan_die(play, 1)
    assert play.ctrl.confirm_problem() is None
    assert play.ctrl.plan_preview()["backlash"].startswith(f"Corruption {threshold}: ")
    before = len(backlash_events(play))
    play.key(pygame.K_RETURN)
    play.to_input()
    assert len(backlash_events(play)) == before + 1


def test_corruption_is_explained_on_the_unit_card_and_in_the_controls_help(tmp_path, monkeypatch):
    play = Play(tmp_path, ["apprentice"])
    play.begin()
    play.to_roll_prompt()
    hero = unit(engine_of(play), "h01")
    rule = play.ctrl.content.balance["corruption"]
    hero.corruption = 1
    play.hover("unit:h01")
    drawn, shortened = redraw(play, monkeypatch)
    words = (f"Corruption (CR) 1 of at most {hero.max_corruption}: from {rule['backlash_threshold']} on, the hero loses "
             f"{rule['backlash_damage']} HP at the end of each of its activations (backlash; shields do not help).")
    assert words in drawn and words not in shortened
    hero.corruption = rule["backlash_threshold"]
    play.app.frame(0)
    drawn, shortened = redraw(play, monkeypatch)
    now = next(text for text in drawn if text.startswith("Corruption (CR)"))
    assert 'That is so now, shown by the "!".' in now and now not in shortened
    assert f"CR {hero.corruption}/{hero.max_corruption}!" in drawn
    assert "Corruption backlash: loses 1 HP after each activation." in (play.ui.widget("unit:h01").tooltip or "")
    play.ctrl.open_pause()
    play.ctrl.toggle_pause_help()
    drawn, _ = redraw(play, monkeypatch)
    board = next(text for text in drawn if "CR (corruption)" in text)
    assert f"from CR {rule['backlash_threshold']} on, a hero loses {rule['backlash_damage']} HP" in board and "{" not in board


# --------------------------------------------------------------------------------------------
# M2: how an enemy chooses
# --------------------------------------------------------------------------------------------


def test_the_enemy_panel_states_the_priority_before_the_weights(tmp_path, monkeypatch):
    play = Play(tmp_path, ["squire"])
    play.begin()
    play.to_roll_prompt()
    foe = enemies(engine_of(play))[0]
    play.hover(f"unit:{foe.id}")
    drawn, shortened = redraw(play, monkeypatch)
    assert screens.ENEMY_CHOICE_TEXT in drawn and screens.ENEMY_CHOICE_TEXT not in shortened
    assert not any("a higher weight is chosen more often)" in text for text in drawn), "the old, incomplete rule is gone"
    for part in ("bring a hero down", "puts a status on a hero who does not have it", "a higher weight is chosen more often",
                 "never a status ability twice running", "Among equally good targets it draws one"):  # the last two: rules 1.2.0
        assert part in screens.ENEMY_CHOICE_TEXT


# --------------------------------------------------------------------------------------------
# D7: Order
# --------------------------------------------------------------------------------------------


def test_order_is_on_only_when_it_changes_the_order(tmp_path, monkeypatch):
    play = Play(tmp_path, ["scout"])
    play.begin()
    play.to_roll_prompt()
    play.roll_faces(striker_d8=4, tools_d4=1)
    assert play.ctrl.order_problem() == "Needs two planned actions."
    plan_die(play, 1)
    plan_die(play, 2)
    assert "fix the order" in (play.ctrl.order_problem() or "")
    play.ctrl.swap_plan_order()  # asked for past the button: still nothing is swapped
    assert [a["die_id"] for a in play.ctrl.draft] == ["striker_d8", "tools_d4"]
    # Rules that leave the order to the player (no shipped class has them yet): the swap is offered and works.
    engine = engine_of(play)
    real = engine.check_plan

    def as_drafted(actions):
        intents, problem, code = real(actions)
        by_die = {intent.source_die_id: intent for intent in intents}
        return [by_die[a["die_id"]] for a in actions], problem, code

    monkeypatch.setattr(engine, "check_plan", as_drafted)
    play.app.frame(0)
    assert play.ctrl.order_problem() is None and play.ui.widget("plan:order").enabled
    play.key(pygame.K_o)
    assert [a["die_id"] for a in play.ctrl.draft] == ["tools_d4", "striker_d8"]


# --------------------------------------------------------------------------------------------
# D4, D16, D17: the planner and the unit cards
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("fonts", FONTS, ids=lambda fonts: fonts[0] if fonts else "pygame")
def test_the_plan_line_about_a_lost_target_is_never_cut_off(tmp_path, monkeypatch, fonts):
    monkeypatch.setattr(toolkit, "FONT_CANDIDATES", fonts)
    play = Play(tmp_path, ["squire", "apprentice"])
    play.begin()
    play.until(lambda: "plan:roll" in play.ui.keys() and play.combat.turn.hero_id == "h01")
    unit(engine_of(play), "h01").status_instances.clear()  # no Weaken: a "Now" line would take the line's place
    play.roll_faces(iron_d6=1, oath_d4=4)
    plan_die(play, 1)
    drawn, shortened = redraw(play, monkeypatch)
    assert FALLBACK_TEXT["single_enemy"] in drawn and FALLBACK_TEXT["single_enemy"] not in shortened
    play.key(pygame.K_c)
    play.combat.turn.rolled["iron_d6"] = 4  # Rally: heal an ally
    unit(engine_of(play), "h02").hp -= 2
    play.app.frame(0)
    plan_die(play, 1, target=2)
    drawn, shortened = redraw(play, monkeypatch)
    assert FALLBACK_TEXT["single_ally"] in drawn and FALLBACK_TEXT["single_ally"] not in shortened


def test_a_die_says_will_reroll_only_while_a_reroll_is_left(tmp_path, monkeypatch):
    play = Play(tmp_path, ["squire"])
    play.begin()
    play.to_roll_prompt()
    play.key(pygame.K_r)
    drawn, _ = redraw(play, monkeypatch)
    assert play.combat.turn.rerolls_remaining > 0 and drawn.count("will reroll") == 2
    while play.combat.turn.rerolls_remaining:
        play.key(pygame.K_r)
    drawn, _ = redraw(play, monkeypatch)
    assert "will reroll" not in drawn


def test_a_downed_hero_shows_no_reaction_and_a_defeated_enemy_no_statuses(tmp_path, monkeypatch):
    play = Play(tmp_path, ["squire", "scout"])
    play.begin()
    play.until(lambda: "plan:roll" in play.ui.keys() and play.combat.turn.hero_id == "h01")
    engine = engine_of(play)
    foes = enemies(engine)
    assert len(foes) >= 2
    for hero_id in ("h01", "h02"):
        unit(engine, hero_id).status_instances.clear()
        unit(engine, hero_id).reaction_charges = 1
    for foe in foes:
        foe.status_instances.clear()
        add_status(engine, foe.id, "poison")
    drawn, _ = redraw(play, monkeypatch)
    assert drawn.count("React 1") == 2 and "React 0" not in drawn
    statuses = [text for text in drawn if text.startswith("PSN")]
    gauges = [text for text in drawn if text.startswith("G") and text[1:].isdigit()]
    assert len(statuses) == len(foes) and len(gauges) == len(foes) + 2
    down(engine, "h02")
    foes[0].hp, foes[0].state = 0, STATE_DEFEATED
    drawn, _ = redraw(play, monkeypatch)
    assert drawn.count("React 1") == 1 and drawn.count("React 0") == 1, "a downed hero cannot react"
    assert len([text for text in drawn if text.startswith("PSN")]) == len(foes) - 1
    assert len([text for text in drawn if text.startswith("G") and text[1:].isdigit()]) == len(foes) - 1 + 1
    assert "DEFEATED" in drawn and "DOWNED" in drawn


# --------------------------------------------------------------------------------------------
# D13, D5: the reaction prompt
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("fonts", FONTS, ids=lambda fonts: fonts[0] if fonts else "pygame")
def test_the_reaction_prompt_gives_the_damage_that_will_land_and_names_the_reactions_used(tmp_path, monkeypatch, fonts):
    monkeypatch.setattr(toolkit, "FONT_CANDIDATES", fonts)
    play = Play(tmp_path, ["squire", "apprentice"])
    play.begin()
    engine = engine_of(play)
    force_slash(engine)
    for foe in enemies(engine):
        add_status(engine, foe.id, "weaken", remaining=9)
    for hero_id in ("h01", "h02"):
        unit(engine, hero_id).corruption = 2  # Grounding has something to do
    play.until(lambda: play.ui.widget("react:h01") is not None and play.ui.widget("react:h01").enabled)
    intent = play.ctrl.view()["intent"]
    assert intent["forecast"]["note"].startswith("deals ") and "Weaken -1" in intent["forecast"]["note"]
    drawn, shortened = redraw(play, monkeypatch)
    headline = next(text for text in drawn if " will use " in text)
    assert headline.endswith(f"  Now {intent['forecast']['note']}.") and headline not in shortened
    assert not any(text.startswith("Used") for text in drawn), "nothing was used yet: nothing is listed"
    play.ctrl.pick_reaction("h01", True, list(play.ctrl.view()["reaction"]["options"][0]["target_ids"])[:1])
    play.app.frame(0)
    assert play.ui.widget("react:h02") is not None, "the Resource stage follows the Guard stage"
    drawn, shortened = redraw(play, monkeypatch)
    used = next(text for text in drawn if text.startswith("Used: "))
    assert used.startswith("Used: Interpose") and used not in shortened
    assert not any("interpose" in text for text in drawn), "no internal name on the screen"


# --------------------------------------------------------------------------------------------
# D6: the status bar
# --------------------------------------------------------------------------------------------


def test_the_status_bar_announces_the_next_hero_instead_of_keeping_the_last_message(tmp_path):
    play = Play(tmp_path, ["squire", "scout"])
    play.begin()
    play.to_roll_prompt()
    first = play.combat.turn.hero_id
    play.key(pygame.K_r)
    play.ctrl.settings.confirm_pass = False
    play.key(pygame.K_p)
    assert play.ctrl.message == "Passed."
    play.until(lambda: "plan:roll" in play.ui.keys() and play.combat.turn.hero_id != first)
    name = unit(engine_of(play), play.combat.turn.hero_id).name
    assert play.ctrl.message == f"{name} is up. Roll the dice (R)."


def test_a_message_does_not_follow_the_player_to_another_screen(tmp_path):
    play = Play(tmp_path, ["squire"])
    ctrl = play.ctrl
    ctrl.to_main_menu()
    play.app.frame(0)
    ctrl.open_settings()
    play.app.frame(0)
    said = ctrl.message
    assert said, "opening Settings says how settings are kept"
    play.app.frame(0)
    assert ctrl.message == said, "a message stays while the player stays"
    ctrl.select_settings_tab("aids")
    play.app.frame(0)
    assert ctrl.message == "", "another group of settings: what was said about the last one is over"
    ctrl.warn("Something about this group.")
    play.app.frame(0)
    play.app.frame(0)
    assert ctrl.message == "Something about this group." and ctrl.message_is_error
    ctrl.show_controls()
    play.app.frame(0)
    assert ctrl.message == "" and not ctrl.message_is_error
    ctrl.close_controls()
    ctrl.info("Said on arriving.")  # a message given together with the move belongs to the new place
    play.app.frame(0)
    play.app.frame(0)
    assert ctrl.message == "Said on arriving."


def test_the_pause_menu_does_not_keep_the_battles_message(tmp_path):
    play = Play(tmp_path, ["squire"])
    play.begin()
    play.to_roll_prompt()
    play.key(pygame.K_r)
    assert play.ctrl.message
    play.ctrl.open_pause()
    play.app.frame(0)
    paused = play.ctrl.message
    assert "Paused" in paused, "the pause menu says its own thing"
    play.ctrl.toggle_pause_help()
    play.app.frame(0)
    assert play.ctrl.message == "", "the controls help is another place"
