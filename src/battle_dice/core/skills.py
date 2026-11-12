"""Inherited skills that change what a hero's dice can do in battle (Class Evolution).

A hero's equipped skills arrive with its build (``HeroBuild.skills``, from the build snapshot of a
saved hero). A skill the rules do not know has no effect in battle. Today the rules know one:

**Field Medic** (taught by a mastered Guardian). Once per encounter, a Healing face that cannot
revive may be used on a downed ally. Used that way it brings the ally back at 5 HP, for the
face's own mana cost. On a standing ally the face is what it always was. It does not create a
new action.

The two numbers are the owner's decision of 2026-11-12 (D-30), taken after a measurement: the v0.1
design (1 more mana, back at 1 HP) was worth nothing to an informed player, and the health on
revival, not the cost, decided the skill's worth (decision log 7.25).
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

from battle_dice.core.models import CATEGORY_HEALING, STATE_DOWNED, Combatant, FaceDefinition

if TYPE_CHECKING:  # pragma: no cover
    from battle_dice.core.engine import Engine

FIELD_MEDIC = "guardian_field_medic"
#: The tag an action carries while it is a Field Medic revival, so it resolves as one.
FIELD_MEDIC_TAG = "field_medic"
FIELD_MEDIC_EXTRA_MANA = 0
FIELD_MEDIC_REVIVE_HP = 5
#: Skills with an effect in battle. A build may carry others; they do nothing here.
KNOWN = (FIELD_MEDIC,)


def field_medic_ready(ctx: Engine, hero: Combatant, face: FaceDefinition) -> bool:
    """True when this hero could use this face as a Field Medic revival now: equipped, unused this encounter, a plain heal."""
    return (
        FIELD_MEDIC in ctx.build(hero.id).skills
        and hero.skill_uses.get(FIELD_MEDIC, 0) == 0
        and face.category == CATEGORY_HEALING
        and not face.can_revive
        and face.target_scope == "single_ally"
    )


def field_medic_targets(ctx: Engine, hero: Combatant, face: FaceDefinition) -> list[str]:
    """The downed allies the face may be used on through Field Medic (none when the skill is not ready)."""
    if not field_medic_ready(ctx, hero, face):
        return []
    return sorted(c.id for c in ctx.combat.side(hero.side) if c.state == STATE_DOWNED)


def field_medic_note(face: FaceDefinition) -> str:
    """What the player is told while the face may be used as a revival."""
    extra = f", {face.mana_cost + FIELD_MEDIC_EXTRA_MANA} mana" if FIELD_MEDIC_EXTRA_MANA else ""  # the face's own cost is on the die already
    return f"Field Medic: revive at {FIELD_MEDIC_REVIVE_HP} HP{extra}"


def as_field_medic(face: FaceDefinition) -> FaceDefinition:
    """The face as a Field Medic revival: it may revive, to ``FIELD_MEDIC_REVIVE_HP``, for its cost plus ``FIELD_MEDIC_EXTRA_MANA``."""
    effects = [{**effect, "amount": FIELD_MEDIC_REVIVE_HP} if effect["type"] == "heal" else dict(effect) for effect in face.effects]
    return dataclasses.replace(
        face,
        name=f"{face.name} (Field Medic)",
        mana_cost=face.mana_cost + FIELD_MEDIC_EXTRA_MANA,
        can_revive=True,
        effects=effects,
        tags=[*face.tags, FIELD_MEDIC_TAG],
    )
