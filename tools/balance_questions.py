"""Two balance questions, measured (owner decision D-36; results in ``docs/DECISION_LOG.md``, section 7.42).

    python tools/balance_questions.py third   --first 300 --count 40
    python tools/balance_questions.py attacks --first 300 --count 40 --variants A B C F C-1

``third``: the optional third battle, for every party of the three starting classes (sizes 1 to 5) and for
the same parties with one Squire replaced by a Guardian. The simulated player always fights on.

``attacks``: how enemies choose their abilities, tried in the simulator only. A variant changes the choice
inside this process while it measures and puts it back; no file of the game is touched.

Both use the informed simulated player and the party order of ``battle_dice.sim.runner``, so variant ``A``
over seeds 300 to 339 is the stored reference (1,703 wins of 2,200), and ``third`` with a Guardian is the
measurement of section 7.16.
"""

from __future__ import annotations

import argparse
import collections
import contextlib
import dataclasses
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor
from typing import Any

from battle_dice.career.evidence import battle_events
from battle_dice.content.loader import Content, load_content
from battle_dice.content.vocations import VocationCatalog, load_vocation_catalog
from battle_dice.core import commands as cmd
from battle_dice.core import enemy_ai
from battle_dice.core.engine import Engine
from battle_dice.core.events import EventType, summarize
from battle_dice.core.models import Combatant, FaceDefinition
from battle_dice.sim.policies import HeuristicPolicy
from battle_dice.sim.runner import compositions

Json = dict[str, Any]
FIGHT = "training_04"
SIZES = (1, 2, 3, 4, 5)

#: How an enemy chooses, by the first letter of a variant. A variant ending in "-1" also weakens every enemy attack.
RULES = {
    "A": "today: an ability that puts a status on a hero who has none always comes before an attack",
    "B": "no preference: every legal ability is drawn by its weight (only a finishing blow comes first)",
    "C": "a status comes first only while no hero it can reach has it; then the weights decide",
    "F": "as today, but an enemy that used a status ability last time draws its next ability by weight",
}
WEAKER = "Every enemy attack does 1 less damage (never less than 1)."

_loaded: dict[str, Any] = {}


def _content() -> Content:
    if "content" not in _loaded:
        _loaded["content"] = load_content()
    content: Content = _loaded["content"]
    return content


def _catalog() -> VocationCatalog:
    if "catalog" not in _loaded:
        _loaded["catalog"] = load_vocation_catalog(_content())
    catalog: VocationCatalog = _loaded["catalog"]
    return catalog


def play(engine: Engine) -> None:
    """The informed player plays the run to its end (and fights on when it is asked)."""
    policy = HeuristicPolicy()
    for _ in range(40000):
        if engine.finished():
            return
        if engine.needs_input():
            policy.act(engine)
        else:
            engine.do(cmd.ADVANCE_PHASE)
    raise RuntimeError("a run did not end")


def describe(variant: str) -> str:
    return RULES[variant[0]] + (f". {WEAKER}" if variant.endswith("-1") else "")


# --------------------------------------------------------------------------------------------
# The third battle
# --------------------------------------------------------------------------------------------


def third_parties(sizes: tuple[int, ...] = SIZES) -> list[tuple[str, tuple[str, ...]]]:
    """Every party of starting classes, and each one that has a Squire again with that Squire as a Guardian."""
    parties: list[tuple[str, tuple[str, ...]]] = []
    for party in compositions(_content(), list(sizes)):
        parties.append(("no Guardian", tuple(party)))
        if "squire" in party:
            swapped = list(party)
            swapped[swapped.index("squire")] = "guardian"
            parties.append(("one Guardian", tuple(swapped)))
    return parties


def third_run(job: tuple[str, tuple[str, ...], int]) -> Json:
    """One run that may go on into the third battle: which battles were entered, and how each went."""
    group, party, seed = job
    content = _content()
    rows = {class_id: content.class_def(class_id)["suggested_row"] for class_id in content.classes} | {"guardian": "front"}
    engine = Engine(content, _catalog())
    started = engine.do(cmd.START_RUN, seed=seed, party=[{"class_id": c, "row": rows[c]} for c in party], encounters=[FIGHT])
    if not started.accepted:
        raise RuntimeError(started.reason)
    play(engine)
    battles: dict[int, Json] = {}
    for record in engine.state.battle_records:
        stats = summarize(battle_events(engine.events, record["battle"]))
        battles[record["battle"]] = {"won": record["outcome"] == "victory", "activations": record["activations"],
                                     "damage_taken": stats["damage_taken"]}
    return {"group": group, "size": len(party), "party": party, "seed": seed, "outcome": engine.state.outcome, "battles": battles}


