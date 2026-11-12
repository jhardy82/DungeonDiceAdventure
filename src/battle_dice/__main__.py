"""Launch Battle Dice: ``python -m battle_dice`` (or the ``battle-dice`` script)."""

from __future__ import annotations

import argparse
import sys
import tempfile
import traceback
from pathlib import Path

SMOKE_PARTY = ("squire", "apprentice", "scout")


def run_smoke_test(report_path: str | None = None, features: frozenset[str] = frozenset()) -> int:
    """Headless self-check: play one full seeded run and exit 0 on success. It never opens a window.

    What it exercises: the bundled content and sprites load; the menus are driven by real key
    events; the pause menu opens and closes; every frame of the run is drawn; the event log is
    written. Battle decisions come from the built-in heuristic policy (sent straight to the rules
    engine), so the run reliably reaches the upgrade and outcome screens. Any frame whose drawing
    raised, or any visit to the error screen, fails the check.
    """
    import os

    lines: list[str] = []
    code = 1
    try:
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        os.environ["SDL_AUDIODRIVER"] = "dummy"

        import pygame

        from battle_dice import RULES_VERSION
        from battle_dice.app.controller import AppController, Screen
        from battle_dice.features import describe
        from battle_dice.sim.policies import HeuristicPolicy
        from battle_dice.ui.app import GameApp

        with tempfile.TemporaryDirectory(prefix="battle-dice-smoke-") as folder:
            # Logs and the save (Class Evolution) both stay inside the temporary folder: a self-check
            # never touches the player's own files.
            controller = AppController(fixed_seed=1, log_dir=Path(folder) / "logs", features=features, save_dir=Path(folder) / "saves")
            evolution = controller.progression is not None
            if features and "class_evolution_v1" in features and not evolution:
                raise RuntimeError(f"the save could not be opened: {controller.progression_error}")
            app = GameApp(controller, headless=True)
            seen = {controller.screen}

            def check_frame() -> None:
                seen.add(controller.screen)
                if app.render_faults or controller.screen == Screen.ERROR:
                    raise RuntimeError(f"a screen failed to draw or an input raised:\n{controller.error_text}")

            def press(key: int) -> None:
                app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode=""))
                app.frame(0)
                check_frame()

            press(pygame.K_n)  # New Run
            for key in (pygame.K_1, pygame.K_2, pygame.K_3):  # Squire, Apprentice, Scout
                press(key)
            if [member["class_id"] for member in controller.party] != list(SMOKE_PARTY):
                raise RuntimeError(f"party setup by hotkeys produced {controller.party}")
            if evolution:  # the three were recruited and saved; look at one hero's career and come back
                press(pygame.K_c)
                if controller.screen != Screen.CAREER:
                    raise RuntimeError("C did not open the career screen")
                press(pygame.K_ESCAPE)
                if controller.screen != Screen.PARTY_SETUP:
                    raise RuntimeError("Esc did not leave the career screen")
            press(pygame.K_RETURN)  # Begin Encounter (the default button)
            engine = controller.engine
            if engine is None:
                raise RuntimeError(f"the run did not start: {controller.message}")
            policy = HeuristicPolicy()
            frames = 0
            sprites = app.ui.assets.load_all()
            if sprites == 0 or app.ui.assets.missing:
                raise RuntimeError(f"sprites failed to load: {sorted(app.ui.assets.missing) or 'none found'}")
            press(pygame.K_ESCAPE)  # pause menu ...
            if not controller.paused:
                raise RuntimeError("Esc did not open the pause menu")
            press(pygame.K_ESCAPE)  # ... and back
            if controller.paused:
                raise RuntimeError("Esc did not close the pause menu")
            while not engine.finished():
                if engine.needs_input():
                    policy.act(engine)
                else:
                    engine.do("AdvancePhase")
                controller.refresh()
                if frames % 25 == 0:  # point at a unit card now and then, so the inspect panel is drawn too
                    card = next((w for w in app.ui.widgets if w.key.startswith("unit:")), None)
                    if card is not None:
                        app.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=card.rect.center, rel=(0, 0), buttons=(0, 0, 0)))
                app.frame(40)
                frames += 1
                check_frame()
                if frames > 20000:
                    raise RuntimeError("the run did not finish")
            if controller.screen != Screen.OUTCOME:
                raise RuntimeError(f"expected the outcome screen, got {controller.screen}: {controller.error_text}")
            if Screen.BATTLE not in seen:
                raise RuntimeError(f"the battle screen was never drawn; saw {sorted(seen)}")
            if controller.log_path is None or not controller.log_path.exists():
                raise RuntimeError(f"the event log was not written: {controller.log_error}")
            if evolution:
                link = controller.progression
                if not link.path.is_file() or len(link.state.heroes) != len(SMOKE_PARTY):
                    raise RuntimeError("the heroes were not saved")
                if not link.last_awards or link.state.run is None or link.state.run.phase != engine.state.outcome:
                    raise RuntimeError("the run's result did not reach the save")
                if len(engine.state.battle_records) >= 2 and engine.state.battle_records[1]["outcome"] == "victory" \
                        and Screen.CONTINUE not in seen:
                    raise RuntimeError("battle 2 was won but the stop-or-fight-on screen was never drawn")
                link.close()
            lines.append(
                f"SMOKE TEST OK: outcome={engine.state.outcome} frames={frames} events={len(engine.events)} "
                f"screens={sorted(seen)} sprites={sprites} rules={RULES_VERSION} content={controller.content.content_version} "
                f"python={sys.version.split()[0]} pygame-ce={pygame.version.ver} frozen={bool(getattr(sys, 'frozen', False))}"
                + (f" {describe(features).replace(': ', '=').replace(', ', ',')}" if features else "")
            )
            pygame.quit()
        code = 0
    except Exception:  # noqa: BLE001 - report every failure as a non-zero exit with the traceback
        lines.append("SMOKE TEST FAILED")
        lines.append(traceback.format_exc())
    text = "\n".join(lines)
    print(text)
    if report_path:
        Path(report_path).write_text(text + "\n", encoding="utf-8")
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="battle-dice", description="Battle Dice: a turn-based tactical dice RPG")
    parser.add_argument("--seed", type=int, default=None, help="use this root seed for every run (reproducible dice)")
    parser.add_argument("--size", default="1280x720", help="window size WIDTHxHEIGHT (minimum 960x540)")
    parser.add_argument("--log-dir", default=None, help="folder for JSONL event logs")
    parser.add_argument("--save-dir", default=None,
                        help="folder for the save file (only used with the class_evolution_v1 feature)")
    parser.add_argument("--no-animation", action="store_true",
                        help="start with animation turned off (reduced motion); M toggles it in battle")
    parser.add_argument("--smoke-test", action="store_true",
                        help="run a headless self-check (no window) and exit 0 on success")
    parser.add_argument("--smoke-out", default=None, metavar="FILE",
                        help="with --smoke-test: also write the result text to FILE")
    parser.add_argument("--version", action="store_true", help="print the rules and content versions and exit")
    parser.add_argument("--feature", action="append", default=[], metavar="NAME",
                        help="switch on a feature gate for this launch (all are off by default); "
                             "the environment variable BATTLE_DICE_FEATURES does the same")
    args = parser.parse_args(argv)

    from battle_dice import features as gates

    try:
        enabled = gates.resolve(args.feature)
    except ValueError as error:
        parser.error(str(error))

    if args.version:
        from battle_dice import RULES_VERSION
        from battle_dice.content.loader import load_content

        line = f"Battle Dice: rules {RULES_VERSION}, content {load_content().content_version}, Python {sys.version.split()[0]}"
        print(f"{line}, {gates.describe(enabled)}" if enabled else line)
        return 0

    if args.smoke_test:
        return run_smoke_test(args.smoke_out, enabled)

    try:
        width, height = (int(part) for part in args.size.lower().split("x"))
    except ValueError:
        parser.error("--size must look like 1280x720")
    if args.seed is not None and not 0 <= args.seed < 2**64:
        parser.error("--seed must be an unsigned 64-bit integer")

    from battle_dice.app.controller import AppController
    from battle_dice.ui.app import GameApp

    controller = AppController(fixed_seed=args.seed, log_dir=args.log_dir, features=enabled, save_dir=args.save_dir)
    try:
        GameApp(controller, size=(width, height), animations=not args.no_animation).run()
    except Exception:  # noqa: BLE001 - a windowed build has no console: leave the reason in a file
        report = traceback.format_exc()
        print(report, file=sys.stderr)
        try:
            import time

            controller.log_dir.mkdir(parents=True, exist_ok=True)
            crash_file = controller.log_dir / f"crash-{time.strftime('%Y%m%d-%H%M%S')}.txt"
            crash_file.write_text(report, encoding="utf-8")
            print(f"Battle Dice stopped unexpectedly. Details were saved to {crash_file}", file=sys.stderr)
        except OSError:
            pass
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
