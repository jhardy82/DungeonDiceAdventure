"""Scripted player personas for scenario-based playtesting (``docs/PLAYTEST.md``).

Each persona is the informed heuristic player with one habit changed, or a deliberately naive
player. Comparing a persona with the informed player on the same seeds answers one design
question: does this mechanic change who wins? They drive the engine only through commands, like
every other policy, and use a private random stream where they need one.
"""

from __future__ import annotations

from typing import Any

from battle_dice import rng
from battle_dice.core import commands as cmd
from battle_dice.core import planning, progression
from battle_dice.core.engine import Engine
from battle_dice.core.models import ActionIntent, Combatant, HeroTurn, RunPhase
from battle_dice.sim.policies import HeuristicPolicy, PolicyError, RandomPolicy


class Informed(HeuristicPolicy):
    """The reference player: every mechanic used as well as the heuristic can."""

    name = "informed"


class Newcomer(HeuristicPolicy):
    """A first-time player who presses the obvious thing.

    Never rerolls, never reacts, uses the first usable die on the first legal target (one action per
    activation), and takes the first upgrade card shown.
    """

    name = "newcomer"

    def _keep_or_plan(self, engine: Engine) -> None:
        hero, turn = engine._active_hero()
        for option in planning.die_options(engine, hero, turn):
            if not option["usable_alone"]:
                continue
            face = option["face"]
            targets = [] if face.target_scope in ("all_enemies", "all_allies", "self") else option["eligible_target_ids"][:1]
            self._send(engine, cmd.SET_ACTION_PLAN, actions=[{"die_id": option["die_id"], "target_ids": targets}])
            return
        self._send(engine, cmd.SET_ACTION_PLAN, actions=[])

    def _react(self, engine: Engine) -> None:
        self._send(engine, cmd.SKIP_REACTION_STAGE)

    def _upgrade(self, engine: Engine) -> None:
        offers = engine.state.upgrade_offers
        for hero_id in sorted(offers):
            for die_id in sorted(offers[hero_id]):
                for offer in offers[hero_id][die_id]:
                    self._send(engine, cmd.CHOOSE_UPGRADE, hero_id=hero_id, die_id=die_id, offer_id=offer["offer_id"])
                    return
        raise PolicyError("No upgrade offer is available.")


class NoReroll(HeuristicPolicy):
    """Informed, but plays every first roll as it lies."""

    name = "no_reroll"

    def _keep_or_plan(self, engine: Engine) -> None:
        hero, turn = engine._active_hero()
        plan, _ = self._best_plan(engine, hero, turn)
        self._send(engine, cmd.SET_ACTION_PLAN, actions=plan)


class NoReaction(HeuristicPolicy):
    """Informed, but never uses Interpose, Grounding or Disrupt."""

    name = "no_reaction"

    def _react(self, engine: Engine) -> None:
        self._send(engine, cmd.SKIP_REACTION_STAGE)


class RandomTarget(HeuristicPolicy):
    """Informed about which dice to use, but aims each single-target action at a random legal target."""

    name = "random_target"

    def __init__(self, seed: int = 0) -> None:
        super().__init__()
        self._stream = rng.seed_stream(seed, 0x7A)

    def _best_plan(self, engine: Engine, hero: Combatant, turn: HeroTurn) -> tuple[list[dict[str, Any]], float]:
        plan, score = super()._best_plan(engine, hero, turn)
        if turn is not engine.combat.turn:
            return plan, score  # a roll that has not happened: only its value is wanted
        legal = {o["die_id"]: o["eligible_target_ids"] for o in planning.die_options(engine, hero, turn)}
        scattered = []
        for action in plan:
            targets = list(action["target_ids"])
            if targets:
                options = legal[action["die_id"]]
                targets = [options[rng.bounded(self._stream, len(options))]]
            scattered.append({"die_id": action["die_id"], "target_ids": targets})
        return scattered, score


