"""Command line for the vocation catalog validator.

    python tools/class_evolution/validate_catalog.py            # every wave; open ends are warnings
    python tools/class_evolution/validate_catalog.py --wave 1   # is wave 1 releasable on shipped content?

The validator itself is part of the game package (``battle_dice.content.vocations``), because the
game loads the catalog through it when the feature gate is on. This file only runs it; every name
of that module is also available here, so ``validate_catalog.validate`` and the module agree.
"""

from __future__ import annotations

from battle_dice.content import vocations
from battle_dice.content.vocations import *  # noqa: F403 - this file is the same tool under its old name
from battle_dice.content.vocations import main

__all__ = [name for name in vars(vocations) if not name.startswith("_")]

if __name__ == "__main__":
    raise SystemExit(main())
