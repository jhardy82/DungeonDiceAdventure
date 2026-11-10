"""Scenario-based playtest runner (method and scenario catalogue: ``docs/PLAYTEST.md``).

Each scenario is a design question, a persona that changes one habit of the informed player, and a
prediction made before the run. The runner plays every persona on the same parties and seeds and
reports win rates and play-experience measures taken from the event log.

    python tools/playtest_scenarios.py --seeds 80 --jobs 4 --out playtest_results.json
"""

from __future__ import annotations

import argparse
import json
import statistics
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from battle_dice.content.loader import load_content
from battle_dice.core import commands as cmd
from battle_dice.core.engine import Engine
from battle_dice.core.events import EventType
from battle_dice.sim.personas import PERSONAS, make_persona

#: Parties every persona plays, in their suggested rows.
PARTIES: dict[str, list[str]] = {
    "solo squire": ["squire"],
    "solo apprentice": ["apprentice"],
    "solo scout": ["scout"],
    "trio": ["squire", "apprentice", "scout"],
    "four": ["squire", "squire", "apprentice", "scout"],
    "five": ["squire", "squire", "apprentice", "scout", "scout"],
}
#: Formation scenario: these parties again with every row inverted (Squires behind, the others in front).
FORMATION_PARTIES = ("trio", "four", "five")


def play(content_dir: str | None, persona: str, party: list[tuple[str, str]], seed: int) -> dict[str, Any]:
    content = load_content(content_dir)
    engine = Engine(content)
    members = [{"class_id": class_id, "row": row} for class_id, row in party]
    result = engine.do(cmd.START_RUN, seed=seed, party=members)
    assert result.accepted, result.reason
    policy = make_persona(persona, seed)
    decisions = 0
    while not engine.finished():
        if len(engine.command_log) > 20000:
            raise RuntimeError(f"{persona} seed {seed}: run did not terminate")
        if engine.needs_input():
            before = len(engine.command_log)
            policy.act(engine)
            decisions += len(engine.command_log) - before
        else:
            assert engine.do(cmd.ADVANCE_PHASE).accepted
    return measure(engine, decisions)


def measure(engine: Engine, decisions: int) -> dict[str, Any]:
    """Play-experience measures of one finished run, all read from the event log."""
    counts: dict[str, int] = {}
    empty_plans = 0
    for event in engine.events:
        kind = str(event.type)
        counts[kind] = counts.get(kind, 0) + 1
        if event.type == EventType.PLAN_COMMITTED and not event.delta.get("actions"):
            empty_plans += 1
    heroes = engine.combat.side("hero")
    hero_ids = {h.id for h in heroes}
    activations = sum(1 for e in engine.events if e.type == EventType.ACTIVATION_STARTED and e.actor_id in hero_ids)
    downed = sum(1 for e in engine.events if e.type == EventType.COMBATANT_DOWNED)
    won = engine.state.outcome == "victory"
    return {
        "won": won,
        "battle_reached": engine.state.encounter_index + 1,
        "decisions": decisions,
        "hero_activations": activations,
        "idle_activations": counts.get(str(EventType.HERO_PASSED), 0) + empty_plans,
        "rerolls": counts.get(str(EventType.DICE_REROLLED), 0),
        "reactions": counts.get(str(EventType.REACTION_USED), 0),
        "reaction_windows": counts.get(str(EventType.REACTION_STAGE_OPENED), 0),
        "heroes_downed": downed,
        "revives": counts.get(str(EventType.HERO_REVIVED), 0),
        "won_after_a_hero_fell": won and downed > 0,
        "health_left": (sum(h.hp for h in heroes) / sum(h.max_hp for h in heroes)) if won else None,
    }


def _job(job: tuple[str | None, str, str, list[tuple[str, str]], list[int]]) -> tuple[str, str, list[dict[str, Any]]]:
    content_dir, persona, party_name, party, seeds = job
    return persona, party_name, [play(content_dir, persona, party, seed) for seed in seeds]


