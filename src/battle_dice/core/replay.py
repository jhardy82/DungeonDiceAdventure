"""Deterministic replay from seed + content version + command log (section 14.5)."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from battle_dice import RULES_VERSION
from battle_dice.content.loader import Content, canonical_json
from battle_dice.core.build import BuildSource
from battle_dice.core.commands import Command
from battle_dice.core.engine import Engine
from battle_dice.core.events import events_hash, state_hash, to_plain


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
        # Only a run with an evolved hero names the vocation catalog; every other record is unchanged.
        **({"vocation_catalog": engine.vocation_catalog_pin} if engine.vocation_catalog_pin is not None else {}),
    }


def replay(content: Content, commands: Iterable[Command | dict[str, Any]], vocations: BuildSource | None = None) -> Engine:
    """Re-run recorded commands on a fresh engine. Any rejection means the replay diverged."""
    engine = Engine(content, vocations)
    for index, raw in enumerate(commands):
        command = raw if isinstance(raw, Command) else Command.from_dict(raw)
        result = engine.submit(command)
        if not result.accepted or result.duplicate:
            raise ReplayError(f"Command {index} ({command.type}) diverged during replay: {result.reason or 'duplicate'}")
    return engine


def verify(content: Content, record: dict[str, Any], vocations: BuildSource | None = None) -> Engine:
    """Replay an exported run and check content identity, event hash and final state hash.

    A run with an evolved hero names the vocation catalog it used; ``vocations`` must then be that
    catalog. When it is not given, the packaged catalog is loaded.
    """
    if record["content_hash"] != content.content_hash:
        raise ReplayError("Content hash differs from the recorded run.")
    pinned = record.get("vocation_catalog")
    if pinned is not None:
        if vocations is None:
            from battle_dice.content.vocations import (
                load_vocation_catalog,  # only a Class Evolution run needs it
            )

            vocations = load_vocation_catalog(content)
        if vocations.sha256 != pinned["sha256"]:
            raise ReplayError("The vocation catalog differs from the recorded run.")
    engine = replay(content, record["commands"], vocations)
    if events_hash(engine.events) != record["events_hash"]:
        raise ReplayError("Event log hash differs from the recorded run.")
    if state_hash(engine.state) != record["final_state_hash"]:
        raise ReplayError("Final state hash differs from the recorded run.")
    return engine


def read_log(path: str | Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Read a JSONL run log: the header record and the event records, in file order."""
    header: dict[str, Any] | None = None
    events: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as error:
                raise ReplayError(f"Line {number} is not valid JSON: {error.msg}.") from error
            record = entry.pop("record", None)
            if record == "header" and header is None:
                header = entry
            elif record == "event":
                events.append(entry)
            else:
                raise ReplayError(f"Line {number} is neither the header nor an event.")
    if header is None:
        raise ReplayError("The file has no header line.")
    return header, events


def verify_log(content: Content, path: str | Path, vocations: BuildSource | None = None) -> dict[str, Any]:
    """Replay a finished run from its log file alone and check that it reproduces exactly.

    Checks, in order: the log carries its commands; it was written by this rules version and
    this content; replaying the commands gives the recorded event hash and final state hash;
    and every event line in the file equals the replayed event.
    """
    header, logged = read_log(path)
    if "commands" not in header:
        raise ReplayError("This log was written before commands were recorded, so it cannot be replayed.")
    if header.get("rules_version") != RULES_VERSION:
        raise ReplayError(f"The log was written by rules {header.get('rules_version')}; this build is rules {RULES_VERSION}.")
    engine = verify(content, header, vocations)
    replayed = [to_plain(event) for event in engine.events]
    if len(logged) != len(replayed):
        raise ReplayError(f"The file has {len(logged)} events but the replay produced {len(replayed)}.")
    for index, (written, produced) in enumerate(zip(logged, replayed, strict=True)):
        if canonical_json(written) != canonical_json(produced):
            raise ReplayError(f"Event {index + 1} in the file differs from the replayed event.")
    return {
        "run_id": header.get("run_id"),
        "seed": header.get("seed"),
        "outcome": engine.state.outcome,
        "commands": len(header["commands"]),
        "events": len(replayed),
    }
