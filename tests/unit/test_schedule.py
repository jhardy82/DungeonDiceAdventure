"""Schedules as ordered slots (``core/schedule.py``).

Two things are checked. First, for the shipped schedules the slot model accepts, rejects (with the
same words) and orders exactly what the code it replaced did; that old code is kept here as the
reference. Second, the shapes the Class Evolution catalog needs and no shipped class uses.
"""

from __future__ import annotations

import dataclasses
import sys
from itertools import permutations, product
from pathlib import Path
from typing import Any

import pytest

from battle_dice.core import commands as cmd
from battle_dice.core import planning
from battle_dice.core.models import EXECUTABLE_CATEGORIES, FaceDefinition
from battle_dice.core.schedule import ORDER_ACTION_SPEED, ORDER_SLOTS, Schedule, ScheduleError, Slot
from tests.conftest import (
    action,
    begin_hero,
    enemies,
    events_of,
    ok,
    packaged_content,
    rejected,
    resolve_hero,
    start,
)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from class_evolution import validate_catalog as vc  # noqa: E402

EVERY = tuple(EXECUTABLE_CATEGORIES)
FREE_2 = {"policy": "free", "label": "Free Actions", "max_actions": 2, "summary": "Test-only policy."}
FREE_3 = {"policy": "free", "label": "Free", "max_actions": 3, "summary": ""}


def face(category: str, speed: int = 1, tags: tuple[str, ...] = (), name: str | None = None) -> FaceDefinition:
    return FaceDefinition(
        id=f"t_{category}_{speed}", name=name or category.capitalize(), category=category, power=1, target_scope="self",
        range_type="self", action_speed=speed, mana_cost=0, effects=[], can_revive=False, tags=list(tags),
    )


def slots(*shapes: Any, distinct: bool = True, order: str = ORDER_SLOTS, label: str = "Test") -> Schedule:
    block = {
        "policy": "slots", "label": label, "summary": "Test-only schedule.", "max_actions": len(shapes),
        "slots": [shape if isinstance(shape, dict) else {"categories": list(shape)} for shape in shapes],
        "distinct_categories": distinct, "order": order,
    }
    return Schedule.from_scheduling(block)


# --------------------------------------------------------------------------------------------
# The shipped schedules read into the slot model
# --------------------------------------------------------------------------------------------


def test_the_three_shipped_schedules_as_slots():
    classes = packaged_content().classes
    squire, apprentice, scout = (Schedule.from_scheduling(classes[c]["scheduling"]) for c in ("squire", "apprentice", "scout"))
    assert squire == Schedule("Single Commitment", "One dice action per activation.", 1, (Slot(EVERY),), False, ORDER_ACTION_SPEED)
    assert (apprentice.max_actions, apprentice.distinct_categories, apprentice.order) == (2, True, ORDER_SLOTS)
    assert apprentice.slots == (Slot(("resource",)), Slot(("attack", "defense", "healing", "status")))
    assert scout.slots == (Slot(("status",)), Slot(("attack",))) and scout.order == ORDER_SLOTS
    assert (squire.opening_categories, apprentice.opening_categories, scout.opening_categories) == ((), ("resource",), ("status",))
    free = Schedule.from_scheduling(FREE_3)
    assert free.slots == (Slot(EVERY),) * 3 and not free.distinct_categories and free.opening_categories == ()


# -- the code the slot model replaced, kept as the reference -------------------------------------


def old_check(faces: list[FaceDefinition], scheduling: dict[str, Any]) -> str | None:
    count = len(faces)
    if count > scheduling["max_actions"]:
        return f"{scheduling['label']} allows at most {scheduling['max_actions']} action(s) per activation."
    if scheduling["policy"] == "sequence" and count == 2:
        first = scheduling["first_category"]
        seconds = scheduling["second_categories"]
        categories = [f.category for f in faces]
        firsts = [c for c in categories if c == first]
        others = [c for c in categories if c != first]
        if len(firsts) != 1 or len(others) != 1 or others[0] not in seconds:
            allowed = " or ".join(s.capitalize() for s in seconds)
            return f"{scheduling['label']}: two actions are only allowed as {first.capitalize()} first, then {allowed}."
    return None


