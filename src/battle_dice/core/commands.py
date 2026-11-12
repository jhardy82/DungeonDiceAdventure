"""Input commands accepted by the rules engine (BD-PRD-MVP-001 section 14.4).

Every command carries a ``command_id`` (idempotency key), the ``state_revision`` the sender
believes is current, and schema-validated parameters. The UI, the simulator and the tests all
drive the engine exclusively through these commands.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

START_RUN = "StartRun"
SET_FORMATION = "SetFormation"
ROLL_DICE = "RollDice"
SET_KEPT_DICE = "SetKeptDice"
REROLL_UNKEPT = "RerollUnkept"
SET_ACTION_PLAN = "SetActionPlan"
COMMIT_ACTION_PLAN = "CommitActionPlan"
USE_REACTION = "UseReaction"
SKIP_REACTION_STAGE = "SkipReactionStage"
CHOOSE_UPGRADE = "ChooseUpgrade"
SWAP_DIE = "SwapDie"
ADVANCE_PHASE = "AdvancePhase"
#: Only in a run started with extra encounters, after the shipped battles are won.
CONTINUE_RUN = "ContinueRun"
END_RUN = "EndRun"

COMMAND_TYPES = (
    START_RUN,
    SET_FORMATION,
    ROLL_DICE,
    SET_KEPT_DICE,
    REROLL_UNKEPT,
    SET_ACTION_PLAN,
    COMMIT_ACTION_PLAN,
    USE_REACTION,
    SKIP_REACTION_STAGE,
    CHOOSE_UPGRADE,
    SWAP_DIE,
    ADVANCE_PHASE,
    CONTINUE_RUN,
    END_RUN,
)

_STR = "str"
_INT = "int"
_STR_LIST = "list[str]"
_PARTY = "party"
_PLAN = "plan"

#: ``{command type: {parameter: (kind, required)}}``. Unknown parameters are rejected.
PARAM_SPECS: dict[str, dict[str, tuple[str, bool]]] = {
    START_RUN: {"seed": (_INT, True), "party": (_PARTY, True), "run_id": (_STR, False), "encounters": (_STR_LIST, False)},
    SET_FORMATION: {"hero_id": (_STR, True), "row": (_STR, True)},
    ROLL_DICE: {},
    SET_KEPT_DICE: {"die_ids": (_STR_LIST, True)},
    REROLL_UNKEPT: {},
    SET_ACTION_PLAN: {"actions": (_PLAN, True)},
    COMMIT_ACTION_PLAN: {},
    USE_REACTION: {"hero_id": (_STR, True), "target_id": (_STR, False)},
    SKIP_REACTION_STAGE: {},
    CHOOSE_UPGRADE: {"hero_id": (_STR, True), "die_id": (_STR, True), "offer_id": (_STR, True)},
    SWAP_DIE: {"hero_id": (_STR, True), "out_die_id": (_STR, True), "in_die_id": (_STR, True)},
    ADVANCE_PHASE: {},
    CONTINUE_RUN: {},
    END_RUN: {},
}


class CommandRejected(Exception):
    """Raised inside a handler to reject a command. State is rolled back by the engine.

    ``code`` is the machine-readable name of the refusal where one is defined. Today that is every
    refusal of an action plan (``planning.PLAN_CODES``); the text is always present.
    """

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Command:
    type: str
    command_id: str
    state_revision: int
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "command_id": self.command_id,
            "state_revision": self.state_revision,
            "params": self.params,
        }

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> Command:
        return Command(raw["type"], raw["command_id"], raw["state_revision"], dict(raw.get("params", {})))


@dataclass
class CommandResult:
    accepted: bool
    revision: int
    reason: str | None = None
    duplicate: bool = False
    events: list[Any] = field(default_factory=list)
    #: Machine-readable name of the refusal, beside ``reason``. ``None`` where no code is defined.
    code: str | None = None

    def __bool__(self) -> bool:
        return self.accepted


#: What a party entry's optional ``hero`` (a saved hero's build snapshot) may hold, and of which type.
SNAPSHOT_KEYS = {"hero_id": str, "name": str, "stats": dict, "dice": list, "bench": list, "skills": list}
SNAPSHOT_STATS = ("max_hp", "max_mana", "speed")


def _snapshot_problem(snapshot: Any) -> str | None:
    """Shape check of a build snapshot. Whether its content is legal is decided when the run starts."""
    if not isinstance(snapshot, dict) or not set(snapshot) <= set(SNAPSHOT_KEYS) or "hero_id" not in snapshot:
        return "a hero snapshot is an object with hero_id and optionally name, stats, dice, bench, skills."
    for key, value in snapshot.items():
        if not isinstance(value, SNAPSHOT_KEYS[key]):
            return f"hero.{key} has the wrong type."
        if key in ("dice", "bench", "skills") and not _is_str_list(value):
            return f"hero.{key} must be a list of strings."
        if key == "stats" and not (set(value) <= set(SNAPSHOT_STATS) and all(_is_int(v) for v in value.values())):
            return f"hero.stats may hold whole numbers for {', '.join(SNAPSHOT_STATS)} only."
        if key in ("hero_id", "name") and not value:
            return f"hero.{key} must not be empty."
    return None


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_str_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def validate_command(command: Command) -> str | None:
    """Return a human-readable problem, or ``None`` when the command envelope is well formed."""
    if command.type not in PARAM_SPECS:
        return f"Unknown command type '{command.type}'."
    if not isinstance(command.command_id, str) or not command.command_id:
        return "command_id must be a non-empty string."
    if not _is_int(command.state_revision) or command.state_revision < 0:
        return "state_revision must be a non-negative integer."
    if not isinstance(command.params, dict):
        return "params must be an object."
    spec = PARAM_SPECS[command.type]
    for name in command.params:
        if name not in spec:
            return f"{command.type} does not accept parameter '{name}'."
    for name, (kind, required) in spec.items():
        if name not in command.params or command.params[name] is None:
            if required:
                return f"{command.type} requires parameter '{name}'."
            continue
        value = command.params[name]
        if kind == _STR and not isinstance(value, str):
            return f"{command.type}.{name} must be a string."
        if kind == _INT and not _is_int(value):
            return f"{command.type}.{name} must be an integer."
        if kind == _STR_LIST and not _is_str_list(value):
            return f"{command.type}.{name} must be a list of strings."
        if kind == _PARTY:
            if not isinstance(value, list) or not all(
                isinstance(m, dict)
                and {"class_id", "row"} <= set(m) <= {"class_id", "row", "hero"}
                and isinstance(m["class_id"], str)
                and isinstance(m["row"], str)
                for m in value
            ):
                return "StartRun.party must be a list of {class_id, row} objects."
            for member in value:
                problem = _snapshot_problem(member["hero"]) if "hero" in member else None
                if problem:
                    return f"StartRun.party: {problem}"
        if kind == _PLAN:
            if not isinstance(value, list) or not all(
                isinstance(a, dict)
                and set(a) <= {"die_id", "target_ids"}
                and isinstance(a.get("die_id"), str)
                and _is_str_list(a.get("target_ids", []))
                for a in value
            ):
                return "SetActionPlan.actions must be a list of {die_id, target_ids} objects."
    return None
