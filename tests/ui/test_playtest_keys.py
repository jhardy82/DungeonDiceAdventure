"""Keys, safeguards and reach: fixes for the playtest of 2026-11-21, batch 2 (owner decision D-34).

- A number key never takes an action out of the plan; a target the game picked is named.
- What cannot be undone is asked for once more, or confirmed by a separate button.
- What the keyboard can do, the mouse can do: the dice seed, the battle speed, motion.
"""

from __future__ import annotations

import pygame

from battle_dice.app.controller import AppController, Screen
from battle_dice.core.engine import Engine
from battle_dice.core.models import STATE_DEFEATED
from battle_dice.settings import Settings
from battle_dice.ui import screens
from battle_dice.ui.app import GameApp
from tests.conftest import down, enemies, force_slash, unit
from tests.ui.test_evolution_ui import Configured, close_every_save  # noqa: F401 - the fixture closes the saves
from tests.ui.test_ui_flow import Play, record_text


def engine_of(play: Play) -> Engine:
    engine = play.ctrl.engine
    assert engine is not None
    return engine


def at_the_outcome(play: Play) -> None:
    """Lose the run quickly: every hero goes down."""
    play.begin()
    play.to_roll_prompt()
    for hero in play.combat.side("hero"):
        down(engine_of(play), hero.id)
    play.ctrl.settings.confirm_pass = False
    play.ctrl.pass_turn()
    play.until(lambda: False)
    assert play.ctrl.screen == Screen.OUTCOME


# --------------------------------------------------------------------------------------------
# K1, K2: dice and targets
# --------------------------------------------------------------------------------------------


def test_a_number_key_never_takes_an_action_out_of_the_plan(tmp_path):
    play = Play(tmp_path, ["squire"])
    play.begin()
    play.to_roll_prompt()
    foes = enemies(engine_of(play))
    for foe in foes[1:]:
        foe.hp, foe.state = 0, STATE_DEFEATED
    play.roll_faces(iron_d6=1, oath_d4=4)  # Strike
    play.key(pygame.K_1)
    planned = [{"die_id": "iron_d6", "target_ids": [foes[0].id]}]
    assert play.ctrl.draft == planned and play.ctrl.targeting_die is None
    # The only legal target was taken without asking, and the status line says so.
    assert play.ctrl.message.startswith(f"Strike aims at {foes[0].name}, the only legal target. ")
    play.key(pygame.K_1)  # the second half of "die, then target", pressed out of habit
    assert play.ctrl.draft == planned, "the action stays in the plan"
    assert "already in the plan" in play.ctrl.message and "Remove button" in play.ctrl.message
    play.click("die:iron_d6:use")  # the Remove button itself still removes
    assert play.ctrl.draft == [] and play.ctrl.message == "Action removed from the plan."
    play.key(pygame.K_1)
    play.key(pygame.K_c)  # and so does Clear
    assert play.ctrl.draft == []


def test_with_several_targets_the_game_asks_and_names_nothing_itself(tmp_path, monkeypatch):
    play = Play(tmp_path, ["scout", "squire"])
    play.begin()
    play.until(lambda: "plan:roll" in play.ui.keys() and play.combat.turn.hero_id == "h01")
    assert len(enemies(engine_of(play))) >= 2
    play.roll_faces(striker_d8=1, tools_d4=4)  # Shot: a ranged attack, so every enemy is a legal target
    play.key(pygame.K_1)
    assert play.ctrl.targeting_die == "striker_d8" and play.ctrl.draft == []
    # While a target is chosen the numbers belong to the targets: the die's button is left with Esc (playtest K2).
    button = play.ui.widget("die:striker_d8:use")
    assert button.hotkeys == ()
    drawn, _ = record_text(monkeypatch)
    play.app.frame(0)
    assert "Cancel" in drawn and "(Esc)" in drawn
    play.key(pygame.K_2)
    assert len(play.ctrl.draft) == 1 and "only legal target" not in play.ctrl.message
    play.key(pygame.K_1)
    assert len(play.ctrl.draft) == 1, "still planned"


