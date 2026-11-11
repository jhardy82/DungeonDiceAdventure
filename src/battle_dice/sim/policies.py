"""Headless player policies for seeded smoke runs and balance measurement (section 15.3).

Policies drive the engine only through commands and read-only queries, exactly like the UI.
They use their own PCG stream for any randomness, never the engine's streams.
"""

from __future__ import annotations

import dataclasses
import itertools
import time
from typing import Any

from battle_dice import rng
from battle_dice.core import commands as cmd
from battle_dice.core import planning, progression, reactions
from battle_dice.core.effects import damage_breakdown, shield_bonus
from battle_dice.core.engine import Engine
from battle_dice.core.models import (
    STATE_DOWNED,
    STATUS_POISON,
    STATUS_WEAKEN,
    ActionIntent,
    Combatant,
    CombatPhase,
    FaceDefinition,
    HeroTurn,
    RunPhase,
)


class PolicyError(RuntimeError):
    pass


def _must(result: Any, what: str) -> None:
    if not result.accepted:
        raise PolicyError(f"{what} was rejected: {result.reason}")


#: Bumped whenever the heuristic player's decisions change, so result files and the replay pin say
#: which player produced them. 1 = threshold keep rule (to rules 1.1.1); 2 = look-ahead player.
POLICY_VERSION = 2

#: Score weights for the statuses a face applies.
_STATUS_SCORE = {STATUS_POISON: 2.5, STATUS_WEAKEN: 1.8}
_DOWN_BONUS = 3.0