def old_order(entries: list[tuple[FaceDefinition, int]], scheduling: dict[str, Any]) -> list[int]:
    indices = list(range(len(entries)))
    if scheduling["policy"] == "sequence" and len(entries) == 2:
        first = scheduling["first_category"]
        return sorted(indices, key=lambda i: (0 if entries[i][0].category == first else 1, entries[i][1]))
    return sorted(indices, key=lambda i: (-(entries[i][0].action_speed or 0), entries[i][1]))


def shipped_blocks() -> list[dict[str, Any]]:
    return [c["scheduling"] for c in packaged_content().classes.values()] + [FREE_2, FREE_3]


@pytest.mark.parametrize("block", shipped_blocks(), ids=lambda b: b["label"])
def test_the_slot_model_decides_and_orders_exactly_as_the_old_code(block):
    """Every multiset of up to four faces (five categories, three speeds), in every player order."""
    schedule = Schedule.from_scheduling(block)
    kinds = [face(category, speed) for category in EVERY for speed in (1, 2, 3)]
    compared = 0
    for count in range(0, 5):
        if count > block["max_actions"] + 1:
            break
        for chosen in product(kinds, repeat=count):
            for player_order in set(permutations(range(count))):
                entries = list(zip(chosen, player_order, strict=True))
                expected = old_check(list(chosen), block)
                try:
                    actual_order = schedule.resolution_order(entries, strict=True)
                    actual = None
                except ScheduleError as error:
                    actual_order, actual = [], str(error)
                assert actual == expected, ([f.category for f in chosen], player_order)
                if expected is None:
                    assert actual_order == old_order(entries, block), ([f.category for f in chosen], player_order)
                    assert planning.order_actions(entries, block) == old_order(entries, block)
                compared += 1
    assert compared > 200


def test_the_shipped_messages_are_word_for_word():
    classes = packaged_content().classes
    scout = Schedule.from_scheduling(classes["scout"]["scheduling"])
    apprentice = Schedule.from_scheduling(classes["apprentice"]["scheduling"])
    squire = Schedule.from_scheduling(classes["squire"]["scheduling"])
    with pytest.raises(ScheduleError) as scout_error:
        scout.check([face("attack"), face("attack")])
    assert str(scout_error.value) == "Exploit Combo: two actions are only allowed as Status first, then Attack."
    with pytest.raises(ScheduleError) as apprentice_error:
        apprentice.check([face("resource"), face("resource")])
    assert str(apprentice_error.value) == (
        "Channel and Cast: two actions are only allowed as Resource first, then Attack or Defense or Healing or Status."
    )
    with pytest.raises(ScheduleError) as squire_error:
        squire.check([face("attack"), face("defense")])
    assert str(squire_error.value) == "Single Commitment allows at most 1 action(s) per activation."


# --------------------------------------------------------------------------------------------
# Shapes the catalog needs and no shipped class uses
# --------------------------------------------------------------------------------------------


def test_one_action_is_always_legal_whatever_its_category():
    schedule = slots(["status"], ["attack"])
    for category in EVERY:
        schedule.check([face(category)])
    schedule.check([])


def test_two_categories_in_the_first_slot():
    """Duelist: Defense or Status, then Attack."""
    schedule = slots(["defense", "status"], ["attack"], label="Defense or Status then Attack")
    assert schedule.opening_categories == ("defense", "status")
    for opener in ("defense", "status"):
        entries = [(face("attack", 3), 0), (face(opener, 1), 1)]
        assert schedule.resolution_order(entries, strict=True) == [1, 0], "slot order beats action speed and the player's order"
    with pytest.raises(ScheduleError) as error:
        schedule.check([face("resource"), face("attack")])
    assert str(error.value) == "Defense or Status then Attack: two actions are only allowed as Defense or Status first, then Attack."
    with pytest.raises(ScheduleError):
        schedule.check([face("defense"), face("status")])


