"""Headless UI smoke tests: every required screen, by mouse and by keyboard only (AC-19).

The driver sends real pygame events through ``GameApp.handle_event``. Mouse mode clicks widget
centres; keyboard mode presses Tab until the widget has focus and then Enter, so the whole core
loop is proven operable without a pointer.
"""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402
import pytest  # noqa: E402

from battle_dice.app.controller import AppController, Screen  # noqa: E402
from battle_dice.core.events import state_hash  # noqa: E402
from battle_dice.core.models import RunPhase  # noqa: E402
from battle_dice.ui.app import GameApp  # noqa: E402
from battle_dice.ui.toolkit import MIN_H, MIN_W  # noqa: E402


class Driver:
    def __init__(self, tmp_path, size=(1280, 720), keyboard=False, seed=7):
        self.ctrl = AppController(fixed_seed=seed, log_dir=tmp_path / "logs")
        self.app = GameApp(self.ctrl, size=size, headless=True)
        self.app.fast = True
        self.keyboard = keyboard
        self.screens_seen = {self.ctrl.screen}
        self.panels_seen: set[str] = set()

    def key(self, key, mod=0):
        self.app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=mod, unicode=""))
        self.app.frame(0)
        self.screens_seen.add(self.ctrl.screen)

    def press(self, widget_key):
        ui = self.app.ui
        widget = ui.widget(widget_key)
        assert widget is not None, f"{widget_key} not on screen; have {ui.keys()}"
        if self.keyboard:
            for _ in range(len(ui.widgets) + 1):
                if ui.focus_key == widget_key:
                    break
                self.app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB, mod=0, unicode=""))
            assert ui.focus_key == widget_key, "Tab navigation could not reach the control"
            self.app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0, unicode=""))
        else:
            self.app.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=widget.rect.center, rel=(0, 0), buttons=(0, 0, 0)))
            self.app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=widget.rect.center, button=1))
        self.app.frame(0)
        self.screens_seen.add(self.ctrl.screen)

    def enabled(self, prefix, suffix=""):
        ui = self.app.ui
        return [k for k in ui.keys(prefix) if k.endswith(suffix) and ui.widget(k).enabled]

    def run_to_input(self):
        for _ in range(5000):
            if self.ctrl.screen != Screen.BATTLE or self.ctrl.waiting_for_player():
                break
            self.app.frame(100)
        self.app.frame(0)
        self.screens_seen.add(self.ctrl.screen)

    def take_turn(self):
        """One player decision on the battle screen, made only through visible controls."""
        keys = self.app.ui.keys()
        if "plan:roll" in keys:
            self.panels_seen.add("roll")
            self.press("plan:roll")
            return
        if "react:skip" in keys:
            self.panels_seen.add("reaction")
            options = [k for k in self.enabled("react:") if k != "react:skip"]
            self.press(options[0] if options else "react:skip")
            return
        self.panels_seen.add("planner")
        for use in self.enabled("die:", ":use"):
            self.press(use)
            if self.ctrl.targeting_die is not None:
                self.panels_seen.add("targeting")
                targets = [k for k in self.enabled("unit:") if self.app.ui.widget(k).action is not None]
                self.press(targets[0])
            if self.ctrl.confirm_problem() is None:
                self.press("plan:confirm")
                return
            self.press("plan:clear")
        self.press("plan:pass")

    def play_battle(self, limit=600):
        for _ in range(limit):
            self.run_to_input()
            if self.ctrl.screen != Screen.BATTLE:
                return
            self.take_turn()
        raise AssertionError("battle did not finish")

    def weaken_enemies(self):
        """Arrange: leave every enemy at 1 HP so the scripted player wins quickly."""
        for enemy in self.ctrl.engine.combat.side("enemy"):
            enemy.hp = 1

    def cripple_heroes(self):
        """Arrange: leave every hero at 1 HP with no mana so the scripted player loses."""
        for hero in self.ctrl.engine.combat.side("hero"):
            hero.hp, hero.mana, hero.shields = 1, 0, 0


def start_party(driver, classes=("squire", "apprentice", "scout")):
    driver.press("menu:new")
    assert driver.ctrl.screen == Screen.PARTY_SETUP
    for class_id in classes:
        driver.press(f"add:{class_id}")
    assert [m["class_id"] for m in driver.ctrl.party] == list(classes)


def colours(surface) -> int:
    width, height = surface.get_size()
    return len({tuple(surface.get_at((x, y)))[:3] for x in range(0, width, 16) for y in range(0, height, 16)})


