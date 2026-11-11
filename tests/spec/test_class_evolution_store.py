"""The acceptance fixtures again, this time through the save file (Class Evolution Phase 3).

Every case the career rules decide is run twice from the same starting point: once in memory and
once through :class:`battle_dice.career.store.StoredCareerService`, which writes each accepted
change to a SQLite file built from the approved schema. The two must agree, the file must hold
exactly the result after it is closed and opened again, and a rejected or failed step must leave
the file as it was.
"""

from __future__ import annotations

import copy
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from battle_dice.career import store as store_module
from battle_dice.career.catalog import CareerCatalog
from battle_dice.career.service import CareerService, InjectedFault, state_view
from battle_dice.career.store import InjectedSaveFault, SaveError, SqliteProfileStore, StoredCareerService
from battle_dice.content.vocations import load_catalog
from tests.conftest import packaged_content
from tests.spec.test_class_evolution_rules import CASES, RUN_HERE, assert_matches, assert_outcome, load_state

NOW = "2026-11-11T12:00:00Z"
PROFILE = "profile_demo"


@pytest.fixture(scope="module")
def catalog() -> CareerCatalog:
    return CareerCatalog(load_catalog(), packaged_content())


def open_store(path: Path | str, catalog: CareerCatalog) -> SqliteProfileStore:
    return SqliteProfileStore(path, catalog, clock=lambda: NOW)


