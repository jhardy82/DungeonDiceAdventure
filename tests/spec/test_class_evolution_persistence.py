"""Class Evolution FDD v0.2: the persistence contract and the acceptance fixtures.

Specification tests. Nothing here runs the game's rules: the tests execute the proposed schema in
an in-memory SQLite database and check the documents under ``docs/class_evolution``.

* The schema creates the documented tables and refuses what the v0.1 review found it accepting
  (one test per constraint, each showing the statement that must fail).
* The example profile loads.
* The claim transaction is atomic, idempotent on the command id and paid per hero.
* The documented profile reset leaves nothing behind.
* The 40 acceptance fixtures match their schema and the one error-code registry.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import re
import sqlite3
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import jsonschema
import pytest

from battle_dice.career import model as career_model
from battle_dice.core import commands as game_commands
from battle_dice.core import planning
from battle_dice.core.models import RunPhase

ROOT = Path(__file__).resolve().parents[2]
PERSISTENCE = ROOT / "docs" / "class_evolution" / "persistence"
FIXTURES_DIR = ROOT / "docs" / "class_evolution" / "fixtures"
DDL_PATH = ROOT / "src" / "battle_dice" / "career" / "schema" / "progression.sql"
TS = "2026-11-02T10:00:00Z"
HASH_A = "a" * 64
PROFILE = "profile_demo"
HERO = "hero_001"
OTHER_HERO = "hero_002"
RUN = "run_demo"
CATALOG = "1.3.1"

#: The tables of schema version 2: the 21 tables of v0.1 and the three added in v0.2.
V01_TABLES = [
    "content_catalog",
    "encounter_build_snapshot",
    "hero",
    "hero_equipped_die",
    "hero_equipped_skill",
    "hero_permanent_upgrade",
    "hero_skill",
    "hero_vocation_mastery",
    "hero_vocation_unlock",
    "item_consumption",
    "mastery_award_event",
    "player_profile",
    "processed_command",
    "profile_item_balance",
    "profile_vocation_discovery",
    "progression_event_log",
    "quest_completion",
    "run",
    "run_die_upgrade",
    "skill_def",
    "vocation_def",
]
ADDED_TABLES = ["hero_die_instance", "item_grant", "schema_migration"]

#: Decided by the owner on 2026-11-11 and no longer in this set: CE-01 (where the gate lives); CE-10,
#: CE-19, CE-24, CE-28 and CE-39 (progression rules); CE-18, CE-25, CE-35 and CE-40 (dice, saving, run start);
#: CE-09, CE-29, CE-30, CE-32 and CE-36 (the career tree, plan codes, hashes, available encounters).
#: CE-31 (what Duelist's Parry does) waits for the Duelist's wave.
NEEDS_DESIGN_DECISION = {31}
BASELINE_DEFINITION = (
    "With the feature gate off, the replay pin tests/golden/replay_pin.json reproduces byte for byte."
)


def _load_tool() -> ModuleType:
    name = "class_evolution_check_persistence"
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "tools" / "class_evolution" / "check_persistence.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


tool = _load_tool()
sys.path.insert(0, str(ROOT / "tools"))

from class_evolution import validate_catalog as catalog_tool  # noqa: E402


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


EXAMPLE = _read_json(PERSISTENCE / "example_profile.json")
REGISTRY = _read_json(PERSISTENCE / "error_codes.json")
FIXTURES = _read_json(FIXTURES_DIR / "acceptance_fixtures.json")
FIXTURE_SCHEMA = _read_json(FIXTURES_DIR / "acceptance_fixtures.schema.json")
REGISTRY_CODES = [entry["code"] for entry in REGISTRY["codes"]]


# --------------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------------


@pytest.fixture
def db() -> Iterator[sqlite3.Connection]:
    """An empty database with the v0.2 schema."""
    conn = tool.create_database()
    yield conn
    conn.close()


@pytest.fixture
def loaded(db: sqlite3.Connection) -> sqlite3.Connection:
    """The database with the example profile: hero_001 can claim Dragon Knight with one drake_scale."""
    tool.load_example(db, copy.deepcopy(EXAMPLE))
    return db


def scalar(conn: sqlite3.Connection, sql: str, *values: Any) -> Any:
    return conn.execute(sql, values).fetchone()[0]


def dump(conn: sqlite3.Connection) -> dict[str, list[tuple[Any, ...]]]:
    """Every row of every table, to compare the database before and after a statement."""
    return {
        table: sorted(conn.execute(f"SELECT * FROM {table}").fetchall(), key=repr)
        for table in tool.table_names(conn)
    }


def add_event(
    conn: sqlite3.Connection, event_type: str = "VocationMastered", profile_id: str = PROFILE
) -> str:
    conn.execute("BEGIN IMMEDIATE")
    event_id: str = tool.append_event(
        conn, profile_id=profile_id, event_type=event_type, payload={"note": "test"}, created_at=TS
    )
    conn.execute("COMMIT")
    return event_id


def add_hero(
    conn: sqlite3.Connection,
    hero_id: str = OTHER_HERO,
    profile_id: str = PROFILE,
    eligibility_state: str = "eligible",
) -> None:
    conn.execute(
        "INSERT INTO hero(hero_id, profile_id, catalog_version, origin_vocation_id, active_vocation_id, "
        "display_name, eligibility_state, created_at) VALUES (?, ?, ?, 'squire', 'squire', ?, ?, ?)",
        (hero_id, profile_id, CATALOG, hero_id, eligibility_state, TS),
    )


def add_profile(conn: sqlite3.Connection, profile_id: str) -> None:
    conn.execute(
        "INSERT INTO player_profile(profile_id, current_catalog_version, created_at) VALUES (?, ?, ?)",
        (profile_id, CATALOG, TS),
    )


def add_run(conn: sqlite3.Connection, run_id: str, phase: str = "battle", **overrides: Any) -> None:
    row: dict[str, Any] = {
        "run_id": run_id,
        "profile_id": PROFILE,
        "catalog_version": CATALOG,
        "content_sha256": EXAMPLE["catalog"]["content_sha256"],
        "rules_version": "1.1.1",
        "rng_version": "BD-PCG32-v1",
        "seed_decimal": "7",
        "build_sha256": HASH_A,
        "phase": phase,
        "started_at": TS,
        "completed_at": TS if phase in ("victory", "defeat") else None,
    }
    row.update(overrides)
    columns = ", ".join(row)
    conn.execute(f"INSERT INTO run({columns}) VALUES ({', '.join('?' for _ in row)})", list(row.values()))


def add_award(
    conn: sqlite3.Connection,
    base: int,
    challenge: int,
    denial: str | None,
    encounter_id: str = "training_04",
    run_id: str = RUN,
) -> None:
    conn.execute(
        "INSERT INTO mastery_award_event(event_id, run_id, encounter_id, hero_id, catalog_version, vocation_id, "
        "base_points, challenge_points, threat_rating, denial_reason, created_at) "
        "VALUES (?, ?, ?, ?, ?, 'champion', ?, ?, 4, ?, ?)",
        (f"award:{run_id}:{encounter_id}", run_id, encounter_id, HERO, CATALOG, base, challenge, denial, TS),
    )


def claim(conn: sqlite3.Connection, **overrides: Any) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "profile_id": PROFILE,
        "hero_id": HERO,
        "target_vocation_id": "dragon_knight",
        "item_id": "drake_scale",
        "command_id": "cmd-test-1",
        "state_revision": EXAMPLE["hero"]["revision"],
        "now": TS,
    }
    arguments.update(overrides)
    result: dict[str, Any] = tool.claim_with_item(conn, **arguments)
    return result


def drake_scales(conn: sqlite3.Connection) -> int:
    quantity: int = scalar(
        conn,
        "SELECT quantity FROM profile_item_balance WHERE profile_id = ? AND item_id = 'drake_scale'",
        PROFILE,
    )
    return quantity


def dragon_knight_unlocks(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT hero_id FROM hero_vocation_unlock WHERE vocation_id = 'dragon_knight' ORDER BY hero_id"
    )
    return [row[0] for row in rows]


def ddl_statements() -> str:
    """The DDL without its comments."""
    return "\n".join(line.split("--", 1)[0] for line in DDL_PATH.read_text(encoding="utf-8").splitlines())


# --------------------------------------------------------------------------------------------
# The schema
# --------------------------------------------------------------------------------------------


def test_the_ddl_creates_exactly_the_documented_tables(db):
    assert tool.table_names(db) == sorted(V01_TABLES + ADDED_TABLES)
    assert len(V01_TABLES) == 21 and len(tool.table_names(db)) == 24
    assert tuple(tool.table_names(db)) == tool.TABLES


def test_the_schema_version_is_recorded_twice_and_agrees(db):
    assert scalar(db, "PRAGMA user_version") == 2
    assert db.execute("SELECT version FROM schema_migration").fetchall() == [(2,)]


def test_a_new_database_passes_the_integrity_and_foreign_key_checks(db):
    assert db.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    assert scalar(db, "PRAGMA foreign_keys") == 1


def test_every_table_is_strict(loaded):
    not_strict = [
        row[0]
        for row in loaded.execute("SELECT name FROM pragma_table_list WHERE schema = 'main' AND strict = 0")
    ]
    assert [name for name in not_strict if not name.startswith("sqlite_")] == []
    with pytest.raises(sqlite3.IntegrityError, match="cannot store TEXT value in INTEGER column"):
        loaded.execute("UPDATE profile_item_balance SET quantity = 'many'")


def test_every_foreign_key_states_its_on_delete_action_and_names_a_unique_parent_key(db):
    statements = ddl_statements()
    assert len(re.findall(r"\bREFERENCES\b", statements)) == len(re.findall(r"\bON DELETE\b", statements)) > 0

    for table in tool.table_names(db):
        keys: dict[int, tuple[str, list[str]]] = {}
        for key_id, _seq, parent, _child_column, parent_column, *_rest in db.execute(
            f"PRAGMA foreign_key_list({table})"
        ):
            keys.setdefault(key_id, (parent, []))[1].append(parent_column)
        for parent, columns in keys.values():
            unique_sets = [
                sorted(info[2] for info in db.execute(f"PRAGMA index_info({index[1]})"))
                for index in db.execute(f"PRAGMA index_list({parent})")
                if index[2]
            ]
            primary_key = sorted(info[1] for info in db.execute(f"PRAGMA table_info({parent})") if info[5])
            assert sorted(columns) in [*unique_sets, primary_key], (
                f"{table} references a non-unique key of {parent}"
            )


def test_run_phases_are_the_engine_phases(loaded):
    """Defect 9: v0.1 used party_setup / preparation / combat / outcome, which the engine does not have."""
    engine_phases = sorted(value for name, value in vars(RunPhase).items() if name.isupper())
    assert engine_phases == ["battle", "continue", "defeat", "equipment", "upgrade", "victory"]
    # 'continue' (Phase 4: stop or fight on) is saved as 'equipment': between battles, every build fixed.
    assert career_model.SAVED_AS == {"continue": "equipment"}
    saved_phases = sorted({career_model.saved_run_phase(phase) for phase in engine_phases})
    assert saved_phases == sorted(career_model.SAVED_RUN_PHASES) == ["battle", "defeat", "equipment", "upgrade", "victory"]
    with pytest.raises(ValueError, match="no run phase"):
        career_model.saved_run_phase("party_setup")
    for number, phase in enumerate(saved_phases):
        add_run(loaded, f"run_phase_{number}", phase)
    for old_name in ("party_setup", "preparation", "combat", "outcome"):
        with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
            add_run(loaded, "run_old_phase", old_name)


# --------------------------------------------------------------------------------------------
# The example profile
# --------------------------------------------------------------------------------------------


def test_the_example_loads_and_the_database_stays_consistent(loaded):
    assert loaded.execute("PRAGMA foreign_key_check").fetchall() == []
    assert loaded.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
    assert tool.verify_event_chain(loaded, PROFILE) == len(EXAMPLE["progression_events"]) == 18
    counts = {table: scalar(loaded, f"SELECT COUNT(*) FROM {table}") for table in tool.table_names(loaded)}
    assert counts == {
        "content_catalog": 1,
        "encounter_build_snapshot": 1,
        "hero": 1,
        "hero_die_instance": 14,
        "hero_equipped_die": 2,
        "hero_equipped_skill": 3,
        "hero_permanent_upgrade": 4,
        "hero_skill": 7,
        "hero_vocation_mastery": 7,
        "hero_vocation_unlock": 7,
        "item_consumption": 0,
        "item_grant": 1,
        "mastery_award_event": 0,
        "player_profile": 1,
        "processed_command": 0,
        "profile_item_balance": 1,
        "profile_vocation_discovery": 14,
        "progression_event_log": 18,
        "quest_completion": 0,
        "run": 1,
        "run_die_upgrade": 0,
        "schema_migration": 1,
        "skill_def": 14,
        "vocation_def": 14,
    }


def test_the_example_tells_the_v01_story_on_the_shipped_baseline(loaded):
    mastered = [
        row[0]
        for row in loaded.execute(
            "SELECT vocation_id FROM hero_vocation_mastery WHERE hero_id = ? AND mastery_rank = 8 ORDER BY rowid",
            (HERO,),
        )
    ]
    assert mastered == ["squire", "apprentice", "scout", "guardian", "duelist", "spellblade", "champion"]
    assert scalar(loaded, "SELECT active_vocation_id FROM hero WHERE hero_id = ?", HERO) == "champion"

    hero = EXAMPLE["hero"]
    assert [skill["cost"] for skill in hero["inherited_skills"]] == [1, 3, 2]
    assert hero["inheritance_capacity_used"] == hero["inheritance_capacity_max"] == 6
    assert hero["permanent_stat_bonus"] == {"max_hp": 2, "max_mana": 1, "speed": 1}
    base, effective = hero["base_class_stats"], hero["effective_max_stats"]
    assert (base["max_hp"], base["max_mana"], base["speed"]) == (18, 5, 10)
    assert (effective["max_hp"], effective["max_mana"], effective["speed"]) == (20, 6, 11)

    # Hero is visible but blocked; Dragon Knight is discovered and waits for its item.
    states = dict(loaded.execute("SELECT vocation_id, discovery_state FROM profile_vocation_discovery"))
    assert (states["hero"], states["dragon_knight"], states["trickster"]) == (
        "discovered",
        "discovered",
        "hinted",
    )
    assert (
        scalar(
            loaded, "SELECT COUNT(*) FROM hero_vocation_unlock WHERE vocation_id IN ('hero', 'dragon_knight')"
        )
        == 0
    )
    assert EXAMPLE["unlock_evaluation"]["hero"]["error_code"] == "PREREQUISITE_UNMET"
    assert EXAMPLE["unlock_evaluation"]["dragon_knight"]["required_item"] == "drake_scale"
    assert tool.item_ledger(loaded, PROFILE) == [("drake_scale", 1, 1)]

    assert loaded.execute(
        "SELECT rules_version, catalog_version, rng_version, phase FROM run"
    ).fetchall() == [("1.1.1", CATALOG, "BD-PCG32-v1", "upgrade")]
    assert loaded.execute("SELECT catalog_version, rules_version FROM content_catalog").fetchall() == [
        (CATALOG, "1.1.1")
    ]


def test_the_example_uses_the_numbers_of_the_shipped_content():
    pin = _read_json(ROOT / "tests" / "golden" / "replay_pin.json")
    classes = _read_json(ROOT / "src" / "battle_dice" / "content" / "data" / "classes.json")
    # Never skipped: when the shipped content moves on, the example is regenerated on the new baseline.
    assert pin["content_version"] == classes["content_version"] == EXAMPLE["catalog"]["catalog_version"] == CATALOG
    assert (
        EXAMPLE["catalog"]["content_sha256"] == EXAMPLE["run_state"]["content_sha256"] == pin["content_hash"]
    )
    assert (EXAMPLE["catalog"]["rules_version"], EXAMPLE["catalog"]["rng_version"]) == (
        pin["rules_version"],
        pin["rng_algorithm"],
    )
    bonus = EXAMPLE["hero"]["permanent_stat_bonus"]
    for vocation_id, stats in EXAMPLE["hero"]["effective_max_stats_if_active"].items():
        shipped = classes["classes"][vocation_id]
        assert stats["base"] == {name: shipped[name] for name in tool.STAT_NAMES}
        assert stats["effective"] == {name: shipped[name] + bonus.get(name, 0) for name in tool.STAT_NAMES}


def test_an_example_with_a_wrong_hash_or_number_is_refused_and_leaves_nothing(db):
    before = dump(db)
    wrong_hash = copy.deepcopy(EXAMPLE)
    wrong_hash["progression_events"][5]["event_hash"] = HASH_A
    wrong_stats = copy.deepcopy(EXAMPLE)
    wrong_stats["hero"]["effective_max_stats"]["max_hp"] = 21
    wrong_reference = copy.deepcopy(EXAMPLE)
    wrong_reference["hero"]["character_unlocked"][0]["claim_event_id"] = "profile_demo:999"
    for broken, error in (
        (wrong_hash, ValueError),
        (wrong_stats, ValueError),
        (wrong_reference, sqlite3.IntegrityError),
    ):
        with pytest.raises(error):
            tool.load_example(db, broken)
        assert dump(db) == before


# --------------------------------------------------------------------------------------------
# Defect 2: owned dice have a location and are never deleted
# --------------------------------------------------------------------------------------------


def test_defect_2_an_unequipped_die_moves_to_the_bench_and_cannot_be_deleted(loaded):
    die = "hero_001-champion_d8-1"
    locations = "SELECT location, COUNT(*) FROM hero_die_instance GROUP BY location ORDER BY location"
    assert loaded.execute(locations).fetchall() == [("bench", 12), ("equipped", 2)]

    loaded.execute("DELETE FROM hero_equipped_die WHERE hero_id = ? AND die_instance_id = ?", (HERO, die))
    assert scalar(loaded, "SELECT location FROM hero_die_instance WHERE die_instance_id = ?", die) == "bench"
    assert loaded.execute(locations).fetchall() == [("bench", 13), ("equipped", 1)]

    with pytest.raises(sqlite3.IntegrityError, match="never deleted"):
        loaded.execute("DELETE FROM hero_die_instance WHERE die_instance_id = ?", (die,))
    assert scalar(loaded, "SELECT COUNT(*) FROM hero_die_instance") == 14


def test_defect_2_a_die_location_cannot_disagree_with_the_equipped_slots(loaded):
    benched = "hero_001-iron_d6-1"
    with pytest.raises(sqlite3.IntegrityError, match="location must match"):
        loaded.execute(
            "UPDATE hero_die_instance SET location = 'equipped' WHERE die_instance_id = ?", (benched,)
        )
    with pytest.raises(sqlite3.IntegrityError, match="location must match"):
        loaded.execute(
            "UPDATE hero_die_instance SET location = 'bench' WHERE die_instance_id = 'hero_001-champion_d6-1'"
        )
    with pytest.raises(sqlite3.IntegrityError, match="starts on the bench"):
        loaded.execute(
            "INSERT INTO hero_die_instance(die_instance_id, hero_id, definition_id, definition_version, location, "
            "acquisition_key, acquired_at) VALUES ('hero_001-hero_d8-1', ?, 'hero_d8', 1, 'equipped', 'starter:hero:0', ?)",
            (HERO, TS),
        )
    with pytest.raises(sqlite3.IntegrityError, match="keeps its owner and definition"):
        loaded.execute(
            "UPDATE hero_die_instance SET definition_id = 'champion_d8' WHERE die_instance_id = ?", (benched,)
        )

    # Swapping the die in a slot moves both dice.
    loaded.execute(
        "UPDATE hero_equipped_die SET die_instance_id = ?, definition_id = 'iron_d6' WHERE slot_index = 0",
        (benched,),
    )
    moved = dict(loaded.execute("SELECT die_instance_id, location FROM hero_die_instance"))
    assert (moved[benched], moved["hero_001-champion_d8-1"]) == ("equipped", "bench")


def test_defect_2_a_starter_die_is_granted_once_per_hero(loaded):
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint failed"):
        loaded.execute(
            "INSERT INTO hero_die_instance(die_instance_id, hero_id, definition_id, definition_version, location, "
            "acquisition_key, acquired_at) VALUES ('hero_001-iron_d6-2', ?, 'iron_d6', 1, 'bench', 'starter:squire:0', ?)",
            (HERO, TS),
        )


# --------------------------------------------------------------------------------------------
# Defect 3: the item grant ledger
# --------------------------------------------------------------------------------------------


def test_defect_3_a_repeated_grant_id_grants_nothing(loaded):
    grant_id = EXAMPLE["profile"]["item_grants"][0]["grant_id"]
    assert (
        tool.grant_item(loaded, grant_id=grant_id, profile_id=PROFILE, item_id="drake_scale", now=TS) is False
    )
    assert drake_scales(loaded) == 1
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint failed: item_grant.grant_id"):
        loaded.execute(
            "INSERT INTO item_grant(grant_id, profile_id, item_id, quantity, granted_at) VALUES (?, ?, 'drake_scale', 1, ?)",
            (grant_id, PROFILE, TS),
        )

    add_hero(loaded)
    new_grant = f"first_clear:training_04:{OTHER_HERO}:drake_scale"
    assert (
        tool.grant_item(
            loaded, grant_id=new_grant, profile_id=PROFILE, item_id="drake_scale", hero_id=OTHER_HERO
        )
        is True
    )
    assert (
        tool.grant_item(
            loaded, grant_id=new_grant, profile_id=PROFILE, item_id="drake_scale", hero_id=OTHER_HERO
        )
        is False
    )
    assert tool.item_ledger(loaded, PROFILE) == [("drake_scale", 2, 2)]


# --------------------------------------------------------------------------------------------
# Defect 4: events have an id, claims reference it, and an event needs no run
# --------------------------------------------------------------------------------------------

INSERT_UNLOCK = (
    "INSERT INTO hero_vocation_unlock(hero_id, catalog_version, vocation_id, unlock_route_id, claim_event_id, "
    "unlocked_at) VALUES (?, ?, 'dragon_knight', 'route_0', ?, ?)"
)
INSERT_EVENT = (
    "INSERT INTO progression_event_log(profile_id, event_seq, event_id, run_id, event_type, event_json, "
    "previous_event_hash, event_hash, created_at) VALUES (?, ?, ?, NULL, 'Test', '{}', ?, ?, ?)"
)


def test_defect_4_a_claim_must_reference_an_event_that_exists(loaded):
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
        loaded.execute(INSERT_UNLOCK, (HERO, CATALOG, "no-such-event", TS))
    event_id = add_event(loaded, "VocationClaimed")
    loaded.execute(INSERT_UNLOCK, (HERO, CATALOG, event_id, TS))
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
        loaded.execute("DELETE FROM progression_event_log WHERE event_id = ?", (event_id,))


def test_defect_4_an_event_outside_a_run_is_stored_with_its_own_id(loaded):
    event_id = add_event(loaded)
    assert event_id == "profile_demo:18"
    assert loaded.execute(
        "SELECT run_id, event_seq FROM progression_event_log WHERE event_id = ?", (event_id,)
    ).fetchall() == [(None, 18)]
    last_hash = scalar(loaded, "SELECT event_hash FROM progression_event_log WHERE event_id = ?", event_id)
    with pytest.raises(
        sqlite3.IntegrityError, match="UNIQUE constraint failed: progression_event_log.event_id"
    ):
        loaded.execute(INSERT_EVENT, (PROFILE, 19, event_id, last_hash, HASH_A, TS))


def test_defect_4_an_event_must_continue_the_sequence_and_the_hash_chain(loaded):
    last_hash = scalar(
        loaded,
        "SELECT event_hash FROM progression_event_log WHERE profile_id = ? AND event_seq = 17",
        PROFILE,
    )
    with pytest.raises(sqlite3.IntegrityError, match="breaks the sequence or the hash chain"):
        loaded.execute(INSERT_EVENT, (PROFILE, 25, "profile_demo:25", last_hash, HASH_A, TS))
    with pytest.raises(sqlite3.IntegrityError, match="breaks the sequence or the hash chain"):
        loaded.execute(INSERT_EVENT, (PROFILE, 18, "profile_demo:18", HASH_A, HASH_A, TS))
    with pytest.raises(sqlite3.IntegrityError, match="append only"):
        loaded.execute(
            "UPDATE progression_event_log SET event_json = '{\"forged\": true}' WHERE event_seq = 3"
        )
    loaded.execute(INSERT_EVENT, (PROFILE, 18, "profile_demo:18", last_hash, HASH_A, TS))


# --------------------------------------------------------------------------------------------
# Defect 5: a consumption belongs to its claim's hero, once
# --------------------------------------------------------------------------------------------

INSERT_CONSUMPTION = (
    "INSERT INTO item_consumption(consumption_id, profile_id, hero_id, item_id, quantity, claim_event_id, consumed_at) "
    "VALUES (?, ?, ?, 'drake_scale', 1, ?, ?)"
)


def champion_claim(conn: sqlite3.Connection) -> str:
    claim_event_id: str = scalar(
        conn,
        "SELECT claim_event_id FROM hero_vocation_unlock WHERE hero_id = ? AND vocation_id = 'champion'",
        HERO,
    )
    return claim_event_id


def test_defect_5_a_consumption_must_name_the_hero_of_its_claim(loaded):
    add_hero(loaded)
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
        loaded.execute(INSERT_CONSUMPTION, ("c1", PROFILE, OTHER_HERO, champion_claim(loaded), TS))
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
        loaded.execute(INSERT_CONSUMPTION, ("c1", PROFILE, HERO, "profile_demo:999", TS))
    loaded.execute(INSERT_CONSUMPTION, ("c1", PROFILE, HERO, champion_claim(loaded), TS))


def test_defect_5_a_consumption_must_be_paid_by_the_heros_own_profile(loaded):
    add_profile(loaded, "profile_other")
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
        loaded.execute(INSERT_CONSUMPTION, ("c1", "profile_other", HERO, champion_claim(loaded), TS))


def test_defect_5_a_claim_is_consumed_for_at_most_once(loaded):
    loaded.execute(INSERT_CONSUMPTION, ("c1", PROFILE, HERO, champion_claim(loaded), TS))
    with pytest.raises(
        sqlite3.IntegrityError, match="UNIQUE constraint failed: item_consumption.claim_event_id"
    ):
        loaded.execute(INSERT_CONSUMPTION, ("c2", PROFILE, HERO, champion_claim(loaded), TS))


# --------------------------------------------------------------------------------------------
# Defect 6: no challenge point without a base point
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("base", "challenge", "denial"),
    [
        pytest.param(0, 1, "UNDER_THREAT_CAP", id="bonus-without-base"),
        pytest.param(0, 1, None, id="bonus-without-base-or-reason"),
        pytest.param(0, 0, None, id="denial-without-reason"),
        pytest.param(1, 0, "UNDER_THREAT_CAP", id="award-with-denial-reason"),
    ],
)
def test_defect_6_an_award_row_is_either_an_award_or_a_denial(loaded, base, challenge, denial):
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        add_award(loaded, base, challenge, denial)


def test_defect_6_the_three_legal_award_rows_are_accepted_once_per_encounter(loaded):
    add_award(loaded, 1, 0, None, "training_01")
    add_award(loaded, 1, 1, None, "training_02")
    add_award(loaded, 0, 0, "UNDER_THREAT_CAP", "training_03")
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint failed"):
        loaded.execute(
            "INSERT INTO mastery_award_event(event_id, run_id, encounter_id, hero_id, catalog_version, vocation_id, "
            "base_points, challenge_points, threat_rating, created_at) VALUES ('again', ?, 'training_01', ?, ?, "
            "'champion', 1, 0, 1, ?)",
            (RUN, HERO, CATALOG, TS),
        )


# --------------------------------------------------------------------------------------------
# Defect 7: run upgrades are never permanent; permanent upgrades name their source event
# --------------------------------------------------------------------------------------------

INSERT_RUN_UPGRADE = (
    "INSERT INTO run_die_upgrade(run_id, upgrade_id, hero_id, die_instance_id, override_json, permanent, applied_at) "
    "VALUES (?, ?, ?, ?, '{}', ?, ?)"
)
INSERT_PERMANENT_UPGRADE = (
    "INSERT INTO hero_permanent_upgrade(upgrade_id, hero_id, upgrade_kind, effect_json, source_event_id, earned_at) "
    "VALUES (?, ?, 'mastery_stat_bonus', '{}', ?, ?)"
)


def test_defect_7_a_run_upgrade_cannot_be_permanent(loaded):
    die = "hero_001-champion_d8-1"
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        loaded.execute(INSERT_RUN_UPGRADE, (RUN, "u1", HERO, die, 1, TS))
    loaded.execute(INSERT_RUN_UPGRADE, (RUN, "u1", HERO, die, 0, TS))
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        loaded.execute("UPDATE run_die_upgrade SET permanent = 1")
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
        loaded.execute(INSERT_RUN_UPGRADE, (RUN, "u2", HERO, "no-such-die", 0, TS))


def test_defect_7_a_permanent_upgrade_needs_its_own_source_event(loaded):
    with pytest.raises(
        sqlite3.IntegrityError, match="NOT NULL constraint failed: hero_permanent_upgrade.source_event_id"
    ):
        loaded.execute(INSERT_PERMANENT_UPGRADE, ("p1", HERO, None, TS))
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
        loaded.execute(INSERT_PERMANENT_UPGRADE, ("p1", HERO, "no-such-event", TS))
    used = EXAMPLE["hero"]["permanent_upgrades"][0]["source_event_id"]
    with pytest.raises(
        sqlite3.IntegrityError, match="UNIQUE constraint failed: hero_permanent_upgrade.source_event_id"
    ):
        loaded.execute(INSERT_PERMANENT_UPGRADE, ("p1", HERO, used, TS))
    loaded.execute(INSERT_PERMANENT_UPGRADE, ("p1", HERO, add_event(loaded), TS))


# --------------------------------------------------------------------------------------------
# Defect 8: build hash, pins and delete behaviour
# --------------------------------------------------------------------------------------------


def test_defect_8_a_run_needs_a_build_hash_and_the_hash_of_its_catalog(loaded):
    with pytest.raises(sqlite3.IntegrityError, match="NOT NULL constraint failed: run.build_sha256"):
        add_run(loaded, "run_x", build_sha256=None)
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        add_run(loaded, "run_x", build_sha256="not-a-hash")
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
        add_run(loaded, "run_x", content_sha256=HASH_A)
    add_run(loaded, "run_x")


@pytest.mark.parametrize(
    "column",
    ["build_sha256", "content_sha256", "catalog_version", "rules_version", "rng_version", "seed_decimal"],
)
def test_defect_8_the_pins_of_a_run_never_change(loaded, column):
    with pytest.raises(sqlite3.IntegrityError, match="run pins are immutable"):
        loaded.execute(f"UPDATE run SET {column} = ? WHERE run_id = ?", (HASH_A, RUN))
    loaded.execute("UPDATE run SET phase = 'equipment', revision = revision + 1 WHERE run_id = ?", (RUN,))


def test_defect_8_a_hero_can_be_deleted_with_its_history(loaded):
    claim(loaded)
    add_award(loaded, 0, 0, "UNDER_THREAT_CAP")
    loaded.execute(
        "INSERT INTO quest_completion(profile_id, quest_id, qualifier_scope, qualifier_id, completed_at) "
        "VALUES (?, 'trial_of_the_hero', 'hero', ?, ?)",
        (PROFILE, HERO, TS),
    )
    loaded.execute("DELETE FROM hero WHERE hero_id = ?", (HERO,))

    assert loaded.execute("PRAGMA foreign_key_check").fetchall() == []
    counts = tool.count_profile_rows(loaded, "no-such-profile", {"hero_id": [HERO]})
    assert {table: count for table, count in counts.items() if count} == {}
    assert scalar(loaded, "SELECT COUNT(*) FROM quest_completion") == 0
    # The grant stays as a spent reward id, and the profile keeps its events and its run.
    assert loaded.execute("SELECT grant_id, hero_id FROM item_grant").fetchall() == [
        (EXAMPLE["profile"]["item_grants"][0]["grant_id"], None)
    ]
    assert tool.verify_event_chain(loaded, PROFILE) == 19
    assert scalar(loaded, "SELECT COUNT(*) FROM run") == 1


def test_defect_8_a_run_can_be_deleted_unless_it_has_mastery_awards(loaded):
    add_award(loaded, 0, 0, "UNDER_THREAT_CAP")
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
        loaded.execute("DELETE FROM run WHERE run_id = ?", (RUN,))
    loaded.execute("DELETE FROM mastery_award_event")

    loaded.execute("DELETE FROM run WHERE run_id = ?", (RUN,))
    assert scalar(loaded, "SELECT COUNT(*) FROM encounter_build_snapshot") == 0
    assert scalar(loaded, "SELECT COUNT(*) FROM progression_event_log WHERE run_id IS NOT NULL") == 0
    assert loaded.execute("SELECT run_id FROM item_grant").fetchall() == [(None,)]
    assert tool.verify_event_chain(loaded, PROFILE) == 18


def test_a_hero_can_only_switch_to_a_vocation_it_has_claimed(loaded):
    with pytest.raises(sqlite3.IntegrityError, match="not unlocked for this hero"):
        loaded.execute("UPDATE hero SET active_vocation_id = 'dragon_knight' WHERE hero_id = ?", (HERO,))
    loaded.execute("UPDATE hero SET active_vocation_id = 'guardian' WHERE hero_id = ?", (HERO,))


def test_a_hero_quest_completion_must_name_a_hero_of_the_profile(loaded):
    insert = (
        "INSERT INTO quest_completion(profile_id, quest_id, qualifier_scope, qualifier_id, completed_at) "
        "VALUES (?, 'trial_of_the_hero', ?, ?, ?)"
    )
    with pytest.raises(sqlite3.IntegrityError, match="names no hero of this profile"):
        loaded.execute(insert, (PROFILE, "hero", "nobody", TS))
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        loaded.execute(insert, (PROFILE, "profile", "someone-else", TS))
    loaded.execute(insert, (PROFILE, "hero", HERO, TS))
    loaded.execute(insert, (PROFILE, "profile", PROFILE, TS))


# --------------------------------------------------------------------------------------------
# The claim transaction
# --------------------------------------------------------------------------------------------


def test_a_claim_writes_every_row_in_one_transaction(loaded):
    result = claim(loaded)

    assert result["result"] == "accepted" and result["duplicate"] is False
    assert result["state_revision"] == EXAMPLE["hero"]["revision"] + 1
    assert scalar(loaded, "SELECT revision FROM hero WHERE hero_id = ?", HERO) == result["state_revision"]
    assert drake_scales(loaded) == 0
    assert dragon_knight_unlocks(loaded) == [HERO]
    claim_event_id = result["claim_event_id"]
    assert loaded.execute(
        "SELECT hero_id, item_id, quantity, claim_event_id FROM item_consumption"
    ).fetchall() == [(HERO, "drake_scale", 1, claim_event_id)]
    assert loaded.execute(
        "SELECT claim_event_id, unlock_route_id FROM hero_vocation_unlock WHERE vocation_id = 'dragon_knight'"
    ).fetchall() == [(claim_event_id, "route_0")]
    assert loaded.execute(
        "SELECT event_type, run_id, json_extract(event_json, '$.consumed_items[0].item_id') "
        "FROM progression_event_log WHERE event_id = ?",
        (claim_event_id,),
    ).fetchall() == [("VocationClaimed", None, "drake_scale")]
    assert loaded.execute(
        "SELECT mastery_rank, mastery_points FROM hero_vocation_mastery WHERE vocation_id = 'dragon_knight'"
    ).fetchall() == [(1, 0)]
    assert loaded.execute(
        "SELECT command_scope, command_id, command_type FROM processed_command"
    ).fetchall() == [("profile:profile_demo", "cmd-test-1", "ClaimVocation")]
    assert tool.item_ledger(loaded, PROFILE) == [("drake_scale", 0, 0)]
    assert tool.verify_event_chain(loaded, PROFILE) == 19
    assert loaded.execute("PRAGMA foreign_key_check").fetchall() == []


def test_a_claim_that_fails_midway_changes_nothing(loaded):
    """CE-38: a failure after the item decrement and before the unlock insert rolls everything back."""
    before = dump(loaded)

    with pytest.raises(tool.InjectedFailure):
        claim(loaded, fail_after_decrement=True)

    assert dump(loaded) == before
    assert drake_scales(loaded) == 1 and dragon_knight_unlocks(loaded) == []
    assert not loaded.in_transaction
    # The command id was not recorded, so the same command can be sent again and succeeds once.
    assert claim(loaded)["duplicate"] is False
    assert claim(loaded)["duplicate"] is True
    assert drake_scales(loaded) == 0 and dragon_knight_unlocks(loaded) == [HERO]


def test_a_claim_stopped_by_a_constraint_changes_nothing(loaded):
    """A second claim of the same vocation with a new command id hits the primary key after the decrement."""
    claim(loaded)
    tool.grant_item(loaded, grant_id="test:extra-scale", profile_id=PROFILE, item_id="drake_scale", now=TS)
    before = dump(loaded)

    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint failed: hero_vocation_unlock"):
        claim(loaded, command_id="cmd-test-2", state_revision=EXAMPLE["hero"]["revision"] + 1)

    assert dump(loaded) == before
    assert drake_scales(loaded) == 1


def test_the_same_command_id_twice_consumes_one_token(loaded):
    """CE-33: the repeated command returns the stored result and has no second effect."""
    first = claim(loaded)
    after_first = dump(loaded)

    second = claim(loaded)

    assert second == {**first, "duplicate": True}
    assert dump(loaded) == after_first
    assert scalar(loaded, "SELECT COUNT(*) FROM item_consumption") == 1
    assert scalar(loaded, "SELECT COUNT(*) FROM processed_command") == 1
    assert drake_scales(loaded) == 0


def test_a_second_hero_needs_its_own_token(loaded):
    """CE-13: discovery is shared by the profile, the token is paid per hero."""
    add_hero(loaded)
    assert claim(loaded)["result"] == "accepted"
    before = dump(loaded)

    refused = claim(loaded, hero_id=OTHER_HERO, command_id="cmd-test-2", state_revision=0)

    assert refused == {"result": "rejected", "error_code": "ITEM_INSUFFICIENT", "state_revision": 0}
    assert dump(loaded) == before
    assert dragon_knight_unlocks(loaded) == [HERO]

    grant_id = f"first_clear:training_04:{OTHER_HERO}:drake_scale"
    assert tool.grant_item(
        loaded, grant_id=grant_id, profile_id=PROFILE, item_id="drake_scale", hero_id=OTHER_HERO, now=TS
    )
    assert (
        claim(loaded, hero_id=OTHER_HERO, command_id="cmd-test-2", state_revision=0)["result"] == "accepted"
    )
    assert dragon_knight_unlocks(loaded) == [HERO, OTHER_HERO]
    assert loaded.execute("SELECT hero_id, quantity FROM item_consumption ORDER BY hero_id").fetchall() == [
        (HERO, 1),
        (OTHER_HERO, 1),
    ]
    assert tool.item_ledger(loaded, PROFILE) == [("drake_scale", 0, 0)]


def _stale_revision(conn: sqlite3.Connection) -> dict[str, Any]:
    return {"state_revision": EXAMPLE["hero"]["revision"] - 1}


def _run_in_battle(conn: sqlite3.Connection) -> dict[str, Any]:
    conn.execute("UPDATE run SET phase = 'battle' WHERE run_id = ?", (RUN,))
    return {}


def _guest(conn: sqlite3.Connection) -> dict[str, Any]:
    add_hero(conn, "guest_001", eligibility_state="guest")
    return {"hero_id": "guest_001", "state_revision": 0}


def _only_hinted(conn: sqlite3.Connection) -> dict[str, Any]:
    conn.execute(
        "UPDATE profile_vocation_discovery SET discovery_state = 'hinted' WHERE vocation_id = 'dragon_knight'"
    )
    return {}


def _no_token(conn: sqlite3.Connection) -> dict[str, Any]:
    return {"item_id": "jester_mask"}


@pytest.mark.parametrize(
    ("arrange", "error_code"),
    [
        pytest.param(_stale_revision, "REVISION_CONFLICT", id="stale-revision"),
        pytest.param(_run_in_battle, "PHASE_LOCKED", id="run-in-battle"),
        pytest.param(_guest, "HERO_NOT_ELIGIBLE", id="guest"),
        pytest.param(_only_hinted, "NOT_DISCOVERED", id="only-hinted"),
        pytest.param(_no_token, "ITEM_INSUFFICIENT", id="no-token"),
    ],
)
def test_a_rejected_claim_changes_nothing_and_names_a_registry_code(loaded, arrange, error_code):
    overrides = arrange(loaded)
    before = dump(loaded)

    result = claim(loaded, **overrides)

    assert (result["result"], result["error_code"]) == ("rejected", error_code)
    assert error_code in REGISTRY_CODES
    assert dump(loaded) == before
    assert not loaded.in_transaction


def test_a_command_id_reused_for_a_different_command_is_rejected(loaded):
    add_hero(loaded)
    claim(loaded)
    before = dump(loaded)

    result = claim(loaded, hero_id=OTHER_HERO, state_revision=0)

    assert (result["result"], result["error_code"]) == ("rejected", "COMMAND_ID_REUSED")
    assert "COMMAND_ID_REUSED" in REGISTRY_CODES
    assert dump(loaded) == before


# --------------------------------------------------------------------------------------------
# Profile reset
# --------------------------------------------------------------------------------------------


def _fill_every_profile_table(conn: sqlite3.Connection) -> None:
    """Give the example profile at least one row in every table that belongs to a profile."""
    claim(conn)  # item_consumption, processed_command
    add_award(conn, 0, 0, "UNDER_THREAT_CAP")
    conn.execute(INSERT_RUN_UPGRADE, (RUN, "u1", HERO, "hero_001-champion_d8-1", 0, TS))
    conn.execute(
        "INSERT INTO quest_completion(profile_id, quest_id, qualifier_scope, qualifier_id, completed_at) "
        "VALUES (?, 'trial_of_the_hero', 'hero', ?, ?)",
        (PROFILE, HERO, TS),
    )


def test_reset_profile_leaves_no_rows_for_that_profile(loaded):
    _fill_every_profile_table(loaded)
    add_profile(loaded, "profile_other")
    add_hero(loaded, "hero_900", "profile_other")
    add_event(loaded, "VocationClaimed", "profile_other")
    keys = tool.profile_keys(loaded, PROFILE)
    other_keys = tool.profile_keys(loaded, "profile_other")
    assert keys == {"hero_id": [HERO], "run_id": [RUN]}
    before = tool.count_profile_rows(loaded, PROFILE, keys)
    assert sorted(before) == sorted(set(tool.TABLES) - set(tool.SHARED_TABLES))
    assert all(count > 0 for count in before.values()), before
    other_before = tool.count_profile_rows(loaded, "profile_other", other_keys)
    shared_before = {table: scalar(loaded, f"SELECT COUNT(*) FROM {table}") for table in tool.SHARED_TABLES}

    tool.reset_profile(loaded, PROFILE)

    after = tool.count_profile_rows(loaded, PROFILE, keys)
    assert {table: count for table, count in after.items() if count} == {}
    assert tool.count_profile_rows(loaded, "profile_other", other_keys) == other_before
    assert {
        table: scalar(loaded, f"SELECT COUNT(*) FROM {table}") for table in tool.SHARED_TABLES
    } == shared_before
    assert loaded.execute("PRAGMA foreign_key_check").fetchall() == []
    assert loaded.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
    assert not loaded.in_transaction


def test_a_reset_profile_can_be_created_again_with_the_same_id(loaded):
    _fill_every_profile_table(loaded)
    tool.reset_profile(loaded, PROFILE)
    tool.reset_profile(loaded, PROFILE)  # resetting a profile that is gone is not an error

    add_profile(loaded, PROFILE)
    add_hero(loaded, HERO)
    assert add_event(loaded) == "profile_demo:0"
    assert tool.grant_item(
        loaded,
        grant_id=EXAMPLE["profile"]["item_grants"][0]["grant_id"],
        profile_id=PROFILE,
        item_id="drake_scale",
    )
    assert tool.item_ledger(loaded, PROFILE) == [("drake_scale", 1, 1)]


def test_the_documented_reset_sequence_is_the_one_the_tool_runs():
    text = DDL_PATH.read_text(encoding="utf-8")
    block = text[text.index("-- RESET PROFILE") :]
    for statement in (
        "BEGIN IMMEDIATE;",
        "DELETE FROM player_profile WHERE profile_id = :profile_id;",
        "PRAGMA foreign_key_check;",
        "COMMIT;",
    ):
        assert statement in block


def test_the_checking_tool_runs_end_to_end(capsys):
    assert tool.main() == 0
    assert capsys.readouterr().out == "OK\n"


# --------------------------------------------------------------------------------------------
# The error-code registry
# --------------------------------------------------------------------------------------------


def walk(value: Any) -> Iterator[tuple[str, Any]]:
    """Every (key, value) pair of a JSON document, at any depth."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield key, item
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


