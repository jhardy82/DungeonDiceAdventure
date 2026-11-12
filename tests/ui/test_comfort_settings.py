"""The comfort and play-aid settings the owner chose on 2026-11-12 (D-31, part 2).

High contrast, battle speed at start, a confirmation before a pass that throws a die away, and a
delay before a control's help text shows. None of them changes a rule of the game.
"""

from __future__ import annotations

import pygame
import pytest

from battle_dice import settings as module
from battle_dice.app.controller import Screen
from battle_dice.settings import Settings
from battle_dice.ui import toolkit
from battle_dice.ui.screens import CATEGORY_COLORS
from battle_dice.ui.toolkit import HIGH_CONTRAST_PALETTE, NORMAL_PALETTE, Theme, contrast_ratio
from tests.ui.test_evolution_ui import Configured, close_every_save  # noqa: F401 - the fixture closes the saves
from tests.ui.test_ui_flow import Play

TEXT_COLOURS = ("TEXT", "DIM", "FAINT", "ACCENT", "HERO", "ENEMY", "GOOD", "BAD", "WARN", "SHIELD", "MANA", "CORRUPT", "GAUGE")
SURFACES = ("BG", "PANEL", "PANEL_ALT", "PANEL_DEEP", "PANEL_DOWN", "BAR")
#: What a button's label is drawn in, on which fill (toolkit.UI.button).
BUTTON_PAIRS = (("TEXT", "BUTTON"), ("TEXT", "BUTTON_HOVER"), ("ACCENT", "BUTTON_SELECTED"), ("FAINT", "BUTTON_DISABLED"), ("DIM", "BUTTON"))


@pytest.fixture(autouse=True)
def the_normal_palette_afterwards():
    """The palette is one for the whole program; a test that switches it puts it back."""
    yield
    toolkit.apply_theme("normal")


# --------------------------------------------------------------------------------------------
# The settings file
# --------------------------------------------------------------------------------------------


def test_the_four_new_settings_have_defaults_that_change_nothing_but_the_pass_question():
    fresh = Settings()
    assert (fresh.high_contrast, fresh.battle_speed, fresh.confirm_pass, fresh.tooltip_delay) == (False, "normal", True, "instant")
    assert module.BATTLE_SPEEDS == ("normal", "fast") and module.TOOLTIP_DELAYS == {"instant": 0, "short": 350, "long": 900}


@pytest.mark.parametrize(("name", "value", "said"), [
    ("high_contrast", "yes", "must be true or false"),
    ("confirm_pass", 1, "must be true or false"),
    ("battle_speed", "slow", "must be one of normal, fast"),
    ("tooltip_delay", 350, "must be one of instant, short, long"),
])
def test_a_value_that_is_not_allowed_is_named_and_its_default_used(tmp_path, name, value, said):
    import json

    file = tmp_path / "settings.json"
    file.write_text(json.dumps({name: value, "battle_speed": "fast" if name != "battle_speed" else value}), encoding="utf-8")
    loaded, problems = module.load(file)
    assert problems == [f"settings.json: {name} {said}; the default is used."]
    assert getattr(loaded, name) == getattr(Settings(), name)
    with pytest.raises(ValueError, match=name):
        module.validate(name, value)


def test_the_new_settings_are_written_and_read_back(tmp_path):
    chosen = Settings(high_contrast=True, battle_speed="fast", confirm_pass=False, tooltip_delay="long")
    file = module.save(chosen, tmp_path / "settings.json")
    again, problems = module.load(file)
    assert problems == [] and again == chosen


# --------------------------------------------------------------------------------------------
# High contrast
# --------------------------------------------------------------------------------------------


def test_every_text_colour_of_the_high_contrast_palette_has_seven_to_one_on_every_surface():
    """Xbox Accessibility Guideline 102 asks for 7:1 in a high-contrast mode."""
    palette = HIGH_CONTRAST_PALETTE
    worst = min((contrast_ratio(palette[text], palette[surface]), text, surface) for text in TEXT_COLOURS for surface in SURFACES)
    assert worst[0] >= 7.0, worst
    for text, fill in BUTTON_PAIRS:
        assert contrast_ratio(palette[text], palette[fill]) >= 7.0, (text, fill)
    assert contrast_ratio(palette["BORDER"], palette["PANEL"]) >= 7.0 and contrast_ratio(palette["FOCUS"], palette["BUTTON"]) >= 7.0
    # The measure itself: black on white is 21, a colour on itself is 1.
    assert round(contrast_ratio((0, 0, 0), (255, 255, 255)), 2) == 21.0 and contrast_ratio((90, 90, 90), (90, 90, 90)) == 1.0


def test_the_normal_palette_is_the_shipped_one():
    assert (NORMAL_PALETTE["BG"], NORMAL_PALETTE["TEXT"], NORMAL_PALETTE["ACCENT"], NORMAL_PALETTE["BUTTON"]) == (
        (18, 20, 26), (232, 235, 241), (242, 193, 78), (52, 60, 80))
    assert set(HIGH_CONTRAST_PALETTE) == set(NORMAL_PALETTE), "both palettes name the same colours"
    assert Theme.NAME == "normal" and Theme.TEXT == NORMAL_PALETTE["TEXT"]


