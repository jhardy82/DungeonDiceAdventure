"""Class action scheduling, plan validation and action-speed ordering (sections 5.5 and 5.6).

A plan is validated as a whole: dice availability, class policy, target legality and a mana
projection in resolution order. The same function serves previews (UI) and the authoritative
``SetActionPlan`` / ``CommitActionPlan`` commands, so both always agree.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from battle_dice.core import skills
from battle_dice.core.models import ActionIntent, Combatant, FaceDefinition, HeroTurn
from battle_dice.core.schedule import Schedule, ScheduleError
from battle_dice.core.targeting import eligible_targets, protected_targets

if TYPE_CHECKING:  # pragma: no cover
    from battle_dice.core.engine import Engine


#: The machine-readable code of every plan refusal, in the order the checks run: the per-action
#: checks in the player's order, then the class schedule, then the mana projection. The registry
#: (``docs/class_evolution/persistence/error_codes.json``) lists the same codes in the same order.
PLAN_CODES = (
    "DIE_NOT_ROLLED",
    "DIE_ALREADY_USED",
    "FACE_NOT_AN_ACTION",
    "NO_LEGAL_TARGET",
    "WRONG_TARGET_COUNT",
    "TARGET_UNKNOWN",
    "TARGET_PROTECTED",
    "TARGET_DOWNED",
    "TARGET_NOT_LEGAL",
    "SCHEDULE_VIOLATION",
    "INSUFFICIENT_MANA",
)


class PlanError(ValueError):
    """The submitted plan is not legal. The message is shown to the player; the code is for programs."""

    def __init__(self, message: str, code: str):
        super().__init__(message)
        assert code in PLAN_CODES, code
        self.code = code


def describe_policy(scheduling: dict[str, Any]) -> str:
    return f"{scheduling['label']}: {scheduling['summary']}"


def order_actions(entries: list[tuple[FaceDefinition, int]], scheduling: dict[str, Any] | Schedule) -> list[int]:
    """Return resolution order as indices into ``entries`` (``(face, player_order)`` pairs).

    A class-defined dependency (Resource then cast, Status then Attack) always comes first.
    Otherwise higher ``action_speed`` resolves earlier and the player's order breaks ties.
    The rule itself lives in :class:`~battle_dice.core.schedule.Schedule`.
    """
    schedule = scheduling if isinstance(scheduling, Schedule) else Schedule.from_scheduling(scheduling)
    return schedule.resolution_order(entries)


def build_plan(ctx: Engine, hero: Combatant, turn: HeroTurn, actions: list[dict[str, Any]]) -> list[ActionIntent]:
    """Validate ``actions`` (``[{die_id, target_ids}]`` in the player's order) and return ordered intents."""
    combat = ctx.combat
    schedule = ctx.build(hero.id).schedule
    seen: set[str] = set()
    chosen: list[tuple[FaceDefinition, str, int, list[str]]] = []

    for order, action in enumerate(actions):
        die_id = action["die_id"]
        if die_id not in turn.rolled:
            raise PlanError(f"Die '{die_id}' has not been rolled this activation.", "DIE_NOT_ROLLED")
        if die_id in seen:
            raise PlanError(f"Die '{die_id}' already supplies another action this activation.", "DIE_ALREADY_USED")
        seen.add(die_id)
        face_index = turn.rolled[die_id]
        face = ctx.die_for(hero.id, die_id).faces[face_index]
        if face.is_blank:
            raise PlanError(f"{face.name} is a non-action and cannot be committed.", "FACE_NOT_AN_ACTION")
        eligible = eligible_targets(combat, hero, face)
        if not eligible:
            raise PlanError(f"{face.name} has no legal target.", "NO_LEGAL_TARGET")
        requested = list(action.get("target_ids", []))
        if face.target_scope in ("all_enemies", "all_allies"):
            targets = eligible
        elif face.target_scope == "self":
            if requested not in ([], [hero.id]):
                raise PlanError(f"{face.name} can only target its user.", "WRONG_TARGET_COUNT")
            targets = [hero.id]
        else:
            if len(requested) != 1:
                raise PlanError(f"{face.name} needs exactly one target.", "WRONG_TARGET_COUNT")
            if requested[0] in skills.field_medic_targets(ctx, hero, face):
                # A downed ally, and the hero has Field Medic ready: the face is used as a revival
                # (1 more mana, back at 1 HP). The mana check below is made on that dearer face.
                if any(skills.FIELD_MEDIC_TAG in earlier[0].tags for earlier in chosen):
                    raise PlanError("Field Medic can revive once per encounter.", "TARGET_DOWNED")
                face = skills.as_field_medic(face)
            elif requested[0] not in eligible:
                code, message = target_refusal(ctx, hero, face, requested[0])
                raise PlanError(message, code)
            targets = requested
        chosen.append((face, die_id, order, targets))

    try:
        resolution_order = schedule.resolution_order([(c[0], c[2]) for c in chosen], strict=True)
    except ScheduleError as error:
        raise PlanError(str(error), "SCHEDULE_VIOLATION") from error

    # Mana projection in resolution order: costs are charged on resolution, gains arrive first.
    mana = hero.mana
    intents: list[ActionIntent] = []
    for position in resolution_order:
        face, die_id, order, targets = chosen[position]
        if face.mana_cost > mana:
            raise PlanError(f"{face.name} needs {face.mana_cost} mana but only {mana} will be available.", "INSUFFICIENT_MANA")
        mana -= face.mana_cost
        for effect in face.effects:
            if effect["type"] == "gain_mana" and effect.get("target", "target") == "self":
                mana = min(hero.max_mana, mana + face.effect_amount(effect))
        intents.append(
            ActionIntent(
                id=f"a{combat.next_intent_seq + len(intents):05d}",
                actor_id=hero.id,
                source_die_id=die_id,
                ability_id=None,
                effect_id=f"{die_id}#{turn.rolled[die_id] + 1}",
                category=face.category,
                committed_target_ids=list(targets),
                action_speed=face.action_speed or 0,
                costs={"mana": face.mana_cost},
                tags=list(face.tags),
                name=face.name,
                power=face.power,
                face_index=turn.rolled[die_id],
                plan_order=order,
            )
        )
    return intents


def target_refusal(ctx: Engine, hero: Combatant, face: FaceDefinition, target_id: str) -> tuple[str, str]:
    """``(code, message)`` for a target the face may not take."""
    combat = ctx.combat
    target = combat.combatants.get(target_id)
    if target is None:
        return "TARGET_UNKNOWN", f"Unknown target '{target_id}'."
    if target_id in protected_targets(combat, hero, face):
        return "TARGET_PROTECTED", f"{target.name} is protected: melee must target the standing front row first."
    if face.target_scope == "single_ally" and target.side == hero.side and not target.standing:
        return "TARGET_DOWNED", f"{target.name} is downed; only a revival-capable Heal can target a downed ally."
    if not target.standing:
        return "TARGET_DOWNED", f"{target.name} is not a valid target."
    return "TARGET_NOT_LEGAL", f"{target.name} is not a legal target for {face.name}."


def target_problem(ctx: Engine, hero: Combatant, face: FaceDefinition, target_id: str) -> str:
    return target_refusal(ctx, hero, face, target_id)[1]


def die_options(ctx: Engine, hero: Combatant, turn: HeroTurn) -> list[dict[str, Any]]:
    """Per rolled die: the face, whether it can be used on its own, the reason if not, and targets."""
    combat = ctx.combat
    options = []
    for die_id in sorted(turn.rolled):
        die = ctx.die_for(hero.id, die_id)
        face_index = turn.rolled[die_id]
        face = die.faces[face_index]
        eligible = [] if face.is_blank else eligible_targets(combat, hero, face)
        # Field Medic: a downed ally is a target too, while the skill is ready.
        medic = [] if face.is_blank else skills.field_medic_targets(ctx, hero, face)
        eligible = [*eligible, *medic]
        reason = None
        needs_mana = False
        if face.is_blank:
            reason = "Blank: no action."
        elif not eligible:
            reason = "No legal target."
        elif face.mana_cost > hero.mana:
            needs_mana = True
            reason = f"Needs {face.mana_cost} mana (has {hero.mana})."
        options.append(
            {
                "die_id": die_id,
                "die_name": die.name,
                "die_size": die.size,
                "face_index": face_index,
                "face": face,
                "kept": die_id in turn.kept,
                "usable_alone": reason is None,
                "needs_mana": needs_mana,
                "selectable": not face.is_blank and bool(eligible),
                "reason": reason,
                "eligible_target_ids": eligible,
                "protected_target_ids": [] if face.is_blank else protected_targets(combat, hero, face),
                "skill_target_ids": medic,
                "skill_note": skills.field_medic_note(face) if medic else None,
            }
        )
    return options


def has_legal_action(ctx: Engine, hero: Combatant, turn: HeroTurn) -> bool:
    """True when at least one legal non-empty plan exists for the current roll."""
    return bool(enumerate_plans(ctx, hero, turn, include_targets=False))


def enumerate_plans(
    ctx: Engine, hero: Combatant, turn: HeroTurn, include_targets: bool = True
) -> list[list[dict[str, Any]]]:
    """All legal non-empty plans (used by the simulator and the 'no legal action' check).

    With ``include_targets=False`` only one representative target per action is tried.
    """
    options = [o for o in die_options(ctx, hero, turn) if o["selectable"]]
    max_actions = ctx.build(hero.id).schedule.max_actions

    def target_choices(option: dict[str, Any]) -> list[list[str]]:
        face = option["face"]
        if face.target_scope in ("all_enemies", "all_allies", "self"):
            return [[]]
        choices = [[t] for t in option["eligible_target_ids"]]
        return choices if include_targets else choices[:1]

    plans: list[list[dict[str, Any]]] = []

    def extend(start: int, current: list[dict[str, Any]]) -> None:
        if current:
            try:
                build_plan(ctx, hero, turn, current)
            except PlanError:
                pass
            else:
                plans.append(list(current))
        if len(current) >= max_actions:
            return
        for index in range(start, len(options)):
            for targets in target_choices(options[index]):
                current.append({"die_id": options[index]["die_id"], "target_ids": targets})
                extend(index + 1, current)
                current.pop()

    extend(0, [])
    return plans