# --------------------------------------------------------------------------------------------
# K4: an ally's number is its place in the party
# --------------------------------------------------------------------------------------------


def test_target_numbers_of_allies_are_their_places_in_the_party():
    assert screens.target_numbers_of(["h01", "h03"]) == {"h01": 1, "h03": 3}
    assert screens.target_numbers_of(["h03", "h02"]) == {"h03": 3, "h02": 2}
    assert screens.target_numbers_of(["b1_e02", "b1_e03"]) == {"b1_e02": 1, "b1_e03": 2}
    assert screens.target_numbers_of([]) == {}
    assert screens.party_number("h05") == 5 and screens.party_number("b1_e01") is None and screens.party_number("hx") is None


def test_an_allys_key_follows_its_name_when_another_hero_is_down(tmp_path):
    play = Play(tmp_path, ["squire", "scout", "apprentice"])
    play.begin()
    play.until(lambda: "plan:roll" in play.ui.keys() and play.combat.turn.hero_id == "h01")
    engine = engine_of(play)
    down(engine, "h02")
    play.roll_faces(iron_d6=3, oath_d4=4)  # Guard: a shield for one standing ally
    play.key(pygame.K_1)
    assert play.ctrl.targeting_die == "iron_d6"
    keys = {w.key: w.hotkeys for w in play.ui.widgets if w.key.startswith("unit:h")}
    assert keys == {"unit:h01": (pygame.K_1,), "unit:h02": (), "unit:h03": (pygame.K_3,)}, "Apprentice 3 is key 3"
    play.key(pygame.K_2)  # the downed Scout 2 cannot be shielded: nothing is planned
    assert play.ctrl.draft == []
    play.key(pygame.K_3)
    assert play.ctrl.draft == [{"die_id": "iron_d6", "target_ids": ["h03"]}]


# --------------------------------------------------------------------------------------------
# K1 (second half), S3: reactions
# --------------------------------------------------------------------------------------------


def reacting(tmp_path) -> Play:
    """A Squire and an Apprentice face a Slash on the Squire: Interpose in the Guard stage, Grounding in the next."""
    play = Play(tmp_path, ["squire", "apprentice"])
    play.begin()
    engine = engine_of(play)
    force_slash(engine)
    for hero_id in ("h01", "h02"):
        unit(engine, hero_id).corruption = 2
        unit(engine, hero_id).mana = 1
    play.until(lambda: play.ui.widget("react:h01") is not None and play.ui.widget("react:h01").enabled)
    return play


def test_a_second_reaction_on_the_same_enemy_action_is_asked_for_once_more(tmp_path):
    play = reacting(tmp_path)
    combat = play.combat
    target = unit(engine_of(play), combat.committed_intent.committed_target_ids[0]).name
    assert len(combat.reactions_used) == 0
    play.key(pygame.K_1)  # the first reaction on this enemy action: used at once
    assert len(combat.reactions_used) == 1
    assert play.ctrl.message.startswith(f"Interpose used on {target}, the only ally it can be used on. Another reaction is possible: ")
    assert play.ui.widget("react:h02") is not None and play.ui.widget("react:h02").enabled, "the Resource stage is open"
    play.key(pygame.K_1)  # "row, then ally" out of habit, or a second click on the same spot
    assert len(combat.reactions_used) == 1, "the press did not spend another reaction"
    assert play.ctrl.message == "A reaction was just used on this enemy action. Press again to use Grounding as well."
    play.key(pygame.K_1)
    assert len(combat.reactions_used) == 2 and play.ctrl.message.startswith("Grounding used on ")