def test_a_slot_can_require_a_face_tag():
    """Arcanist: Resource, then a spell Attack or spell Healing face."""
    schedule = slots(["resource"], {"categories": ["attack", "healing"], "tags_any": ["spell"]}, label="Resource then Spell or Heal")
    schedule.check([face("resource"), face("attack", tags=("ranged", "spell"))])
    schedule.check([face("healing", tags=("spell",)), face("resource")])
    with pytest.raises(ScheduleError) as error:
        schedule.check([face("resource"), face("attack", tags=("melee",))])
    assert str(error.value) == "Resource then Spell or Heal: two actions are only allowed as Resource first, then spell Attack or Healing."
    schedule.check([face("attack", tags=("melee",))])  # alone, any face is legal


def test_three_slots_are_all_or_one():
    """Archmage: Resource, Attack, then Healing or Defense. Two of the three is not a legal plan (v0.1 reads 'otherwise one')."""
    schedule = slots(["resource"], ["attack"], ["healing", "defense"], label="Resource, Attack, Support")
    entries = [(face("defense", 3), 0), (face("attack", 2), 1), (face("resource", 1), 2)]
    assert schedule.resolution_order(entries, strict=True) == [2, 1, 0]
    with pytest.raises(ScheduleError) as error:
        schedule.check([face("resource"), face("attack")])
    assert str(error.value) == (
        "Resource, Attack, Support: three actions are only allowed as Resource first, then Attack, then Healing or Defense."
    )
    with pytest.raises(ScheduleError):
        schedule.check([face("resource"), face("attack"), face("status")])
    with pytest.raises(ScheduleError) as too_many:
        schedule.check([face("resource"), face("attack"), face("healing"), face("defense")])
    assert "allows at most 3 action(s)" in str(too_many.value)


def test_two_distinct_categories_resolve_by_action_speed():
    """Hero: any two actions of different categories."""
    schedule = slots(EVERY, EVERY, order=ORDER_ACTION_SPEED, label="Two Distinct Categories")
    assert schedule.opening_categories == ()
    assert schedule.resolution_order([(face("attack", 1), 0), (face("defense", 2), 1)], strict=True) == [1, 0]
    assert schedule.resolution_order([(face("attack", 2), 1), (face("status", 2), 0)], strict=True) == [1, 0]  # tie: player's order
    with pytest.raises(ScheduleError) as error:
        schedule.check([face("attack"), face("attack")])
    assert str(error.value) == "Two Distinct Categories: the actions must be of different categories."


def test_narrow_slots_without_an_order_still_need_a_slot_each():
    schedule = slots(["attack"], ["defense", "healing"], distinct=False, order=ORDER_ACTION_SPEED, label="Strike and Mend")
    schedule.check([face("healing"), face("attack")])
    with pytest.raises(ScheduleError) as error:
        schedule.check([face("attack"), face("attack")])
    assert str(error.value) == "Strike and Mend: these actions do not fit together in one activation."


def test_overlapping_slots():
    """Trickster: Status or Resource, then Attack or Resource."""
    schedule = slots(["status", "resource"], ["attack", "resource"], label="Trickster Two-Step")
    for first, second in (("status", "attack"), ("resource", "attack"), ("status", "resource")):
        assert schedule.resolution_order([(face(second), 0), (face(first), 1)], strict=True) == [1, 0], (first, second)
    for bad in (("resource", "resource"), ("attack", "attack"), ("status", "status"), ("defense", "attack")):
        with pytest.raises(ScheduleError):
            schedule.check([face(bad[0]), face(bad[1])])
    # When both fillings are valid, the player's order decides.
    loose = slots(["status", "resource"], ["attack", "resource"], distinct=False)
    assert loose.resolution_order([(face("resource", name="A"), 1), (face("resource", name="B"), 0)], strict=True) == [1, 0]