@pytest.mark.parametrize("size, keyboard", [((1280, 720), False), ((960, 540), True)])
def test_full_victory_run_through_every_screen(tmp_path, size, keyboard):
    driver = Driver(tmp_path, size=size, keyboard=keyboard)
    assert driver.app.surface.get_size() == size

    driver.press("menu:controls")
    assert driver.ctrl.screen == Screen.CONTROLS
    driver.press("controls:back")
    start_party(driver)

    driver.press("slot:2:row")  # Scout: back -> front
    assert driver.ctrl.party[2]["row"] == "front"
    driver.press("slot:2:row")
    driver.press("add:scout")
    driver.press("slot:3:remove")
    assert len(driver.ctrl.party) == 3
    assert colours(driver.app.surface) > 8

    driver.press("party:begin")
    assert driver.ctrl.screen == Screen.BATTLE and driver.ctrl.engine.state.phase == RunPhase.BATTLE

    # A few real decisions first, so the reaction panel and targeting are exercised at full strength.
    for _ in range(14):
        driver.run_to_input()
        if driver.ctrl.screen != Screen.BATTLE:
            break
        driver.take_turn()
    assert {"roll", "planner"} <= driver.panels_seen
    assert colours(driver.app.surface) > 12

    if driver.ctrl.screen == Screen.BATTLE:
        driver.weaken_enemies()
        driver.play_battle()
    assert driver.ctrl.screen == Screen.UPGRADE, driver.ctrl.engine.state.outcome

    # Mandatory upgrade: Start Battle 2 is disabled, with a reason, until a card is applied.
    start = driver.app.ui.widget("up:start")
    assert not start.enabled and "upgrade must be applied" in start.reason
    driver.press("up:start")
    assert driver.ctrl.message_is_error and driver.ctrl.screen == Screen.UPGRADE
    driver.press("up:hero:h02")
    driver.press("up:hero:h01")
    driver.press("up:die:oath_d4")
    driver.press("up:die:iron_d6")
    apply = driver.app.ui.widget("up:apply")
    assert not apply.enabled and "Select one" in apply.reason
    driver.press("up:offer:0")
    driver.press("up:apply")
    assert len(driver.ctrl.engine.state.upgrades) == 1

    locked = driver.app.ui.widget("up:swap:h01:iron_d6")
    assert not locked.enabled and "locked" in locked.reason
    driver.press("up:swap:h01:oath_d4")
    assert driver.ctrl.engine.combat.combatants["h01"].equipped_dice_ids == ["iron_d6", "bulwark_d4"]
    driver.press("up:row:h03")
    assert driver.ctrl.engine.combat.combatants["h03"].row == "front"
    driver.press("up:start")
    assert driver.ctrl.screen == Screen.BATTLE and driver.ctrl.engine.state.encounter_index == 1

    driver.run_to_input()
    driver.weaken_enemies()
    driver.play_battle()
    assert driver.ctrl.screen == Screen.OUTCOME and driver.ctrl.engine.state.outcome == "victory"
    assert driver.ctrl.log_path is not None and driver.ctrl.log_path.exists()
    assert driver.ctrl.log_path.read_text(encoding="utf-8").count("\n") == len(driver.ctrl.engine.events) + 1
    assert colours(driver.app.surface) > 6

    driver.press("out:retry")
    assert driver.ctrl.screen == Screen.BATTLE
    assert driver.ctrl.engine.state.encounter_index == 0 and driver.ctrl.engine.state.upgrades == []
    assert driver.screens_seen >= {Screen.MAIN_MENU, Screen.CONTROLS, Screen.PARTY_SETUP, Screen.BATTLE, Screen.UPGRADE, Screen.OUTCOME}


@pytest.mark.parametrize("keyboard", [False, True])
def test_defeat_summary_offers_retry_and_modify_party(tmp_path, keyboard):
    driver = Driver(tmp_path, keyboard=keyboard, seed=3)
    start_party(driver, ("apprentice", "scout"))
    driver.press("party:begin")
    driver.run_to_input()
    driver.cripple_heroes()
    for _ in range(400):
        driver.run_to_input()
        if driver.ctrl.screen != Screen.BATTLE:
            break
        keys = driver.app.ui.keys()
        if "plan:roll" in keys:
            driver.press("plan:roll")
        elif "react:skip" in keys:
            driver.press("react:skip")
        else:
            driver.press("plan:pass")
    assert driver.ctrl.screen == Screen.OUTCOME and driver.ctrl.engine.state.outcome == "defeat"
    driver.press("out:modify")
    assert driver.ctrl.screen == Screen.PARTY_SETUP and len(driver.ctrl.party) == 2
    driver.press("party:begin")
    assert driver.ctrl.screen == Screen.BATTLE and driver.ctrl.engine.state.encounter_index == 0


