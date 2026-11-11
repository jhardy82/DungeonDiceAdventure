"""Fixture CE-32: a recorded session replays to the same bytes, whatever the clock says.

Owner decision of 2026-11-11: "as built". A progression event is hashed over the previous event's
hash, its id, its type and the canonical JSON of its payload. Times are stored and are in no hash.

The session is recorded here, on every test run: a hero claims Ranger and changes to it, a run
with the case's seed is started and played through both encounters by the heuristic player, and
the mastery award of each encounter is applied. It is then replayed twice from the record, each
time into a new save file with a different clock.

Until Phase 4 the game does not hand a run's results to the career rules. This test does that
hand-over itself (the party from the heroes' active vocations, an award per hero and encounter),
so what it proves is the determinism of the two parts and of their records, not of the wiring
that does not exist yet.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import sqlite3
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

import battle_dice
from battle_dice.career.catalog import CareerCatalog
from battle_dice.career.model import CareerState, EncounterResult, HeroRecord, MasteryRow, Profile
from battle_dice.career.service import state_view
from battle_dice.career.store import SqliteProfileStore, StoredCareerService, event_hash
from battle_dice.content.loader import canonical_json
from battle_dice.content.vocations import VocationCatalog, load_catalog, load_vocation_catalog
from battle_dice.core import commands as cmd
from battle_dice.core.commands import Command
from battle_dice.core.engine import Engine
from battle_dice.core.events import EventType, events_hash, state_hash
from battle_dice.core.replay import export_run, verify
from battle_dice.sim.policies import HeuristicPolicy
from tests.conftest import packaged_content
from tests.spec.test_class_evolution_rules import CASES

CASE = CASES["CE-32"]
PROFILE, RUN_ID = "profile_demo", "run_0001"
SEED = int(CASE["given"]["recorded_session"]["seed_decimal"])
ZERO_HASH = "0" * 64

#: The career part of the recorded session: what is sent, and what must come back.
CAREER_COMMANDS: list[tuple[dict[str, Any], str | None]] = [
    # Refused: Ranger is not unlocked yet.
    ({"type": "ChangeVocation", "command_id": "cmd-ce32-1", "state_revision": 0,
      "params": {"hero_id": "hero_001", "target_vocation_id": "ranger"}}, "PREREQUISITE_UNMET"),
    ({"type": "ClaimVocation", "command_id": "cmd-ce32-2", "state_revision": 0,
      "params": {"hero_id": "hero_001", "target_vocation_id": "ranger"}}, None),
    # Refused: the claim moved the hero to revision 1.
    ({"type": "ChangeVocation", "command_id": "cmd-ce32-3", "state_revision": 0,
      "params": {"hero_id": "hero_001", "target_vocation_id": "ranger"}}, "REVISION_CONFLICT"),
    ({"type": "ChangeVocation", "command_id": "cmd-ce32-4", "state_revision": 1,
      "params": {"hero_id": "hero_001", "target_vocation_id": "ranger"}}, None),
]
#: Hero of the save -> (the engine's id for it, its row). The Squire stands in front.
PARTY = {"hero_002": ("h01", "front"), "hero_001": ("h02", "back")}


@dataclasses.dataclass
class Played:
    """Everything a replay must reproduce, and the little that may differ."""

    event_rows: list[tuple[Any, ...]]  # the progression event log without its times
    event_times: list[str]
    save_without_times: dict[str, list[tuple[Any, ...]]]
    times_in_save: set[str]
    career_state_hash: str
    run_record: dict[str, Any]
    run_state_hash: str
    run_events_hash: str
    encounters: list[tuple[str, str]]
    rejected_commands: int
    draws_on_rejected_commands: int


@pytest.fixture(scope="module")
def catalog() -> CareerCatalog:
    return CareerCatalog(load_catalog(), packaged_content())


@pytest.fixture(scope="module")
def vocations() -> VocationCatalog:
    return load_vocation_catalog(packaged_content())


def clock_from(start: str) -> Callable[[], str]:
    """A clock that never gives the same time twice: ``start`` is an hour, the calls count minutes and seconds."""
    ticks: Iterator[int] = iter(range(3600))
    return lambda: (lambda n: f"{start}:{n // 60:02d}:{n % 60:02d}Z")(next(ticks))


def new_profile(catalog: CareerCatalog) -> CareerState:
    """Two heroes. The first has mastered Scout, which is what Ranger asks for."""
    state = CareerState(Profile(PROFILE))
    novices = ["squire", "apprentice", "scout"]
    for hero_id, active, mastered in (("hero_001", "scout", "scout"), ("hero_002", "squire", None)):
        mastery = {v: MasteryRow(v) for v in novices}
        if mastered:
            top = catalog.thresholds(mastered)[-1]
            mastery[mastered] = MasteryRow(mastered, catalog.rank_for(mastered, top), top)
        learned = [skill for v, row in mastery.items() for skill in catalog.skills_learned_by(v, row.rank)]
        state.heroes[hero_id] = HeroRecord(hero_id, active, unlocked_vocations=list(novices), mastery=mastery, learned_skills=learned)
    return state


def shipped_encounters(catalog: CareerCatalog) -> dict[int, tuple[str, int]]:
    """Shipped battle number -> (encounter id, threat rating), as the catalog rates them (fixture CE-36)."""
    return {e["shipped_ref"]["battle"]: (e["id"], e["threat_rating"]) for e in catalog.raw["encounters"] if e["source"] == "shipped"}


#: The one row the schema script stamps itself, with SQLite's own clock: the baseline entry of the migration list.
STAMPED_BY_THE_SCRIPT = "schema_migration"


def table_rows(store: SqliteProfileStore) -> tuple[dict[str, list[tuple[Any, ...]]], set[str]]:
    """Every row of the save with its time columns taken out, and the times the store wrote into them."""
    rows: dict[str, list[tuple[Any, ...]]] = {}
    times: set[str] = set()
    tables = [r[0] for r in store.conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
    for table in tables:
        columns = [r[1] for r in store.conn.execute(f"PRAGMA table_info({table})")]
        timed = [index for index, name in enumerate(columns) if name.endswith("_at")]
        rows[table] = []
        for row in store.conn.execute(f"SELECT * FROM {table} ORDER BY rowid"):
            if table != STAMPED_BY_THE_SCRIPT:
                times |= {row[index] for index in timed if row[index] is not None}
            rows[table].append(tuple(value for index, value in enumerate(row) if index not in timed))
    return rows, times


def try_rejected_commands(engine: Engine) -> tuple[int, int]:
    """Send three commands that must be refused. Returns (commands sent, random draws they caused)."""
    before = state_hash(engine.state), engine.revision, len(engine.events), len(engine.command_log)
    draws = {name: stream.draws for name, stream in engine.state.rng.items()}
    results = [
        engine.do(cmd.START_RUN, seed=1, party=[{"class_id": "squire", "row": "front"}]),  # refused by its handler
        engine.do(cmd.SET_ACTION_PLAN, actions=[{"die_id": "no_such_die", "target_ids": []}]),  # by phase or by plan
        engine.submit(Command(cmd.ADVANCE_PHASE, "stale-command", engine.revision - 1, {})),  # refused before any handler
    ]
    assert not any(result.accepted for result in results)
    assert (state_hash(engine.state), engine.revision, len(engine.events), len(engine.command_log)) == before
    drawn = sum(stream.draws - draws[name] for name, stream in engine.state.rng.items())
    return len(results), drawn


def play_session(catalog: CareerCatalog, vocations: VocationCatalog, path: Path, clock: Callable[[], str],
                 recorded_run: list[dict[str, Any]] | None = None) -> Played:
    """The whole session into a new save. The run is played by the heuristic player, or replayed from ``recorded_run``."""
    content = packaged_content()
    store = SqliteProfileStore(path, catalog, clock=clock)
    store.import_state(new_profile(catalog))
    career = StoredCareerService(store, PROFILE)

    for command, refusal in CAREER_COMMANDS:
        file_before, events_before = table_rows(store), len(career.state.events)
        result = career.submit(dict(command))
        assert result.error_code == refusal and result.accepted == (refusal is None), (command["command_id"], result)
        if refusal is not None:  # a rejected command writes nothing
            assert table_rows(store) == file_before and len(career.state.events) == events_before
    assert career.submit(dict(CAREER_COMMANDS[-1][0])).duplicate, "a repeated command id returns the stored result"

    # The hand-over this test does itself: the party is the saved heroes with their active vocations.
    engine = Engine(content, vocations)
    members = sorted(PARTY, key=lambda hero_id: PARTY[hero_id][0])
    party = [{"class_id": career.state.heroes[h].active_vocation_id, "row": PARTY[h][1]} for h in members]
    pending = iter(recorded_run) if recorded_run is not None else None
    if pending is None:
        assert engine.do(cmd.START_RUN, seed=SEED, party=party).accepted
    else:
        first = Command.from_dict(next(pending))
        assert first.type == cmd.START_RUN and first.params["party"] == party and first.params["seed"] == SEED
        assert engine.submit(first).accepted
    career.begin_run(RUN_ID)

    ratings = shipped_encounters(catalog)
    policy, seen_events, battle = HeuristicPolicy(), 0, 0
    encounters: list[tuple[str, str]] = []
    rejected = drawn = 0
    while not engine.finished():
        sent, draws = try_rejected_commands(engine)
        rejected, drawn = rejected + sent, drawn + draws
        if pending is not None:
            replayed = engine.submit(Command.from_dict(next(pending)))
            assert replayed.accepted and not replayed.duplicate, replayed.reason
        elif engine.needs_input():
            policy.act(engine)
        else:
            assert engine.do(cmd.ADVANCE_PHASE).accepted
        for event in engine.events[seen_events:]:
            if event.type == EventType.BATTLE_STARTED:
                battle = event.delta["battle"]
            if event.type in (EventType.BATTLE_WON, EventType.BATTLE_LOST):
                encounter_id, threat = ratings[battle]
                outcome = "victory" if event.type == EventType.BATTLE_WON else "defeat"
                encounters.append((encounter_id, outcome))
                career.state.encounter = EncounterResult(encounter_id, threat, True, outcome)
                for hero_id in members:
                    award = career.award_mastery({
                        "type": "AwardEncounterMastery", "run_id": RUN_ID, "encounter_id": encounter_id, "hero_id": hero_id,
                        "vocation_id": career.state.heroes[hero_id].active_vocation_id, "deployed_at_encounter_start": True})
                    assert award.accepted and not award.duplicate
        seen_events = len(engine.events)
    if pending is not None:
        assert next(pending, None) is None, "the record holds commands after the end of the run"
    assert engine.state.outcome is not None
    career.end_run(RUN_ID, engine.state.outcome)
    store.close()

    # Everything below is read from the file, opened again.
    with SqliteProfileStore(path, catalog, clock=clock) as reopened:
        loaded = StoredCareerService(reopened, PROFILE)
        log = reopened.conn.execute(
            "SELECT event_seq, event_id, run_id, event_type, event_json, previous_event_hash, event_hash, created_at "
            "FROM progression_event_log WHERE profile_id = ? ORDER BY event_seq", (PROFILE,)).fetchall()
        rows, times = table_rows(reopened)
        return Played(
            event_rows=[row[:-1] for row in log],
            event_times=[row[-1] for row in log],
            save_without_times=rows,
            times_in_save=times,
            career_state_hash=hashlib.sha256(canonical_json(state_view(loaded.service)).encode("utf-8")).hexdigest(),
            run_record=export_run(engine),
            run_state_hash=state_hash(engine.state),
            run_events_hash=events_hash(engine.events),
            encounters=encounters,
            rejected_commands=rejected,
            draws_on_rejected_commands=drawn,
        )


@pytest.fixture(scope="module")
def sessions(catalog: CareerCatalog, vocations: VocationCatalog, tmp_path_factory: pytest.TempPathFactory) -> list[Played]:
    """The recording, then the number of replays the case asks for, each with its own clock and file."""
    folder = tmp_path_factory.mktemp("ce32")
    recording = play_session(catalog, vocations, folder / "recording.sqlite", clock_from("2026-11-11T09"))
    replays = [
        play_session(catalog, vocations, folder / f"replay{number}.sqlite", clock_from(f"2031-0{number}-0{number}T1{number}"),
                     recorded_run=recording.run_record["commands"])
        for number in range(1, CASE["when"]["event"]["times"] + 1)
    ]
    return [recording, *replays]


def test_ce32_is_decided_and_names_the_baseline_this_build_has() -> None:
    assert "needs_design_decision" not in CASE and CASE["when"]["event"] == {"type": "ReplayRecordedSession", "times": 2}
    baseline, content = CASE["given"]["baseline"], packaged_content()
    assert baseline["rules_version"] == battle_dice.RULES_VERSION and baseline["content_version"] == content.content_version
    assert (ROOT / baseline["replay_pin"]).is_file()


def test_the_recorded_session_holds_what_the_case_lists(sessions: list[Played], vocations: VocationCatalog) -> None:
    recording = sessions[0]
    assert CASE["given"]["recorded_session"]["includes"] == ["ChangeVocation", "StartRun", "two encounters"]
    types = [row[3] for row in recording.event_rows]
    assert types.count("VocationChanged") == 1 and types.count("VocationClaimed") == 7  # six on import, then Ranger
    run = recording.run_record
    assert run["commands"][0]["type"] == cmd.START_RUN and run["seed"] == str(SEED) and run["rng_algorithm"] == CASE["given"]["baseline"]["rng_algorithm"]
    assert run["commands"][0]["params"]["party"] == [{"class_id": "squire", "row": "front"}, {"class_id": "ranger", "row": "back"}]
    assert run["vocation_catalog"] == {"version": vocations.version, "sha256": vocations.sha256}  # an evolved hero is in the party
    assert recording.encounters == [("training_01", "victory"), ("training_03", "victory")], "two encounters, as the case lists"
    verify(packaged_content(), run)  # the run replays from its record alone


def test_the_awards_of_the_session_follow_the_mastery_rules(sessions: list[Played]) -> None:
    """Battle 1 is threat 1: enough for a Squire at rank 1, too low for a Ranger. Battle 2 is threat 3: enough for both."""
    awards = sessions[0].save_without_times["mastery_award_event"]
    told = [(row[2], row[3], row[5], row[6], row[9]) for row in awards]  # encounter, hero, vocation, base points, denial
    assert told == [
        ("training_01", "hero_002", "squire", 1, None),
        ("training_01", "hero_001", "ranger", 0, "UNDER_THREAT_CAP"),
        ("training_03", "hero_002", "squire", 1, None),
        ("training_03", "hero_001", "ranger", 1, None),
    ], awards
    assert [row[3] for row in sessions[0].event_rows].count("MasteryAwarded") == 3  # a denied award is a row, not an event


def test_ce32_every_replay_reproduces_the_progression_events_byte_for_byte(sessions: list[Played]) -> None:
    recording, *replays = sessions
    assert len(replays) == 2 and len(recording.event_rows) >= 11
    for replay in replays:
        assert canonical_json(replay.event_rows).encode("utf-8") == canonical_json(recording.event_rows).encode("utf-8")
        assert replay.save_without_times == recording.save_without_times, "apart from its times the whole save is the same"
    # The clocks did differ, and the times are stored: the sameness above is not for lack of a difference.
    for one, other in ((0, 1), (0, 2), (1, 2)):
        assert not sessions[one].times_in_save & sessions[other].times_in_save
        assert not set(sessions[one].event_times) & set(sessions[other].event_times)
    # One reading of the clock per write: the import, the two accepted commands, the run, its four awards and its end.
    assert all(len(set(played.event_times)) > 1 and len(played.times_in_save) >= 9 for played in sessions)


def test_ce32_every_replay_ends_in_the_same_state(sessions: list[Played]) -> None:
    recording, *replays = sessions
    for replay in replays:
        assert replay.career_state_hash == recording.career_state_hash
        assert (replay.run_state_hash, replay.run_events_hash) == (recording.run_state_hash, recording.run_events_hash)
        assert replay.run_record == recording.run_record and replay.encounters == recording.encounters
    assert recording.run_record["final_state_hash"] == recording.run_state_hash


def test_ce32_a_rejected_command_draws_no_random_number(sessions: list[Played]) -> None:
    for played in sessions:
        assert played.rejected_commands >= 3 * 100, "three refused commands were tried before every step of the run"
        assert played.draws_on_rejected_commands == 0
    assert len({played.rejected_commands for played in sessions}) > 0


def test_ce32_the_outcome_is_the_one_the_case_states(sessions: list[Played]) -> None:
    recording, *replays = sessions
    measured = {
        "progression_events_byte_identical": all(r.event_rows == recording.event_rows for r in replays),
        "final_state_hash_identical": all(
            (r.career_state_hash, r.run_state_hash) == (recording.career_state_hash, recording.run_state_hash) for r in replays),
        "rng_draws_on_rejected_commands": sum(played.draws_on_rejected_commands for played in sessions),
    }
    assert CASE["then"]["result"] == "accepted" and measured == CASE["then"]["state"]["determinism"]


# --------------------------------------------------------------------------------------------
# The decision itself: what an event hash covers, and how a payload is encoded
# --------------------------------------------------------------------------------------------


def test_an_event_hash_covers_the_chain_the_id_the_type_and_the_canonical_payload(sessions: list[Played]) -> None:
    previous = ZERO_HASH
    for seq, event_id, _run_id, event_type, event_json, stored_previous, stored_hash in sessions[0].event_rows:
        assert event_id == f"{PROFILE}:{seq}" and stored_previous == previous
        text = "\n".join((previous, event_id, event_type, event_json))
        assert stored_hash == hashlib.sha256(text.encode("utf-8")).hexdigest() == event_hash(previous, event_id, event_type, event_json)
        previous = stored_hash


def test_a_payload_is_stored_in_its_canonical_form(sessions: list[Played]) -> None:
    """Sorted keys, no space between tokens, and plain ASCII (any other character is escaped)."""
    for row in sessions[0].event_rows:
        event_json = row[4]
        payload = json.loads(event_json)
        assert event_json == canonical_json(payload) == json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        assert event_json.isascii() and "created_at" not in payload and "time" not in event_json
    assert canonical_json({"b": "é", "a": [1, 2]}) == '{"a":[1,2],"b":"\\u00e9"}'


def test_the_time_of_an_event_is_in_no_hash(sessions: list[Played]) -> None:
    """The same events were written at three different times, and every hash is the same."""
    recording, *replays = sessions
    for replay in replays:
        assert [row[-1] for row in replay.event_rows] == [row[-1] for row in recording.event_rows]  # event_hash
        assert all(a != b for a, b in zip(replay.event_times, recording.event_times, strict=True))


def test_a_saved_event_cannot_be_changed_afterwards(catalog: CareerCatalog, tmp_path: Path) -> None:
    """The log is append only, so neither the payload nor the time of an event can be rewritten."""
    with SqliteProfileStore(tmp_path / "save.sqlite", catalog, clock=clock_from("2026-11-11T09")) as store:
        store.import_state(new_profile(catalog))
        count = store.verify_event_chain(PROFILE)
        assert count == 6  # each hero's three starting vocations
        for column, value in (("created_at", "1999-01-01T00:00:00Z"), ("event_json", "{}"), ("event_hash", ZERO_HASH)):
            with pytest.raises(sqlite3.IntegrityError, match="append only"):
                store.conn.execute(f"UPDATE progression_event_log SET {column} = ? WHERE profile_id = ?", (value, PROFILE))
        assert store.verify_event_chain(PROFILE) == count


def test_a_run_begins_once(catalog: CareerCatalog, tmp_path: Path) -> None:
    store = SqliteProfileStore(tmp_path / "save.sqlite", catalog, clock=clock_from("2026-11-11T09"))
    store.import_state(new_profile(catalog))
    career = StoredCareerService(store, PROFILE)
    career.begin_run(RUN_ID)
    assert career.state.run is not None and (career.state.run.run_id, career.state.run.phase) == (RUN_ID, "battle")
    with pytest.raises(ValueError, match="still being played"):
        career.begin_run("run_0002")
    career.end_run(RUN_ID, "defeat")
    with pytest.raises(ValueError, match="used once"):
        career.begin_run(RUN_ID)
    career.begin_run("run_0002")
    assert StoredCareerService(store, PROFILE).state.run == career.state.run  # and it is in the file
    store.close()


ROOT = Path(__file__).resolve().parents[2]
