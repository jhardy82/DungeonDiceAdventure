"""Terminal-state evaluation (section 10)."""

from __future__ import annotations

from battle_dice.core.models import SIDE_ENEMY, SIDE_HERO, CombatState

OUTCOME_VICTORY = "victory"
OUTCOME_DEFEAT = "defeat"


def legal_revival_pending(combat: CombatState) -> bool:
    """Whether a queued revival event could still execute with no hero standing.

    The MVP has no passive, delayed or automatic revival, and both revival faces (Rally, Mend)
    need a *standing* caster. So once no hero stands, no legal revival remains. A future automatic
    revival effect would expose its queued event here.
    """
    return False


def evaluate(combat: CombatState) -> str | None:
    """Defeat takes priority over victory so simultaneous elimination is deterministic."""
    if not combat.standing(SIDE_HERO) and not legal_revival_pending(combat):
        return OUTCOME_DEFEAT
    if not combat.standing(SIDE_ENEMY):
        return OUTCOME_VICTORY
    return None
