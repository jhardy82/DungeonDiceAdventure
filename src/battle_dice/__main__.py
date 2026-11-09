"""Launch Battle Dice: ``python -m battle_dice`` (or the ``battle-dice`` script)."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="battle-dice", description="Battle Dice: a turn-based tactical dice RPG")
    parser.add_argument("--seed", type=int, default=None, help="use this root seed for every run (reproducible dice)")
    parser.add_argument("--size", default="1280x720", help="window size WIDTHxHEIGHT (minimum 960x540)")
    parser.add_argument("--log-dir", default=None, help="folder for JSONL event logs (default: ./logs)")
    args = parser.parse_args(argv)

    try:
        width, height = (int(part) for part in args.size.lower().split("x"))
    except ValueError:
        parser.error("--size must look like 1280x720")
    if args.seed is not None and not 0 <= args.seed < 2**64:
        parser.error("--seed must be an unsigned 64-bit integer")

    from battle_dice.app.controller import AppController
    from battle_dice.ui.app import GameApp

    controller = AppController(fixed_seed=args.seed, log_dir=args.log_dir)
    GameApp(controller, size=(width, height)).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
