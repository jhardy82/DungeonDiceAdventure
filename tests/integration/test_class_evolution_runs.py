"""Class Evolution Phase 1, end to end: runs with the vocation catalog handed to the engine.

Two claims are checked. With the gate on and only shipped classes in the party, a run is byte for
byte the run the game has always produced (fixtures CE-01 and CE-40). With an evolved hero in the
party, the run plays to an outcome under the same invariants and replays exactly from its record.
"""

from __future__ import annotations

import copy
import json

import pytest

from battle_dice.content.vocations import VocationCatalog, load_vocation_catalog
from battle_dice.core import commands as cmd
from battle_dice.core.engine import Engine
from battle_dice.core.events import events_hash, state_hash, write_jsonl
from battle_dice.core.replay import ReplayError, export_run, replay, verify, verify_log
from battle_dice.sim.policies import HeuristicPolicy, RandomPolicy, play_run
from battle_dice.sim.runner import simulate
from tests.conftest import packaged_content
from tests.integration.test_full_runs import play_checked

PARTIES_WITH_A_RANGER = [
    [("ranger", "back")],
    [("squire", "front"), ("ranger", "back")],
    [("squire", "front"), ("apprentice", "back"), ("ranger", "back")],
    [("ranger", "front"), ("ranger", "back"), ("scout", "back"), ("squire", "front")],
]


@pytest.fixture(scope="module")
def catalog() -> VocationCatalog:
    return load_vocation_catalog(packaged_content())


def started(catalog: VocationCatalog | None, seed: int, members: list[tuple[str, str]]) -> Engine:
    engine = Engine(packaged_content(), catalog)
    result = engine.do(cmd.START_RUN, seed=seed, party=[{"class_id": c, "row": r} for c, r in members])
    assert result.accepted, result.reason
    return engine


# --------------------------------------------------------------------------------------------
# Gate on, shipped classes: nothing changes
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("seed", "members"),
    [
        (1, [("squire", "front"), ("apprentice", "back"), ("scout", "back")]),
        (2, [("scout", "back")]),
        (3, [("squire", "front"), ("squire", "front"), ("apprentice", "back"), ("scout", "back"), ("scout", "back")]),
    ],
)
def test_with_the_gate_on_a_party_of_shipped_classes_plays_the_identical_run(catalog, seed, members):
    """The three pinned parties: same events, same final state, same exported record."""
    plain, gated = started(None, seed, members), started(catalog, seed, members)
    assert play_run(plain, HeuristicPolicy()) == play_run(gated, HeuristicPolicy())
    assert events_hash(gated.events) == events_hash(plain.events)
    assert state_hash(gated.state) == state_hash(plain.state)
    record = export_run(gated)
    assert record == export_run(plain) and "vocation_catalog" not in record
    verify(packaged_content(), record)  # and it replays without the catalog


# --------------------------------------------------------------------------------------------
# Gate on, an evolved hero in the party
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(8))
def test_a_party_with_a_ranger_plays_to_an_outcome_with_every_invariant_held(catalog, seed):
    members = PARTIES_WITH_A_RANGER[seed % len(PARTIES_WITH_A_RANGER)]
    policy = HeuristicPolicy() if seed % 2 == 0 else RandomPolicy(seed)
    engine = started(catalog, seed, members)
    assert play_checked(engine, policy) in ("victory", "defeat")
    assert {engine.build(h.id).vocation_id for h in engine.combat.side("hero")} >= {"ranger"}


def test_a_run_with_a_ranger_replays_exactly_from_its_record(catalog):
    content = packaged_content()
    engine = started(catalog, 5, PARTIES_WITH_A_RANGER[2])
    play_run(engine, HeuristicPolicy())
    record = json.loads(json.dumps(export_run(engine)))  # as it would come back from a file
    assert record["vocation_catalog"] == {"version": catalog.version, "sha256": catalog.sha256}

    again = verify(content, record, catalog)
    assert events_hash(again.events) == record["events_hash"] and state_hash(again.state) == record["final_state_hash"]
    verify(content, record)  # the packaged catalog is loaded when none is given

    with pytest.raises(ReplayError, match="diverged"):
        replay(content, record["commands"])  # without the catalog the first command is an unknown class
    tampered = copy.deepcopy(record)
    tampered["vocation_catalog"]["sha256"] = "0" * 64
    with pytest.raises(ReplayError, match="vocation catalog differs"):
        verify(content, tampered, catalog)


def test_a_log_file_of_a_run_with_a_ranger_verifies_on_its_own(tmp_path, catalog):
    engine = started(catalog, 6, PARTIES_WITH_A_RANGER[1])
    play_run(engine, HeuristicPolicy())
    header = export_run(engine)
    header["command_count"] = len(engine.command_log)
    path = tmp_path / "run.jsonl"
    write_jsonl(path, header, engine.events)
    summary = verify_log(packaged_content(), path)
    assert summary["outcome"] == engine.state.outcome and summary["events"] == len(engine.events)
    first_event = json.loads(path.read_text(encoding="utf-8").splitlines()[1])
    assert first_event["delta"]["vocation_catalog"]["sha256"] == catalog.sha256


def test_the_simulator_plays_a_party_with_an_evolved_hero(catalog):
    content = packaged_content()
    first = simulate(content, 9, ["squire", "ranger"], HeuristicPolicy(), vocations=catalog, rows=["front", "back"])
    second = simulate(content, 9, ["squire", "ranger"], HeuristicPolicy(), vocations=catalog, rows=["front", "back"])
    assert first == second and first["outcome"] in ("victory", "defeat")
    with pytest.raises(RuntimeError, match="Unknown class 'ranger'"):
        simulate(content, 9, ["squire", "ranger"], HeuristicPolicy(), rows=["front", "back"])
