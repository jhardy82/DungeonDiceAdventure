"""Feature gates: launch settings, all off by default.

A gate is switched on for one launch with ``--feature NAME`` or by naming it in the environment
variable ``BATTLE_DICE_FEATURES`` (comma-separated). Nothing is stored between launches.

Gates live here, in the app layer, and never in the content files: the content hash covers those
files, and a game with every gate off must stay byte for byte what it was. The rules engine has no
global switch either; it is simply handed what a feature needs, or not.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping

#: Class Evolution (``docs/class_evolution/FDD_v0.2.md``). On: the engine is handed the vocation catalog.
CLASS_EVOLUTION = "class_evolution_v1"
KNOWN_FEATURES: tuple[str, ...] = (CLASS_EVOLUTION,)
ENV_VAR = "BATTLE_DICE_FEATURES"


def resolve(requested: Iterable[str] = (), environ: Mapping[str, str] | None = None) -> frozenset[str]:
    """The gates that are on for this launch. Raises ``ValueError`` for a name that is not a known gate."""
    source = os.environ if environ is None else environ
    names = [name.strip() for name in requested]
    names += [name.strip() for name in source.get(ENV_VAR, "").split(",")]
    wanted = {name for name in names if name}
    unknown = sorted(wanted - set(KNOWN_FEATURES))
    if unknown:
        raise ValueError(f"Unknown feature(s): {', '.join(unknown)}. Known: {', '.join(KNOWN_FEATURES)}.")
    return frozenset(wanted)


def describe(enabled: Iterable[str]) -> str:
    """Text for ``--version`` and the status bar: empty when every gate is off."""
    names = sorted(enabled)
    return f"features: {', '.join(names)}" if names else ""
