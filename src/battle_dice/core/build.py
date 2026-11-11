"""What a hero is for the length of one run: its resolved build.

Every rule that needs a hero's class data (stats, schedule, passive, reaction, dice) reads it from
the hero's :class:`HeroBuild`, never from the class table directly. Today a build is always a
shipped class. Class Evolution (``docs/class_evolution/FDD_v0.2.md``) adds builds that come from
the vocation catalog; the rules do not need to know which kind they are given.

Builds are resolved once, when the run starts, from the ``StartRun`` command and the content. They
are derived data, like the content itself, and are not part of the hashed run state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
from typing import TYPE_CHECKING, Any

from battle_dice.core.models import DieDefinition
from battle_dice.core.schedule import Schedule

if TYPE_CHECKING:  # pragma: no cover
    from battle_dice.content.loader import Content


@dataclass(frozen=True)
class HeroBuild:
    """One hero's class data for a run. Treat every field as read-only."""

    vocation_id: str
    name: str
    max_hp: int
    start_hp: int
    speed: int
    base_initiative: int
    max_mana: int
    start_mana: int
    max_corruption: int
    start_corruption: int
    rerolls: int
    dice_capacity: int
    starting_dice: tuple[str, ...]
    bench_dice: tuple[str, ...]
    scheduling: dict[str, Any]
    passive: dict[str, Any]
    reaction_id: str
    #: The class whose Reforge and Imbue catalogs this hero's upgrade offers are drawn from.
    upgrade_family: str
    #: Dice this build brings with it. Empty for a shipped class, whose dice are in the content.
    dice: dict[str, DieDefinition] = field(default_factory=dict)

    @cached_property
    def schedule(self) -> Schedule:
        """``scheduling`` in the slot model the rules use. ``scheduling`` stays the one source and the display block."""
        return Schedule.from_scheduling(self.scheduling)


def build_from_class(content: Content, class_id: str) -> HeroBuild:
    """The build of a shipped class: exactly its entry in ``classes.json``."""
    cls = content.class_def(class_id)
    return HeroBuild(
        vocation_id=class_id,
        name=cls["name"],
        max_hp=cls["max_hp"],
        start_hp=cls["start_hp"],
        speed=cls["speed"],
        base_initiative=cls["base_initiative"],
        max_mana=cls["max_mana"],
        start_mana=cls["start_mana"],
        max_corruption=cls["max_corruption"],
        start_corruption=cls["start_corruption"],
        rerolls=cls["rerolls"],
        dice_capacity=cls["dice_capacity"],
        starting_dice=tuple(cls["starting_dice"]),
        bench_dice=tuple(cls["bench_dice"]),
        scheduling=cls["scheduling"],
        passive=cls["passive"],
        reaction_id=cls["reaction"],
        upgrade_family=class_id,
    )
