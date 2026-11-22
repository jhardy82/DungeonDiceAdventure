"""The measuring tool for the two balance questions of D-36 (``tools/balance_questions.py``).

Its numbers go to the owner as the ground for a decision, so the tool is tested like the game: today's
rule must be the game itself, a variant must change what it says and nothing else, and nothing may be
left changed behind it.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from battle_dice.core import commands as cmd
from battle_dice.core import enemy_ai
from battle_dice.core.engine import Engine
from battle_dice.core.events import EventType
from battle_dice.sim.policies import HeuristicPolicy
from battle_dice.sim.runner import simulate
from tests.conftest import enemies, packaged_content

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("balance_questions", ROOT / "tools" / "balance_questions.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["balance_questions"] = module
    spec.loader.exec_module(module)
    yield module
    del sys.modules["balance_questions"]


def share(rows) -> float:
    return sum(r["attacks"] for r in rows) / sum(r["enemy_actions"] for r in rows)


def test_todays_rule_is_the_game_itself(tool):
    """Variant A must be the stored reference's run, seed for seed: same outcome, same number of activations."""
    for party, seed in ((("squire",), 300), (("apprentice", "scout"), 301)):
        measured = tool.attacks_run(("A", party, seed))
        reference = simulate(packaged_content(), seed, list(party), HeuristicPolicy())
        assert measured["won"] == (reference["outcome"] == "victory")
        assert (measured["activations"], measured["damage_taken"]) == (reference["stats"]["activations"], reference["stats"]["damage_taken"])
        assert 0 < measured["attacks"] < measured["enemy_actions"]
        # Counted here once more from a run of the same seed: only what enemies chose, and their attacks among it.
        content = packaged_content()
        engine = Engine(content)
        assert engine.do(cmd.START_RUN, seed=seed, party=[{"class_id": c, "row": content.class_def(c)["suggested_row"]} for c in party]).accepted
        tool.play(engine)
        chosen = [e.delta["category"] for e in engine.events if e.type == EventType.INTENT_REVEALED and "_e" in (e.actor_id or "")]
        by_heroes = [e for e in engine.events if e.type == EventType.INTENT_REVEALED and "_e" not in (e.actor_id or "")]
        assert (measured["enemy_actions"], measured["attacks"]) == (len(chosen), chosen.count("attack"))
        assert by_heroes == [], "only enemies reveal an ability: the tool relies on that"


def test_a_variant_is_put_back_whatever_happens(tool):
    evaluate, action = enemy_ai.evaluate_actions, Engine.enemy_action
    with tool.enemy_choice("B-1"):
        assert enemy_ai.evaluate_actions is not evaluate and Engine.enemy_action is not action
    assert enemy_ai.evaluate_actions is evaluate and Engine.enemy_action is action
    with pytest.raises(RuntimeError), tool.enemy_choice("F-1"):
        raise RuntimeError("a run went wrong")
    assert enemy_ai.evaluate_actions is evaluate and Engine.enemy_action is action
    for unknown in ("X", "A-2", "B1"):
        with pytest.raises(ValueError, match="unknown variant"), tool.enemy_choice(unknown):
            pass
    assert enemy_ai.evaluate_actions is evaluate and Engine.enemy_action is action
    with tool.enemy_choice("A"):
        assert enemy_ai.evaluate_actions is evaluate and Engine.enemy_action is action, "today's rule changes nothing"


def test_the_weaker_attack_is_one_less_and_never_less_than_one(tool):
    content = packaged_content()
    engine = Engine(content)
    assert engine.do(cmd.START_RUN, seed=5, party=[{"class_id": "squire", "row": "front"}, {"class_id": "scout", "row": "back"}]).accepted
    goblin = next(foe for foe in enemies(engine) if foe.archetype_id == "goblin")
    usual = (engine.enemy_action(goblin, "slash").power, engine.enemy_action(goblin, "dirty_trick").power)
    its_own = dict(goblin.action_overrides)  # this battle's own numbers for the goblin
    with tool.enemy_choice("A-1"):
        assert engine.enemy_action(goblin, "slash").power == usual[0] - 1 >= 1
        assert engine.enemy_action(goblin, "dirty_trick").power == usual[1], "a status ability keeps its number"
        goblin.action_overrides["dirty_trick"] = {"power": 3}
        assert engine.enemy_action(goblin, "dirty_trick").power == 3, "also when the number is more than 1"
        goblin.action_overrides["slash"] = {"power": 1}
        assert engine.enemy_action(goblin, "slash").power == 1
    goblin.action_overrides = its_own
    assert engine.enemy_action(goblin, "slash").power == usual[0]


def test_each_rule_changes_how_often_enemies_attack_as_it_says(tool):
    party, seeds = ("apprentice", "squire"), (300, 301, 302)
    by_rule = {rule: [tool.attacks_run((rule, party, seed)) for seed in seeds] for rule in ("A", "B", "C", "F")}
    assert share(by_rule["A"]) < share(by_rule["C"]) < share(by_rule["B"])
    assert share(by_rule["A"]) < share(by_rule["F"]) < share(by_rule["B"])
    assert share(by_rule["B"]) > 0.6, "by the weights alone most enemy abilities are attacks"
    # A lone hero either has the status or has not: "while no hero has it" is then today's rule.
    solo = [("squire",), ("scout",)]
    assert [tool.attacks_run(("C", p, 300)) | {"variant": "A"} for p in solo] == [tool.attacks_run(("A", p, 300)) for p in solo]