def test_the_question_is_per_enemy_action_and_ends_when_something_else_is_done(tmp_path):
    play = reacting(tmp_path)
    first_intent = play.combat.committed_intent.id
    play.key(pygame.K_1)
    play.key(pygame.K_1)  # asked
    assert play.ctrl.asked("react:h02")
    play.key(pygame.K_s)  # the stage is skipped instead: the question is over
    assert not play.ctrl.asked("react:h02")
    for hero_id in ("h01", "h02"):
        hero = unit(engine_of(play), hero_id)
        hero.hp, hero.mana, hero.corruption = hero.max_hp, 1, 2
    play.until(lambda: play.ui.widget("react:h01") is not None and play.ui.widget("react:h01").enabled
               and play.combat.committed_intent.id != first_intent)
    assert play.combat.reactions_used == []
    play.key(pygame.K_1)  # a new enemy action: its first reaction needs one press again
    assert len(play.combat.reactions_used) == 1 and play.ctrl.message.startswith("Interpose used on ")


# --------------------------------------------------------------------------------------------
# K3, S1: retry and abandon ask once more
# --------------------------------------------------------------------------------------------


def test_retry_needs_a_second_press_so_one_r_too_many_keeps_the_result(tmp_path, monkeypatch):
    play = Play(tmp_path, ["squire"])
    at_the_outcome(play)
    engine = play.ctrl.engine
    play.key(pygame.K_r)
    assert play.ctrl.screen == Screen.OUTCOME and play.ctrl.engine is engine, "the result is still there"
    assert play.ctrl.message == "Press Retry again to start a new run with this party. This result will be gone."
    drawn, _ = record_text(monkeypatch)
    play.app.frame(0)
    assert "Press again: new run  (R)" in drawn and "Retry Same Party  (R)" not in drawn
    play.ctrl.info("Something else was said.")  # anything in between ends the question
    play.app.frame(0)
    play.key(pygame.K_r)
    assert play.ctrl.screen == Screen.OUTCOME and play.ctrl.engine is engine
    play.key(pygame.K_r)
    assert play.ctrl.screen == Screen.BATTLE and play.ctrl.engine is not engine


def test_enter_on_the_outcome_screen_is_asked_once_more_too(tmp_path):
    play = Play(tmp_path, ["squire"])
    at_the_outcome(play)
    play.key(pygame.K_RETURN)
    assert play.ctrl.screen == Screen.OUTCOME
    play.key(pygame.K_RETURN)
    assert play.ctrl.screen == Screen.BATTLE


def test_abandoning_a_run_is_asked_once_more_and_the_other_button_does_not_answer(tmp_path, monkeypatch):
    play = Play(tmp_path, ["squire", "scout"])
    play.begin()
    play.click("battle:menu")
    play.click("pause:party")
    assert play.ctrl.paused and play.ctrl.engine is not None and play.ctrl.asked("abandon:party")
    drawn, _ = record_text(monkeypatch)
    play.app.frame(0)
    assert drawn.count("Press again: abandon, change party") == 1 and "Abandon Run: Main Menu" in drawn, "the armed button still says where it leads"
    play.click("pause:menu")  # the other way of abandoning is its own question
    assert play.ctrl.paused and play.ctrl.engine is not None and play.ctrl.asked("abandon:menu") and not play.ctrl.asked("abandon:party")
    play.click("pause:resume")
    assert not play.ctrl.paused and not play.ctrl.asked("abandon:menu")
    play.click("battle:menu")
    play.click("pause:menu")
    assert play.ctrl.engine is not None, "resuming ended the question"
    play.click("pause:menu")
    assert play.ctrl.screen == Screen.MAIN_MENU and play.ctrl.engine is None and play.ctrl.message == "Run abandoned."


def test_leaving_for_another_place_ends_a_question(tmp_path):
    play = Play(tmp_path, ["squire"])
    play.begin()
    play.click("battle:menu")
    play.click("pause:party")
    play.ctrl.toggle_pause_help()  # the controls help: another place, nothing new is said
    play.app.frame(0)
    play.ctrl.toggle_pause_help()
    play.app.frame(0)
    assert not play.ctrl.asked("abandon:party")
    play.click("pause:party")
    assert play.ctrl.engine is not None


# --------------------------------------------------------------------------------------------
# A1, D18, D19: the dice seed with the mouse
# --------------------------------------------------------------------------------------------


