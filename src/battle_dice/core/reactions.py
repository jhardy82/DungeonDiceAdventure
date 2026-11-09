"""Staged, non-recursive reaction windows: Guard, Resource Manipulation, Interrupt (section 7.2).

The enemy's single intent is committed before any window opens. Windows are visited once, in a
fixed order, and never reopen. Reactions do not open reaction windows (depth is one).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from battle_dice.core import effects
from battle_dice.core.events import EventType
from battle_dice.core.models import REACTION_STAGES, ActionIntent, Combatant, FaceDefinition, Reaction

if TYPE_CHECKING:  # pragma: no cover
    from battle_dice.core.engine import Engine


def intent_is_reactable(ctx: Engine, intent: ActionIntent, face: FaceDefinition) -> bool:
    """Hostile actions aimed at heroes are reactable; self buffs and ``unreactable`` are not."""
    if "unreactable" in intent.tags or "hostile" not in intent.tags:
        return False
    return any(ctx.combat.combatants[t].is_hero for t in intent.committed_target_ids)


def _targeted_heroes(ctx: Engine, intent: ActionIntent) -> list[Combatant]:
    combat = ctx.combat
    return [
        combat.combatants[t]
        for t in sorted(intent.committed_target_ids)
        if combat.combatants[t].is_hero and combat.combatants[t].standing
    ]


def stage_options(ctx: Engine, stage: str) -> list[dict[str, Any]]:
    """Every standing or downed hero's reaction for this stage, with eligibility and the reason."""
    combat = ctx.combat
    intent = combat.committed_intent
    options: list[dict[str, Any]] = []
    if intent is None:
        return options
    face = ctx.intent_face(intent)
    for hero in combat.side("hero"):
        reaction_id = ctx.content.class_def(hero.archetype_id)["reaction"]
        reaction = ctx.content.reactions[reaction_id]
        if reaction["stage"] != stage:
            continue
        target_ids: list[str] = []
        reason: str | None = None
        expected = reaction["summary"]
        targeted = _targeted_heroes(ctx, intent)

        if not hero.standing:
            reason = "Downed heroes cannot react."
        elif intent.cancelled:
            reason = "The enemy action is already cancelled."
        elif not intent_is_reactable(ctx, intent, face):
            reason = "This enemy action cannot be reacted to."
        elif hero.reaction_charges <= 0:
            reason = "No reaction charge until this hero's next activation."
        elif hero.mana < reaction["mana_cost"]:
            reason = f"Needs {reaction['mana_cost']} mana (has {hero.mana})."
        elif reaction["requires_row"] and hero.row != reaction["requires_row"]:
            reason = f"Must be in the {reaction['requires_row']} row."
        elif reaction["trigger"] == "hostile_damage" and not face.has_effect("damage"):
            reason = "The enemy action deals no damage."
        elif reaction["trigger"] == "hostile_interruptible" and "interruptible" not in intent.tags:
            reason = "The enemy action is not interruptible."

        if reason is None:
            if reaction["target"] == "intent_target":
                candidates = targeted
                if reaction.get("requires_resource_change") and hero.mana >= hero.max_mana:
                    candidates = [t for t in targeted if t.corruption > 0]
                target_ids = [t.id for t in candidates]
                if not target_ids:
                    reason = (
                        "No resource change is possible."
                        if reaction.get("requires_resource_change")
                        else "No targeted ally can be protected."
                    )
            else:
                resisted = "elite_resistant" in intent.tags
                interrupt = reaction["effects"][0]
                if not resisted:
                    expected = f"Cancel {intent.name}."
                elif face.has_effect("damage"):
                    expected = f"Resisted: {intent.name} deals {interrupt['resisted_damage_reduction']} less damage (not cancelled)."
                else:
                    expected = f"Resisted: {intent.name} magnitude reduced by {interrupt['resisted_magnitude_reduction']} (not cancelled)."

        options.append(
            {
                "hero_id": hero.id,
                "hero_name": hero.name,
                "reaction_id": reaction_id,
                "name": reaction["name"],
                "stage": stage,
                "mana_cost": reaction["mana_cost"],
                "charges": hero.reaction_charges,
                "priority": reaction["priority"],
                "eligible": reason is None,
                "reason": reason,
                "needs_target": reaction["target"] == "intent_target",
                "target_ids": target_ids,
                "expected": expected,
            }
        )
    options.sort(key=lambda o: (-o["priority"], o["hero_id"]))
    return options


