"""Launch Battle Dice: ``python -m battle_dice`` (or the ``battle-dice`` script)."""

from __future__ import annotations

import argparse
import sys
import tempfile
import traceback
from pathlib import Path

SMOKE_PARTY = ("squire", "apprentice", "scout")


def run_smoke_test(report_path: str | None = None) -> int:
    """Headless self-check: play one full seeded run through the real UI and exit 0 on success.

    It loads the bundled content, starts pygame without a display, draws every screen the run
    passes through, and writes a JSONL log. Packaged builds run this to prove that content,
    pygame-ce and fonts were bundled correctly. It never opens a window.
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
        from battle_dice.sim.policies import HeuristicPolicy
        from battle_dice.ui.app import GameApp

        with tempfile.TemporaryDirectory(prefix="battle-dice-smoke-") as log_dir:
            controller = AppController(fixed_seed=1, log_dir=log_dir)
            app = GameApp(controller, headless=True)
            seen = {controller.screen}
            controller.new_run()
            for class_id in SMOKE_PARTY:
                controller.add_hero(class_id)
            app.frame(0)
            seen.add(controller.screen)
            controller.begin_run()
            engine = controller.engine
            if engine is None:
                raise RuntimeError(f"the run did not start: {controller.message}")
            policy = HeuristicPolicy()
            frames = 0
            sprites = app.ui.assets.load_all()
            if sprites == 0 or app.ui.assets.missing:
                raise RuntimeError(f"sprites failed to load: {sorted(app.ui.assets.missing) or 'none found'}")
            while not engine.finished():
                if engine.needs_input():
                    policy.act(engine)
                else:
                    engine.do("AdvancePhase")
                controller.refresh()
                app.frame(40)
                frames += 1
                seen.add(controller.screen)
                if frames > 20000:
                    raise RuntimeError("the run did not finish")
            if controller.screen != Screen.OUTCOME:
                raise RuntimeError(f"expected the outcome screen, got {controller.screen}: {controller.error_text}")
            if controller.log_path is None or not controller.log_path.exists():
                raise RuntimeError(f"the event log was not written: {controller.log_error}")
            lines.append(
                f"SMOKE TEST OK: outcome={engine.state.outcome} frames={frames} events={len(engine.events)} "
                f"screens={sorted(seen)} sprites={sprites} rules={RULES_VERSION} content={controller.content.content_version} "
                f"python={sys.version.split()[0]} pygame-ce={pygame.version.ver} frozen={bool(getattr(sys, 'frozen', False))}"
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
    parser.add_argument("--no-animation", action="store_true",
                        help="start with animation turned off (reduced motion); M toggles it in battle")
    parser.add_argument("--smoke-test", action="store_true",
                        help="run a headless self-check (no window) and exit 0 on success")
    parser.add_argument("--smoke-out", default=None, metavar="FILE",
                        help="with --smoke-test: also write the result text to FILE")
    args = parser.parse_args(argv)

    if args.smoke_test:
        return run_smoke_test(args.smoke_out)

    try:
        width, height = (int(part) for part in args.size.lower().split("x"))
    except ValueError:
        parser.error("--size must look like 1280x720")
    if args.seed is not None and not 0 <= args.seed < 2**64:
        parser.error("--seed must be an unsigned 64-bit integer")

    from battle_dice.app.controller import AppController
    from battle_dice.ui.app import GameApp

    controller = AppController(fixed_seed=args.seed, log_dir=args.log_dir)
    GameApp(controller, size=(width, height), animations=not args.no_animation).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
