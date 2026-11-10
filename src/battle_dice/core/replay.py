"""Deterministic replay from seed + content version + command log (section 14.5)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from battle_dice.content.loader import Content
from battle_dice.core.commands import Command
from battle_dice.core.engine import Engine
from battle_dice.core.events import events_hash, state_hash


class ReplayError(RuntimeError):
    pass


def export_run(engine: Engine) -> dict[str, Any]:
    """A self-describing, serialisable record sufficient to reproduce the run exactly."""
    state = engine.state
    return {
        "run_id": state.run_id,
        "seed": str(state.seed),
        "rules_version": state.rules_version,
        "content_version": state.content_version,
        "content_hash": state.content_hash,
        "rng_algorithm": state.rng_algorithm,
        "commands": [c.to_dict() for c in engine.command_log],
        "final_state_hash": state_hash(state),
        "events_hash": events_hash(engine.events),
        "event_count": len(engine.events),
    }


def replay(content: Content, commands: Iterable[Command | dict[str, Any]]) -> Engine:
    """Re-run recorded commands on a fresh engine. Any rejection means the replay diverged."""
    engine = Engine(content)
    for index, raw in enumerate(commands):
        command = raw if isinstance(raw, Command) else Command.from_dict(raw)
        result = engine.submit(command)
        if not result.accepted or result.duplicate:
            raise ReplayError(f"Command {index} ({command.type}) diverged during replay: {result.reason or 'duplicate'}")
    return engine


def verify(content: Content, record: dict[str, Any]) -> Engine:
    """Replay an exported run and check content identity, event hash and final state hash."""
    if record["content_hash"] != content.content_hash:
        raise ReplayError("Content hash differs from the recorded run.")
    engine = replay(content, record["commands"])
    if events_hash(engine.events) != record["events_hash"]:
        raise ReplayError("Event log hash differs from the recorded run.")
    if state_hash(engine.state) != record["final_state_hash"]:
        raise ReplayError("Final state hash differs from the recorded run.")
    return engine
