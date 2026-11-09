"""Battle Dice: single-player, turn-based tactical fantasy dice RPG (MVP vertical slice).

The rules engine (``battle_dice.core``), content layer (``battle_dice.content``) and RNG service
(``battle_dice.rng``) are pure Python with no pygame dependency. Presentation lives in
``battle_dice.ui``.
"""

#: Version of the executable rules. Golden RNG vectors and replay hashes are locked to this value.
RULES_VERSION = "1.0.0"

#: Identifier of the pinned RNG algorithm (BD-PRD-MVP-001 section 14.4).
RNG_ALGORITHM = "BD-PCG32-v1"

__all__ = ["RNG_ALGORITHM", "RULES_VERSION"]