def test_not_twice_running_looks_at_what_that_enemy_did_last(tool):
    """Rule F at the moments it decides: an enemy whose own last ability was a status has no preference this time;
    one whose own last ability was something else chooses as today, whatever another unit did since."""
    today = enemy_ai.evaluate_actions
    content = packaged_content()
    setup = content.balance["ai"]["priority_setup"]
    seen = {"as today although another unit's last was a status": 0, "no preference after its own status": 0}
    with tool.enemy_choice("F"):
        engine = Engine(content)
        assert engine.do(cmd.START_RUN, seed=300, party=[{"class_id": "apprentice", "row": "back"}, {"class_id": "squire", "row": "front"}]).accepted
        policy = HeuristicPolicy()
        while not engine.finished() and engine.state.encounter_index == 0:
            revealed = [e for e in events_of_this_battle(engine) if e.type == EventType.INTENT_REVEALED]
            for foe in enemies(engine):
                own = [e.delta["category"] for e in revealed if e.actor_id == foe.id]
                if foe.state != "standing" or not own or not revealed:
                    continue
                usual = [(entry["action_id"], entry["priority"]) for entry in today(engine, foe)]
                now = [(entry["action_id"], entry["priority"]) for entry in enemy_ai.evaluate_actions(engine, foe)]
                if not any(priority == setup for _, priority in usual):
                    continue  # nothing to prefer at this moment
                if own[-1] == "status":
                    assert all(priority != setup for _, priority in now) and [a for a, _ in now] == [a for a, _ in usual]
                    seen["no preference after its own status"] += 1
                else:
                    assert now == usual
                    seen["as today although another unit's last was a status"] += revealed[-1].delta["category"] == "status"
            policy.act(engine) if engine.needs_input() else engine.do(cmd.ADVANCE_PHASE)
    assert all(count > 0 for count in seen.values()), seen


def events_of_this_battle(engine: Engine) -> list:
    start = max(position for position, event in enumerate(engine.events) if event.type == EventType.BATTLE_STARTED)
    return engine.events[start:]


def test_the_third_battle_is_measured_for_each_party_with_and_without_a_guardian(tool):
    assert tool.third_parties((1,)) == [("no Guardian", ("apprentice",)), ("no Guardian", ("scout",)), ("no Guardian", ("squire",)),
                                        ("one Guardian", ("guardian",))]
    assert ("one Guardian", ("apprentice", "guardian", "squire")) in tool.third_parties((3,)), "one Squire becomes a Guardian, the other stays"
    run = tool.third_run(("one Guardian", ("guardian",), 300))
    assert run["size"] == 1 and set(run["battles"]) <= {1, 2, 3} and 1 in run["battles"]
    assert run["outcome"] == ("victory" if all(battle["won"] for battle in run["battles"].values()) and len(run["battles"]) == 3 else "defeat")


def test_the_tables_count_only_the_runs_that_entered_a_battle(tool):
    def run(group, party, *won):
        return {"group": group, "size": len(party), "party": party, "seed": 1, "outcome": "victory" if all(won) and len(won) == 3 else "defeat",
                "battles": {number: {"won": w, "activations": 10 * number, "damage_taken": number} for number, w in enumerate(won, start=1)}}
    results = [run("no Guardian", ("squire",), True, True, True), run("no Guardian", ("squire",), True, True, False),
               run("no Guardian", ("squire",), True, False), run("no Guardian", ("scout",), False),
               run("one Guardian", ("guardian",), True, True, True)]
    lines = tool.third_table(results)
    assert lines[1] == "one Guardian | 1 | 1 | 100.0% (1/1) | 100.0% (1/1) | 20 / 30 | 2 / 3"
    assert lines[2] == "no Guardian | 1 | 4 | 66.7% (2/3) | 50.0% (1/2) | 20 / 30 | 2 / 3"
    assert lines[3] == "no Guardian, with a Squire | 1 | 3 | 66.7% (2/3) | 50.0% (1/2) | 20 / 30 | 2 / 3"
    assert lines[4] == "no Guardian, no Squire | 1 | 1 | none entered | none entered | - / - | - / -"


def test_the_command_prints_a_table_for_each_variant(tool, capsys):
    assert tool.main(["attacks", "--first", "300", "--count", "1", "--sizes", "1", "--jobs", "1", "--variants", "A", "B-1"]) == 0
    out = capsys.readouterr().out
    assert "Variant A: today: an ability that puts a status on a hero who has none always comes before an attack\n" in out
    assert "Variant B-1: no preference: every legal ability is drawn by its weight (only a finishing blow comes first). Every enemy attack does 1 less damage" in out
    assert out.count("\nall | 3 | ") == 2
    with pytest.raises(ValueError, match="unknown variant 'Z'"):
        tool.main(["attacks", "--count", "1", "--sizes", "1", "--jobs", "1", "--variants", "A", "Z"])
    assert tool.main(["third", "--first", "300", "--count", "1", "--sizes", "1", "--jobs", "1"]) == 0
    assert "one Guardian | 1 | 1 | " in capsys.readouterr().out
