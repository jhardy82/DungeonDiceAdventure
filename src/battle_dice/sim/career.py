"""Runs with saved heroes, played by a simulated player (Class Evolution Phase 4, step C).

One function plays one run from the save's point of view: it builds the party from saved heroes,
starts the run, and hands every battle's result to the career rules as the game itself will.
A second one keeps playing until a hero has mastered its vocation, which is how pacing is measured.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from battle_dice.app.progression import Progression
from battle_dice.career.catalog import MASTERED_RANK
from battle_dice.content.loader import Content
from battle_dice.core import commands as cmd
from battle_dice.core.build import BuildSource
from battle_dice.core.engine import Engine
from battle_dice.sim.policies import HeuristicPolicy

Json = dict[str, Any]


def play_saved_run(progression: Progression, content: Content, vocations: BuildSource, party: list[tuple[str, str]], seed: int,
                   policy: Any | None = None, third_battle: bool = True) -> Json:
    """Play one run with the saved heroes ``party`` (``(hero id, row)`` pairs). Returns its outcome and awards."""
    engine = Engine(content, vocations)
    params: Json = {"seed": seed, "run_id": progression.next_run_id(seed),
                    "party": [progression.party_entry(hero_id, row) for hero_id, row in party]}
    if third_battle:
        params["encounters"] = progression.extra_encounters()
    result = engine.do(cmd.START_RUN, **params)
    if not result.accepted:
        raise RuntimeError(result.reason)
    progression.run_started(engine)
    player = policy if policy is not None else HeuristicPolicy()
    while not engine.finished():
        if engine.needs_input():
            player.act(engine)
        else:
            engine.do(cmd.ADVANCE_PHASE)
        progression.sync(engine)
    return {"run_id": engine.state.run_id, "seed": seed, "outcome": engine.state.outcome,
            "battles": len(engine.state.battle_records), "awards": list(progression.last_awards), "engine": engine}


def runs_to_master(progression: Progression, content: Content, vocations: BuildSource, party: list[tuple[str, str]], hero_id: str,
                   first_seed: int, limit: int = 200, third_battle: bool = True,
                   policy_factory: Callable[[], Any] = HeuristicPolicy) -> Json:
    """Play runs until ``hero_id`` has mastered its active vocation. Returns the count and the wins."""
    vocation_id = progression.state.heroes[hero_id].active_vocation_id
    runs = wins = 0
    while progression.state.heroes[hero_id].mastery[vocation_id].rank < MASTERED_RANK:
        if runs >= limit:
            raise RuntimeError(f"{hero_id} did not master '{vocation_id}' within {limit} runs.")
        played = play_saved_run(progression, content, vocations, party, first_seed + runs, policy_factory(), third_battle)
        runs += 1
        wins += played["outcome"] == "victory"
    return {"hero_id": hero_id, "vocation_id": vocation_id, "runs": runs, "wins": wins}