class WorstUpgrade(HeuristicPolicy):
    """Informed in battle, but takes the upgrade card that adds the least."""

    name = "worst_upgrade"

    def _upgrade(self, engine: Engine) -> None:
        ranked: list[tuple[float, str, str, str]] = []
        for hero_id, dice in engine.state.upgrade_offers.items():
            hero = engine.combat.combatants[hero_id]
            for die_id, offers in dice.items():
                size = engine.die_for(hero_id, die_id).size
                for offer in offers:
                    before = self._face_value(engine, hero, progression.face_from_plain(offer["before"]))
                    after = self._face_value(engine, hero, progression.face_from_plain(offer["after"]))
                    ranked.append(((after - before) / size, hero_id, die_id, offer["offer_id"]))
        if not ranked:
            raise PolicyError("No upgrade offer is available.")
        _, hero_id, die_id, offer_id = min(ranked)
        self._send(engine, cmd.CHOOSE_UPGRADE, hero_id=hero_id, die_id=die_id, offer_id=offer_id)


class _OneTrick(HeuristicPolicy):
    """Informed, with one kind of action valued far above the rest."""

    favoured: tuple[str, ...] = ()

    def _score_plan(self, engine: Engine, hero: Combatant, intents: list[ActionIntent]) -> float:
        total = super()._score_plan(engine, hero, intents)
        favourite = super()._score_plan(engine, hero, [i for i in intents if i.category in self.favoured])
        return total + 10.0 * favourite


class Attacker(_OneTrick):
    """Always attacks when it can; everything else only breaks ties."""

    name = "attacker"
    favoured = ("attack",)


class Defender(_OneTrick):
    """Always shields or heals when it can; everything else only breaks ties."""

    name = "defender"
    favoured = ("defense", "healing")


class Gambler(HeuristicPolicy):
    """Keeps a die only when it shows that die's best face, and rerolls the rest until rerolls run out."""

    name = "gambler"

    def _keep_or_plan(self, engine: Engine) -> None:
        hero, turn = engine._active_hero()
        if turn.rerolls_remaining > 0:
            keep = []
            for die_id in sorted(turn.rolled):
                faces = engine.die_for(hero.id, die_id).faces
                values = [self._face_value(engine, hero, face) for face in faces]
                if values[turn.rolled[die_id]] >= max(values) - 1e-9:
                    keep.append(die_id)
            if len(keep) < len(turn.rolled):
                if sorted(turn.kept) != keep:
                    self._send(engine, cmd.SET_KEPT_DICE, die_ids=keep)
                self._send(engine, cmd.REROLL_UNKEPT)
                return
        plan, _ = self._best_plan(engine, hero, turn)
        self._send(engine, cmd.SET_ACTION_PLAN, actions=plan)


class BenchSwapper(HeuristicPolicy):
    """Informed, and before Battle 2 swaps each hero's bench die in for the smaller starting die."""

    name = "bench_swapper"
    swap_out_largest = False

    def act(self, engine: Engine) -> None:
        state = engine.state
        if state.phase == RunPhase.EQUIPMENT and cmd.SWAP_DIE in engine.permissible_commands():
            for hero_id in sorted(state.inventory):
                hero = engine.combat.combatants[hero_id]
                by_size = sorted(hero.equipped_dice_ids, key=lambda d: (engine.die_for(hero_id, d).size, d))
                out_die = by_size[-1] if self.swap_out_largest else by_size[0]
                for in_die in sorted(state.inventory[hero_id]):
                    if progression.swap_problem(engine, hero_id, out_die, in_die) is None:
                        self._send(engine, cmd.SWAP_DIE, hero_id=hero_id, out_die_id=out_die, in_die_id=in_die)
                        return
        super().act(engine)


class MainDieSwapper(BenchSwapper):
    """Informed, but swaps the bench die in for the hero's *largest* die: the swap the rules allow and a
    player would regret."""

    name = "main_die_swapper"
    swap_out_largest = True


class Uninformed(RandomPolicy):
    """Uniformly random legal decisions (the existing random policy), as the floor."""

    name = "uninformed"


PERSONAS: dict[str, type] = {
    cls.name: cls
    for cls in (Informed, Newcomer, Uninformed, NoReroll, NoReaction, RandomTarget, WorstUpgrade, Attacker, Defender,
                Gambler, BenchSwapper, MainDieSwapper)
}


def make_persona(name: str, seed: int) -> Any:
    """A fresh persona for one run. Personas that use chance are seeded from the run seed."""
    cls = PERSONAS[name]
    return cls(seed) if cls in (RandomTarget, Uninformed) else cls()