def fixture_codes() -> set[str]:
    """Every error code or denial reason a fixture names."""
    return {
        item
        for key, item in walk(FIXTURES["cases"])
        if key in ("error_code", "denial_reason") and item is not None
    }


def test_the_registry_lists_each_code_once_with_a_meaning_and_its_commands():
    assert len(REGISTRY_CODES) == len(set(REGISTRY_CODES))
    for entry in REGISTRY["codes"]:
        assert re.fullmatch(r"[A-Z]+(_[A-Z]+)*", entry["code"])
        assert entry["meaning"].endswith(".") and len(entry["meaning"]) > 20
        assert entry["raised_by"] and all(isinstance(name, str) and name for name in entry["raised_by"])
        assert entry["kind"] in REGISTRY["kinds"]


def test_the_registry_resolves_the_v01_code_conflicts():
    """Defect 10: two pairs of duplicate names, and DUPLICATE_COMMAND as an error."""
    merged = {entry["v0_1_code"]: entry["use"] for entry in REGISTRY["merged_codes"]}
    assert merged == {
        "CHARACTER_NOT_ELIGIBLE": "HERO_NOT_ELIGIBLE",
        "MISSING_MASTERY": "PREREQUISITE_UNMET",
        "DUPLICATE_COMMAND": "replay_result",
    }
    assert not set(merged) & set(REGISTRY_CODES)
    replay = REGISTRY["replay_result"]
    assert (replay["is_error"], replay["result"], replay["duplicate"]) == (False, "accepted", True)
    v01_stated = {
        "PHASE_LOCKED",
        "NOT_DISCOVERED",
        "HERO_NOT_ELIGIBLE",
        "PREREQUISITE_UNMET",
        "ITEM_INSUFFICIENT",
        "CAPACITY_EXCEEDED",
        "INCOMPATIBLE_DIE",
        "NO_LEGAL_FACE",
        "CONTENT_MIGRATION_REQUIRED",
        "REVISION_CONFLICT",
        "UNSUPPORTED_SECONDARY_VOCATION",
    }
    assert v01_stated <= set(REGISTRY_CODES)
    plan_codes = {entry["code"] for entry in REGISTRY["codes"] if entry["kind"] == "plan_rejection"}
    assert set(REGISTRY_CODES) - v01_stated - plan_codes == {
        "UNDER_THREAT_CAP",
        "TRAINING_DEAD_END",
        "UNLOCK_DEAD_END",
        "ENCOUNTER_NOT_WON",
        "COMMAND_ID_REUSED",
    }
    # Added on 2026-11-11 (fixtures CE-29 and CE-30): the codes of a refused action plan, as the rules engine names them.
    assert plan_codes == set(planning.PLAN_CODES) and len(plan_codes) == 11
    assert REGISTRY["plan_check_order"]["order"] == list(planning.PLAN_CODES)
    assert not plan_codes & set(REGISTRY["check_order"]["order"]), "a plan is checked by the engine, in its own order"
    # The catalog validator and the registry name the same content-validation codes.
    assert {entry["code"] for entry in REGISTRY["codes"] if entry["kind"] == "content_validation"} == set(
        catalog_tool.CONTENT_VALIDATION_CODES
    )
    assert set(REGISTRY["check_order"]["order"]) - {"replay_result"} <= set(REGISTRY_CODES)


