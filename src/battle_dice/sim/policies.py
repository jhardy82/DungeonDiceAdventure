"""Headless player policies for seeded smoke runs and balance measurement (section 15.3).

Policies drive the engine only through commands and read-only queries, exactly like the UI.
They use their own PCG stream for any randomness, never the engine's streams.
"""

from __future__ import annotations

from typing import Any

from battle_dice import rng
from battle_dice.core import commands as cmd
from battle_dice.core import planning, reactions
from battle_dice.core.effects import damage_breakdown
from battle_dice.core.engine import Engine
from battle_dice.core.models import (
    STATE_DOWNED,
    STATUS_POISON,
    STATUS_WEAKEN,
    Combatant,
    CombatPhase,
    FaceDefinition,
    RunPhase,
)


class PolicyError(RuntimeError):
    pass


def _must(result: Any, what: str) -> None:
    if not result.accepted:
        raise PolicyError(f"{what} was rejected: {result.reason}")


class HeuristicPolicy:
    """A simple informed player: keeps useful dice, rerolls the rest, picks the best-scoring plan."""

    name = "heuristic"
    keep_threshold = 2.0

    def act(self, engine: Engine) -> None:
        state = engine.state
        if state.phase == RunPhase.UPGRADE:
            self._upgrade(engine)
        elif state.phase == RunPhase.EQUIPMENT:
            _must(engine.do(cmd.ADVANCE_PHASE), "AdvancePhase")
        elif state.phase == RunPhase.BATTLE:
            phase = engine.combat.phase
            if phase == CombatPhase.HERO_ROLL:
                _must(engine.do(cmd.ROLL_DICE), "RollDice")
            elif phase == CombatPhase.KEEP_REROLL:
                self._keep_or_plan(engine)
            elif phase == CombatPhase.ACTION_PLAN:
                _must(engine.do(cmd.COMMIT_ACTION_PLAN), "CommitActionPlan")
            elif phase in (CombatPhase.GUARD_WINDOW, CombatPhase.RESOURCE_WINDOW, CombatPhase.INTERRUPT_WINDOW):
                self._react(engine)
            else:  # pragma: no cover - callers only invoke policies at decision points
                raise PolicyError(f"Policy called in non-input phase '{phase}'.")

    # -- scoring -----------------------------------------------------------------------------

    def _score_action(self, engine: Engine, hero: Combatant, face: FaceDefinition, target_ids: list[str]) -> float:
        combat = engine.combat
        score = 0.0
        targets = [combat.combatants[t] for t in target_ids] or [hero]
        for effect in face.effects:
            recipients = [hero] if effect.get("target", "target") == "self" else targets
            for target in recipients:
                kind = effect["type"]
                amount = face.effect_amount(effect)
                if kind == "damage":
                    dealt = damage_breakdown(engine, hero, face, effect, None)["effective"]
                    hp_damage = max(0, dealt - target.shields)
                    score += min(hp_damage, target.hp) * 1.0
                    if hp_damage >= target.hp:
                        score += 3.0
                elif kind == "shield":
                    room = engine.content.balance["shield"]["cap"] - target.shields
                    urgency = 1.0 if target.hp * 2 <= target.max_hp else 0.5
                    score += min(amount, room) * urgency * (0.3 if target.shields >= 4 else 1.0)
                elif kind == "heal":
                    if target.state == STATE_DOWNED:
                        score += 8.0 if face.can_revive else 0.0
                    else:
                        score += min(amount, target.max_hp - target.hp) * 1.2
                elif kind == "apply_status":
                    cap = engine.content.status_cap(effect["status"])
                    if target.stacks_of(effect["status"]) < cap:
                        score += {STATUS_POISON: 2.5, STATUS_WEAKEN: 1.8}.get(effect["status"], 1.0)
                    else:
                        score += 0.3
                elif kind == "gain_mana":
                    score += min(amount, target.max_mana - target.mana) * 0.6
                elif kind == "gain_corruption":
                    score -= 0.4 * amount if target.corruption + amount >= 5 else 0.0
                elif kind == "remove_corruption":
                    removed = min(amount, target.corruption)
                    score += removed * (1.5 if target.corruption >= 4 else 0.4)
        return score

    def _best_plan(self, engine: Engine) -> tuple[list[dict[str, Any]], float]:
        hero, turn = engine._active_hero()
        best: list[dict[str, Any]] = []
        best_score = 0.0
        for plan in planning.enumerate_plans(engine, hero, turn):
            intents, problem = engine.preview_plan(plan)
            if problem:
                continue
            score = sum(
                self._score_action(engine, hero, engine.intent_face(i), i.committed_target_ids) for i in intents
            )
            if score > best_score + 1e-9:
                best, best_score = plan, score
        return best, best_score

    # -- decisions ---------------------------------------------------------------------------

    def _keep_or_plan(self, engine: Engine) -> None:
        hero, turn = engine._active_hero()
        plan, score = self._best_plan(engine)
        used = sorted(a["die_id"] for a in plan)
        keep = used if score >= self.keep_threshold else []
        unkept = [d for d in sorted(turn.rolled) if d not in keep]
        if turn.rerolls_remaining > 0 and unkept:
            if sorted(turn.kept) != keep:
                _must(engine.do(cmd.SET_KEPT_DICE, die_ids=keep), "SetKeptDice")
            _must(engine.do(cmd.REROLL_UNKEPT), "RerollUnkept")
            return
        _must(engine.do(cmd.SET_ACTION_PLAN, actions=plan), "SetActionPlan")

    def _react(self, engine: Engine) -> None:
        combat = engine.combat
        assert combat.reaction_stage is not None
        options = reactions.eligible_options(engine, combat.reaction_stage)
        if not options:  # pragma: no cover - the engine only opens a window with an eligible option
            _must(engine.do(cmd.SKIP_REACTION_STAGE), "SkipReactionStage")
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
        _must(engine.do(cmd.USE_REACTION, hero_id=option["hero_id"], target_id=target_id), "UseReaction")

    def _upgrade(self, engine: Engine) -> None:
        offers = engine.state.upgrade_offers
        for hero_id in sorted(offers):
            for die_id in sorted(offers[hero_id]):
                ranked = sorted(
                    offers[hero_id][die_id],
                    key=lambda o: (0 if o["kind"] == "reforge" else 1 if o["kind"] == "sharpen" else 2, o["offer_id"]),
                )
                if ranked:
                    offer = ranked[0]
                    _must(
                        engine.do(cmd.CHOOSE_UPGRADE, hero_id=hero_id, die_id=die_id, offer_id=offer["offer_id"]),
                        "ChooseUpgrade",
                    )
                    return
        raise PolicyError("No upgrade offer is available.")


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
