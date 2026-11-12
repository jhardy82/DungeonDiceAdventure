"""Bonus-challenge evidence is counted from a battle's events (Class Evolution Phase 4, step C).

Shields are attributed first in, first out per target: the log does not say whose shield absorbed
a hit. That rule is this build's reading and is tested here as such.
"""

from __future__ import annotations

from battle_dice.career.evidence import COUNTED, battle_events, challenge_evidence
from battle_dice.core import commands as cmd
from battle_dice.core.engine import Engine
from battle_dice.core.events import EventType
from battle_dice.core.models import CombatEvent
from battle_dice.sim.policies import HeuristicPolicy, play_run
from tests.conftest import packaged_content


def event(kind: str, actor: str | None = None, intent: str | None = None, **delta) -> CombatEvent:
    return CombatEvent(seq=0, tick=0, actor_id=actor, type=kind, intent_id=intent, delta=delta, before={}, after={})


def shield(actor: str, target: str, gained: int, category: str = "defense") -> CombatEvent:
    return event(EventType.ACTION_RESOLVED, actor, "a1", side="hero", category=category, results=[{"type": "shield", "target": target, "gained": gained}])


def guard(actor: str, target: str, gained: int, stage: str = "guard") -> CombatEvent:
    return event(EventType.REACTION_USED, actor, "e1", stage=stage, results=[{"type": "shield", "target": target, "gained": gained}])


def hit(target: str, absorbed: int, intent: str = "e1", more: list | None = None) -> CombatEvent:
    results = [{"type": "damage", "target": target, "absorbed": absorbed}, *(more or [])]
    return event(EventType.ACTION_RESOLVED, "b1_e01", intent, side="enemy", category="attack", results=results)


def plan(actor: str, *categories: str) -> list[CombatEvent]:
    actions = [{"intent_id": f"{actor}-{n}", "category": c} for n, c in enumerate(categories)]
    resolved = [event(EventType.ACTION_RESOLVED, actor, a["intent_id"], side="hero", category=a["category"], results=[]) for a in actions]
    return [event(EventType.PLAN_COMMITTED, actor, actions=actions), *resolved]


def count(events: list[CombatEvent], hero: str, challenge: str) -> int:
    return challenge_evidence(events).get(hero, dict.fromkeys(COUNTED, 0))[challenge]


def test_a_defense_die_shield_on_another_ally_that_absorbs_damage_is_protect_ally():
    events = [shield("h01", "h02", 3), hit("h02", 2)]
    assert count(events, "h01", "protect_ally") == 1 and count(events, "h01", "prevent_3_damage") == 0
    assert count([shield("h01", "h02", 3), hit("h02", 0)], "h01", "protect_ally") == 0  # nothing was absorbed
    assert count([shield("h01", "h01", 3), hit("h01", 2)], "h01", "protect_ally") == 0  # itself is not another ally
    assert count([shield("h01", "h02", 3, category="healing"), hit("h02", 2)], "h01", "protect_ally") == 0  # not a Defense die


def test_three_absorbed_from_one_enemy_action_is_prevent_3_damage():
    assert count([shield("h01", "h02", 4), hit("h02", 3)], "h01", "prevent_3_damage") == 1
    assert count([guard("h01", "h02", 3), hit("h02", 3)], "h01", "prevent_3_damage") == 1  # the guard reaction counts too
    assert count([guard("h01", "h02", 3, stage="resource"), hit("h02", 3)], "h01", "prevent_3_damage") == 0
    # Two and then one, from two different enemy actions, is not three from one.
    assert count([shield("h01", "h02", 4), hit("h02", 2, "e1"), hit("h02", 1, "e2")], "h01", "prevent_3_damage") == 0
    # A die and a reaction of the same hero on the same ally add up within one action.
    assert count([shield("h01", "h02", 2), guard("h01", "h02", 2), hit("h02", 4)], "h01", "prevent_3_damage") == 1


def test_shields_are_used_up_first_in_first_out():
    """Scout's cover came first, so it absorbs first; the Squire's shield takes what is left."""
    events = [shield("h03", "h02", 2), shield("h01", "h02", 3), hit("h02", 4)]
    found = challenge_evidence(events)
    assert found["h03"]["protect_ally"] == 1 and found["h01"]["protect_ally"] == 1
    assert found["h01"]["prevent_3_damage"] == 0  # only 2 of the 4 were the Squire's
    # With 2 absorbed the older shield takes it all and the newer one is not credited.
    assert "h01" not in challenge_evidence([shield("h03", "h02", 2), shield("h01", "h02", 3), hit("h02", 2)])


def test_recovery_and_a_new_battle_remove_the_shields():
    for cleared in (event(EventType.RECOVERY_APPLIED, heroes=[]), event(EventType.BATTLE_STARTED, battle=2, encounter_id="x")):
        assert challenge_evidence([shield("h01", "h02", 3), cleared, hit("h02", 3)]) == {}


def test_two_action_plans_are_counted_when_both_actions_resolve():
    assert count(plan("h01", "resource", "attack"), "h01", "resource_into_action") == 1
    assert count(plan("h01", "resource", "resource"), "h01", "resource_into_action") == 0  # two Resources are not Resource then another
    status_attack = plan("h02", "status", "attack")
    assert count(status_attack, "h02", "status_into_attack") == 1 and count(status_attack, "h02", "mark_and_strike") == 1
    assert count(plan("h02", "status", "defense"), "h02", "status_into_attack") == 0
    assert count(plan("h02", "attack"), "h02", "status_into_attack") == 0  # one action is not a sequence
    # The second action was cancelled: only one resolved, so nothing is counted.
    assert count(status_attack[:2], "h02", "status_into_attack") == 0
    # Three actions are not a two-action sequence, whatever their categories (a later vocation has three slots).
    assert challenge_evidence(plan("h01", "resource", "attack", "attack")) == {}
    assert challenge_evidence(plan("h02", "status", "attack", "attack")) == {}


def test_the_events_of_one_battle_are_cut_out_of_a_run():
    engine = Engine(packaged_content())
    assert engine.do(cmd.START_RUN, seed=5, party=[{"class_id": "squire", "row": "front"}, {"class_id": "scout", "row": "back"},
                                                   {"class_id": "apprentice", "row": "back"}]).accepted
    play_run(engine, HeuristicPolicy())
    first, second = battle_events(engine.events, 1), battle_events(engine.events, 2)
    assert first[0].type == EventType.BATTLE_STARTED and first[0].delta["battle"] == 1 and first[-1].type == EventType.BATTLE_WON
    assert second[0].delta["battle"] == 2 and second[-1].type in (EventType.BATTLE_WON, EventType.BATTLE_LOST)
    assert not {e.seq for e in first} & {e.seq for e in second} and battle_events(engine.events, 3) == []
    found = challenge_evidence(first)
    assert set(found) <= {"h01", "h02", "h03"} and all(set(row) == set(COUNTED) for row in found.values())
    # On real events the Scout's Status then Attack turns show up, and nothing is ever negative.
    assert found.get("h02", {}).get("status_into_attack", 0) >= 1
    assert all(value >= 0 for row in found.values() for value in row.values())
