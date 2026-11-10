"""Combat effects: damage, shields, healing/revival, statuses, mana and corruption (section 9).

Hero die faces, enemy abilities and reactions all run through the functions in this module, so
there is exactly one implementation of each rule. Every function mutates only the working copy
of state owned by the engine's current command transaction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from battle_dice.core.events import EventType
from battle_dice.core.models import (
    CATEGORY_ATTACK,
    CATEGORY_DEFENSE,
    SIDE_HERO,
    STATE_DEFEATED,
    STATE_DOWNED,
    STATE_STANDING,
    STATUS_POISON,
    STATUS_SPEED_UP,
    STATUS_WEAKEN,
    ActionIntent,
    Combatant,
    FaceDefinition,
    StatusInstance,
)
from battle_dice.core.targeting import resolve_targets

if TYPE_CHECKING:  # pragma: no cover
    from battle_dice.core.engine import Engine


# --------------------------------------------------------------------------------------------
# Primitive state changes
# --------------------------------------------------------------------------------------------


def lose_hp(ctx: Engine, target: Combatant, amount: int, followups: list[dict[str, Any]]) -> int:
    """Reduce HP (never below 0) and mark the combatant downed/defeated at 0."""
    lost = min(target.hp, max(0, amount))
    target.hp -= lost
    if target.hp == 0 and target.state == STATE_STANDING:
        if target.side == SIDE_HERO:
            target.state = STATE_DOWNED
            followups.append({"event": EventType.COMBATANT_DOWNED, "id": target.id})
        else:
            target.state = STATE_DEFEATED
            followups.append({"event": EventType.COMBATANT_DEFEATED, "id": target.id})
    return lost


def deal_damage(
    ctx: Engine, target: Combatant, amount: int, followups: list[dict[str, Any]], bypass_shield: bool = False
) -> dict[str, Any]:
    """Shields absorb first; the remainder reduces HP. Returns a breakdown for the log."""
    amount = max(0, amount)
    absorbed = 0 if bypass_shield else min(target.shields, amount)
    target.shields -= absorbed
    hp_damage = lose_hp(ctx, target, amount - absorbed, followups)
    return {"damage": amount, "absorbed": absorbed, "hp_damage": hp_damage}


def add_shield(ctx: Engine, target: Combatant, amount: int) -> int:
    cap = ctx.content.balance["shield"]["cap"]
    gained = max(0, min(cap - target.shields, amount))
    target.shields += gained
    return gained


def gain_mana(target: Combatant, amount: int) -> int:
    gained = max(0, min(target.max_mana - target.mana, amount))
    target.mana += gained
    return gained


def gain_corruption(target: Combatant, amount: int) -> int:
    gained = max(0, min(target.max_corruption - target.corruption, amount))
    target.corruption += gained
    return gained


def remove_corruption(target: Combatant, amount: int) -> int:
    removed = max(0, min(target.corruption, amount))
    target.corruption -= removed
    return removed


def apply_status(
    ctx: Engine, source: Combatant, target: Combatant, kind: str, magnitude: int, duration: int
) -> list[dict[str, Any]]:
    """Apply a status. Poison/Weaken add one instance per stack up to the cap, then refresh the oldest."""
    combat = ctx.combat
    results: list[dict[str, Any]] = []
    if magnitude <= 0 or not target.standing:
        return results
    own_activation = combat.active_combatant_id == target.id
    cap = ctx.content.status_cap(kind)

    def new_instance(stacks: int) -> StatusInstance:
        instance = StatusInstance(
            id=f"st{combat.next_status_seq:04d}",
            kind=kind,
            source_id=source.id,
            target_id=target.id,
            stacks=stacks,
            remaining_target_activations=duration,
            created_event_seq=combat.event_seq,
            applied_during_own_activation=own_activation,
        )
        combat.next_status_seq += 1
        target.status_instances.append(instance)
        return instance

    def refresh(instance: StatusInstance) -> bool:
        if instance.remaining_target_activations >= duration:
            return False
        instance.remaining_target_activations = duration
        instance.created_event_seq = combat.event_seq
        instance.applied_during_own_activation = own_activation
        # A refreshed stack becomes the newest one.
        target.status_instances.remove(instance)
        target.status_instances.append(instance)
        return True

    if kind == STATUS_SPEED_UP:
        existing = target.instances_of(kind)
        if existing:
            changed = refresh(existing[0])
            results.append({"status": kind, "result": "refreshed" if changed else "no_change", "id": existing[0].id})
        else:
            instance = new_instance(magnitude)
            results.append({"status": kind, "result": "applied", "id": instance.id, "stacks": magnitude, "duration": duration})
        return results

    for _ in range(magnitude):
        existing = target.instances_of(kind)
        if len(existing) < cap:
            instance = new_instance(1)
            results.append({"status": kind, "result": "applied", "id": instance.id, "stacks": 1, "duration": duration})
        else:
            oldest = existing[0]
            changed = refresh(oldest)
            results.append({"status": kind, "result": "refreshed" if changed else "no_change", "id": oldest.id})
    return results


def status_unrefreshable(ctx: Engine, target: Combatant, kind: str, duration: int) -> bool:
    """True when applying the status would change nothing: at cap with every stack at full duration."""
    existing = target.instances_of(kind)
    if len(existing) < ctx.content.status_cap(kind):
        return False
    return all(s.remaining_target_activations >= duration for s in existing)


# --------------------------------------------------------------------------------------------
# Damage formula
# --------------------------------------------------------------------------------------------


def damage_breakdown(
    ctx: Engine, actor: Combatant, face: FaceDefinition, effect: dict[str, Any], intent: ActionIntent | None
) -> dict[str, int]:
    """effective = max(0, power + bonuses - weaken_penalty - explicit_mitigation)."""
    base = face.effect_amount(effect)
    bonus = 0
    weaken = 0
    if face.category == CATEGORY_ATTACK:
        bonus = attack_bonus(ctx, actor, face, intent)
        penalty = ctx.content.balance["statuses"]["weaken"]["damage_penalty_per_stack"]
        weaken = actor.stacks_of(STATUS_WEAKEN) * penalty
    mitigation = intent.damage_reduction if intent is not None else 0
    return {
        "base": base,
        "bonus": bonus,
        "weaken": weaken,
        "mitigation": mitigation,
        "effective": max(0, base + bonus - weaken - mitigation),
    }


def attack_bonus(ctx: Engine, actor: Combatant, face: FaceDefinition, intent: ActionIntent | None) -> int:
    if not actor.is_hero:
        return 0
    passive = ctx.content.class_def(actor.archetype_id)["passive"]
    if passive["type"] == "spell_damage_at_corruption":
        if "spell" in face.tags and actor.corruption >= passive["threshold"]:
            return int(passive["amount"])
    if passive["type"] == "combo_attack_bonus" and intent is not None:
        turn = ctx.combat.turn
        scheduling = ctx.content.class_def(actor.archetype_id)["scheduling"]
        if (
            turn is not None
            and turn.hero_id == actor.id
            and len(turn.plan) == 2
            and turn.plan[1].id == intent.id
            and scheduling.get("first_category") in turn.resolved_categories
        ):
            return int(passive["amount"])
    return 0


def shield_bonus(ctx: Engine, actor: Combatant, face: FaceDefinition, target: Combatant, intent: ActionIntent | None) -> int:
    """Steadfast: +1 shield on every Defense die action the Squire takes (self or ally), never on reactions."""
    if not actor.is_hero or intent is None or intent.source_die_id is None:
        return 0
    passive = ctx.content.class_def(actor.archetype_id)["passive"]
    if passive["type"] == "defense_die_bonus" and face.category == CATEGORY_DEFENSE and target.standing:
        return int(passive["amount"])
    return 0


# --------------------------------------------------------------------------------------------
# Atomic action resolution
# --------------------------------------------------------------------------------------------


def _apply_effect(
    ctx: Engine,
    intent: ActionIntent,
    face: FaceDefinition,
    actor: Combatant,
    target: Combatant,
    effect: dict[str, Any],
    followups: list[dict[str, Any]],
) -> dict[str, Any] | None:
    kind = effect["type"]
    hostile = target.side != actor.side
    result: dict[str, Any] = {"type": kind, "target": target.id}

    if kind == "damage":
        if not target.standing:
            return None
        breakdown = damage_breakdown(ctx, actor, face, effect, intent)
        result.update(breakdown)
        result.update(deal_damage(ctx, target, breakdown["effective"], followups))
    elif kind == "shield":
        if not target.standing:
            return None
        bonus = shield_bonus(ctx, actor, face, target, intent)
        result.update({"bonus": bonus, "gained": add_shield(ctx, target, face.effect_amount(effect) + bonus)})
    elif kind == "heal":
        amount = face.effect_amount(effect)
        if target.state == STATE_DOWNED:
            if not face.can_revive:
                return None
            target.hp = min(target.max_hp, amount)
            target.state = STATE_STANDING
            target.gauge = ctx.content.balance["timeline"]["revive_gauge"]
            result.update({"healed": target.hp, "revived": True})
            followups.append({"event": EventType.HERO_REVIVED, "id": target.id, "hp": target.hp})
        elif target.standing:
            healed = min(target.max_hp - target.hp, amount)
            target.hp += healed
            result.update({"healed": healed, "revived": False})
        else:
            return None
    elif kind == "apply_status":
        magnitude = face.effect_amount(effect)
        if hostile:
            magnitude = max(0, magnitude - intent.magnitude_reduction)
        applied = apply_status(ctx, actor, target, effect["status"], magnitude, effect["duration"])
        result.update({"status": effect["status"], "magnitude": magnitude, "duration": effect["duration"], "applied": applied})
        for entry in applied:
            followups.append({"event": _STATUS_EVENTS[entry["result"]], "id": target.id, **entry})
    elif kind == "gain_mana":
        result["gained"] = gain_mana(target, face.effect_amount(effect))
    elif kind == "gain_corruption":
        amount = face.effect_amount(effect)
        if hostile:
            amount = max(0, amount - intent.magnitude_reduction)
        result["gained"] = gain_corruption(target, amount)
    elif kind == "remove_corruption":
        result["removed"] = remove_corruption(target, face.effect_amount(effect))
    else:  # pragma: no cover - rejected by content validation
        raise ValueError(f"unknown effect type '{kind}'")
    return result


_STATUS_EVENTS = {
    "applied": EventType.STATUS_APPLIED,
    "refreshed": EventType.STATUS_REFRESHED,
    "no_change": EventType.STATUS_REFRESHED,
}


def emit_followups(ctx: Engine, actor_id: str | None, intent_id: str | None, followups: list[dict[str, Any]]) -> None:
    for entry in followups:
        payload = {k: v for k, v in entry.items() if k != "event"}
        ctx.emit(entry["event"], actor_id=actor_id, intent_id=intent_id, delta=payload, affected=[entry["id"]])


def resolve_action(ctx: Engine, intent: ActionIntent, face: FaceDefinition) -> bool:
    """Revalidate and resolve one committed action atomically. Returns True when it resolved.

    Costs are charged only here, on successful resolution. A cancelled action spends nothing.
    """
    combat = ctx.combat
    actor = combat.combatants[intent.actor_id]

    resolution = resolve_targets(combat, actor, face, intent.committed_target_ids)
    reason = resolution.reason
    if not resolution.cancelled and actor.is_hero and actor.mana < face.mana_cost:
        resolution.cancelled = True
        reason = f"insufficient mana ({actor.mana}/{face.mana_cost})"
    if resolution.cancelled:
        intent.cancelled = True
        intent.cancel_reason = reason
        ctx.emit(
            EventType.ACTION_CANCELLED,
            actor_id=actor.id,
            intent_id=intent.id,
            delta={"name": face.name, "category": face.category, "reason": reason, "cost_spent": 0,
                   "committed_target_ids": list(intent.committed_target_ids)},
            affected=[actor.id],
        )
        return False
    if resolution.retargeted_to is not None:
        ctx.emit(
            EventType.ACTION_RETARGETED,
            actor_id=actor.id,
            intent_id=intent.id,
            delta={"name": face.name, "from": resolution.retargeted_from, "to": resolution.retargeted_to,
                   "rule": "same row, then lowest HP percentage, then stable ID"},
            affected=[resolution.retargeted_to],
        )

    targets = [combat.combatants[t] for t in resolution.targets]
    affected = sorted({actor.id, *resolution.targets})
    before = ctx.snap(affected)
    followups: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []

    if actor.is_hero:
        actor.mana -= face.mana_cost
    for effect in face.effects:
        recipients = [actor] if effect.get("target", "target") == "self" else targets
        for target in recipients:
            outcome = _apply_effect(ctx, intent, face, actor, target, effect, followups)
            if outcome is not None:
                results.append(outcome)

    intent.resolved = True
    ctx.emit(
        EventType.ACTION_RESOLVED,
        actor_id=actor.id,
        intent_id=intent.id,
        delta={
            "name": face.name,
            "category": face.category,
            "side": actor.side,
            "mana_spent": face.mana_cost if actor.is_hero else 0,
            "target_ids": list(resolution.targets),
            "results": results,
        },
        before=before,
        affected=affected,
    )
    emit_followups(ctx, actor.id, intent.id, followups)
    return True


# --------------------------------------------------------------------------------------------
# Activation start / end processing (section 6.2 steps 3 and 7)
# --------------------------------------------------------------------------------------------


def activation_start_effects(ctx: Engine, actor: Combatant) -> None:
    """Poison: each stack deals its damage to HP, bypassing shields, in creation order."""
    per_stack = ctx.content.balance["statuses"]["poison"]["damage_per_stack"]
    for instance in list(actor.instances_of(STATUS_POISON)):
        if not actor.standing:
            break
        before = ctx.snap([actor.id])
        followups: list[dict[str, Any]] = []
        breakdown = deal_damage(ctx, actor, instance.stacks * per_stack, followups, bypass_shield=True)
        ctx.emit(
            EventType.POISON_TICK,
            actor_id=actor.id,
            delta={"status_id": instance.id, "side": actor.side, **breakdown},
            before=before,
            affected=[actor.id],
        )
        emit_followups(ctx, actor.id, None, followups)
        if ctx.check_terminal():
            return


def activation_end_effects(ctx: Engine, actor: Combatant) -> None:
    """Corruption backlash, then duration countdown for the actor's activation-counted statuses."""
    corruption = ctx.content.balance["corruption"]
    if actor.is_hero and actor.standing and actor.corruption >= corruption["backlash_threshold"]:
        before = ctx.snap([actor.id])
        followups: list[dict[str, Any]] = []
        breakdown = deal_damage(ctx, actor, corruption["backlash_damage"], followups, bypass_shield=True)
        ctx.emit(
            EventType.CORRUPTION_BACKLASH,
            actor_id=actor.id,
            delta={"side": actor.side, "corruption": actor.corruption, **breakdown},
            before=before,
            affected=[actor.id],
        )
        emit_followups(ctx, actor.id, None, followups)
        if ctx.check_terminal():
            return
    if not actor.standing:
        return  # downed combatants do not tick activation-based effects
    for instance in list(actor.status_instances):
        if instance.applied_during_own_activation:
            instance.applied_during_own_activation = False
            continue
        instance.remaining_target_activations -= 1
        if instance.remaining_target_activations <= 0:
            actor.status_instances.remove(instance)
            ctx.emit(
                EventType.STATUS_EXPIRED,
                actor_id=actor.id,
                delta={"status_id": instance.id, "status": instance.kind, "id": actor.id},
                affected=[actor.id],
            )
