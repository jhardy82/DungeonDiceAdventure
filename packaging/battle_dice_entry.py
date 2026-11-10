"""PyInstaller entry point for the standalone Battle Dice build."""

import sys

from battle_dice.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
