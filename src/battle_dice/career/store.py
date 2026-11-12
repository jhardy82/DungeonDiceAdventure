"""Saving the career state: a SQLite profile store over the approved schema (Class Evolution Phase 3).

The rules stay where they are (``career/service.py``): they decide in memory. This module writes
what they decided. After an accepted change the difference between the state before and the state
after is written in **one** ``BEGIN IMMEDIATE`` transaction; if that fails, nothing is in the file
and the memory state is put back. A rejected command writes nothing.

The schema is ``career/schema/progression.sql`` (24 tables, FDD v0.2). The file is opened only when
the feature gate ``class_evolution_v1`` is on; nothing in the game opens it yet.

What the file does not hold: a hero's values inside a run (``HeroRecord.combat``) and the result
of the encounter that just ended. The run owns those and hands them over.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import battle_dice
from battle_dice import RNG_ALGORITHM
from battle_dice.career.catalog import MASTERED_RANK, CareerCatalog
from battle_dice.career.model import (
    AwardRow,
    CareerState,
    DieInstance,
    DiscoveryRow,
    HeroRecord,
    MasteryRow,
    ProcessedCommand,
    Profile,
    RunInfo,
)
from battle_dice.career.service import CareerResult, CareerService
from battle_dice.content.loader import canonical_json

Json = dict[str, Any]

SCHEMA_PATH = Path(__file__).resolve().parent / "schema" / "progression.sql"
#: The schema version of ``progression.sql``. Later versions are reached through ``MIGRATIONS``.
BASELINE_VERSION = 2
#: version -> SQL that takes a file from the version before it to this one (it must not touch ``user_version``).
MIGRATIONS: dict[int, str] = {}
#: Oldest SQLite the schema runs on: STRICT tables (3.37.0) and built-in ``json_valid`` (3.38.0).
MIN_SQLITE_VERSION = (3, 38, 0)
ZERO_HASH = "0" * 64
UNKNOWN_SHA = "0" * 64
FINISHED_PHASES = ("victory", "defeat")
CLUE_EVENTS = ("DiscoveryChanged", "DiscoveryClueCounted")


class SaveError(RuntimeError):
    """The save cannot be opened or written as it is. ``code`` is a registry code where one applies."""

    def __init__(self, code: str, message: str, details: Json | None = None):
        super().__init__(message)
        self.code, self.details = code, details or {}


class InjectedSaveFault(RuntimeError):
    """Raised by a test-only fault point inside a write, to prove that the file keeps nothing of it."""


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def event_hash(previous_event_hash: str, event_id: str, event_type: str, event_json: str) -> str:
    """``SHA-256(previous hash, event id, event type, canonical event JSON)``, joined by newlines."""
    return sha256_hex("\n".join((previous_event_hash, event_id, event_type, event_json)))


def target_version() -> int:
    return max([BASELINE_VERSION, *MIGRATIONS])


class SqliteProfileStore:
    """One save file. ``path`` may be ``":memory:"``. The caller closes the store."""

    def __init__(self, path: str | Path, catalog: CareerCatalog, clock: Callable[[], str] = utc_now):
        if sqlite3.sqlite_version_info < MIN_SQLITE_VERSION:
            raise SaveError("", f"SQLite {sqlite3.sqlite_version} is too old: the save needs 3.38 or later.")
        self.path = str(path)
        self.catalog = catalog
        self.clock = clock
        #: Test-only: the name of the write step after which the next commit fails.
        self.fault_after: str | None = None
        self.backup_path: Path | None = None
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, isolation_level=None)  # autocommit: every transaction is explicit
        try:
            self.conn.execute("PRAGMA foreign_keys = ON")
            self._create_or_migrate()
            self._install_catalog()
        except BaseException:
            self.conn.close()
            raise

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> SqliteProfileStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ----------------------------------------------------------------------------------------
    # Schema: create, check, migrate
    # ----------------------------------------------------------------------------------------

    def schema_version(self) -> int:
        return int(self.conn.execute("PRAGMA user_version").fetchone()[0])

    def _create_or_migrate(self) -> None:
        conn = self.conn
        empty = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'").fetchone()[0] == 0
        if empty:
            conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))  # the script is one transaction
        version = self.schema_version()
        try:
            recorded = conn.execute("SELECT MAX(version) FROM schema_migration").fetchone()[0]
        except sqlite3.Error:
            recorded = None  # some other SQLite file
        if version < BASELINE_VERSION or recorded != version:
            raise SaveError("", f"This file is not a Battle Dice save (schema version {version}, migrations {recorded}).")
        if version > target_version():
            raise SaveError("", f"This save was written by a newer build (schema {version}; this build reads up to {target_version()}).")
        pending = [v for v in sorted(MIGRATIONS) if v > version]
        if not pending:
            return
        if not empty and self.path != ":memory:":
            # A copy of the save as it was, made through SQLite itself so an open file is copied whole.
            self.backup_path = Path(f"{self.path}.v{version}.bak")
            with sqlite3.connect(str(self.backup_path)) as copy_to:
                conn.backup(copy_to)
            copy_to.close()
        conn.execute("BEGIN IMMEDIATE")
        try:
            for new_version in pending:
                for statement in _statements(MIGRATIONS[new_version]):
                    conn.execute(statement)
                conn.execute("INSERT INTO schema_migration(version, description, applied_at) VALUES (?, ?, ?)",
                             (new_version, f"migration to schema version {new_version}", self.clock()))
            conn.execute(f"PRAGMA user_version = {pending[-1]}")
            conn.execute("COMMIT")
        except BaseException:
            self._rollback()
            raise

    def _install_catalog(self) -> None:
        """Make sure the active catalog and its vocation and skill rows are in the file (other rows reference them)."""
        catalog, conn, version = self.catalog, self.conn, self.catalog.version
        if conn.execute("SELECT 1 FROM content_catalog WHERE catalog_version = ?", (version,)).fetchone():
            return
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "INSERT INTO content_catalog(catalog_version, content_sha256, rules_version, state, installed_at) VALUES (?, ?, ?, 'active', ?)",
                (version, catalog.content.content_hash, battle_dice.RULES_VERSION, self.clock()),
            )
            conn.execute("UPDATE content_catalog SET state = 'retired' WHERE catalog_version <> ?", (version,))
            for vocation_id, vocation in catalog.vocations.items():
                name = vocation.get("name") or catalog.content.class_def(vocation["class_id"])["name"]
                visibility = vocation.get("visibility", "public")
                conn.execute(
                    "INSERT INTO vocation_def(catalog_version, vocation_id, display_name, family, visibility, definition_json) VALUES (?, ?, ?, ?, ?, ?)",
                    (version, vocation_id, name, catalog.group(vocation_id).split("_")[0], visibility, canonical_json(vocation)),
                )
            for skill_id, skill in catalog.skills.items():
                conn.execute("INSERT INTO skill_def(catalog_version, skill_id, definition_json) VALUES (?, ?, ?)",
                             (version, skill_id, canonical_json(skill)))
            conn.execute("COMMIT")
        except BaseException:
            self._rollback()
            raise

    def _rollback(self) -> None:
        if self.conn.in_transaction:
            self.conn.execute("ROLLBACK")

    # ----------------------------------------------------------------------------------------
    # Reading
    # ----------------------------------------------------------------------------------------

    def profile_ids(self) -> list[str]:
        return [row[0] for row in self.conn.execute("SELECT profile_id FROM player_profile ORDER BY rowid")]

    def load(self, profile_id: str) -> CareerState:
        """The saved state of one profile. Refuses a save of another catalog version and leaves it untouched."""
        conn, version = self.conn, self.catalog.version
        row = conn.execute("SELECT current_catalog_version FROM player_profile WHERE profile_id = ?", (profile_id,)).fetchone()
        if row is None:
            raise SaveError("", f"No profile '{profile_id}' in this save.")
        if row[0] != version:
            raise SaveError("CONTENT_MIGRATION_REQUIRED", f"The profile was saved with catalog {row[0]}; this build has {version}.",
                            {"saved_catalog_version": row[0], "active_catalog_version": version})
        self.verify_event_chain(profile_id)

        profile = Profile(profile_id)
        for vocation_id, state, clues in conn.execute(
            "SELECT vocation_id, discovery_state, clue_count FROM profile_vocation_discovery WHERE profile_id = ? ORDER BY rowid", (profile_id,)
        ):
            profile.discovery[vocation_id] = DiscoveryRow(vocation_id, state, clues)
        for event_type, event_json in conn.execute(
            "SELECT event_type, event_json FROM progression_event_log WHERE profile_id = ? ORDER BY event_seq", (profile_id,)
        ):
            if event_type in CLUE_EVENTS:  # the log remembers which clues were already counted
                payload = json.loads(event_json)
                seen = profile.discovery[payload["vocation_id"]].signals_seen
                if payload["signal"] not in seen:
                    seen.append(payload["signal"])
        profile.items = dict(conn.execute("SELECT item_id, quantity FROM profile_item_balance WHERE profile_id = ? ORDER BY rowid", (profile_id,)))
        profile.item_consumptions = [
            {"hero_id": hero_id, "item_id": item_id, "quantity": quantity, "claim_event": claim}
            for hero_id, item_id, quantity, claim in conn.execute(
                "SELECT hero_id, item_id, quantity, claim_event_id FROM item_consumption WHERE profile_id = ? ORDER BY rowid", (profile_id,))
        ]
        profile.quests_completed = [
            {"quest_id": quest_id, "qualifier_scope": scope, "qualifier_id": qualifier}
            for quest_id, scope, qualifier in conn.execute(
                "SELECT quest_id, qualifier_scope, qualifier_id FROM quest_completion WHERE profile_id = ? ORDER BY rowid", (profile_id,))
        ]

        state = CareerState(profile)
        heroes = conn.execute(
            "SELECT hero_id, active_vocation_id, eligibility_state, revision, origin_vocation_id, display_name FROM hero "
            "WHERE profile_id = ? ORDER BY rowid", (profile_id,)).fetchall()
        for hero_id, active, eligibility, revision, origin, name in heroes:
            hero = HeroRecord(hero_id, active, eligibility, revision, origin_vocation_id=origin, display_name=name)
            for vocation_id, route_id in conn.execute(
                "SELECT vocation_id, unlock_route_id FROM hero_vocation_unlock WHERE hero_id = ? ORDER BY rowid", (hero_id,)):
                hero.unlocked_vocations.append(vocation_id)
                hero.unlock_routes[vocation_id] = route_id
            for vocation_id, points, rank in conn.execute(
                "SELECT vocation_id, mastery_points, mastery_rank FROM hero_vocation_mastery WHERE hero_id = ? ORDER BY rowid", (hero_id,)):
                hero.mastery[vocation_id] = MasteryRow(vocation_id, rank, points)
            hero.learned_skills = [r[0] for r in conn.execute("SELECT skill_id FROM hero_skill WHERE hero_id = ? ORDER BY rowid", (hero_id,))]
            hero.equipped_skills = dict(conn.execute("SELECT slot_index, skill_id FROM hero_equipped_skill WHERE hero_id = ? ORDER BY slot_index", (hero_id,)))
            slots = dict(conn.execute("SELECT die_instance_id, slot_index FROM hero_equipped_die WHERE hero_id = ?", (hero_id,)))
            for instance_id, definition_id, location in conn.execute(
                "SELECT die_instance_id, definition_id, location FROM hero_die_instance WHERE hero_id = ? ORDER BY rowid", (hero_id,)):
                hero.dice.append(DieInstance(instance_id, definition_id, location, slots.get(instance_id)))
            state.heroes[hero_id] = hero

        run = conn.execute("SELECT run_id, phase, revision FROM run WHERE profile_id = ? ORDER BY rowid DESC LIMIT 1", (profile_id,)).fetchone()
        if run is not None:
            state.run = RunInfo(*run)
        state.awards = [
            AwardRow(*award) for award in conn.execute(
                "SELECT a.run_id, a.encounter_id, a.hero_id, a.vocation_id, a.base_points, a.challenge_points, a.threat_rating, a.denial_reason "
                "FROM mastery_award_event a JOIN hero h ON h.hero_id = a.hero_id WHERE h.profile_id = ? ORDER BY a.rowid", (profile_id,))
        ]
        for command_id, command_type, sha, result_json in conn.execute(
            "SELECT command_id, command_type, command_sha256, result_json FROM processed_command WHERE profile_id = ? ORDER BY rowid", (profile_id,)):
            state.processed[command_id] = ProcessedCommand(command_id, command_type, json.loads(result_json), None if sha == UNKNOWN_SHA else sha)
        state.next_event_seq = conn.execute("SELECT COUNT(*) FROM progression_event_log WHERE profile_id = ?", (profile_id,)).fetchone()[0]
        return state

    def verify_event_chain(self, profile_id: str) -> int:
        """Recompute every event hash of a profile. Returns the number of events; raises on a break."""
        previous, count = ZERO_HASH, 0
        rows = self.conn.execute(
            "SELECT event_seq, event_id, event_type, event_json, previous_event_hash, event_hash FROM progression_event_log "
            "WHERE profile_id = ? ORDER BY event_seq", (profile_id,))
        for event_seq, event_id, event_type, event_json, stored_previous, stored_hash in rows:
            if event_seq != count or stored_previous != previous or stored_hash != event_hash(previous, event_id, event_type, event_json):
                raise SaveError("", f"The event log of '{profile_id}' was changed or is damaged at event {event_seq}.")
            previous, count = stored_hash, count + 1
        return count

    def run_count(self, profile_id: str) -> int:
        """How many runs this profile has started, finished or not."""
        return int(self.conn.execute("SELECT COUNT(*) FROM run WHERE profile_id = ?", (profile_id,)).fetchone()[0])

    def has_run(self, run_id: str) -> bool:
        return self.conn.execute("SELECT 1 FROM run WHERE run_id = ?", (run_id,)).fetchone() is not None

    def run_upgrades(self, run_id: str) -> list[Json]:
        """Every die upgrade recorded for a run. ``applies`` is false once the run has ended: the rows stay as history."""
        finished = self.conn.execute("SELECT phase FROM run WHERE run_id = ?", (run_id,)).fetchone()
        applies = finished is not None and finished[0] not in FINISHED_PHASES
        return [
            {"run_id": run_id, "upgrade_id": upgrade_id, "hero_id": hero_id, "die_instance_id": die, "override": json.loads(override),
             "permanent": False, "applies": applies}
            for upgrade_id, hero_id, die, override in self.conn.execute(
                "SELECT upgrade_id, hero_id, die_instance_id, override_json FROM run_die_upgrade WHERE run_id = ? ORDER BY rowid", (run_id,))
        ]

    # ----------------------------------------------------------------------------------------
    # Writing
    # ----------------------------------------------------------------------------------------

    def import_state(self, state: CareerState) -> dict[str, str]:
        """Save a profile that is not in the file yet. Returns ``{event id in the state: event id in the file}``.

        The state may come from anywhere (a new profile, a test). What the schema needs and the
        state does not carry is written the way the game itself would have produced it: every
        vocation a hero has is claimed by an event, and every item held was granted.
        """
        profile_id = state.profile.profile_id
        if self.conn.execute("SELECT 1 FROM player_profile WHERE profile_id = ?", (profile_id,)).fetchone():
            raise SaveError("", f"Profile '{profile_id}' is already in this save.")
        renamed: dict[str, str] = {}

        def write(conn: sqlite3.Connection, now: str) -> None:
            version = self.catalog.version
            conn.execute("INSERT INTO player_profile(profile_id, current_catalog_version, created_at, revision) VALUES (?, ?, ?, 0)",
                         (profile_id, version, now))
            empty = CareerState(Profile(profile_id))
            if state.run is not None:
                self._write_run(conn, profile_id, state.run, now)
            for run_id in sorted({row.run_id for row in state.awards} - ({state.run.run_id} if state.run else set())):
                self._write_run(conn, profile_id, RunInfo(run_id, "victory"), now)
            consumed_by: dict[tuple[str, str], str] = {}
            for hero in state.heroes.values():
                origin = hero.origin_vocation_id or (hero.unlocked_vocations[0] if hero.unlocked_vocations else hero.active_vocation_id)
                conn.execute(
                    "INSERT INTO hero(hero_id, profile_id, catalog_version, origin_vocation_id, active_vocation_id, display_name, "
                    "eligibility_state, revision, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (hero.hero_id, profile_id, version, origin, origin, hero.display_name or hero.hero_id, hero.eligibility_state, hero.revision, now))
                claims = {c["claim_event"]: c for c in state.profile.item_consumptions if c["hero_id"] == hero.hero_id}
                for vocation_id in hero.unlocked_vocations:
                    route_id = hero.unlock_routes.get(vocation_id, "route_0")
                    old_id = next((event for event, c in claims.items() if self._route_consumes(vocation_id, route_id, c["item_id"])), None)
                    consumed = [{"item_id": claims[old_id]["item_id"], "quantity": claims[old_id]["quantity"]}] if old_id else []
                    event_id = self._append_event(conn, profile_id, "VocationClaimed", now, {
                        "hero_id": hero.hero_id, "vocation_id": vocation_id, "route_id": route_id, "consumed_items": consumed})
                    conn.execute(
                        "INSERT INTO hero_vocation_unlock(hero_id, catalog_version, vocation_id, unlock_route_id, claim_event_id, unlocked_at) "
                        "VALUES (?, ?, ?, ?, ?, ?)", (hero.hero_id, version, vocation_id, route_id, event_id, now))
                    if old_id:
                        renamed[old_id] = event_id
                        consumed_by[(hero.hero_id, old_id)] = event_id
                blank = HeroRecord(hero.hero_id, origin, hero.eligibility_state, hero.revision, unlocked_vocations=list(hero.unlocked_vocations))
                self._write_hero(conn, blank, hero, now, new_unlocks={})
            missing = [c for c in state.profile.item_consumptions if (c["hero_id"], c["claim_event"]) not in consumed_by]
            if missing:
                raise SaveError("", f"No unlocked vocation of the hero consumes the item of {missing[0]}.")
            for item_id, quantity in state.profile.items.items():
                used = sum(c["quantity"] for c in state.profile.item_consumptions if c["item_id"] == item_id)
                if quantity + used > 0:
                    conn.execute("INSERT INTO item_grant(grant_id, profile_id, item_id, quantity, granted_at) VALUES (?, ?, ?, ?, ?)",
                                 (f"import:{profile_id}:{item_id}", profile_id, item_id, quantity + used, now))
            after = copy.copy(state)
            after.profile = copy.copy(state.profile)
            after.profile.item_consumptions = [{**c, "claim_event": consumed_by[(c["hero_id"], c["claim_event"])]} for c in state.profile.item_consumptions]
            self._write_items(conn, empty, after)
            self._write_profile_rows(conn, empty, after, now)

        self._transaction(write)
        return renamed

    def commit(self, before: CareerState, after: CareerState, run_id: str | None = None) -> None:
        """Write what changed between two states of the same profile, in one transaction."""
        profile_id = after.profile.profile_id

        def write(conn: sqlite3.Connection, now: str) -> None:
            if after.run is not None and after.run != before.run:
                self._write_run(conn, profile_id, after.run, now)
            new_events = after.events[len(before.events):]
            for event in new_events:
                payload = {key: value for key, value in event.items() if key not in ("type", "event_id", "event_seq")}
                event_id = self._append_event(conn, profile_id, event["type"], now, payload, run_id)
                if event_id != event["event_id"]:
                    raise SaveError("", f"The save expected event {event_id} next, the rules produced {event['event_id']}.")
            self._write_items(conn, before, after)
            self._fault("item_decrement")
            for hero_id, hero in after.heroes.items():
                claimed = {e["vocation_id"]: e["event_id"] for e in new_events if e["type"] == "VocationClaimed" and e["hero_id"] == hero_id}
                earlier = before.heroes.get(hero_id)
                if earlier is None:  # a hero recruited by this change
                    origin = hero.origin_vocation_id or hero.active_vocation_id
                    conn.execute(
                        "INSERT INTO hero(hero_id, profile_id, catalog_version, origin_vocation_id, active_vocation_id, display_name, "
                        "eligibility_state, revision, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (hero_id, profile_id, self.catalog.version, origin, hero.active_vocation_id, hero.display_name or hero_id,
                         hero.eligibility_state, hero.revision, now))
                    earlier = HeroRecord(hero_id, hero.active_vocation_id, hero.eligibility_state, hero.revision)
                self._write_hero(conn, earlier, hero, now, claimed)
            self._fault("unlock_insert")
            self._write_profile_rows(conn, before, after, now)
            conn.execute("UPDATE player_profile SET revision = revision + 1 WHERE profile_id = ?", (profile_id,))

        self._transaction(write)

    def record_run_upgrade(self, run_id: str, upgrade_id: str, hero_id: str, die_instance_id: str, override: Json) -> None:
        """A die upgrade chosen inside a run. It belongs to that run and is never permanent."""
        self._transaction(lambda conn, now: conn.execute(
            "INSERT INTO run_die_upgrade(run_id, upgrade_id, hero_id, die_instance_id, override_json, permanent, applied_at) "
            "VALUES (?, ?, ?, ?, ?, 0, ?)", (run_id, upgrade_id, hero_id, die_instance_id, canonical_json(override), now)))

    def _transaction(self, write: Callable[[sqlite3.Connection, str], Any]) -> None:
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            write(self.conn, self.clock())
            self.conn.execute("COMMIT")
        except BaseException:
            self._rollback()
            raise

    def _fault(self, step: str) -> None:
        if self.fault_after == step:
            self.fault_after = None
            raise InjectedSaveFault(f"fault injected after '{step}'")

    def _route_consumes(self, vocation_id: str, route_id: str, item_id: str) -> bool:
        """True when that unlock route of the vocation names the item."""
        return f'"item":"{item_id}"' in canonical_json(self.catalog.routes[vocation_id].get(route_id, {}))

    def _append_event(self, conn: sqlite3.Connection, profile_id: str, event_type: str, now: str, payload: Json, run_id: str | None = None) -> str:
        last = conn.execute("SELECT event_seq, event_hash FROM progression_event_log WHERE profile_id = ? ORDER BY event_seq DESC LIMIT 1",
                            (profile_id,)).fetchone()
        seq, previous = (0, ZERO_HASH) if last is None else (last[0] + 1, last[1])
        event_id, event_json = f"{profile_id}:{seq}", canonical_json(payload)
        conn.execute(
            "INSERT INTO progression_event_log(profile_id, event_seq, event_id, run_id, event_type, event_json, previous_event_hash, "
            "event_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (profile_id, seq, event_id, run_id, event_type, event_json, previous, event_hash(previous, event_id, event_type, event_json), now))
        return event_id

    def _write_run(self, conn: sqlite3.Connection, profile_id: str, run: RunInfo, now: str) -> None:
        """Phase 3 saves what the career rules know of a run. Seed and build hash arrive with Phase 4."""
        done = now if run.phase in FINISHED_PHASES else None
        exists = conn.execute("SELECT 1 FROM run WHERE run_id = ?", (run.run_id,)).fetchone()
        if exists:
            conn.execute("UPDATE run SET phase = ?, revision = ?, completed_at = COALESCE(completed_at, ?) WHERE run_id = ?",
                         (run.phase, run.revision, done, run.run_id))
            return
        conn.execute(
            "INSERT INTO run(run_id, profile_id, catalog_version, content_sha256, rules_version, rng_version, seed_decimal, build_sha256, "
            "phase, revision, started_at, completed_at) VALUES (?, ?, ?, ?, ?, ?, '0', ?, ?, ?, ?, ?)",
            (run.run_id, profile_id, self.catalog.version, self.catalog.content.content_hash, battle_dice.RULES_VERSION, RNG_ALGORITHM,
             sha256_hex(canonical_json([])), run.phase, run.revision, now, done))

    def _write_items(self, conn: sqlite3.Connection, before: CareerState, after: CareerState) -> None:
        profile_id = after.profile.profile_id
        for item_id, quantity in after.profile.items.items():
            if item_id not in before.profile.items:
                conn.execute("INSERT INTO profile_item_balance(profile_id, item_id, quantity, revision) VALUES (?, ?, ?, 0)",
                             (profile_id, item_id, quantity))
            elif before.profile.items[item_id] != quantity:
                conn.execute("UPDATE profile_item_balance SET quantity = ?, revision = revision + 1 WHERE profile_id = ? AND item_id = ?",
                             (quantity, profile_id, item_id))

    def _write_hero(self, conn: sqlite3.Connection, before: HeroRecord, hero: HeroRecord, now: str, new_unlocks: dict[str, str]) -> None:
        version, hero_id = self.catalog.version, hero.hero_id
        for vocation_id in hero.unlocked_vocations:
            if vocation_id not in before.unlocked_vocations:
                conn.execute(
                    "INSERT INTO hero_vocation_unlock(hero_id, catalog_version, vocation_id, unlock_route_id, claim_event_id, unlocked_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)", (hero_id, version, vocation_id, hero.unlock_routes[vocation_id], new_unlocks[vocation_id], now))
        for vocation_id, row in hero.mastery.items():
            old = before.mastery.get(vocation_id)
            if old is None:
                conn.execute(
                    "INSERT INTO hero_vocation_mastery(hero_id, catalog_version, vocation_id, mastery_points, mastery_rank, completed_at, revision) "
                    "VALUES (?, ?, ?, ?, ?, ?, 0)", (hero_id, version, vocation_id, row.points, row.rank, now if row.rank >= MASTERED_RANK else None))
            elif (old.points, old.rank) != (row.points, row.rank):
                conn.execute(
                    "UPDATE hero_vocation_mastery SET mastery_points = ?, mastery_rank = ?, revision = revision + 1, "
                    "completed_at = CASE WHEN ? THEN COALESCE(completed_at, ?) ELSE NULL END WHERE hero_id = ? AND catalog_version = ? AND vocation_id = ?",
                    (row.points, row.rank, row.rank >= MASTERED_RANK, now, hero_id, version, vocation_id))
        for skill_id in hero.learned_skills:
            if skill_id not in before.learned_skills:
                conn.execute("INSERT INTO hero_skill(hero_id, catalog_version, skill_id, acquired_from_vocation_id, learned_at) VALUES (?, ?, ?, ?, ?)",
                             (hero_id, version, skill_id, self.catalog.skill_origin[skill_id][0], now))
        if (before.active_vocation_id, before.eligibility_state, before.revision) != (hero.active_vocation_id, hero.eligibility_state, hero.revision):
            conn.execute("UPDATE hero SET active_vocation_id = ?, eligibility_state = ?, revision = ? WHERE hero_id = ?",
                         (hero.active_vocation_id, hero.eligibility_state, hero.revision, hero_id))
        if before.equipped_skills != hero.equipped_skills:
            conn.execute("DELETE FROM hero_equipped_skill WHERE hero_id = ?", (hero_id,))
            for slot, skill_id in sorted(hero.equipped_skills.items()):
                conn.execute("INSERT INTO hero_equipped_skill(hero_id, catalog_version, slot_index, skill_id) VALUES (?, ?, ?, ?)",
                             (hero_id, version, slot, skill_id))
        owned = {die.die_instance_id for die in before.dice}
        for die in hero.dice:
            if die.die_instance_id not in owned:  # a die always arrives on the bench; the slot table moves it
                conn.execute(
                    "INSERT INTO hero_die_instance(die_instance_id, hero_id, definition_id, definition_version, location, acquisition_key, acquired_at) "
                    "VALUES (?, ?, ?, 1, 'bench', ?, ?)", (die.die_instance_id, hero_id, die.definition_id, f"starter:{die.die_instance_id}", now))
        slots_before = {die.slot_index or 0: die.die_instance_id for die in before.dice if die.location == "equipped"}
        slots_after = {die.slot_index or 0: die for die in hero.dice if die.location == "equipped"}
        if slots_before != {slot: equipped.die_instance_id for slot, equipped in slots_after.items()}:
            conn.execute("DELETE FROM hero_equipped_die WHERE hero_id = ?", (hero_id,))
            for slot in sorted(slots_after):
                equipped = slots_after[slot]
                conn.execute("INSERT INTO hero_equipped_die(hero_id, slot_index, die_instance_id, definition_id, definition_version) VALUES (?, ?, ?, ?, 1)",
                             (hero_id, slot, equipped.die_instance_id, equipped.definition_id))

    def _write_profile_rows(self, conn: sqlite3.Connection, before: CareerState, after: CareerState, now: str) -> None:
        """Rows that hang off the profile: consumptions, discovery, quests, awards, processed commands."""
        profile_id, version = after.profile.profile_id, self.catalog.version
        for consumption in after.profile.item_consumptions[len(before.profile.item_consumptions):]:
            conn.execute(
                "INSERT INTO item_consumption(consumption_id, profile_id, hero_id, item_id, quantity, claim_event_id, consumed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (f"{consumption['claim_event']}:{consumption['item_id']}", profile_id, consumption["hero_id"], consumption["item_id"],
                 consumption["quantity"], consumption["claim_event"], now))
        for vocation_id, row in after.profile.discovery.items():
            old = before.profile.discovery.get(vocation_id)
            if old is None:
                conn.execute(
                    "INSERT INTO profile_vocation_discovery(profile_id, catalog_version, vocation_id, discovery_state, clue_count, modified_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)", (profile_id, version, vocation_id, row.state, row.clue_count, now))
            elif (old.state, old.clue_count) != (row.state, row.clue_count):
                conn.execute(
                    "UPDATE profile_vocation_discovery SET discovery_state = ?, clue_count = ?, modified_at = ? "
                    "WHERE profile_id = ? AND catalog_version = ? AND vocation_id = ?", (row.state, row.clue_count, now, profile_id, version, vocation_id))
        for done in after.profile.quests_completed[len(before.profile.quests_completed):]:
            conn.execute("INSERT INTO quest_completion(profile_id, quest_id, qualifier_scope, qualifier_id, completed_at) VALUES (?, ?, ?, ?, ?)",
                         (profile_id, done["quest_id"], done["qualifier_scope"], done["qualifier_id"], now))
        for award in after.awards[len(before.awards):]:
            if not conn.execute("SELECT 1 FROM run WHERE run_id = ?", (award.run_id,)).fetchone():
                raise SaveError("", f"The mastery award names run '{award.run_id}', which is not in the save.")
            conn.execute(
                "INSERT INTO mastery_award_event(event_id, run_id, encounter_id, hero_id, catalog_version, vocation_id, base_points, "
                "challenge_points, threat_rating, denial_reason, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (":".join(award.identity), award.run_id, award.encounter_id, award.hero_id, version, award.vocation_id, award.base_points,
                 award.challenge_points, award.threat_rating, award.denial_reason, now))
        for command_id, done_command in after.processed.items():
            if command_id not in before.processed:
                conn.execute(
                    "INSERT INTO processed_command(command_scope, command_id, profile_id, command_type, command_sha256, result_json, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (f"profile:{profile_id}", command_id, profile_id, done_command.type, done_command.fingerprint or UNKNOWN_SHA,
                     canonical_json(done_command.result), now))


def _statements(script: str) -> list[str]:
    """The statements of a migration script (no semicolon may appear inside a statement)."""
    return [statement.strip() for statement in script.split(";") if statement.strip()]


class StoredCareerService:
    """The career rules with every accepted change written to the save before it is acknowledged."""

    def __init__(self, store: SqliteProfileStore, profile_id: str):
        self.store = store
        self.profile_id = profile_id
        self.service = CareerService(store.catalog, store.load(profile_id))

    @property
    def state(self) -> CareerState:
        return self.service.state

    def submit(self, command: Json) -> CareerResult:
        return self._saved(lambda: self.service.submit(command))

    def award_mastery(self, event: Json) -> CareerResult:
        run = self.state.run
        return self._saved(lambda: self.service.award_mastery(event), run.run_id if run is not None and run.run_id == event["run_id"] else None)

    def apply_discovery_signal(self, event: Json) -> CareerResult:
        return self._saved(lambda: self.service.apply_discovery_signal(event))

    def grant_mastery(self, hero_id: str, vocation_id: str, points: int, reason: str) -> CareerResult:
        return self._saved(lambda: self.service.grant_mastery(hero_id, vocation_id, points, reason))

    def rederive_ranks(self, reason: str) -> CareerResult:
        return self._saved(lambda: self.service.rederive_ranks(reason))

    def begin_run(self, run_id: str) -> None:
        """Trusted event ``RunStarted``: a run of this profile has begun and is in its first battle.

        The save holds what the career rules know of a run: its id, phase and revision. The seed and
        the build snapshots arrive with Phase 4.
        """
        run = self.state.run
        if run is not None and run.phase not in FINISHED_PHASES:
            raise ValueError(f"'{run.run_id}' is still being played.")
        if self.store.has_run(run_id):
            raise ValueError(f"'{run_id}' is already in the save; a run id is used once.")
        before = copy.deepcopy(self.state)
        self.state.run = RunInfo(run_id, "battle")
        self._write(before)

    def report_run(self, phase: str, revision: int) -> None:
        """Trusted event: the current run moved on. ``phase`` is a saved phase (``model.saved_run_phase``)."""
        run = self.state.run
        if run is None or run.phase in FINISHED_PHASES:
            raise ValueError("There is no run in progress to report on.")
        if phase in FINISHED_PHASES:
            raise ValueError("A run is finished with end_run, not reported as finished.")
        if (run.phase, run.revision) == (phase, revision):
            return
        before = copy.deepcopy(self.state)
        run.phase, run.revision = phase, revision
        self._write(before)

    def end_run(self, run_id: str, outcome: str) -> None:
        """Trusted event ``RunEnded``: the run is finished. Its die upgrades stay as history and stop applying."""
        run = self.state.run
        if run is None or run.run_id != run_id or outcome not in FINISHED_PHASES:
            raise ValueError(f"'{run_id}' is not the current run, or '{outcome}' is not how a run ends.")
        before = copy.deepcopy(self.state)
        run.phase = outcome
        self._write(before)

    def _saved(self, change: Callable[[], CareerResult], run_id: str | None = None) -> CareerResult:
        before = copy.deepcopy(self.state)
        result = change()
        if result.accepted and not result.duplicate and self.state != before:  # a preview, for one, changes nothing
            self._write(before, run_id)
        return result

    def _write(self, before: CareerState, run_id: str | None = None) -> None:
        try:
            self.store.commit(before, self.state, run_id)
        except BaseException:
            self.service.state = before  # nothing was saved, so nothing is kept in memory either
            raise
