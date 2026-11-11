"""The career state of one profile: heroes, their vocations, mastery, skills, items and discovery.

Plain data only. The rules that change it are in :mod:`battle_dice.career.service`. Nothing here
is stored yet: Phase 2 of Class Evolution keeps the state in memory, and Phase 3 puts the same
shapes into the save database (``docs/class_evolution/persistence/progression.sql``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

DISCOVERY_ORDER = ("hidden", "hinted", "discovered")
ELIGIBLE = "eligible"


@dataclass
class MasteryRow:
    vocation_id: str
    rank: int = 1
    points: int = 0


@dataclass
class DieInstance:
    die_instance_id: str
    definition_id: str
    location: str = "equipped"  # "equipped" or "bench"
    slot_index: int | None = None


@dataclass
class CombatSnapshot:
    """A hero's current values inside a run, converted when the hero changes vocation."""

    hp: int
    max_hp: int
    mana: int | None = None
    max_mana: int | None = None
    corruption: int | None = None
    state: str = "standing"


@dataclass
class HeroRecord:
    hero_id: str
    active_vocation_id: str
    eligibility_state: str = ELIGIBLE
    revision: int = 0
    unlocked_vocations: list[str] = field(default_factory=list)
    #: vocation id -> the route it was claimed by. Vocations a hero starts with have no entry.
    unlock_routes: dict[str, str] = field(default_factory=dict)
    mastery: dict[str, MasteryRow] = field(default_factory=dict)
    learned_skills: list[str] = field(default_factory=list)
    #: slot index -> skill id.
    equipped_skills: dict[int, str] = field(default_factory=dict)
    #: Owned dice. Empty means "the active vocation's starting dice" (no die has been moved yet).
    dice: list[DieInstance] = field(default_factory=list)
    combat: CombatSnapshot | None = None

    def rank(self, vocation_id: str) -> int:
        row = self.mastery.get(vocation_id)
        return row.rank if row is not None else 0


@dataclass
class DiscoveryRow:
    vocation_id: str
    state: str = "hidden"
    clue_count: int = 0
    #: The distinct signals already counted, so a repeated clue changes nothing.
    signals_seen: list[str] = field(default_factory=list)


@dataclass
class Profile:
    profile_id: str
    discovery: dict[str, DiscoveryRow] = field(default_factory=dict)
    items: dict[str, int] = field(default_factory=dict)
    item_consumptions: list[dict[str, Any]] = field(default_factory=list)
    quests_completed: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RunInfo:
    run_id: str
    phase: str
    revision: int = 0


@dataclass
class EncounterResult:
    """What the run reports about the encounter that just ended. Trusted input of a mastery award."""

    encounter_id: str
    threat_rating: int
    mastery_eligible: bool
    outcome: str


@dataclass
class AwardRow:
    run_id: str
    encounter_id: str
    hero_id: str
    vocation_id: str
    base_points: int
    challenge_points: int
    threat_rating: int
    denial_reason: str | None = None

    @property
    def identity(self) -> tuple[str, str, str, str]:
        return (self.run_id, self.encounter_id, self.hero_id, self.vocation_id)


@dataclass
class ProcessedCommand:
    command_id: str
    type: str
    result: dict[str, Any]
    #: Canonical form of the accepted command. ``None`` when only its id and type are known.
    fingerprint: str | None = None


@dataclass
class CareerState:
    profile: Profile
    heroes: dict[str, HeroRecord] = field(default_factory=dict)
    run: RunInfo | None = None
    encounter: EncounterResult | None = None
    awards: list[AwardRow] = field(default_factory=list)
    processed: dict[str, ProcessedCommand] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    #: Sequence number of the next progression event of this profile.
    next_event_seq: int = 0