class HeuristicPolicy:
    """An informed scripted player.

    - **Keep or reroll:** exact look-ahead. Every possible roll of the hero's dice is scored by its best
      plan, and the dice to keep are the subset with the highest expected score over the rerolls left.
    - **Scoring:** the engine's own amounts (weaken, Steadfast, the Scout's combo bonus), applied in
      resolution order so two actions cannot both claim the same kill.
    - **Reactions:** always taken when one is eligible, on the most pressed target (unchanged from
      version 1).
    - **Upgrades:** the offer that raises its die's average face value the most.

    It values the current activation only. It is a competent player, not an optimal one.
    """

    name = "heuristic"
    version = POLICY_VERSION
    #: Each part can be switched off, to measure what it contributes (decision log 7.6).
    lookahead = True
    real_amounts = True
    value_upgrades = True
    #: Shields are scored at this fraction of their old per-point weight. With the Steadfast bonus
    #: counted at 1.0 the player guarded too much: five Squires won less often than under version 1.
    #: 0.75 gives the same overall win rate and no party that does clearly worse (decision log 7.6).
    shield_weight = 0.75
    #: Used only when ``lookahead`` is off: the version 1 rule (keep the best plan's dice if it scores this much).
    keep_threshold = 2.0

    def __init__(self) -> None:
        #: Seconds spent inside engine commands, so the simulator can report engine latency without
        #: the player's own thinking time.
        self.engine_seconds = 0.0
        self._stop_values: dict[tuple[Any, ...], tuple[float, list[dict[str, Any]]]] = {}
        self._stop_key: tuple[int, int, str] | None = None

    def _send(self, engine: Engine, command_type: str, **params: Any) -> None:
        started = time.perf_counter()
        result = engine.do(command_type, **params)
        self.engine_seconds += time.perf_counter() - started
        _must(result, command_type)

    def act(self, engine: Engine) -> None:
        state = engine.state
        if state.phase == RunPhase.UPGRADE:
            self._upgrade(engine)
        elif state.phase == RunPhase.EQUIPMENT:
            self._send(engine, cmd.ADVANCE_PHASE)
        elif state.phase == RunPhase.BATTLE:
            phase = engine.combat.phase
            if phase == CombatPhase.HERO_ROLL:
                self._send(engine, cmd.ROLL_DICE)
            elif phase == CombatPhase.KEEP_REROLL:
                self._keep_or_plan(engine)
            elif phase == CombatPhase.ACTION_PLAN:
                self._send(engine, cmd.COMMIT_ACTION_PLAN)
            elif phase in (CombatPhase.GUARD_WINDOW, CombatPhase.RESOURCE_WINDOW, CombatPhase.INTERRUPT_WINDOW):
                self._react(engine)
            else:  # pragma: no cover - callers only invoke policies at decision points
                raise PolicyError(f"Policy called in non-input phase '{phase}'.")

    # -- scoring -----------------------------------------------------------------------------

    def _score_plan(self, engine: Engine, hero: Combatant, intents: list[ActionIntent]) -> float:
        """Value of a plan, with its actions applied in resolution order to projected health and shields."""
        combat = engine.combat
        shield_cap = engine.content.balance["shield"]["cap"]
        passive = engine.build(hero.id).passive
        opening = engine.build(hero.id).schedule.opening_categories
        hp: dict[str, int] = {}
        shields: dict[str, int] = {}
        status_credit: dict[str, float] = {}
        mana = hero.mana
        corruption = hero.corruption
        score = 0.0
        for position, intent in enumerate(intents):
            face = engine.intent_face(intent)
            targets = [combat.combatants[t] for t in intent.committed_target_ids] or [hero]
            mana -= face.mana_cost
            for effect in face.effects:
                recipients = [hero] if effect.get("target", "target") == "self" else targets
                for target in recipients:
                    kind = effect["type"]
                    amount = face.effect_amount(effect)
                    target_hp = hp.get(target.id, target.hp)
                    target_shields = shields.get(target.id, target.shields)
                    if kind == "damage":
                        dealt = damage_breakdown(engine, hero, face, effect, None)["effective"]
                        if (
                            self.real_amounts
                            and passive["type"] == "combo_attack_bonus"
                            and face.category == "attack"
                            and len(intents) == 2
                            and position == 1
                            and intents[0].category in opening
                        ):
                            dealt += int(passive["amount"])
                        hp_damage = min(max(0, dealt - target_shields), target_hp)
                        score += hp_damage * 1.0
                        if hp_damage >= target_hp > 0:
                            score += _DOWN_BONUS
                        if self.real_amounts:
                            shields[target.id] = max(0, target_shields - dealt)
                            hp[target.id] = target_hp - hp_damage
                    elif kind == "shield":
                        if self.real_amounts:
                            amount += shield_bonus(engine, hero, face, target, intent)
                        gained = min(amount, shield_cap - target_shields)
                        urgency = 1.0 if target_hp * 2 <= target.max_hp else 0.5
                        score += gained * urgency * (0.3 if target_shields >= 4 else 1.0) * self.shield_weight
                        if self.real_amounts:
                            shields[target.id] = target_shields + gained
                    elif kind == "heal":
                        if target.state == STATE_DOWNED:
                            score += 8.0 if face.can_revive else 0.0
                        else:
                            healed = min(amount, target.max_hp - target_hp)
                            score += healed * 1.2
                            if self.real_amounts:
                                hp[target.id] = target_hp + healed
                    elif kind == "apply_status":
                        cap = engine.content.status_cap(effect["status"])
                        credit = _STATUS_SCORE.get(effect["status"], 1.0) if target.stacks_of(effect["status"]) < cap else 0.3
                        score += credit
                        status_credit[target.id] = status_credit.get(target.id, 0.0) + credit
                    elif kind == "gain_mana":
                        gained = min(amount, target.max_mana - (mana if self.real_amounts else target.mana))
                        score += gained * 0.6
                        mana += gained
                    elif kind == "gain_corruption":
                        current = corruption if self.real_amounts else target.corruption
                        score -= 0.4 * amount if current + amount >= 5 else 0.0
                        corruption += amount
                    elif kind == "remove_corruption":
                        removed = min(amount, target.corruption)
                        score += removed * (1.5 if target.corruption >= 4 else 0.4)
        if self.real_amounts:
            # A status on an enemy that the same plan defeats does nothing.
            score -= sum(credit for target_id, credit in status_credit.items() if hp.get(target_id, 1) <= 0)
        return score

    def _best_plan(self, engine: Engine, hero: Combatant, turn: HeroTurn) -> tuple[list[dict[str, Any]], float]:
        """The best-scoring legal plan for ``turn``'s roll. ``turn`` may be a copy holding a roll that
        has not happened; nothing in the engine is changed.

        Which dice may act together, and in what order, does not depend on the targets, so each legal
        set of dice is built once and its target choices are scored on copies of the intents.
        """
        best: list[dict[str, Any]] = []
        best_score = 0.0
        choices = {
            o["die_id"]: [[]] if o["face"].target_scope in ("all_enemies", "all_allies", "self")
            else [[t] for t in o["eligible_target_ids"]]
            for o in planning.die_options(engine, hero, turn)
        }
        for shape in planning.enumerate_plans(engine, hero, turn, include_targets=False):
            try:
                template = planning.build_plan(engine, hero, turn, shape)
            except planning.PlanError:  # pragma: no cover - enumerate_plans only returns legal plans
                continue
            fixed = {i.source_die_id: i.committed_target_ids for i in template}
            for targets in itertools.product(*(choices[a["die_id"]] for a in shape)):
                chosen = {a["die_id"]: t for a, t in zip(shape, targets, strict=True)}
                intents = [
                    dataclasses.replace(i, committed_target_ids=chosen[i.source_die_id] or fixed[i.source_die_id])
                    for i in template
                ]
                score = self._score_plan(engine, hero, intents)
                if score > best_score + 1e-9:
                    best = [{"die_id": a["die_id"], "target_ids": list(chosen[a["die_id"]])} for a in shape]
                    best_score = score
        return best, best_score

    # -- keep or reroll ----------------------------------------------------------------------

    def _choose_keep(self, engine: Engine, hero: Combatant, turn: HeroTurn) -> tuple[list[str], list[dict[str, Any]]]:
        """``(dice to keep, plan to submit if nothing is rerolled)`` for the current roll.

        Exact look-ahead: ``value[0]`` of a roll is its best plan's score; ``value[r]`` is the best
        expected ``value[r - 1]`` over every choice of dice to keep. Every face of a die is equally
        likely, as in ``Engine._roll_die``.
        """
        dice = sorted(turn.rolled)
        faces = {d: engine.die_for(hero.id, d).faces for d in dice}
        key = (id(engine), engine.revision, hero.id)
        if self._stop_key != key:
            self._stop_values = {}

        def stop(roll: tuple[int, ...]) -> tuple[float, list[dict[str, Any]]]:
            signature = tuple(faces[d][i].signature() for d, i in zip(dice, roll, strict=True))
            if signature not in self._stop_values:
                imagined = dataclasses.replace(turn, rolled=dict(zip(dice, roll, strict=True)), kept=[], plan=[])
                plan, score = self._best_plan(engine, hero, imagined)
                self._stop_values[signature] = (score, plan)
            score, plan = self._stop_values[signature]
            # The cached plan may come from another roll with the same faces; only its score is shared.
            return score, plan

        current = tuple(turn.rolled[d] for d in dice)
        plan, _ = self._best_plan(engine, hero, turn)
        if turn.rerolls_remaining <= 0:
            return list(dice), plan
        rolls = list(itertools.product(*(range(len(faces[d])) for d in dice)))
        value = {roll: stop(roll)[0] for roll in rolls}
        subsets = [
            tuple(d for d, keep in zip(dice, mask, strict=True) if keep)
            for mask in itertools.product((True, False), repeat=len(dice))
        ]  # keeps-everything first, so a tie never rerolls

        def expected(roll: tuple[int, ...], kept: tuple[str, ...], table: dict[tuple[int, ...], float]) -> float:
            options = [(roll[i],) if d in kept else tuple(range(len(faces[d]))) for i, d in enumerate(dice)]
            outcomes = list(itertools.product(*options))
            return sum(table[o] for o in outcomes) / len(outcomes)

        best_keep = tuple(dice)
        for remaining in range(1, turn.rerolls_remaining + 1):
            table = value
            if remaining == turn.rerolls_remaining:
                best_value = -1.0
                for kept in subsets:
                    candidate = expected(current, kept, table)
                    if candidate > best_value + 1e-9:
                        best_keep, best_value = kept, candidate
            else:
                value = {roll: max(expected(roll, kept, table) for kept in subsets) for roll in rolls}
        self._stop_key = key
        return list(best_keep), plan

    def _keep_or_plan(self, engine: Engine) -> None:
        hero, turn = engine._active_hero()
        if self.lookahead:
            keep, plan = self._choose_keep(engine, hero, turn)
        else:
            plan, score = self._best_plan(engine, hero, turn)
            keep = sorted(a["die_id"] for a in plan) if score >= self.keep_threshold else []
        unkept = [d for d in sorted(turn.rolled) if d not in keep]
        if turn.rerolls_remaining > 0 and unkept:
            if sorted(turn.kept) != keep:
                self._send(engine, cmd.SET_KEPT_DICE, die_ids=keep)
            self._send(engine, cmd.REROLL_UNKEPT)
            if self._stop_key is not None:
                self._stop_key = (id(engine), engine.revision, hero.id)  # the same activation continues
            return
        self._send(engine, cmd.SET_ACTION_PLAN, actions=plan)

    # -- reactions ---------------------------------------------------------------------------

    def _react(self, engine: Engine) -> None:
        """Use the first eligible reaction, on the most pressed target.

        A value-based rule (react only when it prevents more than the mana is worth, hold mana for a
        revival) was measured and changed the win rate by less than the noise, so the simple rule stays
        (decision log 7.6).
        """
        combat = engine.combat
        assert combat.reaction_stage is not None
        options = reactions.eligible_options(engine, combat.reaction_stage)
        if not options:  # pragma: no cover - the engine only opens a window with an eligible option
            self._send(engine, cmd.SKIP_REACTION_STAGE)
            return
        option = options[0]
        target_id = None
        if option["needs_target"]:
            candidates = [combat.combatants[t] for t in option["target_ids"]]
            if option["reaction_id"] == "grounding":
                candidates.sort(key=lambda c: (-c.corruption, c.id))
            else:
                candidates.sort(key=lambda c: (c.hp + c.shields, c.id))
            target_id = candidates[0].id
        self._send(engine, cmd.USE_REACTION, hero_id=option["hero_id"], target_id=target_id)

    # -- upgrades ----------------------------------------------------------------------------

    def _face_value(self, engine: Engine, hero: Combatant, face: FaceDefinition) -> float:
        """A face's worth outside any particular battle, for comparing upgrade offers."""
        if face.is_blank:
            return 0.0
        passive = engine.build(hero.id).passive
        spread = 2.0 if face.target_scope in ("all_enemies", "all_allies") else 1.0
        value = -0.6 * face.mana_cost
        for effect in face.effects:
            kind = effect["type"]
            amount = face.effect_amount(effect)
            if kind == "damage":
                value += amount * spread
            elif kind == "shield":
                bonus = passive["amount"] if passive["type"] == "defense_die_bonus" and face.category == "defense" else 0
                value += (amount + bonus) * 0.5 * spread
            elif kind == "heal":
                value += amount * 0.8 * spread + (1.0 if face.can_revive else 0.0)
            elif kind == "apply_status":
                value += (_STATUS_SCORE.get(effect["status"], 1.0) + 0.6 * (effect.get("duration", 2) - 2)) * spread
            elif kind == "gain_mana":
                value += amount * 0.6
            elif kind == "remove_corruption":
                value += amount * 0.4
            elif kind == "gain_corruption":
                value -= amount * 0.2
        return value

    def _upgrade(self, engine: Engine) -> None:
        offers = engine.state.upgrade_offers
        ranked: list[tuple[float, str, str, str]] = []
        for hero_id in sorted(offers):
            hero = engine.combat.combatants[hero_id]
            for die_id in sorted(offers[hero_id]):
                size = engine.die_for(hero_id, die_id).size
                for offer in offers[hero_id][die_id]:
                    if self.value_upgrades:
                        before = self._face_value(engine, hero, progression.face_from_plain(offer["before"]))
                        after = self._face_value(engine, hero, progression.face_from_plain(offer["after"]))
                        merit = -(after - before) / size
                    else:
                        merit = {"reforge": 0.0, "sharpen": 1.0}.get(offer["kind"], 2.0)
                    ranked.append((merit, hero_id, die_id, offer["offer_id"]))
        if not ranked:
            raise PolicyError("No upgrade offer is available.")
        if not self.value_upgrades:
            first = min((hero_id, die_id) for _, hero_id, die_id, _ in ranked)
            ranked = [r for r in ranked if (r[1], r[2]) == first]
        _, hero_id, die_id, offer_id = min(ranked)
        self._send(engine, cmd.CHOOSE_UPGRADE, hero_id=hero_id, die_id=die_id, offer_id=offer_id)


