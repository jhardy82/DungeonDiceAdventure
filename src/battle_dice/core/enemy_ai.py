"""Deterministic enemy decision model (sections 7.1 and 14.4).

Enemies use authored abilities, not dice. The AI never inspects future random numbers or player
choices: it sees only the current combat state, and makes exactly one seeded weighted draw from
the ``enemy`` stream among the highest valid priority tier.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from battle_dice.core import effects
from battle_dice.core.models import STATUS_SPEED_UP, STATUS_WEAKEN, ActionIntent, Combatant, FaceDefinition
from battle_dice.core.targeting import eligible_targets, hp_fraction

if TYPE_CHECKING:  # pragma: no cover
    from battle_dice.core.engine import Engine


def predicted_hp_damage(ctx: Engine, actor: Combatant, face: FaceDefinition, target: Combatant) -> int:
    """Immediate HP damage after the actor's Weaken and the target's current shields."""
    total = 0
    for effect in face.effects:
        if effect["type"] != "damage":
            continue
        amount = face.effect_amount(effect)
        if face.category == "attack":
            penalty = ctx.content.balance["statuses"]["weaken"]["damage_penalty_per_stack"]
            amount -= actor.stacks_of(STATUS_WEAKEN) * penalty
        total += max(0, amount)
    return max(0, total - target.shields)


def _is_lethal(ctx: Engine, actor: Combatant, face: FaceDefinition, target: Combatant) -> bool:
    return face.has_effect("damage") and predicted_hp_damage(ctx, actor, face, target) >= target.hp


def evaluate_actions(ctx: Engine, enemy: Combatant) -> list[dict[str, Any]]:
    """Legal actions in stable action-ID order with their priority tier and candidate targets."""
    combat = ctx.combat
    priorities = ctx.content.balance["ai"]
    evaluated: list[dict[str, Any]] = []
    for action_id in sorted(ctx.content.enemy_actions[enemy.archetype_id]):
        face = ctx.enemy_action(enemy, action_id)
        if face.weight <= 0:
            continue
        targets = [combat.combatants[t] for t in eligible_targets(combat, enemy, face)]
        status = face.status_effect()
        if status is not None:
            if status["status"] == STATUS_SPEED_UP:
                # Repeating a speed modifier while it is active is illegal.
                changeable = [t for t in targets if not t.instances_of(STATUS_SPEED_UP)]
            else:
                changeable = [
                    t for t in targets
                    if not effects.status_unrefreshable(ctx, t, status["status"], status["duration"])
                ]
            if face.target_scope in ("all_enemies", "all_allies"):
                # An area action hits everyone it can reach. It is illegal only when it would do
                # nothing at all: no status would change and it has no other effect.
                if not changeable and all(e["type"] == "apply_status" for e in face.effects):
                    continue
            else:
                targets = changeable
        if not targets:
            continue
        lethal = [t for t in targets if _is_lethal(ctx, enemy, face, t)]
        if lethal:
            priority = priorities["priority_lethal"]
        elif status is not None and any(t.stacks_of(status["status"]) == 0 for t in targets):
            priority = priorities["priority_setup"]
        else:
            priority = priorities["priority_default"]
        evaluated.append({"action_id": action_id, "face": face, "priority": priority, "targets": targets, "lethal": lethal})
    return evaluated


def _choose_targets(ctx: Engine, enemy: Combatant, choice: dict[str, Any]) -> tuple[list[str], dict[str, Any] | None]:
    face: FaceDefinition = choice["face"]
    targets: list[Combatant] = choice["targets"]
    if face.target_scope in ("all_enemies", "all_allies", "self"):
        return [t.id for t in targets], None

    if choice["lethal"]:
        candidates = choice["lethal"]
    else:
        candidates = targets

    if face.has_effect("damage"):
        def key(t: Combatant) -> tuple:
            return (-predicted_hp_damage(ctx, enemy, face, t), hp_fraction(t), t.id)
    elif (status := face.status_effect()) is not None:
        kind = status["status"]

        def key(t: Combatant) -> tuple:
            return (0 if t.stacks_of(kind) == 0 else 1, hp_fraction(t), t.id)
    else:
        def key(t: Combatant) -> tuple:
            return (0 if t.corruption < t.max_corruption else 1, hp_fraction(t), t.id)

    ordered = sorted(candidates, key=key)
    if face.random_target:
        best = key(ordered[0])[0]
        bucket = [t for t in ordered if key(t)[0] == best]
        bucket.sort(key=lambda t: t.id)
        value, draw = ctx.draw("enemy", len(bucket))
        return [bucket[value].id], draw
    return [ordered[0].id], None


def choose_intent(ctx: Engine, enemy: Combatant) -> tuple[ActionIntent | None, dict[str, Any]]:
    """Select the enemy's action and targets. Returns the intent and a loggable decision record."""
    combat = ctx.combat
    evaluated = evaluate_actions(ctx, enemy)
    if not evaluated:
        return None, {"considered": []}
    top = max(e["priority"] for e in evaluated)
    tier = [e for e in evaluated if e["priority"] == top]
    weights = [e["face"].weight for e in tier]
    value, draw = ctx.draw("enemy", sum(weights))
    cumulative = 0
    choice = tier[-1]
    for entry, weight in zip(tier, weights, strict=True):
        cumulative += weight
        if value < cumulative:
            choice = entry
            break
    target_ids, target_draw = _choose_targets(ctx, enemy, choice)
    face: FaceDefinition = choice["face"]
    intent = ActionIntent(
        id=f"a{combat.next_intent_seq:05d}",
        actor_id=enemy.id,
        source_die_id=None,
        ability_id=choice["action_id"],
        effect_id=f"{enemy.archetype_id}.{choice['action_id']}",
        category=face.category,
        committed_target_ids=target_ids,
        action_speed=face.action_speed or 0,
        costs={"mana": face.mana_cost},
        tags=list(face.tags),
        name=face.name,
        power=face.power,
    )
    combat.next_intent_seq += 1
    record = {
        "considered": [
            {"action_id": e["action_id"], "priority": e["priority"], "weight": e["face"].weight} for e in evaluated
        ],
        "tier_priority": top,
        "tier": [e["action_id"] for e in tier],
        "weight_total": sum(weights),
        "roll": value,
        "chosen": choice["action_id"],
        "target_ids": target_ids,
        "draw": draw,
        "target_draw": target_draw,
    }
    return intent, record