def third_table(results: list[Json]) -> list[str]:
    def share(part: int, whole: int) -> str:
        return f"{100 * part / whole:.1f}% ({part}/{whole})" if whole else "none entered"

    lines = ["group | size | runs | Battle 2 won, of those that entered | Battle 3 won, of those that entered | "
             "activations in a won Battle 2 / 3 | health lost in a won Battle 2 / 3"]
    for group in ("one Guardian", "no Guardian", "no Guardian, with a Squire", "no Guardian, no Squire"):
        for size in sorted({r["size"] for r in results}):
            rows = [r for r in results if r["size"] == size and r["group"] == group.split(",")[0]
                    and ("," not in group or ("squire" in r["party"]) == group.endswith("with a Squire"))]
            if not rows:
                continue
            entered = {b: [r for r in rows if b in r["battles"]] for b in (2, 3)}
            won = {b: [r for r in entered[b] if r["battles"][b]["won"]] for b in (2, 3)}

            def mean(battle: int, key: str, won: dict[int, list[Json]] = won) -> str:
                values = [r["battles"][battle][key] for r in won[battle]]
                return f"{sum(values) / len(values):.0f}" if values else "-"

            lines.append(f"{group} | {size} | {len(rows)} | {share(len(won[2]), len(entered[2]))} | {share(len(won[3]), len(entered[3]))} | "
                         f"{mean(2, 'activations')} / {mean(3, 'activations')} | {mean(2, 'damage_taken')} / {mean(3, 'damage_taken')}")
    return lines


# --------------------------------------------------------------------------------------------
# How enemies choose
# --------------------------------------------------------------------------------------------


def _default_tier(evaluated: list[Json], ai: Json, keep: Any) -> list[Json]:
    """The evaluated abilities with every status ability that ``keep`` does not hold back moved to the common tier."""
    for entry in evaluated:
        if entry["priority"] == ai["priority_setup"] and not keep(entry):
            entry["priority"] = ai["priority_default"]
    return evaluated


@contextlib.contextmanager
def enemy_choice(variant: str) -> Iterator[None]:
    """While it is open, enemies choose by ``variant``. What the game had is put back, whatever happens."""
    if variant[0] not in RULES or variant[1:] not in ("", "-1"):
        raise ValueError(f"unknown variant '{variant}'")
    evaluate, action = enemy_ai.evaluate_actions, Engine.enemy_action

    def no_preference(ctx: Engine, enemy: Combatant) -> list[Json]:
        return _default_tier(evaluate(ctx, enemy), ctx.content.balance["ai"], lambda entry: False)

    def until_someone_has_it(ctx: Engine, enemy: Combatant) -> list[Json]:
        def nobody_has_it(entry: Json) -> bool:
            status = entry["face"].status_effect()
            return status is not None and all(target.stacks_of(status["status"]) == 0 for target in entry["targets"])
        return _default_tier(evaluate(ctx, enemy), ctx.content.balance["ai"], nobody_has_it)

    def not_twice_running(ctx: Engine, enemy: Combatant) -> list[Json]:
        last = None
        for event in reversed(ctx.events):
            if event.type == EventType.BATTLE_STARTED:
                break
            if event.type == EventType.INTENT_REVEALED and event.actor_id == enemy.id:
                last = event.delta["category"]
                break
        return _default_tier(evaluate(ctx, enemy), ctx.content.balance["ai"], lambda entry: last != "status")

    def weaker(self: Engine, enemy: Combatant, action_id: str) -> FaceDefinition:
        face = action(self, enemy, action_id)
        return dataclasses.replace(face, power=max(1, face.power - 1)) if face.category == "attack" else face

    rules = {"A": evaluate, "B": no_preference, "C": until_someone_has_it, "F": not_twice_running}
    enemy_ai.evaluate_actions = rules[variant[0]]
    if variant.endswith("-1"):
        Engine.enemy_action = weaker  # type: ignore[method-assign]
    try:
        yield
    finally:
        enemy_ai.evaluate_actions = evaluate
        Engine.enemy_action = action  # type: ignore[method-assign]