def test_fixtures_use_only_registry_codes():
    assert fixture_codes() <= set(REGISTRY_CODES)
    assert FIXTURE_SCHEMA["$defs"]["errorCode"]["enum"] == REGISTRY_CODES


def test_every_registry_code_is_used_by_a_fixture_or_listed_as_unused_with_a_reason():
    unused = {entry["code"]: entry["reason"] for entry in REGISTRY["unused_codes"]}
    used = fixture_codes()
    assert set(REGISTRY_CODES) - used == set(unused)
    assert all(len(reason) > 20 for reason in unused.values())
    # A plan code no fixture uses must name the test that raises it; of every other kind at most five codes go unused.
    plan_codes = set(planning.PLAN_CODES)
    assert len(set(unused) - plan_codes) <= 5
    assert plan_codes & used == {"INSUFFICIENT_MANA", "TARGET_DOWNED"}  # fixtures CE-29 and CE-30
    for code in plan_codes & set(unused):
        assert "tests/unit/test_plan_codes.py" in unused[code] and (ROOT / "tests" / "unit" / "test_plan_codes.py").is_file()


# --------------------------------------------------------------------------------------------
# Route ids: the saved data and the fixtures use the catalog's rule
# --------------------------------------------------------------------------------------------


def route_uses(node: Any, vocation_id: str | None = None) -> Iterator[tuple[str, list[str], bool]]:
    """(vocation, route ids, is a full list of the vocation's routes) for every route id in a document.

    The vocation is the nearest ``target_vocation_id`` or ``vocation_id`` at or above the route id, or
    the nearest key that is a vocation id.
    """
    if isinstance(node, list):
        for item in node:
            yield from route_uses(item, vocation_id)
        return
    if not isinstance(node, dict):
        return
    vocation_id = node.get("target_vocation_id") or node.get("vocation_id") or vocation_id
    for key in ("route_id", "unlock_route_id"):
        if key in node:
            assert vocation_id is not None, node
            yield vocation_id, [node[key]], False
    for key, value in node.items():
        if key == "routes":
            assert vocation_id is not None, node
            yield vocation_id, [route["route_id"] for route in value], True
            for route in value:  # the conditions inside a route name other vocations, not routes
                yield from route_uses(route["unmet"], None)
        else:
            yield from route_uses(value, key if key in CATALOG_ROUTES else vocation_id)