def test_without_strict_actions_that_do_not_fit_resolve_by_speed():
    schedule = slots(["status"], ["attack"])
    assert schedule.resolution_order([(face("attack", 1), 0), (face("attack", 3), 1)]) == [1, 0]
    assert schedule.resolution_order([(face("attack", 1), 0), (face("defense", 2), 1), (face("status", 3), 2)]) == [2, 1, 0]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"policy": "chaos"}, "Unknown scheduling policy 'chaos'"),
        ({"order": "alphabetical"}, "Unknown schedule order 'alphabetical'"),
        ({"max_actions": 3}, "has 2 slot(s) but max_actions 3"),
    ],
)
def test_a_malformed_block_is_refused(change, message):
    block = {"policy": "slots", "label": "Test", "summary": "", "max_actions": 2,
             "slots": [{"categories": ["status"]}, {"categories": ["attack"]}], "distinct_categories": True, "order": "slots"}
    with pytest.raises(ValueError, match=message.replace("(", r"\(").replace(")", r"\)")):
        Schedule.from_scheduling({**block, **change})


# --------------------------------------------------------------------------------------------
# The catalog's schedules and the engine
# --------------------------------------------------------------------------------------------


def test_every_catalog_schedule_reads_into_the_slot_model_and_the_existing_ones_match_their_shipped_form():
    catalog = vc.load_catalog()
    assert len(catalog["schedules"]) == 10
    for entry in catalog["schedules"]:
        schedule = Schedule.from_scheduling({"policy": "slots", **entry})
        assert schedule.label == entry["label"] and len(schedule.slots) == entry["max_actions"]
        if entry["engine_support"] == "existing":
            assert schedule == Schedule.from_scheduling(vc.shipped_scheduling(entry)), entry["id"]
    for class_id, cls in packaged_content().classes.items():
        as_catalog = vc.slot_schedule(class_id, cls["scheduling"])
        assert Schedule.from_scheduling({"policy": "slots", **as_catalog}) == Schedule.from_scheduling(cls["scheduling"]), class_id


def test_a_hero_whose_build_has_a_slot_schedule_plans_and_resolves_by_it():
    """A Scout given the Duelist's schedule: Defense now opens the combo, and the combo bonus follows it."""
    engine = start("scout", content=packaged_content())
    duelist = {"policy": "slots", "label": "Defense or Status then Attack", "summary": "Test.", "max_actions": 2,
               "slots": [{"categories": ["defense", "status"]}, {"categories": ["attack"]}], "distinct_categories": True, "order": "slots"}
    engine._builds["h01"] = dataclasses.replace(engine.build("h01"), scheduling=duelist)
    foe = enemies(engine)[0]
    begin_hero(engine, "h01", striker_d8=1, tools_d4=3)  # Shot (attack) and Cover (defense)
    ok(engine.do(cmd.SET_ACTION_PLAN, actions=[action("striker_d8", foe.id), action("tools_d4", "h01")]))
    assert [intent.category for intent in engine.combat.turn.plan] == ["defense", "attack"]
    hp_before = foe.hp
    shot = engine.die_for("h01", "striker_d8").faces[0]
    bonus = engine.build("h01").passive["amount"]
    resolve_hero(engine, action("striker_d8", foe.id), action("tools_d4", "h01"))
    assert [e.delta["name"] for e in events_of(engine, "action_resolved")] == ["Cover", "Shot"]
    assert hp_before - foe.hp == shot.power + bonus, "the Defense opener grants the combo bonus to the Attack"

    two_attacks = start("scout", content=packaged_content())
    two_attacks._builds["h01"] = dataclasses.replace(two_attacks.build("h01"), scheduling=duelist)
    target = enemies(two_attacks)[0].id
    begin_hero(two_attacks, "h01", striker_d8=1, tools_d4=1)
    rejected(
        two_attacks.do(cmd.SET_ACTION_PLAN, actions=[action("striker_d8", target), action("tools_d4", target)]),
        "only allowed as Defense or Status first, then Attack",
    )
