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
from battle_dice.core.build import BuildSource
from battle_dice.core.engine import Engine
from battle_dice.core.events import state_hash, summarize
from battle_dice.sim.policies import POLICY_VERSION, HeuristicPolicy, RandomPolicy

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
             max_commands: int = 20000, vocations: BuildSource | None = None, rows: list[str] | None = None) -> dict[str, Any]:
    """Play one run. ``vocations`` and ``rows`` are for parties with an evolved hero (Class Evolution)."""
    engine = Engine(content, vocations)

    def send(command_type: str, **params: Any) -> Any:
        started = time.perf_counter()
        result = engine.do(command_type, **params)
        if timings is not None:
            timings.append(time.perf_counter() - started)
        return result

    if rows is None:
        party = party_for(content, class_ids)
    else:
        party = [{"class_id": class_id, "row": row} for class_id, row in zip(class_ids, rows, strict=True)]
    result = send(cmd.START_RUN, seed=seed, party=party)
    if not result.accepted:
        raise RuntimeError(result.reason)
    while not engine.finished():
        if len(engine.command_log) > max_commands:
            raise RuntimeError(f"seed {seed} {class_ids}: run did not terminate")
        if engine.needs_input():
            before = len(engine.command_log)
            started = time.perf_counter()
            in_engine = getattr(policy, "engine_seconds", None)
            policy.act(engine)
            if timings is not None:
                made = max(1, len(engine.command_log) - before)
                # A player that reports its own engine time is charged for that only, not for its thinking.
                spent = time.perf_counter() - started if in_engine is None else policy.engine_seconds - in_engine
                timings.extend([spent / made] * made)
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


def _new_tally() -> dict[str, int]:
    return {"runs": 0, "victory": 0, "defeat": 0, "defeat_in_battle_1": 0}


def run_composition(content: Content, class_ids: list[str], seeds: list[int], policy_name: str) -> dict[str, Any]:
    """Play every seed for one class composition. Returns its tally and per-transition timings."""
    tally = _new_tally()
    timings: list[float] = []
    for seed in seeds:
        policy = HeuristicPolicy() if policy_name == "heuristic" else RandomPolicy(seed)
        outcome = simulate(content, seed, class_ids, policy, timings)
        tally["runs"] += 1
        tally[outcome["outcome"]] += 1
        if outcome["outcome"] == "defeat" and outcome["battle_reached"] == 1:
            tally["defeat_in_battle_1"] += 1
    return {"party": class_ids, "tally": tally, "timings": timings}


def _composition_worker(job: tuple[str | None, list[str], list[int], str]) -> dict[str, Any]:
    """Process-pool entry point: each worker loads (and validates) the content itself."""
    content_dir, class_ids, seeds, policy_name = job
    return run_composition(load_content(content_dir), class_ids, seeds, policy_name)


def run_matrix(
    content: Content,
    seeds: list[int],
    sizes: list[int],
    policy_name: str,
    jobs: int = 1,
    content_dir: str | None = None,
) -> dict[str, Any]:
    """Run the seed matrix. Results do not depend on ``jobs``: compositions are merged in a fixed order."""
    parties = compositions(content, sizes)
    if jobs > 1:
        from concurrent.futures import ProcessPoolExecutor

        work = [(content_dir, class_ids, seeds, policy_name) for class_ids in parties]
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            results = list(pool.map(_composition_worker, work))
    else:
        results = [run_composition(content, class_ids, seeds, policy_name) for class_ids in parties]

    timings: list[float] = []
    by_party: dict[str, dict[str, int]] = {}
    by_size: dict[str, dict[str, int]] = {}
    total = _new_tally()
    for result in results:
        timings.extend(result["timings"])
        by_party["+".join(result["party"])] = result["tally"]
        size_entry = by_size.setdefault(str(len(result["party"])), _new_tally())
        for key, value in result["tally"].items():
            size_entry[key] += value
            total[key] += value
    return {
        "policy": policy_name,
        "policy_version": POLICY_VERSION if policy_name == "heuristic" else None,
        "content_version": content.content_version,
        "content_hash": content.content_hash,
        "content_dir": content_dir,
        "seeds": [str(s) for s in seeds],
        "overall": total,
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
    parser.add_argument("--seeds", type=int, default=20, help="number of seeds (seed-start .. seed-start+N-1)")
    parser.add_argument("--seed-start", type=int, default=0)
    parser.add_argument("--sizes", type=int, nargs="*", default=[1, 2, 3, 4, 5])
    parser.add_argument("--policy", choices=["heuristic", "random"], default="heuristic")
    parser.add_argument("--content-dir", type=Path, default=None,
                        help="measure a candidate fixture set from this folder instead of the packaged content")
    parser.add_argument("--jobs", type=int, default=1, help="worker processes (results are identical for any value)")
    parser.add_argument("--out", type=Path, default=None, help="write the JSON summary to this path")
    args = parser.parse_args(argv)

    content_dir = str(args.content_dir) if args.content_dir is not None else None
    content = load_content(content_dir)
    seeds = list(range(args.seed_start, args.seed_start + args.seeds))
    summary = run_matrix(content, seeds, args.sizes, args.policy, jobs=max(1, args.jobs), content_dir=content_dir)
    text = json.dumps(summary, indent=2, sort_keys=True)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    source = content_dir or "packaged content"
    print(f"policy={summary['policy']} seeds={len(seeds)} content={summary['content_version']} ({source})")
    for size, entry in sorted(summary["by_party_size"].items()):
        rate = 100.0 * entry["victory"] / entry["runs"]
        print(f"  party size {size}: {entry['victory']}/{entry['runs']} victories ({rate:.1f}%), {entry['defeat']} defeats")
    overall = summary["overall"]
    print(f"  overall: {overall['victory']}/{overall['runs']} victories ({100.0 * overall['victory'] / overall['runs']:.1f}%)")
    latency = summary["latency_ms"]
    print(f"  engine transitions: {latency['transitions']} median {latency['median']} ms, p95 {latency['p95']} ms")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