def test_hotkeys_drive_the_core_loop(tmp_path):
    driver = Driver(tmp_path, seed=11)
    driver.key(pygame.K_n)
    driver.key(pygame.K_1)
    driver.key(pygame.K_3)
    assert [m["class_id"] for m in driver.ctrl.party] == ["squire", "scout"]
    driver.key(pygame.K_b)
    assert driver.ctrl.screen == Screen.BATTLE
    for _ in range(40):
        driver.run_to_input()
        if "plan:roll" in driver.app.ui.keys():
            break
        if "react:skip" in driver.app.ui.keys():
            driver.key(pygame.K_s)
    driver.key(pygame.K_r)  # roll
    turn = driver.ctrl.engine.combat.turn
    assert turn is not None and turn.rolled
    driver.key(pygame.K_z)  # keep die 1
    assert len(driver.ctrl.engine.combat.turn.kept) == 1
    driver.key(pygame.K_r)  # reroll the other die
    assert driver.ctrl.engine.combat.turn.rerolls_remaining == 1
    driver.key(pygame.K_p)  # pass
    assert driver.ctrl.engine.combat.turn is None or driver.ctrl.engine.combat.turn.committed


def test_disabled_controls_explain_why(tmp_path):
    driver = Driver(tmp_path)
    driver.press("menu:new")
    begin = driver.app.ui.widget("party:begin")
    assert not begin.enabled and begin.reason == "Add at least 1 hero to begin."
    driver.press("party:begin")
    assert driver.ctrl.screen == Screen.PARTY_SETUP
    assert driver.ctrl.message_is_error and "at least 1 hero" in driver.ctrl.message
    driver.app.frame(0)
    text, is_error = driver.app.ui.status_text()
    assert is_error and text.startswith("Unavailable: Add at least 1 hero")
    for _ in range(5):
        driver.press("add:squire")
    add = driver.app.ui.widget("add:squire")
    assert not add.enabled and "already has 5 heroes" in add.reason


def test_window_never_goes_below_the_minimum_size(tmp_path):
    driver = Driver(tmp_path)
    driver.app.handle_event(pygame.event.Event(pygame.VIDEORESIZE, w=640, h=300, size=(640, 300)))
    driver.app.frame(0)
    assert driver.app.surface.get_size() == (MIN_W, MIN_H)
    assert driver.app.ui.widget("menu:new") is not None
    driver.app.handle_event(pygame.event.Event(pygame.VIDEORESIZE, w=1600, h=900, size=(1600, 900)))
    driver.app.frame(0)
    assert driver.app.surface.get_size() == (1600, 900)
    assert driver.app.ui.scale == pytest.approx(1.25)


def test_rendering_never_mutates_state_or_draws_random_numbers(tmp_path):
    driver = Driver(tmp_path)
    start_party(driver)
    driver.press("party:begin")
    driver.run_to_input()
    engine = driver.ctrl.engine
    before = (state_hash(engine.state), len(engine.events), len(engine.command_log))
    for _ in range(30):
        driver.app.frame(16)
        driver.app.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=(300, 600), rel=(1, 1), buttons=(0, 0, 0)))
    assert (state_hash(engine.state), len(engine.events), len(engine.command_log)) == before


def test_unhandled_engine_error_shows_a_recoverable_screen(tmp_path, monkeypatch):
    driver = Driver(tmp_path)
    start_party(driver, ("squire",))
    driver.press("party:begin")
    driver.run_to_input()

    def boom(*args, **kwargs):
        raise RuntimeError("simulated engine fault")

    monkeypatch.setattr(driver.ctrl.engine, "do", boom)
    driver.ctrl.roll()
    driver.app.frame(0)
    assert driver.ctrl.screen == Screen.ERROR and "simulated engine fault" in driver.ctrl.error_text
    driver.press("error:menu")
    assert driver.ctrl.screen == Screen.MAIN_MENU and driver.ctrl.engine is None
    driver.press("menu:new")
    assert driver.ctrl.screen == Screen.PARTY_SETUP


def test_planner_stays_usable_if_a_plan_was_set_but_not_committed(tmp_path):
    """ACTION_PLAN is an input phase: the planner must still be shown so the player is never stuck."""
    driver = Driver(tmp_path, seed=11)
    start_party(driver, ("squire",))
    driver.press("party:begin")
    for _ in range(40):
        driver.run_to_input()
        if "plan:roll" in driver.app.ui.keys():
            break
        driver.press("react:skip")
    driver.press("plan:roll")
    assert driver.ctrl.engine.do("SetActionPlan", actions=[]).accepted  # plan set, commit never sent
    driver.app.frame(0)
    assert driver.ctrl.waiting_for_player()
    assert {"plan:confirm", "plan:pass"} <= set(driver.app.ui.keys())
    driver.press("plan:pass")
    assert driver.ctrl.engine.combat.turn is None or driver.ctrl.engine.combat.turn.committed
