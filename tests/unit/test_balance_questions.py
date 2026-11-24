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
    with pytest.raises(RuntimeError), tool.enemy_choice("O-1"):
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
    """"A" is the game as it is (since rules 1.2.0: never a status twice running); "O" is the rule before."""
    party, seeds = ("apprentice", "squire"), (300, 301, 302)
    by_rule = {rule: [tool.attacks_run((rule, party, seed)) for seed in seeds] for rule in ("A", "O", "B", "C")}
    assert share(by_rule["O"]) < share(by_rule["A"]) < share(by_rule["B"])
    assert share(by_rule["O"]) < share(by_rule["C"]) < share(by_rule["B"])
    assert share(by_rule["B"]) > 0.6, "by the weights alone most enemy abilities are attacks"
    # A lone hero either has the status or has not: "while no hero has it" is then the rule of before.
    solo = [("squire",), ("scout",)]
    assert [tool.attacks_run(("C", p, 300)) | {"variant": "O"} for p in solo] == [tool.attacks_run(("O", p, 300)) for p in solo]


def test_the_rule_of_before_can_still_be_measured(tool):
    """Under "O" an enemy whose last ability was a status prefers a status again; under "A" it does not."""
    content = packaged_content()
    setup = content.balance["ai"]["priority_setup"]
    engine = Engine(content)
    assert engine.do(cmd.START_RUN, seed=5, party=[{"class_id": "squire", "row": "front"}, {"class_id": "scout", "row": "back"}]).accepted
    goblin = next(foe for foe in enemies(engine) if foe.archetype_id == "goblin")
    goblin.last_category = "status"
    today = {entry["action_id"]: entry["priority"] for entry in enemy_ai.evaluate_actions(engine, goblin)}
    with tool.enemy_choice("O"):
        before = {entry["action_id"]: entry["priority"] for entry in enemy_ai.evaluate_actions(engine, goblin)}
        assert goblin.last_category == "status", "the look back is put back"
    assert today["dirty_trick"] != setup and before["dirty_trick"] == setup and today["slash"] == before["slash"]


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
    assert "Variant A: today: a status on a hero who has none comes before an attack, but never twice running\n" in out
    assert "Variant B-1: no preference: every legal ability is drawn by its weight (only a finishing blow comes first). Every enemy attack does 1 less damage" in out
    assert out.count("\nall | 3 | ") == 2
    with pytest.raises(ValueError, match="unknown variant 'Z'"):
        tool.main(["attacks", "--count", "1", "--sizes", "1", "--jobs", "1", "--variants", "A", "Z"])
    assert tool.main(["third", "--first", "300", "--count", "1", "--sizes", "1", "--jobs", "1"]) == 0
    assert "one Guardian | 1 | 1 | " in capsys.readouterr().out


# --------------------------------------------------------------------------------------------
# The order of the heroes (D-37)
# --------------------------------------------------------------------------------------------


def test_every_order_of_every_party_is_played(tool):
    assert tool.ordered_parties((1,)) == [("apprentice",), ("scout",), ("squire",)]
    pairs = tool.ordered_parties((2,))
    assert len(pairs) == 9 and ("squire", "apprentice") in pairs and ("apprentice", "squire") in pairs
    assert len(tool.ordered_parties((1, 2, 3, 4, 5))) == 3 + 9 + 27 + 81 + 243


def runs_of(party, won, lost):
    return [{"size": len(party), "party": list(party), "won": True}] * won + [{"size": len(party), "party": list(party), "won": False}] * lost


def test_a_place_is_compared_inside_the_same_party(tool):
    """Squire first wins 30 of 40, the same two heroes with the Squire last 20 of 40: ten points for the place."""
    results = runs_of(("squire", "scout"), 30, 10) + runs_of(("scout", "squire"), 20, 20)
    first = tool.place_effect(results, 2, "squire", 0)
    last = tool.place_effect(results, 2, "squire", -1)
    assert first is not None and last is not None
    assert first[0] == pytest.approx(25.0) and last[0] == pytest.approx(-25.0) and first[2] == last[2] == 1
    # One standard error of the difference of two shares of 40 runs each.
    assert first[1] == pytest.approx(100 * (0.75 * 0.25 / 40 + 0.5 * 0.5 / 40) ** 0.5)
    # A party of one class has no order, and a class that is not there has no place.
    same = runs_of(("squire", "squire"), 5, 5)
    assert tool.place_effect(same, 2, "squire", 0) is None and tool.place_effect(results, 2, "apprentice", 0) is None
    assert tool.place_effect(results, 3, "squire", 0) is None
    # Another party of the same size is compared for itself and the two differences are averaged, not pooled.
    more = results + runs_of(("squire", "apprentice"), 10, 30) + runs_of(("apprentice", "squire"), 10, 30)
    both = tool.place_effect(more, 2, "squire", 0)
    assert both is not None and both[0] == pytest.approx(12.5) and both[2] == 2


def test_the_order_table_gives_each_class_first_and_last_with_its_uncertainty(tool, tmp_path, capsys):
    results = runs_of(("squire", "scout"), 30, 10) + runs_of(("scout", "squire"), 20, 20)
    lines = tool.order_table(results)
    assert lines[2] == "2 | scout | -25.0 ± 10.5 | +25.0 ± 10.5 | 1" and lines[3] == "2 | squire | +25.0 ± 10.5 | -25.0 ± 10.5 | 1"
    assert "one standard error" in lines[1] and len(lines) == 4
    out = tmp_path / "runs.json"
    assert tool.main(["order", "--first", "300", "--count", "1", "--sizes", "2", "--jobs", "1", "--out", str(out)]) == 0
    assert "2 | squire | " in capsys.readouterr().out
    import json
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert len(saved) == 9 and {tuple(run["party"]) for run in saved} == set(tool.ordered_parties((2,)))