class RandomPolicy:
    """Uniformly random legal decisions from a private PCG stream. Used for robustness fuzzing."""

    name = "random"

    def __init__(self, seed: int = 0):
        self._stream = rng.seed_stream(seed, 0xBD)

    def _pick(self, n: int) -> int:
        return rng.bounded(self._stream, n)

    def act(self, engine: Engine) -> None:
        state = engine.state
        if state.phase == RunPhase.UPGRADE:
            offers = [o for dice in state.upgrade_offers.values() for die in dice.values() for o in die]
            offers.sort(key=lambda o: o["offer_id"])
            offer = offers[self._pick(len(offers))]
            _must(engine.do(cmd.CHOOSE_UPGRADE, hero_id=offer["hero_id"], die_id=offer["die_id"], offer_id=offer["offer_id"]), "ChooseUpgrade")
            return
        if state.phase == RunPhase.EQUIPMENT:
            self._equipment(engine)
            return
        combat = engine.combat
        phase = combat.phase
        if phase == CombatPhase.HERO_ROLL:
            _must(engine.do(cmd.ROLL_DICE), "RollDice")
        elif phase == CombatPhase.KEEP_REROLL:
            hero, turn = engine._active_hero()
            dice = sorted(turn.rolled)
            if turn.rerolls_remaining > 0 and self._pick(2) == 0:
                keep = [d for d in dice if self._pick(2) == 0]
                if len(keep) < len(dice):
                    _must(engine.do(cmd.SET_KEPT_DICE, die_ids=keep), "SetKeptDice")
                    _must(engine.do(cmd.REROLL_UNKEPT), "RerollUnkept")
                    return
            plans: list[list[dict[str, Any]]] = [[]] + planning.enumerate_plans(engine, hero, turn)
            # Prefer acting: an empty plan (pass) is only chosen when nothing else is legal or by a 1-in-8 roll.
            if len(plans) > 1 and self._pick(8) != 0:
                plans = plans[1:]
            _must(engine.do(cmd.SET_ACTION_PLAN, actions=plans[self._pick(len(plans))]), "SetActionPlan")
        elif phase == CombatPhase.ACTION_PLAN:
            _must(engine.do(cmd.COMMIT_ACTION_PLAN), "CommitActionPlan")
        else:
            assert combat.reaction_stage is not None
            options = reactions.eligible_options(engine, combat.reaction_stage)
            if not options or self._pick(3) == 0:
                _must(engine.do(cmd.SKIP_REACTION_STAGE), "SkipReactionStage")
                return
            option = options[self._pick(len(options))]
            target_id = option["target_ids"][self._pick(len(option["target_ids"]))] if option["needs_target"] else None
            _must(engine.do(cmd.USE_REACTION, hero_id=option["hero_id"], target_id=target_id), "UseReaction")

    def _equipment(self, engine: Engine) -> None:
        state = engine.state
        from battle_dice.core import progression

        if cmd.SWAP_DIE in engine.permissible_commands() and self._pick(2) == 0:
            for hero_id in sorted(state.inventory):
                hero = engine.combat.combatants[hero_id]
                for out_die in sorted(hero.equipped_dice_ids):
                    for in_die in sorted(state.inventory[hero_id]):
                        if progression.swap_problem(engine, hero_id, out_die, in_die) is None:
                            _must(engine.do(cmd.SWAP_DIE, hero_id=hero_id, out_die_id=out_die, in_die_id=in_die), "SwapDie")
                            return
        _must(engine.do(cmd.ADVANCE_PHASE), "AdvancePhase")


def play_run(engine: Engine, policy: Any, max_commands: int = 20000) -> str:
    """Drive a started run to its end. Raises if it does not terminate within ``max_commands``."""
    start = len(engine.command_log)
    while not engine.finished():
        if len(engine.command_log) - start > max_commands:
            raise PolicyError("Run did not terminate within the command budget.")
        if engine.needs_input():
            policy.act(engine)
        else:
            _must(engine.do(cmd.ADVANCE_PHASE), "AdvancePhase")
    assert engine.state.outcome is not None
    return engine.state.outcome
