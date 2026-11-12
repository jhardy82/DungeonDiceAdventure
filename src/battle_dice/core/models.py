"""Canonical entities for the rules engine (BD-PRD-MVP-001 section 14.2).

Every entity is a plain dataclass of bounded integers, strings and containers so that the whole
authoritative state can be deep-copied (for transactional command handling) and serialised to
canonical JSON (for hashing and replay comparison).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any

# --------------------------------------------------------------------------------------------
# Vocabulary
# --------------------------------------------------------------------------------------------

SIDE_HERO = "hero"
SIDE_ENEMY = "enemy"

ROW_FRONT = "front"
ROW_BACK = "back"
ROWS = (ROW_FRONT, ROW_BACK)

STATE_STANDING = "standing"
STATE_DOWNED = "downed"
STATE_DEFEATED = "defeated"

CATEGORY_ATTACK = "attack"
CATEGORY_DEFENSE = "defense"
CATEGORY_HEALING = "healing"
CATEGORY_STATUS = "status"
CATEGORY_RESOURCE = "resource"
CATEGORY_BLANK = "blank"
EXECUTABLE_CATEGORIES = (
    CATEGORY_ATTACK,
    CATEGORY_DEFENSE,
    CATEGORY_HEALING,
    CATEGORY_STATUS,
    CATEGORY_RESOURCE,
)

STATUS_POISON = "poison"
STATUS_WEAKEN = "weaken"
STATUS_SPEED_UP = "speed_up"

STAGE_GUARD = "guard"
STAGE_RESOURCE = "resource"
STAGE_INTERRUPT = "interrupt"
REACTION_STAGES = (STAGE_GUARD, STAGE_RESOURCE, STAGE_INTERRUPT)


class RunPhase:
    """Run-level phases owned by the rules engine (application menus live in the controller)."""

    BATTLE = "battle"
    UPGRADE = "upgrade"  # RECOVERY_AND_UPGRADE: mandatory upgrade not yet chosen
    EQUIPMENT = "equipment"  # RECOVERY_AND_UPGRADE: optional swap / formation, then start Battle 2
    #: The shipped battles are won and the run was started with a further encounter: stop here with a
    #: victory, or fight on. Only a run whose ``StartRun`` named extra encounters ever enters this phase.
    CONTINUE = "continue"
    VICTORY = "victory"
    DEFEAT = "defeat"


class CombatPhase:
    """Combat substates (section 14.3)."""

    ADVANCE_TIMELINE = "advance_timeline"
    ACTOR_START = "actor_start"
    HERO_ROLL = "hero_roll"
    KEEP_REROLL = "keep_reroll"
    ACTION_PLAN = "action_plan"
    LOCK_PLAN = "lock_plan"
    ACTION_RESOLVE = "action_resolve"
    ENEMY_INTENT = "enemy_intent"
    REVEAL_INTENT = "reveal_intent"
    GUARD_WINDOW = "guard_window"
    RESOURCE_WINDOW = "resource_window"
    INTERRUPT_WINDOW = "interrupt_window"
    ENEMY_RESOLVE = "enemy_resolve"
    ACTOR_END = "actor_end"
    TERMINAL_CHECK = "terminal_check"
    VICTORY = "victory"
    DEFEAT = "defeat"

    #: Phases in which the engine waits for a player decision.
    INPUT_PHASES = frozenset(
        {HERO_ROLL, KEEP_REROLL, ACTION_PLAN, GUARD_WINDOW, RESOURCE_WINDOW, INTERRUPT_WINDOW}
    )
    WINDOW_BY_STAGE = {
        STAGE_GUARD: GUARD_WINDOW,
        STAGE_RESOURCE: RESOURCE_WINDOW,
        STAGE_INTERRUPT: INTERRUPT_WINDOW,
    }
    STAGE_BY_WINDOW = {v: k for k, v in WINDOW_BY_STAGE.items()}


# --------------------------------------------------------------------------------------------
# Content entities
# --------------------------------------------------------------------------------------------


@dataclass
class FaceDefinition:
    """One die face or one authored enemy ability. Both run through the same effect engine."""

    id: str
    name: str
    category: str
    power: int
    target_scope: str
    range_type: str
    action_speed: int | None
    mana_cost: int
    effects: list[dict[str, Any]]
    can_revive: bool
    tags: list[str]
    weight: int = 0
    random_target: bool = False

    @property
    def is_blank(self) -> bool:
        return self.category == CATEGORY_BLANK

    def effect_amount(self, effect: dict[str, Any]) -> int:
        """Effects without an explicit amount use the face's headline power."""
        return int(effect.get("amount", self.power))

    def status_effect(self) -> dict[str, Any] | None:
        for effect in self.effects:
            if effect["type"] == "apply_status":
                return effect
        return None

    def has_effect(self, effect_type: str) -> bool:
        return any(e["type"] == effect_type for e in self.effects)

    def signature(self) -> tuple:
        """Identity used to group equal faces when showing frequencies and probabilities."""
        return (
            self.name,
            self.category,
            self.power,
            self.target_scope,
            self.range_type,
            self.action_speed,
            self.mana_cost,
            self.can_revive,
            tuple(tuple(sorted(e.items())) for e in self.effects),
        )


@dataclass
class DieDefinition:
    """An ordered collection of exactly ``size`` faces. Immutable during a battle."""

    id: str
    name: str
    affinity_class: str
    size: int
    faces: list[FaceDefinition]
    definition_version: int = 1
    role: str = "starting"


# --------------------------------------------------------------------------------------------
# Combat entities
# --------------------------------------------------------------------------------------------