def test_high_contrast_is_switched_in_the_settings_and_the_next_frame_is_drawn_in_it(tmp_path):
    play = Configured(tmp_path)
    play.key(pygame.K_s)
    assert Theme.NAME == "normal"
    play.click("settings:high_contrast")
    play.app.frame(0)
    assert play.saved()["high_contrast"] is True and play.ctrl.message == "High contrast: On."
    assert Theme.NAME == "high_contrast" and Theme.BG == (0, 0, 0) and Theme.TEXT == (255, 255, 255)
    assert CATEGORY_COLORS["attack"] == HIGH_CONTRAST_PALETTE["ENEMY"], "colours looked up by category follow the palette"
    assert tuple(play.app.surface.get_at((2, 300)))[:3] == (0, 0, 0), "the window's background is black"
    play.click("settings:high_contrast")
    play.app.frame(0)
    assert Theme.NAME == "normal" and Theme.BG == (18, 20, 26) and CATEGORY_COLORS["attack"] == NORMAL_PALETTE["ENEMY"]
    assert tuple(play.app.surface.get_at((2, 300)))[:3] == (18, 20, 26) and play.app.render_faults == 0


def test_in_high_contrast_a_battle_has_no_picture_behind_its_cards_and_every_screen_draws(tmp_path):
    play = Configured(tmp_path, settings=Settings(high_contrast=True), fixed_seed=11)
    assert Theme.NAME == "high_contrast", "the setting of the file is in force from the first frame"
    for screen_step in (lambda: play.key(pygame.K_c), lambda: play.key(pygame.K_ESCAPE), lambda: play.key(pygame.K_n),
                        lambda: play.key(pygame.K_1), lambda: play.key(pygame.K_3), lambda: play.key(pygame.K_b)):
        screen_step()
    assert play.ctrl.screen == Screen.BATTLE
    assert tuple(play.app.surface.get_at((20, 400)))[:3] == (0, 0, 0), "no dungeon floor behind the cards"
    # Panels drawn with the toolkit's default colours follow the palette too (they were once fixed at start):
    # the combat log in the middle and the planning panel below.
    assert tuple(play.app.surface.get_at((640, 440)))[:3] == (0, 0, 0) and tuple(play.app.surface.get_at((700, 600)))[:3] == (0, 0, 0)
    play.key(pygame.K_ESCAPE)  # the pause menu over the battle
    play.key(pygame.K_s)
    play.key(pygame.K_ESCAPE)
    assert play.app.render_faults == 0
    normal = Configured(tmp_path / "other", fixed_seed=11)
    assert Theme.NAME == "normal", "a game with default settings is in the shipped palette"
    for key in (pygame.K_n, pygame.K_1, pygame.K_b):
        normal.key(key)
    assert tuple(normal.app.surface.get_at((20, 400)))[:3] != (0, 0, 0), "the shipped battle keeps its dungeon floor"


# --------------------------------------------------------------------------------------------
# Battle speed at start
# --------------------------------------------------------------------------------------------


def test_the_battle_speed_setting_is_the_speed_a_battle_starts_with(tmp_path):
    from battle_dice.app.controller import AppController
    from battle_dice.ui.app import GameApp

    for speed, fast in (("normal", False), ("fast", True)):
        ctrl = AppController(log_dir=tmp_path / speed / "logs", settings=Settings(battle_speed=speed))
        assert GameApp(ctrl, headless=True, animations=False).fast is fast
        ctrl.close()
    play = Configured(tmp_path)
    play.app.fast = False  # the test helper plays fast; this test is about the setting
    play.key(pygame.K_s)
    play.click("settings:battle_speed")
    play.app.frame(0)
    assert play.saved()["battle_speed"] == "fast" and play.app.fast is True and play.ctrl.message == "Battle speed at start: Fast."
    play.click("settings:animation")  # another setting does not touch the speed
    play.app.fast = False             # nor does it undo what F chose during a battle
    play.click("settings:animation")
    play.app.frame(0)
    assert play.app.fast is False
    play.click("settings:battle_speed")
    play.click("settings:battle_speed")
    play.app.frame(0)
    assert play.app.fast is True and play.saved()["battle_speed"] == "fast"


# --------------------------------------------------------------------------------------------
# Confirm a pass
# --------------------------------------------------------------------------------------------


def at_a_roll_where_a_die_can_act(tmp_path, **settings) -> Play:
    play = Play(tmp_path, ["squire"])
    for name, value in settings.items():
        setattr(play.ctrl.settings, name, value)
    play.begin()
    play.to_roll_prompt()
    play.key(pygame.K_r)
    assert play.combat.turn.rolled and play.ctrl._turn_view()["has_legal_action"]  # type: ignore[index]
    return play


