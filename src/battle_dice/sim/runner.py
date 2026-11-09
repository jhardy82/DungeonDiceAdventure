"""Headless seeded scenario simulation (sections 14.1 and 15.3).

Runs full two-battle runs across a recorded seed matrix and reports win/loss by party size and
composition, plus engine transition latency. Results are measurements, not balance claims.

Usage::

    battle-dice-sim --seeds 50 --policy heuristic --out sim_results/summary.json
"""

from __future__ import annotations

import argparse
import itertools
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

from battle_dice.content.loader import Content, load_content
from battle_dice.core import commands as cmd
from battle_dice.core.engine import Engine
from battle_dice.core.events import state_hash, summarize
from battle_dice.sim.policies import HeuristicPolicy, RandomPolicy

DEFAULT_ROWS = {"squire": "front", "apprentice": "back", "scout": "back"}


def compositions(content: Content, sizes: list[int]) -> list[list[str]]:
    """Every multiset of classes for each requested party size (duplicates allowed)."""
    classes = sorted(content.classes)
    result: list[list[str]] = []
    for size in sizes:
        result.extend(list(combo) for combo in itertools.combinations_with_replacement(classes, size))
    return result


def party_for(content: Content, class_ids: list[str]) -> list[dict[str, str]]:
    return [{"class_id": c, "row": content.class_def(c)["suggested_row"]} for c in class_ids]


def simulate(content: Content, seed: int, class_ids: list[str], policy: Any, timings: list[float] | None = None,
             max_commands: int = 20000) -> dict[str, Any]:
    engine = Engine(content)

    def send(command_type: str, **params: Any) -> Any:
        started = time.perf_counter()
        result = engine.do(command_type, **params)
        if timings is not None:
            timings.append(time.perf_counter() - started)
        return result

    result = send(cmd.START_RUN, seed=seed, party=party_for(content, class_ids))
    if not result.accepted:
        raise RuntimeError(result.reason)
    while not engine.finished():
        if len(engine.command_log) > max_commands:
            raise RuntimeError(f"seed {seed} {class_ids}: run did not terminate")
        if engine.needs_input():
            before = len(engine.command_log)
            started = time.perf_counter()
            policy.act(engine)
            if timings is not None:
                made = max(1, len(engine.command_log) - before)
                timings.extend([(time.perf_counter() - started) / made] * made)
        else:
            send(cmd.ADVANCE_PHASE)
    state = engine.state
    for combatant in engine.combat.combatants.values():
        if min(combatant.hp, combatant.shields, combatant.mana, combatant.corruption, combatant.gauge) < 0:
            raise RuntimeError(f"seed {seed} {class_ids}: negative resource on {combatant.id}")
    return {
        "seed": seed,
        "party": class_ids,
        "outcome": state.outcome,
        "battle_reached": state.encounter_index + 1,
        "commands": len(engine.command_log),
        "events": len(engine.events),
        "state_hash": state_hash(state),
        "stats": summarize(engine.events),
    }


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1))))]


def run_matrix(content: Content, seeds: list[int], sizes: list[int], policy_name: str) -> dict[str, Any]:
    timings: list[float] = []
    by_party: dict[str, dict[str, int]] = {}
    by_size: dict[str, dict[str, int]] = {}
    for class_ids in compositions(content, sizes):
        key = "+".join(class_ids)
        for seed in seeds:
            policy = HeuristicPolicy() if policy_name == "heuristic" else RandomPolicy(seed)
            outcome = simulate(content, seed, class_ids, policy, timings)
            for bucket, name in ((by_party, key), (by_size, str(len(class_ids)))):
                entry = bucket.setdefault(name, {"runs": 0, "victory": 0, "defeat": 0, "defeat_in_battle_1": 0})
                entry["runs"] += 1
                entry[outcome["outcome"]] += 1
                if outcome["outcome"] == "defeat" and outcome["battle_reached"] == 1:
                    entry["defeat_in_battle_1"] += 1
    return {
        "policy": policy_name,
        "content_version": content.content_version,
        "content_hash": content.content_hash,
        "seeds": [str(s) for s in seeds],
        "by_party_size": by_size,
        "by_composition": by_party,
        "latency_ms": {
            "transitions": len(timings),
            "median": round(statistics.median(timings) * 1000, 4),
            "p95": round(percentile(timings, 0.95) * 1000, 4),
            "max": round(max(timings) * 1000, 4),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Battle Dice headless seed-matrix simulator")
    parser.add_argument("--seeds", type=int, default=20, help="number of seeds (0..N-1)")
    parser.add_argument("--seed-start", type=int, default=0)
    parser.add_argument("--sizes", type=int, nargs="*", default=[1, 2, 3, 4, 5])
    parser.add_argument("--policy", choices=["heuristic", "random"], default="heuristic")
    parser.add_argument("--out", type=Path, default=None, help="write the JSON summary to this path")
    args = parser.parse_args(argv)

    content = load_content()
    seeds = list(range(args.seed_start, args.seed_start + args.seeds))
    summary = run_matrix(content, seeds, args.sizes, args.policy)
    text = json.dumps(summary, indent=2, sort_keys=True)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(f"policy={summary['policy']} seeds={len(seeds)} content={summary['content_version']}")
    for size, entry in sorted(summary["by_party_size"].items()):
        print(f"  party size {size}: {entry['victory']}/{entry['runs']} victories, {entry['defeat']} defeats")
    latency = summary["latency_ms"]
    print(f"  engine transitions: {latency['transitions']} median {latency['median']} ms, p95 {latency['p95']} ms")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