def test_a_seed_can_be_set_with_the_mouse_alone(tmp_path):
    play = Configured(tmp_path)
    play.click("menu:new")
    assert play.ui.widget("seed:1") is None, "the pad is there only while a seed is typed"
    play.click("party:seed")
    assert play.ctrl.seed_entry == "" and {f"seed:{digit}" for digit in "0123456789"} <= set(play.ui.keys())
    for key in ("seed:4", "seed:2", "seed:0", "seed:backspace", "seed:7"):
        play.click(key)
    assert play.ctrl.seed_entry == "427"
    play.click("seed:enter")
    assert play.ctrl.seed_entry is None and play.ctrl.fixed_seed == 427 and play.saved()["seed"] == 427
    assert play.ui.widget("seed:1") is None
    play.click("party:seed")  # a fixed seed: one click makes it random again
    assert play.ctrl.fixed_seed is None
    play.click("party:seed")
    play.click("seed:9")
    play.click("seed:escape")
    assert play.ctrl.seed_entry is None and play.ctrl.fixed_seed is None and play.ctrl.message == "Seed entry cancelled."


def test_the_pad_is_on_top_of_what_lies_under_it(tmp_path):
    play = Configured(tmp_path)
    play.click("menu:new")
    play.click("party:seed")
    pad = play.ui.widget("seed:pad")
    assert pad is not None and pad.action is None
    for key in [f"seed:{digit}" for digit in "0123456789"] + ["seed:backspace", "seed:enter", "seed:escape"]:
        rect = play.ui.widget(key).rect
        assert pad.rect.contains(rect), key
        hit = next(w for w in reversed(play.ui.widgets) if w.rect.collidepoint(rect.center))
        assert hit.key == key, "a click on the button reaches the button"
    below = [w.key for w in play.ui.widgets if not w.key.startswith(("seed:", "party:seed")) and w.rect.colliderect(pad.rect)]
    for key in below:
        centre = play.ui.widget(key).rect.clip(pad.rect).center
        hit = next(w for w in reversed(play.ui.widgets) if w.rect.collidepoint(centre))
        assert hit.key.startswith("seed:"), f"{key} cannot be clicked through the pad"


def test_a_seed_fixed_by_a_launch_option_does_not_offer_a_key_that_is_refused(tmp_path):
    ctrl = AppController(log_dir=tmp_path / "logs", fixed_seed=5)
    view = ctrl.seed_view()
    assert view["hint"] == "set by a launch flag" and view["reason"] and "press D" not in view["hint"]
    assert AppController(log_dir=tmp_path / "other").seed_view()["hint"] == "press D to type a seed"


def test_the_main_menu_no_longer_promises_the_seed_under_settings(tmp_path):
    play = Configured(tmp_path)
    assert "seed" not in (play.ui.widget("menu:settings").tooltip or "")  # the seed lives on the New Run screen


# --------------------------------------------------------------------------------------------
# A2, D8, D9, M12: speed, motion and the window
# --------------------------------------------------------------------------------------------


def test_speed_and_motion_are_buttons_in_a_battle_and_are_the_settings_themselves(tmp_path):
    play = Configured(tmp_path, fixed_seed=11)
    play.ctrl.new_run()
    play.ctrl.add_hero("squire")
    play.app.frame(0)
    play.begin()
    play.app.fast = False
    assert play.ctrl.settings.battle_speed == "normal" and play.ctrl.settings.animation is True
    play.click("battle:speed")
    assert play.app.fast is True and play.saved()["battle_speed"] == "fast" and play.ctrl.message == "Battle speed: Fast."
    play.click("battle:motion")
    assert play.ui.anim.enabled is False and play.saved()["animation"] is False
    # Settings shows the same, and a change of another setting leaves both alone (playtest D8).
    play.click("battle:menu")
    play.click("pause:settings")
    rows = {row["key"]: row["value"] for row in play.ctrl.settings_view()}
    assert rows["battle_speed"] == "Fast" and rows["animation"] == "Off (reduced motion)"
    play.click("settings:high_contrast")
    play.app.frame(0)
    assert play.ui.anim.enabled is False and play.app.fast is True
    play.key(pygame.K_ESCAPE)
    play.click("pause:resume")
    play.key(pygame.K_m)
    play.key(pygame.K_f)
    assert play.ui.anim.enabled is True and play.app.fast is False
    assert play.saved()["animation"] is True and play.saved()["battle_speed"] == "normal"