def test_pass_asks_once_more_while_a_die_could_act(tmp_path):
    play = at_a_roll_where_a_die_can_act(tmp_path)
    revision = play.ctrl.engine.revision
    play.key(pygame.K_p)
    assert play.ctrl.message == "A die could still act. Press Pass again to pass anyway." and play.ctrl.message_is_error
    assert play.ctrl.engine.revision == revision and play.ctrl.waiting_for_player(), "nothing was sent to the rules"
    play.key(pygame.K_p)
    assert play.ctrl.message == "Passed." and not play.ctrl.waiting_for_player()


def test_the_question_is_asked_again_after_anything_else_was_done(tmp_path):
    play = at_a_roll_where_a_die_can_act(tmp_path)
    play.key(pygame.K_p)
    assert play.ctrl.message_is_error
    play.key(pygame.K_r)  # a reroll: the situation is another one
    assert play.ctrl._turn_view()["has_legal_action"]  # type: ignore[index]
    play.key(pygame.K_p)
    assert play.ctrl.message == "A die could still act. Press Pass again to pass anyway." and play.ctrl.waiting_for_player()


def test_with_the_aid_off_pass_passes_at_once(tmp_path):
    play = at_a_roll_where_a_die_can_act(tmp_path, confirm_pass=False)
    play.key(pygame.K_p)
    assert play.ctrl.message == "Passed." and not play.ctrl.waiting_for_player()


def test_pass_is_not_questioned_when_no_die_can_act(tmp_path, monkeypatch):
    play = at_a_roll_where_a_die_can_act(tmp_path)
    real = play.ctrl._turn_view
    monkeypatch.setattr(play.ctrl, "_turn_view", lambda: {**real(), "has_legal_action": False})  # type: ignore[dict-item]
    play.key(pygame.K_p)
    assert play.ctrl.message == "Passed."


# --------------------------------------------------------------------------------------------
# Help text delay
# --------------------------------------------------------------------------------------------


def status_text(play) -> str:
    return play.ui.status_line(play.ctrl.message, play.ctrl.message_is_error, play.ctrl.message_serial)[0]


def rest_on(play, widget_key: str) -> None:
    """Move the pointer onto a control; no time passes."""
    widget = play.ui.widget(widget_key)
    play.app.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=widget.rect.center, rel=(0, 0), buttons=(0, 0, 0)))
    play.app.frame(0)
    play.app.frame(0)


def test_help_text_waits_until_the_pointer_has_rested(tmp_path):
    play = Configured(tmp_path, settings=Settings(tooltip_delay="short"))
    assert play.ui.tooltip_delay_ms == 350
    rest_on(play, "menu:new")
    tooltip = play.ui.widget("menu:new").tooltip
    assert tooltip and status_text(play) != tooltip, "nothing yet: the pointer has only just arrived"
    play.app.frame(200)
    assert status_text(play) != tooltip
    play.app.frame(200)
    assert status_text(play) == tooltip, "400 ms of rest: the help shows"
    rest_on(play, "menu:controls")  # another control: its rest starts anew
    assert status_text(play) != play.ui.widget("menu:controls").tooltip
    play.app.frame(400)
    assert status_text(play) == play.ui.widget("menu:controls").tooltip


def test_why_a_control_is_off_shows_at_once_and_so_does_help_reached_by_keyboard(tmp_path):
    play = Configured(tmp_path, settings=Settings(tooltip_delay="long"))
    play.key(pygame.K_s)
    play.key(pygame.K_4)
    rest_on(play, "settings:mastery_pace")  # off while Class Evolution is off
    assert status_text(play) == "Unavailable: Switch Class Evolution on first."
    play.key(pygame.K_1)
    play.app.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=(5, 400), rel=(0, 0), buttons=(0, 0, 0)))
    play.app.frame(0)
    play.ui.focus_key = "settings:window_size"  # reached with the keyboard, not the pointer
    play.app.frame(0)
    assert status_text(play) == play.ui.widget("settings:window_size").tooltip


def test_the_delay_is_chosen_in_the_settings_and_none_is_the_default(tmp_path):
    play = Configured(tmp_path)
    assert play.ui.tooltip_delay_ms == 0
    rest_on(play, "menu:new")
    assert status_text(play) == play.ui.widget("menu:new").tooltip, "by default help shows at once, as it always did"
    play.key(pygame.K_s)
    play.key(pygame.K_2)
    play.click("settings:tooltip_delay")
    play.app.frame(0)
    assert play.saved()["tooltip_delay"] == "short" and play.ui.tooltip_delay_ms == 350 and play.ctrl.message == "Help text delay: Short."
    play.click("settings:tooltip_delay")
    play.app.frame(0)
    assert play.saved()["tooltip_delay"] == "long" and play.ui.tooltip_delay_ms == 900
    play.click("settings:confirm_pass")
    assert play.saved()["confirm_pass"] is False and play.ctrl.message == "Confirm a pass: Off."
