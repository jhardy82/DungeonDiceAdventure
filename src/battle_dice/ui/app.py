"""Pygame-ce application shell: window, event loop, pacing of automatic combat steps.

Rendering code never draws random numbers and never mutates rules state; it only calls
controller methods in response to input and a pacing timer.
"""

from __future__ import annotations

import os

import pygame

from battle_dice.app.controller import AppController, Screen
from battle_dice.ui import screens
from battle_dice.ui.toolkit import LOGICAL_H, LOGICAL_W, MIN_H, MIN_W, UI

STEP_DELAY_MS = 260
FAST_DELAY_MS = 25


class GameApp:
    def __init__(self, controller: AppController | None = None, size: tuple[int, int] = (LOGICAL_W, LOGICAL_H),
                 headless: bool = False, animations: bool = True):
        if headless:
            for variable in ("SDL_VIDEODRIVER", "SDL_AUDIODRIVER"):
                if not os.environ.get(variable):
                    os.environ[variable] = "dummy"
        pygame.display.init()
        pygame.font.init()
        self.controller = controller or AppController()
        self.ui = UI()
        self.ui.on_disabled = self.controller.warn
        self.ui.anim.enabled = animations
        self.running = True
        self.fast = False
        self._timer = 0.0
        self.render_faults = 0  # frames whose drawing raised; the smoke test requires this to stay 0
        self.headless = headless
        self.surface = self._set_mode(size)
        pygame.display.set_caption("Battle Dice")
        self.draw()

    def _set_mode(self, size: tuple[int, int]) -> pygame.Surface:
        width, height = max(MIN_W, size[0]), max(MIN_H, size[1])
        return pygame.display.set_mode((width, height), pygame.RESIZABLE)

    def quit(self) -> None:
        self.running = False

    # -- input -------------------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.QUIT:
            self.quit()
            return
        if event.type == pygame.VIDEORESIZE:
            self.surface = self._set_mode((event.w, event.h))
            return
        try:
            self._route(event)
        except Exception:  # noqa: BLE001 - an input fault must reach the error screen, not close the window
            self.controller.fail()

    def _route(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and self.controller.screen == Screen.BATTLE and not self.controller.paused:
            if event.key == pygame.K_f:
                self.fast = not self.fast
                self.controller.info("Fast mode on." if self.fast else "Fast mode off.")
                return
            if event.key == pygame.K_m:
                self.ui.anim.enabled = not self.ui.anim.enabled
                self.controller.info("Animation on." if self.ui.anim.enabled else "Animation off (reduced motion).")
                return
            if event.key == pygame.K_SPACE and not self.controller.waiting_for_player():
                self._timer = 1e9  # step on the next update
                return
        self.ui.handle_event(event)

    # -- update and draw ---------------------------------------------------------------------

    def update(self, dt_ms: float) -> None:
        controller = self.controller
        try:
            self._animate(dt_ms)
        except Exception:  # noqa: BLE001 - an animation fault must reach the error screen
            controller.fail()
            return
        if controller.screen == Screen.BATTLE and not controller.waiting_for_player():
            self._timer += dt_ms
            delay = FAST_DELAY_MS if self.fast else STEP_DELAY_MS
            if self._timer >= delay:
                self._timer = 0.0
                controller.auto_advance()
        else:
            self._timer = 0.0

    def _animate(self, dt_ms: float) -> None:
        """Feed new engine events to the animator and advance it. Read-only on the engine."""
        animator = self.ui.anim
        engine = self.controller.engine
        animator.fast = self.fast
        animator.sync(engine)
        actual_hp = None
        if engine is not None and engine.started:
            actual_hp = {c.id: c.hp for c in engine.combat.combatants.values()}
        animator.update(dt_ms, actual_hp)

    def draw(self) -> None:
        ui, controller = self.ui, self.controller
        ui.begin(self.surface)
        screen = controller.screen
        try:
            if screen == Screen.MAIN_MENU:
                screens.draw_main_menu(ui, controller, self.quit)
            elif screen == Screen.CONTROLS:
                screens.draw_controls(ui, controller)
            elif screen == Screen.PARTY_SETUP:
                screens.draw_party_setup(ui, controller)
            elif controller.paused and screen in (Screen.BATTLE, Screen.UPGRADE):
                screens.draw_pause(ui, controller)
            elif screen == Screen.BATTLE:
                screens.draw_battle(ui, controller, self.fast)
            elif screen == Screen.UPGRADE:
                screens.draw_upgrade(ui, controller)
            elif screen == Screen.OUTCOME:
                screens.draw_outcome(ui, controller)
            elif screen == Screen.CAREER:
                screens.draw_career(ui, controller)
            elif screen == Screen.CONTINUE:
                screens.draw_continue(ui, controller)
            else:
                screens.draw_error(ui, controller)
        except Exception:  # noqa: BLE001 - a rendering fault must leave a usable error screen
            controller.fail()
            self.render_faults += 1
            ui.begin(self.surface)
            screens.draw_error(ui, controller)
        ui.end()
        if not self.headless:
            pygame.display.flip()

    def frame(self, dt_ms: float = 16.0) -> None:
        """One update + draw. Used by the main loop and by headless tests."""
        self.update(dt_ms)
        self.draw()

    def run(self) -> None:
        clock = pygame.time.Clock()
        try:
            while self.running:
                dt = clock.tick(60)
                for event in pygame.event.get():
                    self.handle_event(event)
                self.frame(dt)
        finally:
            self.controller.close()  # the save file, when one is open
            pygame.quit()