def dump(store: SqliteProfileStore) -> dict[str, list[tuple[Any, ...]]]:
    """Every row of every table, to prove that a step left the file alone."""
    tables = [row[0] for row in store.conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
    return {table: store.conn.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall() for table in tables}


def seeded(case: dict[str, Any], catalog: CareerCatalog, path: Path) -> tuple[SqliteProfileStore, StoredCareerService, dict[str, str]]:
    """The case's given state saved to a new file and loaded back, with what a save does not hold put back on."""
    given = load_state(case["given"], catalog)
    store = open_store(path, catalog)
    renamed = store.import_state(given)
    stored = StoredCareerService(store, given.profile.profile_id)
    stored.state.encounter = given.encounter  # the run hands these over; a save does not hold them
    for hero_id, hero in given.heroes.items():
        stored.state.heroes[hero_id].combat = copy.deepcopy(hero.combat)
    return store, stored, renamed


def apply(target: Any, step: dict[str, Any]) -> Any:
    if "command" in step:
        return target.submit(copy.deepcopy(step["command"]))
    event = step["event"]
    return target.award_mastery(event) if event["type"] == "AwardEncounterMastery" else target.apply_discovery_signal(event)


def saved_view(service: CareerService) -> dict[str, Any]:
    """The state as a save holds it: without the values a run owns."""
    view = state_view(service)
    for hero in view["heroes"]:
        hero.pop("combat", None)
    return view


def with_saved_event_ids(expected: dict[str, Any], renamed: dict[str, str]) -> dict[str, Any]:
    """A case names earlier claim events by the ids of its own story; the file gave them its own."""
    expected = copy.deepcopy(expected)
    for consumption in expected.get("state", {}).get("profile", {}).get("item_consumptions", []):
        consumption["claim_event"] = renamed.get(consumption["claim_event"], consumption["claim_event"])
    return expected


@pytest.mark.parametrize("case_id", RUN_HERE)
def test_acceptance_fixture_through_the_save_file(case_id: str, catalog: CareerCatalog, tmp_path: Path) -> None:
    case = CASES[case_id]
    path = tmp_path / "save.sqlite"
    store, stored, renamed = seeded(case, catalog, path)
    twin = CareerService(catalog, copy.deepcopy(stored.state))  # the same starting point, in memory only

    for number, step in enumerate(case["given"].get("history", []), start=1):
        where = f"{case_id}.history[{number}]"
        if step["outcome"] == "aborted":  # a real failure inside the SQLite transaction
            file_before, memory_before = dump(store), state_view(stored.service)
            store.fault_after = step["fault_injection"]["after"]
            with pytest.raises(InjectedSaveFault):
                apply(stored, step)
            assert dump(store) == file_before, f"{where}: the failed write left rows in the file"
            assert state_view(stored.service) == memory_before, f"{where}: the failed write left changes in memory"
            twin.fault = {"after": step["fault_injection"]["after"]}
            with pytest.raises(InjectedFault):
                apply(twin, step)
        else:
            saved, plain = apply(stored, step), apply(twin, step)
            assert saved.accepted and (saved.duplicate, saved.events) == (plain.duplicate, plain.events), where
        assert_matches(with_saved_event_ids({"state": step.get("state_after", {})}, renamed)["state"], state_view(stored.service), where)

    file_before = dump(store)
    saved, plain = apply(stored, case["when"]), apply(twin, case["when"])
    assert (saved.result, saved.duplicate, saved.error_code, saved.error_details, saved.events, saved.preview) == (
        plain.result, plain.duplicate, plain.error_code, plain.error_details, plain.events, plain.preview), case_id
    assert_outcome(with_saved_event_ids(case["then"], renamed), saved, stored.service, case_id)
    assert state_view(stored.service) == state_view(twin), f"{case_id}: saving changed what the rules decided"
    if saved.result == "rejected" or saved.duplicate or saved.preview is not None:
        assert dump(store) == file_before, f"{case_id}: a rejected command, a replay or a preview wrote to the file"

    # Close the file and open it again: it holds exactly the result.
    expected = saved_view(stored.service)
    store.close()
    with open_store(path, catalog) as reopened:
        assert saved_view(StoredCareerService(reopened, stored.profile_id).service) == expected, f"{case_id}: lost on reopen"
        assert reopened.verify_event_chain(stored.profile_id) == stored.state.next_event_seq


# --------------------------------------------------------------------------------------------
# Failure in the middle of a write (fixture CE-38, at every fault point)
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("step", ["item_decrement", "unlock_insert"])
def test_a_failed_write_leaves_the_file_and_the_memory_as_they_were(step: str, catalog: CareerCatalog, tmp_path: Path) -> None:
    case = CASES["CE-11"]  # a claim that consumes an item
    store, stored, _ = seeded(case, catalog, tmp_path / "save.sqlite")
    file_before, memory_before = dump(store), state_view(stored.service)
    store.fault_after = step
    with pytest.raises(InjectedSaveFault):
        apply(stored, case["when"])
    assert dump(store) == file_before and state_view(stored.service) == memory_before
    assert not store.conn.in_transaction
    result = apply(stored, case["when"])  # the same command id, once the fault is gone
    assert result.accepted and not result.duplicate
    assert store.conn.execute("SELECT quantity FROM profile_item_balance WHERE item_id = 'drake_scale'").fetchone() == (0,)
    store.close()


# --------------------------------------------------------------------------------------------
# Repeated commands and awards, answered from the file (fixture CE-33)
# --------------------------------------------------------------------------------------------


def test_a_repeated_command_and_a_repeated_award_are_answered_from_the_file_after_a_reopen(catalog: CareerCatalog, tmp_path: Path) -> None:
    case = CASES["CE-11"]
    path = tmp_path / "save.sqlite"
    store, stored, _ = seeded(case, catalog, path)
    assert apply(stored, case["when"]).accepted
    store.close()

    with open_store(path, catalog) as reopened:
        again = StoredCareerService(reopened, PROFILE)
        file_before = dump(reopened)
        replay = apply(again, case["when"])
        assert replay.accepted and replay.duplicate and replay.events == [] and dump(reopened) == file_before
        other = copy.deepcopy(case["when"])
        other["command"]["params"]["target_vocation_id"] = "guardian"  # the same id for another command
        assert apply(again, other).error_code == "COMMAND_ID_REUSED" and dump(reopened) == file_before

    award_case = CASES["CE-21"]
    award_path = tmp_path / "award.sqlite"
    store, stored, _ = seeded(award_case, catalog, award_path)
    first = apply(stored, award_case["when"])
    assert first.accepted and not first.duplicate
    store.close()
    with open_store(award_path, catalog) as reopened:
        again = StoredCareerService(reopened, PROFILE)
        again.state.encounter = stored.state.encounter
        file_before = dump(reopened)
        second = apply(again, award_case["when"])
        assert second.accepted and second.duplicate and dump(reopened) == file_before
        assert again.state.heroes["hero_001"].mastery["squire"].points == 2, "awarded once"


# --------------------------------------------------------------------------------------------
# A save of another catalog version (fixture CE-34)
# --------------------------------------------------------------------------------------------


def test_a_save_of_another_catalog_version_is_refused_and_left_untouched(catalog: CareerCatalog, tmp_path: Path) -> None:
    case = CASES["CE-34"]
    saved_version = case["given"]["profile"]["catalog_version"]
    raw = copy.deepcopy(catalog.raw)
    raw["baseline"]["content_version"] = saved_version
    older = CareerCatalog(raw, packaged_content())
    given = {"profile": {"profile_id": PROFILE}, "heroes": [{**hero, "eligibility_state": "eligible"} for hero in case["given"]["heroes"]]}
    path = tmp_path / "save.sqlite"
    with open_store(path, older) as writer:
        writer.import_state(load_state(given, older))
        rows_of_the_save = {table: rows for table, rows in dump(writer).items() if table not in ("content_catalog", "vocation_def", "skill_def")}

    with open_store(path, catalog) as reader:
        with pytest.raises(SaveError) as refusal:
            reader.load(PROFILE)
        assert refusal.value.code == case["then"]["error_code"] == "CONTENT_MIGRATION_REQUIRED"
        assert refusal.value.details == case["then"]["error_details"]
        after = {table: rows for table, rows in dump(reader).items() if table not in ("content_catalog", "vocation_def", "skill_def")}
        assert after == rows_of_the_save, "no row of the save is changed or deleted"
        states = dict(reader.conn.execute("SELECT catalog_version, state FROM content_catalog"))
        assert states == {saved_version: "retired", catalog.version: "active"}
        with pytest.raises(SaveError):
            StoredCareerService(reader, PROFILE)
    with open_store(path, older) as writer:  # the build that wrote it still reads it
        hero = writer.load(PROFILE).heroes["hero_001"]
        assert (hero.active_vocation_id, hero.revision, hero.mastery["guardian"].points) == ("guardian", 6, 5)


# --------------------------------------------------------------------------------------------
# Run upgrades are history once the run ends (fixture CE-25, owner decision of 2026-11-11)
# --------------------------------------------------------------------------------------------


def test_run_upgrades_stay_in_the_save_after_the_run_and_no_longer_apply(catalog: CareerCatalog, tmp_path: Path) -> None:
    case = CASES["CE-25"]
    path = tmp_path / "save.sqlite"
    given = copy.deepcopy(case["given"])
    given["encounter"] = {"encounter_id": "training_01", "threat_rating": 1, "mastery_eligible": True, "outcome": "victory"}
    store, stored, _ = seeded({"given": given}, catalog, path)
    upgrade = case["given"]["run_die_upgrades"][0]
    store.record_run_upgrade(upgrade["run_id"], "upgrade-1", upgrade["hero_id"], upgrade["die_instance_id"], {"face_index": 0, "kind": "sharpen"})
    assert [(u["die_instance_id"], u["applies"], u["permanent"]) for u in store.run_upgrades("run_0001")] == [("hero_001-iron_d6-1", True, False)]

    for step in case["given"]["history"]:  # the earlier victory
        assert apply(stored, step).accepted
        assert_matches(step["state_after"], state_view(stored.service), "CE-25.history")
    stored.end_run(case["when"]["event"]["run_id"], case["when"]["event"]["outcome"])

    expected = case["then"]["state"]
    assert stored.state.run is not None and stored.state.run.phase == expected["run"]["phase"] == "defeat"
    assert store.conn.execute("SELECT completed_at IS NOT NULL FROM run WHERE run_id = 'run_0001'").fetchone() == (1,)
    assert_matches({"heroes": [{"hero_id": "hero_001", "mastery": expected["heroes"][0]["mastery"]}]}, state_view(stored.service), "CE-25")
    kept = store.run_upgrades("run_0001")
    assert [(u["run_id"], u["hero_id"], u["die_instance_id"], u["permanent"]) for u in kept] == [
        (u["run_id"], u["hero_id"], u["die_instance_id"], u["permanent"]) for u in expected["run_die_upgrades"]
    ], "the rows are kept as history"
    assert [u["applies"] for u in kept] == [expected["heroes"][0]["dice"][0]["run_upgrade_applies"]] == [False]
    with pytest.raises(sqlite3.IntegrityError):  # an upgrade can never be made permanent in this table
        store.conn.execute("UPDATE run_die_upgrade SET permanent = 1")
    with pytest.raises(ValueError, match="not the current run"):
        stored.end_run("run_0002", "defeat")
    store.close()
    with open_store(path, catalog) as reopened:
        assert [u["applies"] for u in reopened.run_upgrades("run_0001")] == [False]
        assert reopened.load(PROFILE).heroes["hero_001"].mastery["squire"].points == 2, "the earlier victory persists"


# --------------------------------------------------------------------------------------------
# The event log, the schema version and what a file may be
# --------------------------------------------------------------------------------------------


def test_a_changed_event_is_detected_when_the_save_is_loaded(catalog: CareerCatalog, tmp_path: Path) -> None:
    path = tmp_path / "save.sqlite"
    store, stored, _ = seeded(CASES["CE-03"], catalog, path)
    assert apply(stored, CASES["CE-03"]["when"]).accepted
    assert store.verify_event_chain(PROFILE) == 4  # three starting vocations and the Guardian claim
    with pytest.raises(sqlite3.IntegrityError):  # the schema refuses the edit outright ...
        store.conn.execute("UPDATE progression_event_log SET event_json = '{}' WHERE event_seq = 3")
    store.conn.execute("DROP TRIGGER trg_progression_event_immutable")  # ... so tamper as someone with the file could
    store.conn.execute("UPDATE progression_event_log SET event_json = ? WHERE event_seq = 3", ('{"vocation_id":"hero"}',))
    with pytest.raises(SaveError, match="changed or is damaged at event 3"):
        store.load(PROFILE)
    store.close()


def test_the_clues_already_counted_are_remembered_across_a_reopen(catalog: CareerCatalog, tmp_path: Path) -> None:
    """Owner decision: each distinct clue counts once. The event log is what remembers them."""
    path = tmp_path / "save.sqlite"
    store, stored, _ = seeded(CASES["CE-10"], catalog, path)
    for signal in ("quest_hint:crooked_mirror", "item_found:jester_mask", "quest_complete:crooked_mirror"):
        stored.apply_discovery_signal({"signal": signal})
    store.close()
    with open_store(path, catalog) as reopened:
        again = StoredCareerService(reopened, PROFILE)
        row = again.state.profile.discovery["trickster"]
        assert (row.state, row.clue_count, len(row.signals_seen)) == ("discovered", 3, 3)
        file_before = dump(reopened)
        repeat = again.apply_discovery_signal({"signal": "quest_hint:crooked_mirror"})
        assert repeat.accepted and repeat.events == [] and row.clue_count == 3 and dump(reopened) == file_before


def test_a_new_file_gets_the_schema_and_the_catalog_and_a_second_open_changes_nothing(catalog: CareerCatalog, tmp_path: Path) -> None:
    path = tmp_path / "nested" / "save.sqlite"
    with open_store(path, catalog) as first:
        assert first.schema_version() == store_module.BASELINE_VERSION == 2 and first.backup_path is None
        assert first.conn.execute("PRAGMA foreign_keys").fetchone() == (1,)
        assert first.conn.execute("SELECT COUNT(*) FROM vocation_def").fetchone() == (14,)
        assert first.conn.execute("SELECT COUNT(*) FROM skill_def").fetchone() == (14,)
        assert dict(first.conn.execute("SELECT family, COUNT(*) FROM vocation_def GROUP BY family")) == {
            "novice": 3, "advanced": 6, "capstone": 3, "secret": 2}
        assert first.profile_ids() == []
        before = dump(first)
    with open_store(path, catalog) as second:
        assert dump(second) == before and second.backup_path is None
        with pytest.raises(SaveError, match="No profile"):
            second.load(PROFILE)
    assert store_module.SCHEMA_PATH.is_file() and store_module.SCHEMA_PATH.parent.parent.name == "career"


def test_a_profile_is_imported_once(catalog: CareerCatalog, tmp_path: Path) -> None:
    store, stored, _ = seeded(CASES["CE-03"], catalog, tmp_path / "save.sqlite")
    with pytest.raises(SaveError, match="already in this save"):
        store.import_state(stored.state)
    assert store.profile_ids() == [PROFILE]
    store.close()


def test_an_older_save_is_backed_up_then_migrated_and_a_newer_one_is_refused(catalog: CareerCatalog, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "save.sqlite"
    store, stored, _ = seeded(CASES["CE-03"], catalog, path)
    assert apply(stored, CASES["CE-03"]["when"]).accepted
    before = saved_view(stored.service)
    store.close()

    # A later build with one more schema version.
    monkeypatch.setitem(store_module.MIGRATIONS, 3, "CREATE TABLE profile_note (profile_id TEXT PRIMARY KEY, note TEXT NOT NULL) STRICT")
    with open_store(path, catalog) as migrated:
        assert migrated.schema_version() == 3 and migrated.backup_path == Path(f"{path}.v2.bak")
        assert migrated.conn.execute("SELECT MAX(version) FROM schema_migration").fetchone() == (3,)
        assert migrated.conn.execute("SELECT COUNT(*) FROM profile_note").fetchone() == (0,)
        assert saved_view(StoredCareerService(migrated, PROFILE).service) == before, "the migration kept every row"
    with open_store(path, catalog) as again:
        assert again.backup_path is None, "already migrated: no second backup"
    with open_store(tmp_path / "fresh.sqlite", catalog) as fresh:
        assert fresh.schema_version() == 3 and fresh.backup_path is None, "a new file has nothing to back up"

    # The backup is the save as it was, readable by the build that wrote it.
    monkeypatch.delitem(store_module.MIGRATIONS, 3)
    with open_store(f"{path}.v2.bak", catalog) as backup:
        assert backup.schema_version() == 2 and saved_view(StoredCareerService(backup, PROFILE).service) == before
    with pytest.raises(SaveError, match="written by a newer build"):
        open_store(path, catalog)


def test_a_failed_migration_leaves_the_save_at_its_old_version(catalog: CareerCatalog, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "save.sqlite"
    store, _, _ = seeded(CASES["CE-03"], catalog, path)
    before = dump(store)
    store.close()
    monkeypatch.setitem(store_module.MIGRATIONS, 3, "CREATE TABLE profile_note (id INTEGER PRIMARY KEY) STRICT; INSERT INTO no_such_table VALUES (1)")
    with pytest.raises(sqlite3.OperationalError):
        open_store(path, catalog)
    monkeypatch.delitem(store_module.MIGRATIONS, 3)
    with open_store(path, catalog) as intact:
        assert intact.schema_version() == 2 and dump(intact) == before


def test_a_file_that_is_not_a_save_is_refused(catalog: CareerCatalog, tmp_path: Path) -> None:
    stranger = tmp_path / "other.sqlite"
    with sqlite3.connect(stranger) as other:
        other.execute("CREATE TABLE notes (text TEXT)")
    other.close()
    with pytest.raises(SaveError, match="not a Battle Dice save"):
        open_store(stranger, catalog)


def test_an_award_needs_its_run_in_the_save(catalog: CareerCatalog, tmp_path: Path) -> None:
    case = copy.deepcopy(CASES["CE-21"])
    case["given"]["run"] = None
    store, stored, _ = seeded(case, catalog, tmp_path / "save.sqlite")
    file_before, memory_before = dump(store), state_view(stored.service)
    with pytest.raises(SaveError, match="which is not in the save"):
        apply(stored, case["when"])
    assert dump(store) == file_before and state_view(stored.service) == memory_before
    store.close()