def summarise(runs: list[dict[str, Any]]) -> dict[str, Any]:
    wins = [r for r in runs if r["won"]]
    activations = sum(r["hero_activations"] for r in runs)
    return {
        "runs": len(runs),
        "win_rate": round(100.0 * len(wins) / len(runs), 1),
        "lost_in_battle_1": round(100.0 * sum(1 for r in runs if not r["won"] and r["battle_reached"] == 1) / len(runs), 1),
        "decisions_median": statistics.median(r["decisions"] for r in runs),
        "hero_activations_median": statistics.median(r["hero_activations"] for r in runs),
        "idle_activation_rate": round(100.0 * sum(r["idle_activations"] for r in runs) / max(1, activations), 1),
        "rerolls_per_activation": round(sum(r["rerolls"] for r in runs) / max(1, activations), 2),
        "reaction_windows_per_hero_activation": round(sum(r["reaction_windows"] for r in runs) / max(1, activations), 2),
        "reactions_per_window": round(
            sum(r["reactions"] for r in runs) / max(1, sum(r["reaction_windows"] for r in runs)), 2
        ),
        "runs_with_a_hero_down": round(100.0 * sum(1 for r in runs if r["heroes_downed"]) / len(runs), 1),
        "comeback_wins": round(100.0 * sum(1 for r in runs if r["won_after_a_hero_fell"]) / max(1, len(wins)), 1),
        "health_left_at_victory": round(100.0 * statistics.mean(r["health_left"] for r in wins), 1) if wins else None,
    }


def run_all(content_dir: str | None, seeds: list[int], jobs: int) -> dict[str, Any]:
    content = load_content(content_dir)
    suggested = {c: content.class_def(c)["suggested_row"] for c in content.classes}
    work = [
        (content_dir, persona, name, [(c, suggested[c]) for c in party], seeds)
        for persona in PERSONAS
        for name, party in PARTIES.items()
    ]
    flipped = {"front": "back", "back": "front"}
    for name in FORMATION_PARTIES:
        inverted = [(c, flipped[suggested[c]]) for c in PARTIES[name]]
        work.append((content_dir, "informed", f"{name}, rows inverted", inverted, seeds))
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        results = list(pool.map(_job, work))
    cells: dict[str, dict[str, Any]] = {}
    pooled: dict[str, list[dict[str, Any]]] = {}
    for persona, party_name, runs in results:
        cells.setdefault(persona, {})[party_name] = summarise(runs)
        if party_name in PARTIES:
            pooled.setdefault(persona, []).extend(runs)
    return {
        "content_version": content.content_version,
        "content_hash": content.content_hash,
        "content_dir": content_dir,
        "seeds": [seeds[0], seeds[-1]],
        "parties": {name: party for name, party in PARTIES.items()},
        "by_persona": {persona: summarise(runs) for persona, runs in pooled.items()},
        "by_persona_and_party": cells,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Battle Dice scenario-based playtest runner")
    parser.add_argument("--seeds", type=int, default=40)
    parser.add_argument("--seed-start", type=int, default=0)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--content-dir", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    content_dir = str(args.content_dir) if args.content_dir is not None else None
    summary = run_all(content_dir, list(range(args.seed_start, args.seed_start + args.seeds)), max(1, args.jobs))
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    base = summary["by_persona"]["informed"]["win_rate"]
    print(f"content {summary['content_version']}, seeds {summary['seeds'][0]}-{summary['seeds'][1]}, "
          f"{len(PARTIES)} parties, {summary['by_persona']['informed']['runs']} runs per persona")
    print(f"{'persona':<15}{'win %':>7}{'vs informed':>13}{'idle %':>8}{'decisions':>11}{'health left %':>15}")
    for persona, row in summary["by_persona"].items():
        health = "-" if row["health_left_at_victory"] is None else f"{row['health_left_at_victory']:.0f}"
        print(f"{persona:<15}{row['win_rate']:>7.1f}{row['win_rate'] - base:>+13.1f}{row['idle_activation_rate']:>8.1f}"
              f"{row['decisions_median']:>11.0f}{health:>15}")
    for name in FORMATION_PARTIES:
        cells = summary["by_persona_and_party"]["informed"]
        print(f"formation, {name}: suggested rows {cells[name]['win_rate']:.1f}%, "
              f"rows inverted {cells[f'{name}, rows inverted']['win_rate']:.1f}%")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
