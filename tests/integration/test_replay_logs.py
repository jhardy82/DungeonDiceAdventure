"""A finished run's log file is enough to replay it (PRD 14.5), and replays do not drift (AC-18)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from battle_dice import RULES_VERSION
from battle_dice.app.controller import AppController, Screen
from battle_dice.core import replay
from battle_dice.core.events import events_hash, state_hash
from battle_dice.replay_cli import main as replay_main
from battle_dice.sim.policies import POLICY_VERSION, HeuristicPolicy

ROOT = Path(__file__).resolve().parents[2]
PIN = json.loads((ROOT / "tests" / "golden" / "replay_pin.json").read_text(encoding="utf-8"))


def finished_run(tmp_path, seed=5, party=("squire", "apprentice", "scout")) -> AppController:
    """Play a whole run the way the application does and let the controller write its log."""
    controller = AppController(fixed_seed=seed, log_dir=tmp_path / "logs")
    controller.new_run()
    for class_id in party:
        controller.add_hero(class_id)
    controller.begin_run()
    engine, policy = controller.engine, HeuristicPolicy()
    assert engine is not None
    while not engine.finished():
        if engine.needs_input():
            policy.act(engine)
        else:
            engine.do("AdvancePhase")
    controller.refresh()
    assert controller.screen == Screen.OUTCOME and controller.log_path is not None, controller.log_error
    return controller


def log_of(controller) -> Path:
    """The run log the controller wrote."""
    assert controller.log_path is not None, controller.log_error
    return controller.log_path


def rewrite(path: Path, change) -> Path:
    """Copy a log with one record changed by ``change(records)``."""
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    change(records)
    target = path.with_name("changed-" + path.name)
    target.write_text("".join(json.dumps(record, sort_keys=True) + "\n" for record in records), encoding="utf-8")
    return target


def test_the_log_file_alone_replays_the_run_exactly(tmp_path):
    controller = finished_run(tmp_path)
    engine = controller.engine
    header, events = replay.read_log(log_of(controller))
    assert header["command_count"] == len(header["commands"]) == len(engine.command_log)
    assert len(events) == len(engine.events)
    result = replay.verify_log(controller.content, log_of(controller))
    assert result == {
        "run_id": engine.state.run_id,
        "seed": str(engine.state.seed),
        "outcome": engine.state.outcome,
        "commands": len(engine.command_log),
        "events": len(engine.events),
    }


def test_a_changed_event_line_is_detected(tmp_path):
    controller = finished_run(tmp_path)

    def change(records):
        event = next(r for r in records if r["record"] == "event" and r["type"] == "dice_rolled")
        event["delta"]["face"] = event["delta"]["face"] % event["delta"]["die_size"] + 1

    with pytest.raises(replay.ReplayError, match=r"Event \d+ in the file differs"):
        replay.verify_log(controller.content, rewrite(log_of(controller), change))


def test_a_changed_command_is_detected(tmp_path):
    controller = finished_run(tmp_path)

    def change(records):
        start = records[0]["commands"][0]
        start["params"]["seed"] = int(start["params"]["seed"]) + 1

    with pytest.raises(replay.ReplayError):
        replay.verify_log(controller.content, rewrite(log_of(controller), change))


def test_a_missing_event_line_is_detected(tmp_path):
    controller = finished_run(tmp_path)
    with pytest.raises(replay.ReplayError, match="events but the replay produced"):
        replay.verify_log(controller.content, rewrite(log_of(controller), lambda records: records.pop()))


def test_logs_from_other_rules_or_without_commands_say_so(tmp_path):
    controller = finished_run(tmp_path)
    old_rules = rewrite(log_of(controller), lambda records: records[0].__setitem__("rules_version", "0.9.0"))
    with pytest.raises(replay.ReplayError, match=f"written by rules 0.9.0; this build is rules {RULES_VERSION}"):
        replay.verify_log(controller.content, old_rules)
    no_commands = rewrite(log_of(controller), lambda records: records[0].pop("commands"))
    with pytest.raises(replay.ReplayError, match="before commands were recorded"):
        replay.verify_log(controller.content, no_commands)
    other_content = rewrite(log_of(controller), lambda records: records[0].__setitem__("content_hash", "0" * 64))
    with pytest.raises(replay.ReplayError, match="Content hash differs"):
        replay.verify_log(controller.content, other_content)
    garbage = controller.log_path.with_name("garbage.jsonl")
    garbage.write_text("not json\n", encoding="utf-8")
    with pytest.raises(replay.ReplayError, match="Line 1 is not valid JSON"):
        replay.verify_log(controller.content, garbage)


def test_the_replay_command_reports_each_log_and_sets_the_exit_code(tmp_path, capsys):
    good = log_of(finished_run(tmp_path))
    assert replay_main([str(good)]) == 0
    assert capsys.readouterr().out.startswith("OK")
    bad = rewrite(good, lambda records: records.pop())
    assert replay_main([str(good), str(bad), str(tmp_path / "missing.jsonl")]) == 1
    lines = capsys.readouterr().out.splitlines()
    assert [line.split()[0] for line in lines] == ["OK", "FAILED", "FAILED"]


def test_retry_after_a_finished_run_starts_clean(tmp_path):
    """AC-16 restart: the upgrade, the swap and every die change belong to one run only."""
    controller = finished_run(tmp_path)
    first = controller.engine
    assert first.state.upgrades, "the first run applied its mandatory upgrade"
    controller.retry_same_party()
    fresh = controller.engine
    assert fresh is not first and controller.screen == Screen.BATTLE
    assert fresh.state.encounter_index == 0 and fresh.state.upgrades == [] and fresh.state.die_overrides == {}
    assert fresh.state.swaps_used == {}
    for hero in fresh.combat.side("hero"):
        base = controller.content.class_def(hero.archetype_id)
        assert hero.equipped_dice_ids == base["starting_dice"]
        assert (hero.hp, hero.mana, hero.corruption) == (base["start_hp"], base["start_mana"], base["start_corruption"])
        for die_id in hero.equipped_dice_ids:
            assert fresh.die_for(hero.id, die_id) is controller.content.die(die_id), "no upgraded die carried over"
    assert controller.log_path is None, "the new run has not written a log yet"


# --------------------------------------------------------------------------------------------
# Pinned runs: the same seed must give the same run on every platform and in every later build
# --------------------------------------------------------------------------------------------


def _pin_tool():
    spec = importlib.util.spec_from_file_location("update_replay_pin", ROOT / "tools" / "update_replay_pin.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_pin_was_made_for_this_rules_and_content_version(content):
    assert (PIN["rules_version"], PIN["content_version"], PIN["content_hash"]) == (
        RULES_VERSION, content.content_version, content.content_hash,
    ), "rules or content changed: run tools/update_replay_pin.py if that was intended"
    assert PIN["policy_version"] == POLICY_VERSION, (
        "the scripted player that plays the pinned runs changed: run tools/update_replay_pin.py if that was intended"
    )


@pytest.mark.parametrize("pinned", PIN["runs"], ids=[f"seed{run['seed']}-{len(run['party'])}heroes" for run in PIN["runs"]])
def test_pinned_runs_reproduce_exactly(pinned):
    produced = _pin_tool().play(pinned["seed"], pinned["party"])
    assert produced == pinned, (
        "A fixed-seed run no longer matches its recorded hashes. If rules or content changed on purpose, "
        "run tools/update_replay_pin.py; otherwise this is unintended drift."
    )


def test_the_pin_covers_both_outcomes_or_at_least_a_full_victory():
    assert any(run["outcome"] == "victory" for run in PIN["runs"])
    assert all(len(run["events_hash"]) == 64 and len(run["final_state_hash"]) == 64 for run in PIN["runs"])
    assert events_hash([]) != PIN["runs"][0]["events_hash"] and callable(state_hash)
