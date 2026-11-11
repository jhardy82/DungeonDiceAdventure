"""A class's action schedule as ordered slots (sections 5.5 and 5.6).

A schedule says how many dice actions a hero may commit in one activation and in which shapes.
Every schedule is the same thing: a list of **slots**, each accepting some categories (and
optionally only faces with a tag).

* One action is always legal, whatever its category ("otherwise one").
* With ``order == "slots"`` several actions are legal only when they fill every slot, one action
  per slot, and they resolve in slot order: a class-defined dependency such as Status then Attack.
* With ``order == "action_speed"`` up to ``max_actions`` actions are legal when each fits a
  different slot; they resolve by action speed, the player's order breaking ties.
* ``distinct_categories`` forbids two actions of the same category.

The shipped ``scheduling`` blocks of ``classes.json`` (policies ``single``, ``sequence`` and
``free``) are read into this model; so are the slot schedules of the Class Evolution catalog
(policy ``slots``). The rules use this model only.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations
from typing import Any

from battle_dice.core.models import EXECUTABLE_CATEGORIES, FaceDefinition

ORDER_SLOTS = "slots"
ORDER_ACTION_SPEED = "action_speed"
_COUNT_WORDS = {2: "two", 3: "three", 4: "four"}


class ScheduleError(ValueError):
    """The actions do not fit the schedule. The message is shown to the player."""


@dataclass(frozen=True)
class Slot:
    categories: tuple[str, ...]
    tags_any: tuple[str, ...] = ()

    def accepts(self, face: FaceDefinition) -> bool:
        if face.category not in self.categories:
            return False
        return not self.tags_any or any(tag in face.tags for tag in self.tags_any)

    def describe(self) -> str:
        names = " or ".join(category.capitalize() for category in self.categories)
        return f"{'/'.join(self.tags_any)} {names}" if self.tags_any else names


@dataclass(frozen=True)
class Schedule:
    label: str
    summary: str
    max_actions: int
    slots: tuple[Slot, ...]
    distinct_categories: bool
    order: str

    @classmethod
    def from_scheduling(cls, block: dict[str, Any]) -> Schedule:
        """Read a ``scheduling`` block: a shipped policy, or the catalog's slot form (policy ``slots``)."""
        policy = block["policy"]
        every = tuple(EXECUTABLE_CATEGORIES)
        if policy == "sequence":
            slots: tuple[Slot, ...] = (Slot((block["first_category"],)), Slot(tuple(block["second_categories"])))
            distinct, order = True, ORDER_SLOTS
        elif policy in ("single", "free"):
            slots = tuple(Slot(every) for _ in range(block["max_actions"]))
            distinct, order = False, ORDER_ACTION_SPEED
        elif policy == "slots":
            slots = tuple(Slot(tuple(s["categories"]), tuple(s.get("tags_any", ()))) for s in block["slots"])
            distinct, order = bool(block["distinct_categories"]), block["order"]
        else:
            raise ValueError(f"Unknown scheduling policy '{policy}'.")
        if order not in (ORDER_SLOTS, ORDER_ACTION_SPEED):
            raise ValueError(f"Unknown schedule order '{order}'.")
        if len(slots) != block["max_actions"]:
            raise ValueError(f"Schedule '{block['label']}' has {len(slots)} slot(s) but max_actions {block['max_actions']}.")
        return cls(block["label"], block["summary"], block["max_actions"], slots, distinct, order)

    # -- what the rest of the rules ask ------------------------------------------------------

    @property
    def opening_categories(self) -> tuple[str, ...]:
        """The categories that open a class-defined combo (its first slot); empty when there is none."""
        return self.slots[0].categories if self.order == ORDER_SLOTS and len(self.slots) > 1 else ()

    def check(self, faces: list[FaceDefinition]) -> None:
        """Raise :class:`ScheduleError` unless ``faces`` (one per action) fit this schedule."""
        self.resolution_order([(face, index) for index, face in enumerate(faces)], strict=True)

    def resolution_order(self, entries: list[tuple[FaceDefinition, int]], strict: bool = False) -> list[int]:
        """Resolution order as indices into ``entries`` (``(face, player_order)`` pairs).

        With ``strict`` the actions are validated first and :class:`ScheduleError` is raised when
        they do not fit. Without it, actions that do not fit resolve by action speed.
        """
        count = len(entries)
        if count > self.max_actions:
            if strict:
                raise ScheduleError(f"{self.label} allows at most {self.max_actions} action(s) per activation.")
            return self._by_speed(entries)
        if count <= 1:
            return list(range(count))
        faces = [face for face, _ in entries]
        if self.order == ORDER_SLOTS:
            by_player = sorted(range(count), key=lambda i: entries[i][1])
            if count == len(self.slots) and self._distinct(faces):
                for candidate in permutations(by_player):  # the player's order wins between valid fillings
                    if all(self.slots[position].accepts(faces[index]) for position, index in enumerate(candidate)):
                        return list(candidate)
            if strict:
                raise ScheduleError(self._slot_rule())
            return self._by_speed(entries)
        if strict:
            if not self._distinct(faces):
                raise ScheduleError(f"{self.label}: the actions must be of different categories.")
            if not self._fits_some_slots(faces):
                raise ScheduleError(f"{self.label}: these actions do not fit together in one activation.")
        return self._by_speed(entries)

    # -- helpers -----------------------------------------------------------------------------

    def _distinct(self, faces: list[FaceDefinition]) -> bool:
        return not self.distinct_categories or len({face.category for face in faces}) == len(faces)

    def _fits_some_slots(self, faces: list[FaceDefinition]) -> bool:
        """True when every face can take a slot of its own (order does not matter)."""
        return any(
            all(slot.accepts(face) for slot, face in zip(chosen, faces, strict=True))
            for chosen in permutations(self.slots, len(faces))
        )

    def _slot_rule(self) -> str:
        count = _COUNT_WORDS.get(len(self.slots), str(len(self.slots)))
        first, *rest = (slot.describe() for slot in self.slots)
        return f"{self.label}: {count} actions are only allowed as {first} first, then {', then '.join(rest)}."

    @staticmethod
    def _by_speed(entries: list[tuple[FaceDefinition, int]]) -> list[int]:
        return sorted(range(len(entries)), key=lambda i: (-(entries[i][0].action_speed or 0), entries[i][1]))
