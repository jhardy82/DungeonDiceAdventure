"""Read-only state snapshots and human-readable descriptions for presentation layers.

Nothing here mutates state or consumes randomness. The UI renders these snapshots and sends
commands back; it never touches the authoritative ``CombatState`` directly (section 14.3).
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any

from battle_dice.core import planning, progression, reactions, timeline
from battle_dice.core.engine import Engine
from battle_dice.core.events import EventType
from battle_dice.core.models import (
    SIDE_HERO,
    STATUS_POISON,
    STATUS_SPEED_UP,
    STATUS_WEAKEN,
    Combatant,
    CombatEvent,
    CombatPhase,
    DieDefinition,
    FaceDefinition,
    RunPhase,
)

STATUS_LABELS = {STATUS_POISON: "Poison", STATUS_WEAKEN: "Weaken", STATUS_SPEED_UP: "Speed Up"}
STATUS_GLYPHS = {STATUS_POISON: "PSN", STATUS_WEAKEN: "WKN", STATUS_SPEED_UP: "SPD+"}
CATEGORY_GLYPHS = {
    "attack": "ATK",
    "defense": "DEF",
    "healing": "HEAL",
    "status": "STAT",
    "resource": "RES",
    "blank": "--",
}
SCOPE_LABELS = {
    "single_enemy": "one enemy",
    "single_ally": "self or ally",
    "self": "self",
    "all_enemies": "all enemies",
    "all_allies": "all allies",
    "none": "no target",
}


# --------------------------------------------------------------------------------------------
# Faces and dice
# --------------------------------------------------------------------------------------------


def describe_face(face: FaceDefinition) -> str:
    """One-line rules text generated from the face data, so text can never drift from behaviour."""
    if face.is_blank:
        return "No action"
    parts: list[str] = []
    for effect in face.effects:
        amount = face.effect_amount(effect)
        on_self = effect.get("target", "target") == "self"
        kind = effect["type"]
        if kind == "damage":
            reach = face.range_type if face.range_type in ("melee", "ranged") else ""
            area = " to all enemies" if face.target_scope == "all_enemies" else ""
            parts.append(f"{amount} {reach} damage{area}".replace("  ", " "))
        elif kind == "shield":
            parts.append(f"+{amount} shield")
        elif kind == "heal":
            parts.append(f"heal {amount}" + (f" (revives to {amount} HP)" if face.can_revive else " (cannot revive)"))
        elif kind == "apply_status":
            label = STATUS_LABELS[effect["status"]]
            if effect["status"] == STATUS_SPEED_UP:
                parts.append(f"+{amount} speed for {effect['duration']} activations")
            else:
                parts.append(f"{label} {amount} for {effect['duration']} activations")
        elif kind == "gain_mana":
            parts.append(f"+{amount} mana")
        elif kind == "gain_corruption":
            parts.append(f"+{amount} corruption" + (" (self)" if on_self else ""))
        elif kind == "remove_corruption":
            parts.append(f"-{amount} corruption" + (" (self)" if on_self else ""))
    text = "; ".join(parts)
    if face.mana_cost:
        text += f"; costs {face.mana_cost} mana"
    return text


def face_view(face: FaceDefinition) -> dict[str, Any]:
    return {
        "id": face.id,
        "name": face.name,
        "category": face.category,
        "glyph": CATEGORY_GLYPHS[face.category],
        "power": face.power,
        "target_scope": face.target_scope,
        "target_label": SCOPE_LABELS[face.target_scope],
        "range_type": face.range_type,
        "action_speed": face.action_speed,
        "mana_cost": face.mana_cost,
        "can_revive": face.can_revive,
        "tags": list(face.tags),
        "text": describe_face(face),
    }


def probability_text(count: int, size: int) -> str:
    fraction = Fraction(count, size)
    percent = Fraction(count * 1000, size)
    whole, tenth = divmod(round(percent), 10)
    return f"{fraction.numerator}/{fraction.denominator} ({whole}.{tenth}%)"


def die_view(die: DieDefinition) -> dict[str, Any]:
    """All faces in order plus grouped frequencies and exact probabilities (design pillar 1)."""
    groups: list[dict[str, Any]] = []
    index_by_signature: dict[tuple, int] = {}
    for index, face in enumerate(die.faces):
        signature = face.signature()
        if signature not in index_by_signature:
            index_by_signature[signature] = len(groups)
            groups.append({"face": face_view(face), "count": 0, "face_numbers": []})
        group = groups[index_by_signature[signature]]
        group["count"] += 1
        group["face_numbers"].append(index + 1)
    for group in groups:
        group["probability"] = probability_text(group["count"], die.size)
        group["numerator"] = group["count"]
        group["denominator"] = die.size
    return {
        "id": die.id,
        "name": die.name,
        "size": die.size,
        "affinity_class": die.affinity_class,
        "definition_version": die.definition_version,
        "faces": [face_view(f) for f in die.faces],
        "groups": groups,
    }


# --------------------------------------------------------------------------------------------
# Snapshot
# --------------------------------------------------------------------------------------------


def combatant_view(engine: Engine, c: Combatant) -> dict[str, Any]:
    balance = engine.content.balance
    view: dict[str, Any] = {
        "id": c.id,
        "name": c.name,
        "side": c.side,
        "archetype_id": c.archetype_id,
        "row": c.row,
        "hp": c.hp,
        "max_hp": c.max_hp,
        "shields": c.shields,
        "mana": c.mana,
        "max_mana": c.max_mana,
        "corruption": c.corruption,
        "max_corruption": c.max_corruption,
        "speed": timeline.current_speed(c, balance),
        "base_speed": c.speed,
        "base_initiative": c.base_initiative,
        "gauge": c.gauge,
        "state": c.state,
        "reaction_charges": c.reaction_charges,
        "statuses": [
            {"id": s.id, "kind": s.kind, "label": STATUS_LABELS[s.kind], "glyph": STATUS_GLYPHS[s.kind],
             "stacks": s.stacks, "remaining": s.remaining_target_activations}
            for s in c.status_instances
        ],
    }
    if c.side == SIDE_HERO:
        cls = engine.content.class_def(c.archetype_id)
        view["class_name"] = cls["name"]
        view["dice"] = [die_view(engine.die_for(c.id, d)) for d in c.equipped_dice_ids]
        view["scheduling"] = cls["scheduling"]
        view["passive"] = cls["passive"]
        view["reaction"] = {"id": cls["reaction"], **engine.content.reactions[cls["reaction"]]}
        view["corruption_backlash"] = c.corruption >= balance["corruption"]["backlash_threshold"]
    else:
        view["actions"] = [
            {**face_view(engine.enemy_action(c, action_id)), "weight": engine.enemy_action(c, action_id).weight}
            for action_id in sorted(engine.content.enemy_actions[c.archetype_id])
        ]
    return view


def intent_view(engine: Engine) -> dict[str, Any] | None:
    combat = engine.combat
    intent = combat.committed_intent
    if intent is None:
        return None
    face = engine.intent_face(intent)
    names = [combat.combatants[t].name for t in intent.committed_target_ids]
    return {
        "id": intent.id,
        "actor_id": intent.actor_id,
        "actor_name": combat.combatants[intent.actor_id].name,
        "name": intent.name,
        "category": intent.category,
        "glyph": CATEGORY_GLYPHS[intent.category],
        "power": intent.power,
        "text": describe_face(face),
        "target_ids": list(intent.committed_target_ids),
        "target_names": names,
        "costs": dict(intent.costs),
        "tags": list(intent.tags),
        "interruptible": "interruptible" in intent.tags,
        "elite_resistant": "elite_resistant" in intent.tags,
        "reactable": reactions.intent_is_reactable(engine, intent, face),
        "cancelled": intent.cancelled,
        "damage_reduction": intent.damage_reduction,
        "magnitude_reduction": intent.magnitude_reduction,
    }


def hero_turn_view(engine: Engine) -> dict[str, Any] | None:
    combat = engine.combat
    turn = combat.turn
    if turn is None:
        return None
    hero = combat.combatants[turn.hero_id]
    options = planning.die_options(engine, hero, turn) if turn.rolled else []
    for option in options:
        option["face"] = face_view(option["face"])
        option["die"] = die_view(engine.die_for(hero.id, option["die_id"]))
    scheduling = engine.content.class_def(hero.archetype_id)["scheduling"]
    return {
        "hero_id": hero.id,
        "hero_name": hero.name,
        "rolled": bool(turn.rolled),
        "dice": options,
        "kept": list(turn.kept),
        "rerolls_remaining": turn.rerolls_remaining,
        "rerolls_total": engine.content.class_def(hero.archetype_id)["rerolls"],
        "scheduling": scheduling,
        "policy_text": planning.describe_policy(scheduling),
        "has_legal_action": planning.has_legal_action(engine, hero, turn) if turn.rolled else False,
        "plan": [
            {"die_id": a.source_die_id, "name": a.name, "target_ids": list(a.committed_target_ids),
             "action_speed": a.action_speed, "category": a.category}
            for a in turn.plan
        ],
        "committed": turn.committed,
    }


def upgrade_view(engine: Engine) -> dict[str, Any]:
    state = engine.state
    heroes = engine.combat.side(SIDE_HERO)
    swap_limit = engine.content.balance["upgrades"]["max_swaps_per_hero"]
    swaps_left = {hero.id: max(0, swap_limit - state.swaps_used.get(hero.id, 0)) for hero in heroes}
    result: dict[str, Any] = {
        "upgrade_chosen": bool(state.upgrades),
        "upgrades": list(state.upgrades),
        "swaps_remaining": sum(swaps_left.values()),
        "swaps_per_hero": swap_limit,
        "heroes": [],
    }
    for hero in heroes:
        locked = progression.upgraded_die_ids(engine, hero.id)
        bench = []
        for die_id in state.inventory.get(hero.id, []):
            swaps = []
            for out_id in hero.equipped_dice_ids:
                problem = progression.swap_problem(engine, hero.id, out_id, die_id) if state.phase == RunPhase.EQUIPMENT else "Choose the mandatory upgrade first."
                swaps.append({"out_die_id": out_id, "allowed": problem is None, "reason": problem})
            bench.append({"die": die_view(engine.content.die(die_id)), "swaps": swaps})
        result["heroes"].append(
            {
                "hero_id": hero.id,
                "hero_name": hero.name,
                "swaps_remaining": swaps_left[hero.id],
                "equipped": [
                    {"die": die_view(engine.die_for(hero.id, d)), "locked": d in locked,
                     "offers": state.upgrade_offers.get(hero.id, {}).get(d, [])}
                    for d in hero.equipped_dice_ids
                ],
                "bench": bench,
            }
        )
    return result


def snapshot(engine: Engine) -> dict[str, Any]:
    """Everything a presentation layer needs to render the current decision point."""
    if not engine.started:
        return {"started": False, "permissible_commands": engine.permissible_commands(), "revision": 0}
    state = engine.state
    combat = engine.combat
    balance = engine.content.balance
    snap: dict[str, Any] = {
        "started": True,
        "revision": state.revision,
        "run_id": state.run_id,
        "seed": str(state.seed),
        "rules_version": state.rules_version,
        "content_version": state.content_version,
        "run_phase": state.phase,
        "run_outcome": state.outcome,
        "battle": state.encounter_index + 1,
        "battle_count": engine.content.documents["encounters"]["battle_count"],
        "combat_phase": combat.phase,
        "timeline_tick": combat.timeline_tick,
        "ready_threshold": balance["timeline"]["ready_threshold"],
        "active_combatant_id": combat.active_combatant_id,
        "combatants": [combatant_view(engine, c) for c in combat.sorted_combatants()],
        "forecast": timeline.forecast(combat, balance, 8) if state.phase == RunPhase.BATTLE else [],
        "permissible_commands": engine.permissible_commands(),
        "needs_input": engine.needs_input(),
        "intent": None,
        "hero_turn": None,
        "reaction": None,
        "upgrade": None,
        "battle_records": list(state.battle_records),
    }
    if state.phase == RunPhase.BATTLE:
        snap["intent"] = intent_view(engine)
        snap["hero_turn"] = hero_turn_view(engine)
        if combat.phase in CombatPhase.STAGE_BY_WINDOW and combat.reaction_stage is not None:
            snap["reaction"] = {
                "stage": combat.reaction_stage,
                "stage_number": combat.stage_index + 1,
                "options": reactions.stage_options(engine, combat.reaction_stage),
                "used": [
                    {"hero_id": r.reacting_hero_id, "reaction": r.effect, "stage": r.reaction_stage} for r in combat.reactions_used
                ],
            }
    if state.phase in (RunPhase.UPGRADE, RunPhase.EQUIPMENT):
        snap["upgrade"] = upgrade_view(engine)
    return snap


# --------------------------------------------------------------------------------------------
# Human-readable combat history
# --------------------------------------------------------------------------------------------


def describe_event(event: CombatEvent, names: dict[str, str]) -> str | None:
    """Player-facing log line for an event, or ``None`` for purely technical events."""

    def name(cid: str | None) -> str:
        return names.get(cid or "", cid or "?")

    d = event.delta
    kind = event.type
    actor = name(event.actor_id)
    if kind == EventType.BATTLE_STARTED:
        return f"--- Battle {d['battle']} begins ---"
    if kind == EventType.ACTIVATION_STARTED:
        return f"> {actor} acts (speed {d['speed']}, tick {event.tick})."
    if kind == EventType.POISON_TICK:
        return f"{actor} takes {d['hp_damage']} Poison damage (bypasses shields)."
    if kind == EventType.COMBATANT_DOWNED:
        return f"{name(d['id'])} is DOWNED."
    if kind == EventType.COMBATANT_DEFEATED:
        return f"{name(d['id'])} is defeated."
    if kind == EventType.HERO_REVIVED:
        return f"{name(d['id'])} is revived at {d['hp']} HP (gauge reset to 0)."
    if kind == EventType.DICE_ROLLED:
        return f"{actor} rolls {d['die_id']}: {d['face_name']} (face {d['face']}/{d['die_size']})."
    if kind == EventType.DICE_REROLLED:
        return f"{actor} rerolls {d['die_id']}: {d['face_name']} (face {d['face']}/{d['die_size']}); {d['rerolls_remaining']} reroll(s) left."
    if kind == EventType.HERO_PASSED:
        return f"{actor} passes."
    if kind == EventType.PLAN_COMMITTED and d["actions"]:
        plan = ", then ".join(a["name"] for a in d["actions"])
        discarded = f" Discarded: {', '.join(d['discarded_dice'])}." if d["discarded_dice"] else ""
        return f"{actor} commits: {plan}.{discarded}"
    if kind == EventType.ACTION_RESOLVED:
        parts = []
        for r in d["results"]:
            target = name(r["target"])
            if r["type"] == "damage":
                mods = []
                if r["bonus"]:
                    mods.append(f"+{r['bonus']} bonus")
                if r["weaken"]:
                    mods.append(f"-{r['weaken']} Weaken")
                if r["mitigation"]:
                    mods.append(f"-{r['mitigation']} Disrupt")
                detail = f" [{r['base']} base{', ' if mods else ''}{', '.join(mods)}]" if mods else ""
                shield = f", {r['absorbed']} absorbed by shield" if r["absorbed"] else ""
                parts.append(f"{target} takes {r['hp_damage']} damage{shield}{detail}")
            elif r["type"] == "shield":
                bonus = f" (incl. +{r['bonus']} Steadfast)" if r.get("bonus") else ""
                parts.append(f"{target} gains {r['gained']} shield{bonus}")
            elif r["type"] == "heal":
                parts.append(f"{target} is revived" if r["revived"] else f"{target} heals {r['healed']}")
            elif r["type"] == "apply_status":
                label = STATUS_LABELS[r["status"]]
                outcome = ", ".join(a["result"].replace("_", " ") for a in r["applied"]) or "no effect"
                parts.append(f"{label} on {target}: {outcome}")
            elif r["type"] == "gain_mana":
                parts.append(f"{target} gains {r['gained']} mana")
            elif r["type"] == "gain_corruption":
                parts.append(f"{target} gains {r['gained']} corruption")
            elif r["type"] == "remove_corruption":
                parts.append(f"{target} loses {r['removed']} corruption")
        cost = f" (-{d['mana_spent']} mana)" if d.get("mana_spent") else ""
        return f"{actor} uses {d['name']}{cost}: " + ("; ".join(parts) if parts else "no effect") + "."
    if kind == EventType.ACTION_RETARGETED:
        return f"{actor}'s {d['name']} retargets {name(d['from'])} -> {name(d['to'])} ({d['rule']})."
    if kind == EventType.ACTION_CANCELLED:
        return f"{actor}'s {d['name']} is cancelled: {d['reason']}. No cost spent."
    if kind == EventType.INTENT_REVEALED:
        targets = ", ".join(name(t) for t in d["target_ids"])
        flags = []
        if d["elite_resistant"]:
            flags.append("elite-resistant")
        elif d["interruptible"]:
            flags.append("interruptible")
        if not d["reactable"]:
            flags.append("not reactable")
        return f"{actor} intends {d['name']} ({d['category']} {d['power']}) on {targets} [{', '.join(flags) or 'basic'}]."
    if kind == EventType.ENEMY_PASSED:
        return f"{actor} has no legal action and passes."
    if kind == EventType.REACTION_STAGE_OPENED:
        return f"Reaction window: {d['stage'].capitalize()} stage."
    if kind == EventType.REACTION_STAGE_SKIPPED and d["reason"] == "skipped by player":
        return f"{d['stage'].capitalize()} stage skipped."
    if kind == EventType.REACTION_USED:
        targets = f" on {', '.join(name(t) for t in d['target_ids'])}" if d["target_ids"] else ""
        cost = f" (-{d['mana_spent']} mana)" if d["mana_spent"] else ""
        return f"{actor} reacts with {d['name']}{targets}{cost}."
    if kind == EventType.INTENT_CANCELLED:
        return f"{d['name']} is interrupted by {name(d['by'])}."
    if kind == EventType.INTENT_WEAKENED:
        return f"{d['name']} resists the interrupt but is weakened (-{d['damage_reduction']} damage, -{d['magnitude_reduction']} magnitude)."
    if kind == EventType.CORRUPTION_BACKLASH:
        return f"{actor} suffers {d['hp_damage']} corruption backlash (corruption {d['corruption']})."
    if kind == EventType.STATUS_EXPIRED:
        return f"{STATUS_LABELS[d['status']]} expires on {name(d['id'])}."
    if kind == EventType.BATTLE_WON:
        return f"*** Battle {d['battle']} won ***"
    if kind == EventType.BATTLE_LOST:
        return f"*** Battle {d['battle']} lost: no hero is standing ***"
    if kind == EventType.RECOVERY_APPLIED:
        return "Recovery: HP partly restored, mana refilled, shields and statuses cleared. Corruption persists."
    if kind == EventType.UPGRADE_APPLIED:
        return f"Upgrade: {d['kind'].capitalize()} on {name(d['hero_id'])}'s {d['die_id']} face {d['face_index'] + 1}: {d['before']['name']} -> {d['after']['name']}."
    if kind == EventType.DIE_SWAPPED:
        return f"{name(d['hero_id'])} swaps {d['out_die_id']} for {d['in_die_id']}."
    if kind == EventType.FORMATION_CHANGED:
        return f"{actor} moves to the {d['to']} row."
    return None


def combat_log(engine: Engine, limit: int | None = None) -> list[str]:
    names: dict[str, str] = {}
    for event in engine.events:
        if event.type == EventType.BATTLE_STARTED:
            names.update({entry["id"]: entry["name"] for entry in event.delta["roster"]})
    lines = [line for line in (describe_event(e, names) for e in engine.events) if line]
    return lines if limit is None else lines[-limit:]