def eligible_options(ctx: Engine, stage: str) -> list[dict[str, Any]]:
    return [o for o in stage_options(ctx, stage) if o["eligible"]]


def use_reaction(ctx: Engine, hero_id: str, target_id: str | None) -> str | None:
    """Apply one reaction atomically. Returns a rejection reason, or ``None`` on success."""
    combat = ctx.combat
    stage = combat.reaction_stage
    intent = combat.committed_intent
    if stage is None or intent is None:
        return "No reaction window is open."
    option = next((o for o in stage_options(ctx, stage) if o["hero_id"] == hero_id), None)
    if option is None:
        return f"{hero_id} has no {stage} reaction."
    if not option["eligible"]:
        return option["reason"]
    if option["needs_target"]:
        if target_id is None:
            if len(option["target_ids"]) != 1:
                return "Choose which targeted ally receives the reaction."
            target_id = option["target_ids"][0]
        if target_id not in option["target_ids"]:
            return "That ally is not a legal target for this reaction."
    else:
        target_id = None

    hero = combat.combatants[hero_id]
    reaction = ctx.content.reactions[option["reaction_id"]]
    face = ctx.intent_face(intent)
    affected = sorted({hero_id, *( [target_id] if target_id else [] )})
    before = ctx.snap(affected)
    results: list[dict[str, Any]] = []

    hero.mana -= reaction["mana_cost"]
    hero.reaction_charges -= 1
    for effect in reaction["effects"]:
        kind = effect["type"]
        recipient = hero if effect.get("target") == "self" else (combat.combatants[target_id] if target_id else hero)
        if kind == "shield":
            results.append({"type": kind, "target": recipient.id, "gained": effects.add_shield(ctx, recipient, effect["amount"])})
        elif kind == "remove_corruption":
            results.append({"type": kind, "target": recipient.id, "removed": effects.remove_corruption(recipient, effect["amount"])})
        elif kind == "gain_mana":
            results.append({"type": kind, "target": recipient.id, "gained": effects.gain_mana(recipient, effect["amount"])})
        elif kind == "interrupt":
            if "elite_resistant" in intent.tags:
                if face.has_effect("damage"):
                    intent.damage_reduction += effect["resisted_damage_reduction"]
                    results.append({"type": "interrupt", "result": "resisted", "damage_reduction": effect["resisted_damage_reduction"]})
                else:
                    intent.magnitude_reduction += effect["resisted_magnitude_reduction"]
                    results.append({"type": "interrupt", "result": "resisted", "magnitude_reduction": effect["resisted_magnitude_reduction"]})
            else:
                intent.cancelled = True
                intent.cancel_reason = f"interrupted by {hero.name}"
                results.append({"type": "interrupt", "result": "cancelled"})

    record = Reaction(
        id=f"r{combat.next_reaction_seq:04d}",
        reacting_hero_id=hero_id,
        reaction_stage=stage,
        trigger_intent_id=intent.id,
        target_ids=[target_id] if target_id else [],
        costs={"mana": reaction["mana_cost"], "charges": 1},
        effect=option["reaction_id"],
        priority=reaction["priority"],
    )
    combat.next_reaction_seq += 1
    combat.reactions_used.append(record)
    ctx.emit(
        EventType.REACTION_USED,
        actor_id=hero_id,
        intent_id=intent.id,
        delta={
            "reaction_id": record.id,
            "reaction": option["reaction_id"],
            "name": reaction["name"],
            "stage": stage,
            "target_ids": record.target_ids,
            "mana_spent": reaction["mana_cost"],
            "results": results,
        },
        before=before,
        affected=affected,
    )
    for result in results:
        if result.get("result") == "cancelled":
            ctx.emit(EventType.INTENT_CANCELLED, actor_id=intent.actor_id, intent_id=intent.id,
                     delta={"name": intent.name, "by": hero_id, "reaction": option["reaction_id"]})
        elif result.get("result") == "resisted":
            ctx.emit(EventType.INTENT_WEAKENED, actor_id=intent.actor_id, intent_id=intent.id,
                     delta={"name": intent.name, "by": hero_id, "damage_reduction": intent.damage_reduction,
                            "magnitude_reduction": intent.magnitude_reduction})
    return None


def stage_name(index: int) -> str | None:
    return REACTION_STAGES[index] if 0 <= index < len(REACTION_STAGES) else None