CATALOG_ROUTES = {
    vocation_id: list(routes) for vocation_id, routes in catalog_tool.unlock_routes(catalog_tool.load_catalog()).items()
}


def test_the_catalog_gives_every_vocation_its_routes_by_one_rule():
    assert {v: r for v, r in CATALOG_ROUTES.items() if r != ["route_0"]} == {
        "hero": ["route_0", "route_1"],
        "trickster": ["route_0", "route_1"],
    }
    routes = catalog_tool.unlock_routes(catalog_tool.load_catalog())
    assert routes["squire"] == {"route_0": {}}
    assert routes["guardian"] == {"route_0": {"mastered": "squire"}}
    assert routes["hero"]["route_1"] == {
        "all": [{"mastered_count": {"group": "advanced", "minimum": 3}}, {"quest": "trial_of_the_hero"}]
    }


@pytest.mark.parametrize("document", ["example", "fixtures"])
def test_every_route_id_in_the_saved_data_and_the_fixtures_is_a_route_of_that_vocation(document):
    if document == "example":
        uses = list(route_uses(EXAMPLE))
    else:  # a rejected command's error details list the routes of the vocation the command named
        uses = [
            use
            for case in FIXTURES["cases"]
            for use in route_uses(case, case["when"].get("command", {}).get("params", {}).get("target_vocation_id"))
        ]
    assert len(uses) >= 10
    for vocation_id, route_ids, full_list in uses:
        assert vocation_id in CATALOG_ROUTES, vocation_id
        if full_list:  # a blocked preview lists every route of the vocation, in catalog order
            assert route_ids == CATALOG_ROUTES[vocation_id], (vocation_id, route_ids)
        else:
            assert set(route_ids) <= set(CATALOG_ROUTES[vocation_id]), (vocation_id, route_ids)
    assert {"route_0", "route_1"} <= {route_id for _, route_ids, _ in uses for route_id in route_ids}