def attacks_run(job: tuple[str, tuple[str, ...], int]) -> Json:
    """One run of the game as shipped (two battles), with enemies choosing by a variant."""
    variant, party, seed = job
    content = _content()
    with enemy_choice(variant):
        engine = Engine(content)
        started = engine.do(cmd.START_RUN, seed=seed, party=[{"class_id": c, "row": content.class_def(c)["suggested_row"]} for c in party])
        if not started.accepted:
            raise RuntimeError(started.reason)
        play(engine)
    # Only enemies reveal what they are about to do: a hero's plan is committed, not revealed.
    kinds = collections.Counter(e.delta["category"] for e in engine.events if e.type == EventType.INTENT_REVEALED)
    stats = summarize(engine.events)
    return {"variant": variant, "size": len(party), "party": party, "seed": seed, "won": engine.state.outcome == "victory",
            "enemy_actions": sum(kinds.values()), "attacks": kinds["attack"], "activations": stats["activations"],
            "damage_taken": stats["damage_taken"], "downed": stats["heroes_downed"]}


def attacks_table(results: list[Json], variant: str) -> list[str]:
    lines = [f"Variant {variant}: {describe(variant)}",
             "size | runs | won | attacks among enemy actions | activations per run | heroes downed per run | parties at or below 40% / at or above 95%"]
    mine = [r for r in results if r["variant"] == variant]
    sizes: list[int | str] = [*sorted({r["size"] for r in mine}), "all"]
    for size in sizes:
        rows = [r for r in mine if size == "all" or r["size"] == size]
        by_party: dict[tuple[str, ...], list[bool]] = collections.defaultdict(list)
        for r in rows:
            by_party[tuple(r["party"])].append(r["won"])
        rates = [sum(wins) / len(wins) for wins in by_party.values()]
        won, count = sum(r["won"] for r in rows), len(rows)
        lines.append(f"{size} | {count} | {100 * won / count:.1f}% ({won}) | "
                     f"{100 * sum(r['attacks'] for r in rows) / max(1, sum(r['enemy_actions'] for r in rows)):.0f}% | "
                     f"{sum(r['activations'] for r in rows) / count:.1f} | {sum(r['downed'] for r in rows) / count:.2f} | "
                     f"{sum(rate <= 0.40 for rate in rates)} / {sum(rate >= 0.95 for rate in rates)} of {len(rates)}")
    return lines


# --------------------------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------------------------


def run_jobs(function: Any, jobs: list[Any], workers: int) -> list[Json]:
    if workers <= 1:
        return [function(job) for job in jobs]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(function, jobs, chunksize=8))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("question", choices=("third", "attacks"))
    parser.add_argument("--first", type=int, default=300, help="the first seed")
    parser.add_argument("--count", type=int, default=40, help="how many seeds")
    parser.add_argument("--sizes", type=int, nargs="+", default=list(SIZES), help="party sizes")
    parser.add_argument("--variants", nargs="+", default=["A"], help="for 'attacks': A, B, C, F, each also with -1")
    parser.add_argument("--jobs", type=int, default=4, help="processes")
    args = parser.parse_args(argv)
    seeds, sizes = range(args.first, args.first + args.count), tuple(args.sizes)
    if args.question == "third":
        results = run_jobs(third_run, [(group, party, seed) for group, party in third_parties(sizes) for seed in seeds], args.jobs)
        print("\n".join(third_table(results)))
        return 0
    for variant in args.variants:
        with enemy_choice(variant):  # an unknown variant is refused before anything is played
            pass
    parties = [tuple(party) for party in compositions(_content(), list(sizes))]
    for variant in args.variants:
        results = run_jobs(attacks_run, [(variant, party, seed) for party in parties for seed in seeds], args.jobs)
        print("\n".join(attacks_table(results, variant)), end="\n\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
