"""Bonus-challenge evidence, counted from a battle's event log.

A vocation's bonus challenge gives one more mastery point for an eligible win in which the hero
did what the challenge describes. Nothing is added to the rules engine for this: the events of
the battle already say what happened, and this module reads them.

One thing the log does not say is whose shield absorbed a hit: a combatant's shields are one
number. So shields are attributed **first in, first out** per target: the shield that was granted
first is the first to be used up. That rule is this build's reading; it is written here and in
the decision log so that it can be changed in one place.

The five challenges of the vocations the rules can run today:

``protect_ally`` (Squire)
    A Defense die of the hero put a shield on *another* ally, and that shield absorbed at least 1
    damage.
``prevent_3_damage`` (Guardian)
    Shields the hero gave another ally, by a Defense die or by its guard reaction, absorbed at
    least 3 damage from one enemy action.
``resource_into_action`` (Apprentice)
    The hero committed two actions, a Resource and another kind, and both resolved.
``status_into_attack`` (Scout) and ``mark_and_strike`` (Ranger)
    The hero committed a Status and an Attack, and both resolved. Every attack a Ranger can roll is
    ranged (the catalog validator checks that), so the two challenges are counted the same way.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from battle_dice.core.events import EventType
from battle_dice.core.models import CombatEvent

#: Challenge id -> the rule that counts it. A challenge that is not here has no evidence yet.
SEQUENCES: dict[str, tuple[str, str | None]] = {
    "resource_into_action": ("resource", None),  # a Resource and any other category
    "status_into_attack": ("status", "attack"),
    "mark_and_strike": ("status", "attack"),
}
SHIELD_CHALLENGES = ("protect_ally", "prevent_3_damage")
COUNTED = (*SHIELD_CHALLENGES, *SEQUENCES)
PREVENT_AT_LEAST = 3


def battle_events(events: Iterable[CombatEvent], battle: int) -> list[CombatEvent]:
    """The events of one battle of a run, from its start to its end."""
    inside, found = False, []
    for event in events:
        if event.type == EventType.BATTLE_STARTED:
            inside = event.delta["battle"] == battle
        if inside:
            found.append(event)
        if inside and event.type in (EventType.BATTLE_WON, EventType.BATTLE_LOST):
            break
    return found


def challenge_evidence(events: Iterable[CombatEvent]) -> dict[str, dict[str, int]]:
    """``{hero id: {challenge id: evidence count}}`` for the events of one battle."""
    counts: dict[str, dict[str, int]] = defaultdict(lambda: dict.fromkeys(COUNTED, 0))
    #: target -> the shields on it, oldest first: [granting hero, whether a Defense die or a guard reaction gave it, what is left]
    shields: dict[str, list[list[Any]]] = defaultdict(list)
    plans: dict[str, list[dict[str, Any]]] = {}  # hero -> the actions of its current activation
    resolved: dict[str, set[str]] = defaultdict(set)

    for event in events:
        delta, actor = event.delta, event.actor_id
        if event.type == EventType.BATTLE_STARTED or event.type == EventType.RECOVERY_APPLIED:
            shields.clear()  # every battle starts without shields, and recovery removes them
        elif event.type == EventType.PLAN_COMMITTED and actor is not None:
            plans[actor] = list(delta["actions"])
            resolved[actor] = set()
        elif event.type == EventType.REACTION_USED and actor is not None:
            for result in delta["results"]:
                if result["type"] == "shield" and result["gained"] > 0:
                    shields[result["target"]].append([actor, delta["stage"] == "guard", result["gained"]])
        elif event.type == EventType.ACTION_RESOLVED and actor is not None:
            if delta["side"] == "hero":
                for result in delta["results"]:
                    if result["type"] == "shield" and result["gained"] > 0:
                        shields[result["target"]].append([actor, delta["category"] == "defense", result["gained"]])
                _count_sequences(counts, plans.get(actor, []), resolved[actor], event.intent_id, actor)
            else:
                _count_absorbed(counts, shields, delta["results"])
    return {hero: dict(found) for hero, found in counts.items()}


def _count_sequences(counts: dict[str, dict[str, int]], plan: list[dict[str, Any]], done: set[str], intent_id: str | None, hero: str) -> None:
    """Called for each resolved action of a hero: when it completes a two-action plan, count the sequences it is."""
    if intent_id is None or len(plan) != 2 or intent_id not in {action["intent_id"] for action in plan}:
        return
    done.add(intent_id)
    if len(done) != 2:
        return
    categories = {action["category"] for action in plan}
    for challenge, (first, second) in SEQUENCES.items():
        if first in categories and len(categories) == 2 and (second is None or second in categories):
            counts[hero][challenge] += 1


def _count_absorbed(counts: dict[str, dict[str, int]], shields: dict[str, list[list[Any]]], results: list[dict[str, Any]]) -> None:
    """One enemy action: use the shields up oldest first and credit the heroes who gave them."""
    prevented: dict[tuple[str, str], int] = defaultdict(int)  # (granting hero, target) -> absorbed in this action
    for result in results:
        left = result.get("absorbed", 0) if result["type"] == "damage" else 0
        target = result.get("target")
        ledger = shields[target] if target is not None else []
        while left > 0 and ledger:
            source, counts_for_challenge, remaining = ledger[0]
            used = min(left, remaining)
            left -= used
            ledger[0][2] -= used
            if ledger[0][2] == 0:
                ledger.pop(0)
            if counts_for_challenge and target is not None and source != target:
                prevented[(str(source), str(target))] += used
    for (source, _target), amount in prevented.items():
        counts[source]["protect_ally"] += 1
        if amount >= PREVENT_AT_LEAST:
            counts[source]["prevent_3_damage"] += 1
