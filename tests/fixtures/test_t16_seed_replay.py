"""T16_seed_replay: identical inputs and seed produce an identical event sequence and final hash."""

import json

import pytest

from battle_dice.core import commands as cmd
from battle_dice.core.commands import Command
from battle_dice.core.events import events_hash, state_hash, write_jsonl
from battle_dice.core.replay import ReplayError, export_run, replay, verify
from battle_dice.sim.policies import HeuristicPolicy, RandomPolicy, play_run
from tests.conftest import start

PARTY = ("squire", "apprentice", "scout")


def _played(seed, policy=None):
    engine = start(*PARTY, seed=seed)
    play_run(engine, policy or HeuristicPolicy())
    return engine


def test_t16_replaying_the_command_log_reproduces_events_and_final_state(content):
    original = _played(424242)
    record = export_run(original)
    assert record["seed"] == "424242" and record["rng_algorithm"] == "BD-PCG32-v1"
    json.loads(json.dumps(record))  # the record is plain JSON

    replayed = verify(content, record)
    assert [e.to_dict() for e in replayed.events] == [e.to_dict() for e in original.events]
    assert state_hash(replayed.state) == state_hash(original.state) == record["final_state_hash"]
    assert events_hash(replayed.events) == record["events_hash"]
    assert replayed.state.outcome == original.state.outcome


def test_t16_repeated_headless_runs_are_identical():
    first, second = _played(7), _played(7)
    assert events_hash(first.events) == events_hash(second.events)
    assert state_hash(first.state) == state_hash(second.state)
    assert [c.to_dict() for c in first.command_log] == [c.to_dict() for c in second.command_log]
    random_a, random_b = _played(7, RandomPolicy(3)), _played(7, RandomPolicy(3))
    assert events_hash(random_a.events) == events_hash(random_b.events)


def test_t16_a_different_seed_or_input_changes_the_log():
    base = _played(7)
    assert events_hash(_played(8).events) != events_hash(base.events)
    assert events_hash(_played(7, RandomPolicy(3)).events) != events_hash(base.events)


def test_t16_events_are_sequenced_and_rng_draws_are_recorded():
    engine = _played(31)
    assert [e.seq for e in engine.events] == list(range(1, len(engine.events) + 1))
    ticks = [e.tick for e in engine.events if e.type == "activation_started"]
    drawn = [e for e in engine.events if e.rng_stream is not None]
    assert {e.rng_stream for e in drawn} == {"dice", "enemy", "rewards"}
    for stream in ("dice", "enemy"):
        indices = [e.rng_draw_index for e in drawn if e.rng_stream == stream]
        assert indices == sorted(indices) and len(set(indices)) == len(indices)
    assert ticks  # battles restart their tick counter, so ticks are only monotonic within a battle
    started = engine.events[0].delta
    assert started["seed"] == "31" and started["content_hash"] == engine.content.content_hash


def test_t16_replay_detects_divergence(content):
    original = _played(5)
    record = export_run(original)
    tampered = dict(record, commands=[dict(c) for c in record["commands"]])
    tampered["commands"][0] = dict(tampered["commands"][0], params=dict(tampered["commands"][0]["params"], seed=6))
    with pytest.raises(ReplayError):
        verify(content, tampered)
    with pytest.raises(ReplayError):
        verify(content, dict(record, content_hash="0" * 64))
    with pytest.raises(ReplayError):
        replay(content, [Command(cmd.ROLL_DICE, "x", 0)])


def test_t16_jsonl_log_is_machine_readable_and_byte_stable(tmp_path):
    first, second = _played(11), _played(11)
    paths = []
    for index, engine in enumerate((first, second)):
        path = tmp_path / f"run{index}.jsonl"
        header = {k: v for k, v in export_run(engine).items() if k != "commands"}
        write_jsonl(path, header, engine.events)
        paths.append(path)
    assert paths[0].read_bytes() == paths[1].read_bytes()
    lines = paths[0].read_text(encoding="utf-8").splitlines()
    header = json.loads(lines[0])
    assert header["record"] == "header" and header["seed"] == "11" and header["event_count"] == len(first.events)
    events = [json.loads(line) for line in lines[1:]]
    assert len(events) == len(first.events)
    assert set(events[0]) == {"record", "seq", "tick", "actor_id", "type", "intent_id", "before", "delta", "after", "rng_stream", "rng_draw_index"}