@dataclass
class StatusInstance:
    id: str
    kind: str
    source_id: str
    target_id: str
    stacks: int
    remaining_target_activations: int
    created_event_seq: int
    #: True when applied during the affected actor's own activation; that activation is not counted.
    applied_during_own_activation: bool = False


@dataclass
class Combatant:
    id: str
    side: str
    archetype_id: str
    name: str
    row: str
    hp: int
    max_hp: int
    shields: int
    speed: int
    base_initiative: int
    gauge: int
    mana: int
    max_mana: int
    corruption: int
    max_corruption: int
    status_instances: list[StatusInstance] = field(default_factory=list)
    reaction_charges: int = 0
    equipped_dice_ids: list[str] = field(default_factory=list)
    state: str = STATE_STANDING
    #: Enemy-only per-encounter stat adjustments: ``{action_id: {"power": int, "weight": int}}``.
    action_overrides: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def standing(self) -> bool:
        return self.state == STATE_STANDING

    @property
    def is_hero(self) -> bool:
        return self.side == SIDE_HERO

    def stacks_of(self, kind: str) -> int:
        return sum(s.stacks for s in self.status_instances if s.kind == kind)

    def instances_of(self, kind: str) -> list[StatusInstance]:
        return [s for s in self.status_instances if s.kind == kind]


@dataclass
class ActionIntent:
    """A committed action: a hero's selected die face or an enemy's authored ability."""

    id: str
    actor_id: str
    source_die_id: str | None
    ability_id: str | None
    effect_id: str
    category: str
    committed_target_ids: list[str]
    action_speed: int
    costs: dict[str, int]
    tags: list[str]
    name: str = ""
    power: int = 0
    face_index: int | None = None
    #: Position chosen by the player; breaks equal action-speed ties.
    plan_order: int = 0
    cancelled: bool = False
    cancel_reason: str | None = None
    #: Set by a resisted Interrupt (elite_resistant): explicit mitigation of outgoing damage.
    damage_reduction: int = 0
    #: Set by a resisted Interrupt: reduction of adverse status / resource magnitude.
    magnitude_reduction: int = 0
    resolved: bool = False


@dataclass
class Reaction:
    id: str
    reacting_hero_id: str
    reaction_stage: str
    trigger_intent_id: str
    target_ids: list[str]
    costs: dict[str, int]
    effect: str
    priority: int


@dataclass
class HeroTurn:
    """Working state of the active hero's activation (roll, keep, reroll, plan)."""

    hero_id: str
    rolled: dict[str, int] = field(default_factory=dict)  # die_id -> face index
    kept: list[str] = field(default_factory=list)
    rerolls_remaining: int = 0
    rerolls_used: int = 0
    plan: list[ActionIntent] = field(default_factory=list)
    queue_index: int = 0
    #: Categories of plan actions that actually resolved (drives combo passives).
    resolved_categories: list[str] = field(default_factory=list)
    committed: bool = False


@dataclass
class CombatState:
    encounter_id: str
    timeline_tick: int = 0
    combatants: dict[str, Combatant] = field(default_factory=dict)
    active_combatant_id: str | None = None
    phase: str = CombatPhase.ADVANCE_TIMELINE
    committed_intent: ActionIntent | None = None
    reaction_stage: str | None = None
    event_seq: int = 0
    outcome: str | None = None
    turn: HeroTurn | None = None
    reactions_used: list[Reaction] = field(default_factory=list)
    stage_index: int = 0
    activation_count: int = 0
    next_status_seq: int = 1
    next_intent_seq: int = 1
    next_reaction_seq: int = 1

    def sorted_combatants(self) -> list[Combatant]:
        return [self.combatants[k] for k in sorted(self.combatants)]

    def side(self, side: str) -> list[Combatant]:
        return [c for c in self.sorted_combatants() if c.side == side]

    def standing(self, side: str) -> list[Combatant]:
        return [c for c in self.side(side) if c.standing]


@dataclass
class RngStreamState:
    """Serialisable position of one BD-PCG32-v1 stream."""

    state: int
    increment: int
    draws: int = 0


@dataclass
class RunState:
    run_id: str
    seed: int
    rules_version: str
    content_version: str
    content_hash: str
    rng_algorithm: str
    encounter_index: int = 0
    party: list[dict[str, str]] = field(default_factory=list)  # [{id, class_id, row}]
    inventory: dict[str, list[str]] = field(default_factory=dict)  # hero_id -> bench die ids
    upgrades: list[dict[str, Any]] = field(default_factory=list)
    outcome: str | None = None
    phase: str = RunPhase.BATTLE
    revision: int = 0
    rng: dict[str, RngStreamState] = field(default_factory=dict)
    #: Fixture-only forced bounded draws per stream (section 11.2: "fixture tests can force a known order").
    forced_draws: dict[str, list[int]] = field(default_factory=dict)
    #: hero_id -> die_id -> upgraded, versioned die definition.
    die_overrides: dict[str, dict[str, DieDefinition]] = field(default_factory=dict)
    upgrade_offers: dict[str, dict[str, list[dict[str, Any]]]] = field(default_factory=dict)
    #: hero_id -> optional bench swaps used this run (limit: balance.upgrades.max_swaps_per_hero).
    swaps_used: dict[str, int] = field(default_factory=dict)
    combat: CombatState | None = None
    battle_records: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class CombatEvent:
    seq: int
    tick: int
    actor_id: str | None
    type: str
    intent_id: str | None
    before: dict[str, Any]
    delta: dict[str, Any]
    after: dict[str, Any]
    rng_stream: str | None = None
    rng_draw_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def to_plain(value: Any) -> Any:
    """Recursively convert dataclasses to plain JSON-compatible containers."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_plain(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(k): to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_plain(v) for v in value]
    return value