def test_only_the_window_size_setting_resizes_the_window(tmp_path):
    ctrl = AppController(log_dir=tmp_path / "logs", settings=Settings(), settings_path=tmp_path / "settings.json")
    app = GameApp(ctrl, size=(960, 540), headless=True, animations=False)  # sized by the launch option
    app.frame(0)
    ctrl.open_settings()
    ctrl.change_setting("high_contrast")
    app.frame(0)
    assert app.surface.get_size() == (960, 540), "another setting leaves the window as it is (playtest D9)"
    ctrl.change_setting("window_size")
    app.frame(0)
    assert app.surface.get_size() == ctrl.settings.size() != (960, 540)
    ctrl.close()


# --------------------------------------------------------------------------------------------
# K6: the controls help says what the keys do
# --------------------------------------------------------------------------------------------


def test_the_controls_help_matches_what_esc_and_a_hotkey_do(tmp_path):
    everywhere = dict(screens.CONTROLS_TEXT)["Everywhere"]
    assert "Esc clears it" not in everywhere and "never move the ring" not in everywhere
    assert "A hotkey or a click takes the ring away." in everywhere and "Esc goes back" in everywhere
    play = Play(tmp_path, ["squire"])
    play.key(pygame.K_TAB)
    assert play.ui.focus_key is not None
    play.key(pygame.K_1)  # a hotkey of the party screen: the ring is gone, as the help says
    assert play.ui.focus_key is None
    play.key(pygame.K_TAB)
    assert play.ui.focus_key is not None
    play.key(pygame.K_ESCAPE)  # Esc goes back
    assert play.ctrl.screen == Screen.MAIN_MENU and play.ui.focus_key is None


# --------------------------------------------------------------------------------------------
# Three cases the deliberate breaks showed were not tested
# --------------------------------------------------------------------------------------------


def test_a_key_action_does_not_run_on_a_control_that_is_off():
    from battle_dice.ui.toolkit import UI

    ui = UI()
    ui.begin(pygame.Surface((1280, 720)))
    pressed: list[str] = []
    refused: list[str] = []
    ui.on_disabled = refused.append
    ui.button("a", 10, 10, 100, 40, "A", lambda: pressed.append("click"), enabled=False, reason="Not now.",
              hotkeys=(pygame.K_1,), key_action=lambda: pressed.append("key"))
    ui.button("b", 10, 60, 100, 40, "B", lambda: pressed.append("click"), hotkeys=(pygame.K_2,), key_action=lambda: pressed.append("key"))
    ui.button("c", 10, 110, 100, 40, "C", lambda: pressed.append("click"), hotkeys=(pygame.K_3,))
    ui.end()
    for key in (pygame.K_1, pygame.K_2, pygame.K_3):
        ui.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode=""))
    assert refused == ["Not now."], "a control that is off gives its reason, whatever its key would do"
    assert pressed == ["key", "click"], "a key does its own action where there is one, else what the click does"
    ui.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=ui.widget("b").rect.center, button=1))
    assert pressed == ["key", "click", "click"], "a click never runs the key's action"


def test_a_list_of_heroes_and_enemies_is_numbered_in_its_own_order():
    assert screens.target_numbers_of(["h02", "b1_e01"]) == {"h02": 1, "b1_e01": 2}


def test_the_seed_pad_is_on_the_party_screen_of_saved_heroes_too(tmp_path):
    play = Configured(tmp_path, settings=Settings(class_evolution=True))
    play.click("menu:new")
    assert play.ctrl.progression is not None and play.ui.widget("seed:1") is None
    play.click("party:seed")
    for key in ("seed:3", "seed:1", "seed:enter"):
        play.click(key)
    assert play.ctrl.fixed_seed == 31
