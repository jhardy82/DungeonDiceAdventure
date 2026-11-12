"""What a hero is for the length of one run: its resolved build.

Every rule that needs a hero's class data (stats, schedule, passive, reaction, dice) reads it from
the hero's :class:`HeroBuild`, never from the class table directly. Today a build is always a
shipped class. Class Evolution (``docs/class_evolution/FDD_v0.2.md``) adds builds that come from
the vocation catalog; the rules do not need to know which kind they are given.

Builds are resolved once, when the run starts, from the ``StartRun`` command and the content. They
are derived data, like the content itself, and are not part of the hashed run state.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from functools import cached_property
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

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
    #: The reaction's definition (stage, cost, effects): the hero's own copy, so a build is complete in itself.
    reaction: dict[str, Any]
    #: The class whose Reforge and Imbue catalogs this hero's upgrade offers are drawn from.
    upgrade_family: str
    #: Dice this build brings with it. Empty for a shipped class, whose dice are in the content.
    dice: dict[str, DieDefinition] = field(default_factory=dict)
    #: The saved hero this build is a snapshot of (Class Evolution). Empty for a hero made from a class alone.
    hero_id: str = ""
    #: The saved hero's own name. Empty: the hero is named after its class and its place in the party.
    display_name: str = ""
    #: Inherited skills the hero has equipped, in slot order.
    skills: tuple[str, ...] = ()

    @cached_property
    def schedule(self) -> Schedule:
        """``scheduling`` in the slot model the rules use. ``scheduling`` stays the one source and the display block."""
        return Schedule.from_scheduling(self.scheduling)


class BuildNotSupported(ValueError):
    """The vocation exists but needs something the rules do not implement yet. The message names it."""


class BuildSource(Protocol):
    """Where builds beyond the shipped classes come from: the vocation catalog, when its feature gate is on."""

    @property
    def version(self) -> str:
        """The source's own version (the catalog version)."""
        ...

    @property
    def sha256(self) -> str:
        """Hash of the source; a run with an evolved hero records it."""
        ...

    def known(self, vocation_id: str) -> bool:
        """True when the source lists this vocation, supported or not."""
        ...

    def build(self, vocation_id: str) -> HeroBuild:
        """The vocation's build. Raises :class:`BuildNotSupported` when the rules cannot run it yet."""
        ...


def convert_pool(current: int, old_max: int, new_max: int) -> int:
    """A health or mana pool carried into another vocation: ``ceil(current * new_max / old_max)``, at most ``new_max``.

    Nothing stays nothing: a hero at 0 HP stays down, a change never revives. The one formula for the
    career rules and for a change inside a run (fixture CE-17).
    """
    if current <= 0 or old_max <= 0:
        return 0
    return min(new_max, -((-current * new_max) // old_max))


class SnapshotRefused(ValueError):
    """A saved hero's build snapshot holds something the run cannot use. The message says what."""


def build_from_snapshot(base: HeroBuild, snapshot: dict[str, Any], shipped_dice: Mapping[str, DieDefinition]) -> HeroBuild:
    """The build of a saved hero: its vocation's build with the hero's own stats, dice, skills and name.

    ``snapshot`` is the party entry's ``hero`` object. It is written into the run's command log, so a
    replay needs the log and the pinned catalog only (owner decision of 2026-11-11, fixture CE-35).
    The career rules decide what a hero may have; this function only refuses what a run cannot hold:
    a stat below the vocation's own, a die that does not exist for this hero, the wrong number of dice.
    """
    who = snapshot["hero_id"]
    stats = snapshot.get("stats", {})
    for name, value in stats.items():
        if value < getattr(base, name):
            raise SnapshotRefused(f"{who}: {name} {value} is below the {getattr(base, name)} of a {base.name}.")
    max_hp = stats.get("max_hp", base.max_hp)
    max_mana = stats.get("max_mana", base.max_mana)
    dice = tuple(snapshot.get("dice", base.starting_dice))
    bench = tuple(snapshot.get("bench", base.bench_dice))
    if len(dice) != base.dice_capacity:
        raise SnapshotRefused(f"{who}: a {base.name} takes {base.dice_capacity} dice into a run, not {len(dice)}.")
    if len(set(dice + bench)) != len(dice + bench):
        raise SnapshotRefused(f"{who}: a die is listed twice.")
    for die_id in dice + bench:
        if die_id not in base.dice and die_id not in shipped_dice:
            raise SnapshotRefused(f"{who}: the die '{die_id}' does not exist for a {base.name}.")
    return replace(
        base,
        max_hp=max_hp,
        start_hp=base.start_hp + (max_hp - base.max_hp),  # a bonus to the maximum is health the hero starts with
        max_mana=max_mana,
        speed=stats.get("speed", base.speed),
        starting_dice=dice,
        bench_dice=bench,
        hero_id=who,
        display_name=snapshot.get("name", ""),
        skills=tuple(snapshot.get("skills", ())),
    )


class EncounterNotPlayable(ValueError):
    """The encounter is listed but has no enemies to fight yet (or none for this party size). The message says so."""


@runtime_checkable
class EncounterSource(Protocol):
    """Where battles beyond the shipped ones come from: the vocation catalog, when its feature gate is on.

    The shipped battles of a run always come from the shipped content. A run may add encounters
    from this source after them (``StartRun``'s optional ``encounters``); the player is then asked
    after each won battle whether to fight on.
    """

    @property
    def version(self) -> str:
        ...

    @property
    def sha256(self) -> str:
        """Hash of the source; a run that uses one of its encounters records it."""
        ...

    def has_encounter(self, encounter_id: str) -> bool:
        """True when the source lists this encounter, playable or not."""
        ...

    def encounter(self, encounter_id: str, party_size: int) -> list[dict[str, Any]]:
        """The enemies of the encounter for this party size, in the shape of the shipped encounter table.

        Raises :class:`EncounterNotPlayable` when the encounter has not been authored yet.
        """
        ...


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
        reaction=content.reactions[cls["reaction"]],
        upgrade_family=class_id,
    )
