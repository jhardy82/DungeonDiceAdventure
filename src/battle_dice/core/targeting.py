"""Formation legality and deterministic target fallback (sections 5.1 and 5.7)."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from battle_dice.core.models import (
    ROW_FRONT,
    SIDE_ENEMY,
    SIDE_HERO,
    STATE_DOWNED,
    Combatant,
    CombatState,
    FaceDefinition,
)

OFFENSIVE_SCOPES = ("single_enemy", "all_enemies")
ALLY_SCOPES = ("single_ally", "all_allies")


def opposing_side(side: str) -> str:
    return SIDE_ENEMY if side == SIDE_HERO else SIDE_HERO


def hp_fraction(combatant: Combatant) -> Fraction:
    return Fraction(combatant.hp, combatant.max_hp)


def is_offensive(face: FaceDefinition) -> bool:
    return face.target_scope in OFFENSIVE_SCOPES


def _enemy_candidates(combat: CombatState, actor: Combatant, face: FaceDefinition) -> list[Combatant]:
    """Standing opponents reachable by the action's range under the front-row protection rule."""
    opponents = combat.standing(opposing_side(actor.side))
    if face.range_type == "melee" and face.target_scope == "single_enemy":
        front = [c for c in opponents if c.row == ROW_FRONT]
        if front:
            return front
    return opponents


def _ally_candidates(combat: CombatState, actor: Combatant, face: FaceDefinition) -> list[Combatant]:
    allies = combat.side(actor.side)
    candidates = [c for c in allies if c.standing]
    if face.can_revive and face.target_scope == "single_ally":
        candidates += [c for c in allies if c.state == STATE_DOWNED]
    return sorted(candidates, key=lambda c: c.id)


def eligible_targets(combat: CombatState, actor: Combatant, face: FaceDefinition) -> list[str]:
    """Stable-ID-ordered legal targets for an action. Empty when the action has no legal target."""
    scope = face.target_scope
    if scope in OFFENSIVE_SCOPES:
        return [c.id for c in _enemy_candidates(combat, actor, face)]
    if scope in ALLY_SCOPES:
        return [c.id for c in _ally_candidates(combat, actor, face)]
    if scope == "self":
        return [actor.id] if actor.standing else []
    return []


def protected_targets(combat: CombatState, actor: Combatant, face: FaceDefinition) -> list[str]:
    """Standing opponents that melee cannot reach because a standing front row protects them."""
    if face.range_type != "melee" or face.target_scope != "single_enemy":
        return []
    legal = set(eligible_targets(combat, actor, face))
    return [c.id for c in combat.standing(opposing_side(actor.side)) if c.id not in legal]


@dataclass
class TargetResolution:
    targets: list[str]
    cancelled: bool = False
    reason: str | None = None
    retargeted_from: str | None = None
    retargeted_to: str | None = None


def resolve_targets(
    combat: CombatState, actor: Combatant, face: FaceDefinition, committed: list[str]
) -> TargetResolution:
    """Revalidate committed targets immediately before resolution.

    * Offensive single-target actions retarget: same row as the original target if possible, then
      lowest current HP percentage, then lexicographic stable ID. No legal target cancels.
    * Defense, Healing and ally-targeted effects cancel when their target is invalid.
    * Area effects keep the committed targets that are still eligible.
    """
    if not actor.standing:
        return TargetResolution([], cancelled=True, reason="actor cannot act")
    eligible = eligible_targets(combat, actor, face)
    scope = face.target_scope

    if scope == "self":
        return TargetResolution([actor.id])

    if scope in ("all_enemies", "all_allies"):
        remaining = [t for t in committed if t in eligible]
        if not remaining:
            return TargetResolution([], cancelled=True, reason="no legal target remains")
        return TargetResolution(remaining)

    if scope == "single_ally":
        if committed and committed[0] in eligible:
            return TargetResolution([committed[0]])
        return TargetResolution([], cancelled=True, reason="committed target is no longer valid")

    if scope == "single_enemy":
        original_id = committed[0] if committed else None
        if original_id in eligible:
            return TargetResolution([original_id])  # type: ignore[list-item]
        if not eligible:
            return TargetResolution([], cancelled=True, reason="no legal target remains")
        original = combat.combatants.get(original_id) if original_id else None
        original_row = original.row if original else None
        best = min(
            (combat.combatants[t] for t in eligible),
            key=lambda c: (0 if c.row == original_row else 1, hp_fraction(c), c.id),
        )
        return TargetResolution([best.id], retargeted_from=original_id, retargeted_to=best.id)

    return TargetResolution([], cancelled=True, reason="action has no target")
