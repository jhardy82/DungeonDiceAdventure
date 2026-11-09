"""Speed-driven action-gauge scheduler (BD-PRD-MVP-001 section 6.1).

This is the single authoritative activation scheduler. There is deliberately no round-based
ordering anywhere in the engine (the Q18/Q24 model is superseded by Q74).
"""

from __future__ import annotations

from typing import Any

from battle_dice.core.models import STATUS_SPEED_UP, Combatant, CombatState


def current_speed(combatant: Combatant, balance: dict[str, Any]) -> int:
    """Base speed plus active speed modifiers, clamped to the legal range."""
    timeline = balance["timeline"]
    speed = combatant.speed + combatant.stacks_of(STATUS_SPEED_UP)
    return max(timeline["min_speed"], min(timeline["max_speed"], speed))


def _threshold(balance: dict[str, Any]) -> int:
    return int(balance["timeline"]["ready_threshold"])


def ready_combatants(combat: CombatState, balance: dict[str, Any]) -> list[Combatant]:
    threshold = _threshold(balance)
    return [c for c in combat.sorted_combatants() if c.standing and c.gauge >= threshold]


def select_ready(combat: CombatState, balance: dict[str, Any]) -> Combatant | None:
    """Deterministic tie-breaker: overflow, current speed, base initiative, then lowest stable ID."""
    candidates = ready_combatants(combat, balance)
    if not candidates:
        return None
    threshold = _threshold(balance)
    return min(
        candidates,
        key=lambda c: (-(c.gauge - threshold), -current_speed(c, balance), -c.base_initiative, c.id),
    )


def tick(combat: CombatState, balance: dict[str, Any]) -> None:
    """Advance one timeline tick: each standing combatant below the threshold gains its speed."""
    threshold = _threshold(balance)
    combat.timeline_tick += 1
    for combatant in combat.sorted_combatants():
        if combatant.standing and combatant.gauge < threshold:
            combatant.gauge += max(1, current_speed(combatant, balance))


def advance_until_ready(combat: CombatState, balance: dict[str, Any]) -> int:
    """Tick only while nobody is ready. Returns the number of ticks advanced."""
    ticks = 0
    while not ready_combatants(combat, balance):
        if not any(c.standing for c in combat.combatants.values()):
            break
        tick(combat, balance)
        ticks += 1
    return ticks


def begin_activation(combat: CombatState, balance: dict[str, Any]) -> Combatant | None:
    """Select the next actor and subtract the threshold, retaining positive overflow."""
    actor = select_ready(combat, balance)
    if actor is None:
        return None
    actor.gauge -= _threshold(balance)
    combat.active_combatant_id = actor.id
    combat.activation_count += 1
    return actor


def forecast(combat: CombatState, balance: dict[str, Any], count: int = 8) -> list[str]:
    """Predict the next activations from current gauges and speeds (status expiry is ignored)."""
    threshold = _threshold(balance)
    gauges = {c.id: c.gauge for c in combat.sorted_combatants() if c.standing}
    speeds = {
        c.id: (max(1, current_speed(c, balance)), c.base_initiative)
        for c in combat.sorted_combatants()
        if c.standing
    }
    order: list[str] = []
    if not gauges:
        return order
    guard = 0
    while len(order) < count and guard < 100000:
        guard += 1
        ready = [cid for cid in sorted(gauges) if gauges[cid] >= threshold]
        if ready:
            chosen = min(ready, key=lambda cid: (-(gauges[cid] - threshold), -speeds[cid][0], -speeds[cid][1], cid))
            gauges[chosen] -= threshold
            order.append(chosen)
            continue
        for cid in gauges:
            if gauges[cid] < threshold:
                gauges[cid] += speeds[cid][0]
    return order
