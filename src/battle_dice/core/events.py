"""Observability: sequenced combat events, JSONL export, canonical state hashing (section 14.5)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from battle_dice.core.models import CombatEvent, to_plain


class EventType:
    RUN_STARTED = "run_started"
    BATTLE_STARTED = "battle_started"
    TIMELINE_ADVANCED = "timeline_advanced"
    ACTIVATION_STARTED = "activation_started"
    REACTION_CHARGE_REFRESHED = "reaction_charge_refreshed"
    POISON_TICK = "poison_tick"
    COMBATANT_DOWNED = "combatant_downed"
    COMBATANT_DEFEATED = "combatant_defeated"
    HERO_REVIVED = "hero_revived"
    DICE_ROLLED = "dice_rolled"
    DICE_KEPT = "dice_kept"
    DICE_REROLLED = "dice_rerolled"
    PLAN_SET = "plan_set"
    PLAN_COMMITTED = "plan_committed"
    HERO_PASSED = "hero_passed"
    ACTION_RESOLVED = "action_resolved"
    ACTION_RETARGETED = "action_retargeted"
    ACTION_CANCELLED = "action_cancelled"
    STATUS_APPLIED = "status_applied"
    STATUS_REFRESHED = "status_refreshed"
    STATUS_EXPIRED = "status_expired"
    INTENT_SELECTED = "intent_selected"
    INTENT_REVEALED = "intent_revealed"
    ENEMY_PASSED = "enemy_passed"
    REACTION_STAGE_OPENED = "reaction_stage_opened"
    REACTION_STAGE_SKIPPED = "reaction_stage_skipped"
    REACTION_USED = "reaction_used"
    INTENT_CANCELLED = "intent_cancelled"
    INTENT_WEAKENED = "intent_weakened"
    CORRUPTION_BACKLASH = "corruption_backlash"
    ACTIVATION_ENDED = "activation_ended"
    BATTLE_WON = "battle_won"
    BATTLE_LOST = "battle_lost"
    RECOVERY_APPLIED = "recovery_applied"
    UPGRADE_OFFERS_GENERATED = "upgrade_offers_generated"
    UPGRADE_APPLIED = "upgrade_applied"
    DIE_SWAPPED = "die_swapped"
    FORMATION_CHANGED = "formation_changed"
    RUN_VICTORY = "run_victory"
    #: A further encounter is on offer after a won battle (a run started with extra encounters).
    EXTRA_BATTLE_OFFERED = "extra_battle_offered"
    VOCATION_CHANGED = "vocation_changed"
    RUN_DEFEAT = "run_defeat"


def canonical_json(value: Any) -> str:
    return json.dumps(to_plain(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def state_hash(state: Any) -> str:
    """SHA-256 over the canonical JSON form of the full authoritative state."""
    return hashlib.sha256(canonical_json(state).encode("ascii")).hexdigest()


def events_hash(events: Iterable[CombatEvent]) -> str:
    digest = hashlib.sha256()
    for event in events:
        digest.update(canonical_json(event).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def write_jsonl(path: str | Path, header: dict[str, Any], events: Iterable[CombatEvent]) -> None:
    """Write a machine-readable log: one header line, then one JSON object per event."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps({"record": "header", **header}, sort_keys=True) + "\n")
        for event in events:
            handle.write(json.dumps({"record": "event", **to_plain(event)}, sort_keys=True) + "\n")


def summarize(events: Iterable[CombatEvent]) -> dict[str, int]:
    """Concise combat metrics for the outcome screen."""
    stats = {
        "activations": 0,
        "hero_activations": 0,
        "enemy_activations": 0,
        "damage_dealt": 0,
        "damage_taken": 0,
        "shield_absorbed": 0,
        "healing_done": 0,
        "rerolls_used": 0,
        "reactions_used": 0,
        "heroes_downed": 0,
        "enemies_defeated": 0,
        "revivals": 0,
        "timeline_ticks": 0,
    }
    for event in events:
        kind = event.type
        if kind == EventType.ACTIVATION_STARTED:
            stats["activations"] += 1
            stats["hero_activations" if event.delta.get("side") == "hero" else "enemy_activations"] += 1
        elif kind == EventType.ACTION_RESOLVED:
            dealt = event.delta.get("side") == "hero"
            for result in event.delta.get("results", []):
                if result.get("type") == "damage":
                    stats["damage_dealt" if dealt else "damage_taken"] += result.get("hp_damage", 0)
                    if not dealt:
                        stats["shield_absorbed"] += result.get("absorbed", 0)
                elif result.get("type") == "heal":
                    stats["healing_done"] += result.get("healed", 0)
        elif kind in (EventType.POISON_TICK, EventType.CORRUPTION_BACKLASH):
            key = "damage_taken" if event.delta.get("side") == "hero" else "damage_dealt"
            stats[key] += event.delta.get("hp_damage", 0)
        elif kind == EventType.DICE_REROLLED and event.delta.get("first_of_reroll"):
            stats["rerolls_used"] += 1
        elif kind == EventType.REACTION_USED:
            stats["reactions_used"] += 1
        elif kind == EventType.COMBATANT_DOWNED:
            stats["heroes_downed"] += 1
        elif kind == EventType.COMBATANT_DEFEATED:
            stats["enemies_defeated"] += 1
        elif kind == EventType.HERO_REVIVED:
            stats["revivals"] += 1
        elif kind == EventType.TIMELINE_ADVANCED:
            stats["timeline_ticks"] += event.delta.get("ticks", 0)
    return stats