# --------------------------------------------------------------------------------------------
# The acceptance fixtures
# --------------------------------------------------------------------------------------------


def test_the_fixtures_validate_against_their_schema():
    jsonschema.Draft202012Validator.check_schema(FIXTURE_SCHEMA)
    assert FIXTURE_SCHEMA["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    errors = list(jsonschema.Draft202012Validator(FIXTURE_SCHEMA).iter_errors(FIXTURES))
    assert [f"{list(error.absolute_path)}: {error.message}" for error in errors] == []


def test_the_fixtures_are_ce_01_to_ce_40_exactly_once():
    assert [case["id"] for case in FIXTURES["cases"]] == [f"CE-{number:02d}" for number in range(1, 41)]


def test_one_case_still_needs_a_design_decision():
    needing = {int(case["id"][3:]) for case in FIXTURES["cases"] if "needs_design_decision" in case}
    assert needing == NEEDS_DESIGN_DECISION
    assert len(needing) == 1 and len(FIXTURES["cases"]) - len(needing) == 39
    # A decided case says so, with the date, where its open question used to be.
    decided_today = ("CE-09", "CE-29", "CE-30", "CE-32", "CE-36")
    for case in FIXTURES["cases"]:
        if case["id"] in decided_today:
            assert case["notes"].startswith("Decided by the owner on 2026-11-11: "), case["id"]


def test_ce_01_and_ce_40_share_the_replay_pin_baseline():
    assert FIXTURES["baseline"]["definition"] == BASELINE_DEFINITION
    assert (ROOT / FIXTURES["baseline"]["replay_pin"]).is_file()
    cases = {case["id"]: case for case in FIXTURES["cases"]}
    for case_id, gate in (("CE-01", False), ("CE-40", True)):
        case = cases[case_id]
        assert case["given"]["feature_gate"] == {"class_evolution_v1": gate}
        assert case["when"]["event"] == {
            "type": "ReplayPinnedRuns",
            "pin_path": "tests/golden/replay_pin.json",
        }
        assert case["then"]["state"]["replay"]["final_state_hash_matches_pin"] is True
        assert BASELINE_DEFINITION in case["notes"]


def fixture_commands() -> list[dict[str, Any]]:
    return [item for key, item in walk(FIXTURES["cases"]) if key == "command"]


def test_fixture_commands_use_the_game_envelope():
    """The game's envelope is {type, command_id, state_revision, params}; v0.1 wrote expected_state_revision."""
    commands = fixture_commands()
    assert len(commands) >= 20
    for command in commands:
        assert set(command) == set(game_commands.Command("x", "y", 0).to_dict())
    shipped = [command for command in commands if command["type"] in game_commands.COMMAND_TYPES]
    assert {command["type"] for command in shipped} == {"StartRun", "ChooseUpgrade", "SetActionPlan"}
    for command in shipped:
        assert game_commands.validate_command(game_commands.Command(**command)) is None


@pytest.mark.parametrize(
    ("case_id", "path", "value"),
    [
        pytest.param("CE-37", ("then", "error_code"), "CHARACTER_NOT_ELIGIBLE", id="merged-v01-code"),
        pytest.param("CE-12", ("then", "error_code"), "DUPLICATE_COMMAND", id="duplicate-command-as-error"),
        pytest.param(
            "CE-23",
            ("then", "state", "mastery_award_events", 0, "denial_reason"),
            "TOO_EASY",
            id="unknown-denial",
        ),
        pytest.param("CE-03", ("when", "command", "expected_state_revision"), 3, id="v01-revision-name"),
        pytest.param(
            "CE-03", ("when", "command", "params", "target_vocation_id"), "paladin", id="unknown-vocation"
        ),
        pytest.param("CE-16", ("given", "run", "phase"), "combat", id="v01-phase-name"),
        pytest.param("CE-03", ("given", "heroes", 0, "level"), 3, id="unknown-field"),
        pytest.param("CE-03", ("then", "error_code"), "PHASE_LOCKED", id="accepted-with-error-code"),
    ],
)
def test_the_fixture_schema_is_strict(case_id, path, value):
    broken = copy.deepcopy(FIXTURES)
    target: Any = next(case for case in broken["cases"] if case["id"] == case_id)
    for step in path[:-1]:
        target = target[step]
    target[path[-1]] = value
    assert list(jsonschema.Draft202012Validator(FIXTURE_SCHEMA).iter_errors(broken)) != []
