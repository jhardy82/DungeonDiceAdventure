"""Verify finished-run logs: ``battle-dice-replay LOG [LOG ...]`` (or ``python -m battle_dice.replay_cli``).

Each log is replayed from its own header (seed, content identity, ordered commands) on a fresh
rules engine and compared with what the file recorded. Exit code 0 means every log reproduced
exactly; 1 means at least one did not.
"""

from __future__ import annotations

import argparse
import sys

from battle_dice.content.loader import ContentError, load_content
from battle_dice.core.replay import ReplayError, verify_log


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="battle-dice-replay", description="Replay Battle Dice run logs and verify them")
    parser.add_argument("logs", nargs="+", metavar="LOG", help="a .jsonl run log written by the game")
    parser.add_argument("--content-dir", default=None,
                        help="verify against the content fixtures in this folder instead of the shipped ones")
    args = parser.parse_args(argv)
    try:
        content = load_content(args.content_dir)
    except (ContentError, OSError) as error:
        print(f"FAILED  content could not be loaded: {error}")
        return 1
    failures = 0
    for path in args.logs:
        try:
            result = verify_log(content, path)
        except (ReplayError, OSError, KeyError, TypeError, ValueError) as error:
            failures += 1
            print(f"FAILED  {path}: {error}")
        else:
            print(f"OK      {path}: {result['outcome']}, seed {result['seed']}, "
                  f"{result['commands']} commands and {result['events']} events reproduced exactly")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
