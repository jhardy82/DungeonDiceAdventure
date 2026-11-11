"""Check the Class Evolution persistence contract (FDD v0.2). Specification only.

Nothing in the shipped game uses this module. It executes the proposed schema
(``src/battle_dice/career/schema/progression.sql``) in an in-memory SQLite database, loads
the example profile and shows the reference transactions the schema is designed for:

* ``create_database``: a new in-memory database with the schema and foreign keys on.
* ``load_example``: inserts ``example_profile.json``, including the catalog rows its foreign
  keys need, and checks every hash and derived number the example states.
* ``grant_item``: the item grant ledger; a repeated grant id grants nothing.
* ``claim_with_item``: the atomic claim (item decrement, event, unlock, consumption, command
  record), idempotent on the command id.
* ``reset_profile``: the documented reset sequence.

Run ``python tools/class_evolution/check_persistence.py``; it prints ``OK`` when every step holds.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PERSISTENCE_DIR = ROOT / "docs" / "class_evolution" / "persistence"
DDL_PATH = ROOT / "src" / "battle_dice" / "career" / "schema" / "progression.sql"
EXAMPLE_PATH = PERSISTENCE_DIR / "example_profile.json"

#: Oldest SQLite the schema runs on: STRICT tables (3.37.0) and built-in json_valid (3.38.0).
MIN_SQLITE_VERSION = (3, 38, 0)
SCHEMA_VERSION = 2
ZERO_HASH = "0" * 64

#: Tables of the v0.2 schema, in alphabetical order (21 from v0.1 plus the three marked new).
TABLES = (
    "content_catalog",
    "encounter_build_snapshot",
    "hero",
    "hero_die_instance",  # new in v0.2
    "hero_equipped_die",
    "hero_equipped_skill",
    "hero_permanent_upgrade",
    "hero_skill",
    "hero_vocation_mastery",
    "hero_vocation_unlock",
    "item_consumption",
    "item_grant",  # new in v0.2
    "mastery_award_event",
    "player_profile",
    "processed_command",
    "profile_item_balance",
    "profile_vocation_discovery",
    "progression_event_log",
    "quest_completion",
    "run",
    "run_die_upgrade",
    "schema_migration",  # new in v0.2
    "skill_def",
    "vocation_def",
)

#: Tables that are shared by every profile and survive a profile reset.
SHARED_TABLES = ("content_catalog", "schema_migration", "skill_def", "vocation_def")

STAT_NAMES = ("max_hp", "max_mana", "speed", "base_initiative", "max_corruption")


class InjectedFailure(RuntimeError):
    """Raised on purpose in the middle of a transaction to show that it rolls back."""


# --------------------------------------------------------------------------------------------
# Hashing and time
# --------------------------------------------------------------------------------------------


# One definition each: the game's save code (``battle_dice.career.store``) owns the hashing rules,
# and this checker uses them, so the specification and the game cannot drift apart.
from battle_dice.career.store import event_hash, sha256_hex  # noqa: E402
from battle_dice.content.loader import canonical_json  # noqa: E402


def build_hash(build: dict[str, Any]) -> str:
    return sha256_hex(canonical_json(build))


def run_build_hash(first_encounter_builds: dict[str, str]) -> str:
    """Hash of the party build frozen by StartRun: ``{hero_id: build_sha256}`` of encounter one."""
    return sha256_hex(
        canonical_json(
            [[hero_id, first_encounter_builds[hero_id]] for hero_id in sorted(first_encounter_builds)]
        )
    )


def command_fingerprint(command_type: str, params: dict[str, Any]) -> str:
    return sha256_hex(canonical_json({"type": command_type, "params": params}))


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------------------------


def create_database() -> sqlite3.Connection:
    """Return a new in-memory database holding the v0.2 schema, with foreign keys enforced.

    The connection is in autocommit mode: every transaction below is an explicit
    ``BEGIN IMMEDIATE`` ... ``COMMIT``. The caller closes the connection.
    """
    if sqlite3.sqlite_version_info < MIN_SQLITE_VERSION:
        raise RuntimeError(
            f"SQLite {sqlite3.sqlite_version} is too old: the schema needs "
            f"{'.'.join(str(part) for part in MIN_SQLITE_VERSION)} or later."
        )
    conn = sqlite3.connect(":memory:", isolation_level=None)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(DDL_PATH.read_text(encoding="utf-8"))
        if conn.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise RuntimeError("Foreign keys are not enforced on this connection.")
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]
        migrated = conn.execute("SELECT MAX(version) FROM schema_migration").fetchone()[0]
        if user_version != SCHEMA_VERSION or migrated != SCHEMA_VERSION:
            raise RuntimeError(
                f"Schema version mismatch: user_version {user_version}, migrations {migrated}."
            )
    except BaseException:
        conn.close()
        raise
    return conn


def _rollback(conn: sqlite3.Connection) -> None:
    if conn.in_transaction:
        conn.execute("ROLLBACK")


def append_event(
    conn: sqlite3.Connection,
    *,
    profile_id: str,
    event_type: str,
    payload: dict[str, Any],
    created_at: str,
    run_id: str | None = None,
) -> str:
    """Append one event to the profile's hash chain and return its event id.

    Call inside a transaction. The event id is ``<profile_id>:<event_seq>``.
    """
    row = conn.execute(
        "SELECT event_seq, event_hash FROM progression_event_log WHERE profile_id = ? "
        "ORDER BY event_seq DESC LIMIT 1",
        (profile_id,),
    ).fetchone()
    event_seq = 0 if row is None else row[0] + 1
    previous = ZERO_HASH if row is None else row[1]
    event_id = f"{profile_id}:{event_seq}"
    event_json = canonical_json(payload)
    conn.execute(
        "INSERT INTO progression_event_log(profile_id, event_seq, event_id, run_id, event_type, event_json, "
        "previous_event_hash, event_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            profile_id,
            event_seq,
            event_id,
            run_id,
            event_type,
            event_json,
            previous,
            event_hash(previous, event_id, event_type, event_json),
            created_at,
        ),
    )
    return event_id


def verify_event_chain(conn: sqlite3.Connection, profile_id: str) -> int:
    """Recompute every event hash of a profile. Return the number of events; raise on a mismatch."""
    previous = ZERO_HASH
    count = 0
    rows = conn.execute(
        "SELECT event_seq, event_id, event_type, event_json, previous_event_hash, event_hash "
        "FROM progression_event_log WHERE profile_id = ? ORDER BY event_seq",
        (profile_id,),
    )
    for event_seq, event_id, event_type, event_json, stored_previous, stored_hash in rows:
        if event_seq != count or stored_previous != previous:
            raise ValueError(f"Event chain of '{profile_id}' is broken at sequence {event_seq}.")
        if stored_hash != event_hash(previous, event_id, event_type, event_json):
            raise ValueError(f"Event '{event_id}' does not match its hash.")
        previous = stored_hash
        count += 1
    return count


# --------------------------------------------------------------------------------------------
# Example profile
# --------------------------------------------------------------------------------------------


def read_example() -> dict[str, Any]:
    example: dict[str, Any] = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
    return example


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _check_example_numbers(example: dict[str, Any]) -> None:
    """Check the numbers the example states but the database does not store."""
    catalog = example["catalog"]
    hero = example["hero"]
    caps = catalog["global_permanent_bonus_caps"]
    requested = dict.fromkeys(caps, 0)
    for upgrade in hero["permanent_upgrades"]:
        requested[upgrade["effect"]["stat"]] += upgrade["effect"]["amount"]
    bonus = {stat: min(requested[stat], caps[stat]) for stat in caps}
    _require(
        bonus == hero["permanent_stat_bonus"], "permanent_stat_bonus is not the capped sum of the upgrades."
    )

    def effective(base: dict[str, int]) -> dict[str, int]:
        return {stat: base[stat] + bonus.get(stat, 0) for stat in STAT_NAMES}

    _require(
        effective(hero["base_class_stats"]) == hero["effective_max_stats"],
        "effective_max_stats is not base_class_stats plus the capped permanent bonus.",
    )
    for vocation_id, stats in hero["effective_max_stats_if_active"].items():
        _require(
            effective(stats["base"]) == stats["effective"], f"Effective stats of '{vocation_id}' are wrong."
        )

    costs = {skill["skill_id"]: skill["capacity_cost"] for skill in catalog["skills"]}
    used = 0
    for skill in hero["inherited_skills"]:
        _require(
            skill["cost"] == costs[skill["skill_id"]],
            f"Cost of '{skill['skill_id']}' differs from the catalog.",
        )
        used += skill["cost"]
    _require(
        used == hero["inheritance_capacity_used"], "inheritance_capacity_used is not the sum of the costs."
    )
    _require(
        used <= hero["inheritance_capacity_max"], "The inherited skills exceed the inheritance capacity."
    )


def load_example(conn: sqlite3.Connection, example: dict[str, Any]) -> None:
    """Insert the example profile in one transaction and check what it states.

    Raises ``ValueError`` when a stated hash or derived number is wrong and ``sqlite3.Error`` when
    the database refuses a row. Either way nothing is left behind.
    """
    _check_example_numbers(example)
    catalog = example["catalog"]
    profile = example["profile"]
    hero = example["hero"]
    run = example["run_state"]
    version = catalog["catalog_version"]
    profile_id = profile["profile_id"]
    hero_id = hero["hero_id"]

    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "INSERT INTO content_catalog(catalog_version, content_sha256, rules_version, state, installed_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                version,
                catalog["content_sha256"],
                catalog["rules_version"],
                catalog["state"],
                catalog["installed_at"],
            ),
        )
        for vocation in catalog["vocations"]:
            conn.execute(
                "INSERT INTO vocation_def(catalog_version, vocation_id, display_name, family, visibility, "
                "definition_json) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    version,
                    vocation["vocation_id"],
                    vocation["display_name"],
                    vocation["family"],
                    vocation["visibility"],
                    canonical_json(vocation),
                ),
            )
        for skill in catalog["skills"]:
            conn.execute(
                "INSERT INTO skill_def(catalog_version, skill_id, definition_json) VALUES (?, ?, ?)",
                (version, skill["skill_id"], canonical_json(skill)),
            )

        conn.execute(
            "INSERT INTO player_profile(profile_id, current_catalog_version, created_at, revision) VALUES (?, ?, ?, ?)",
            (profile_id, version, profile["created_at"], profile["revision"]),
        )
        conn.execute(
            "INSERT INTO hero(hero_id, profile_id, catalog_version, origin_vocation_id, active_vocation_id, "
            "display_name, eligibility_state, revision, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                hero_id,
                profile_id,
                version,
                hero["origin_vocation_id"],
                hero["active_vocation_id"],
                hero["display_name"],
                hero["eligibility_state"],
                hero["revision"],
                hero["created_at"],
            ),
        )

        # The run comes before the events and grants that name it.
        snapshot_hashes: dict[str, str] = {}
        for snapshot in run["encounter_build_snapshots"]:
            _require(
                build_hash(snapshot["build"]) == snapshot["build_sha256"],
                "A build snapshot does not match its hash.",
            )
            if snapshot["encounter_id"] == run["first_encounter_id"]:
                snapshot_hashes[snapshot["hero_id"]] = snapshot["build_sha256"]
        _require(
            run_build_hash(snapshot_hashes) == run["build_sha256"],
            "run_state.build_sha256 does not match the snapshots.",
        )
        conn.execute(
            "INSERT INTO run(run_id, profile_id, catalog_version, content_sha256, rules_version, rng_version, "
            "seed_decimal, build_sha256, phase, revision, started_at, completed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run["run_id"],
                profile_id,
                run["catalog_version"],
                run["content_sha256"],
                run["rules_version"],
                run["rng_version"],
                run["seed_decimal"],
                run["build_sha256"],
                run["phase"],
                run["revision"],
                run["started_at"],
                run["completed_at"],
            ),
        )
        for snapshot in run["encounter_build_snapshots"]:
            conn.execute(
                "INSERT INTO encounter_build_snapshot(run_id, encounter_id, hero_id, vocation_id, build_json, "
                "build_sha256) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    run["run_id"],
                    snapshot["encounter_id"],
                    snapshot["hero_id"],
                    snapshot["vocation_id"],
                    canonical_json(snapshot["build"]),
                    snapshot["build_sha256"],
                ),
            )

        for event in example["progression_events"]:
            event_id = append_event(
                conn,
                profile_id=profile_id,
                event_type=event["event_type"],
                payload=event["payload"],
                created_at=event["created_at"],
                run_id=event["run_id"],
            )
            _require(event_id == event["event_id"], f"Event id '{event['event_id']}' is out of sequence.")
            stored = conn.execute(
                "SELECT event_seq, previous_event_hash, event_hash FROM progression_event_log WHERE event_id = ?",
                (event_id,),
            ).fetchone()
            _require(
                tuple(stored) == (event["event_seq"], event["previous_event_hash"], event["event_hash"]),
                f"Event '{event_id}' does not match the hashes the example states.",
            )

        for unlock in hero["character_unlocked"]:
            conn.execute(
                "INSERT INTO hero_vocation_unlock(hero_id, catalog_version, vocation_id, unlock_route_id, "
                "claim_event_id, unlocked_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    hero_id,
                    version,
                    unlock["vocation_id"],
                    unlock["unlock_route_id"],
                    unlock["claim_event_id"],
                    unlock["unlocked_at"],
                ),
            )
        for mastery in hero["mastery"]:
            conn.execute(
                "INSERT INTO hero_vocation_mastery(hero_id, catalog_version, vocation_id, mastery_points, "
                "mastery_rank, completed_at, revision) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    hero_id,
                    version,
                    mastery["vocation_id"],
                    mastery["points"],
                    mastery["rank"],
                    mastery["completed_at"],
                    mastery["revision"],
                ),
            )
        for skill in hero["learned_skills"]:
            conn.execute(
                "INSERT INTO hero_skill(hero_id, catalog_version, skill_id, acquired_from_vocation_id, learned_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    hero_id,
                    version,
                    skill["skill_id"],
                    skill["acquired_from_vocation_id"],
                    skill["learned_at"],
                ),
            )
        for skill in hero["inherited_skills"]:
            conn.execute(
                "INSERT INTO hero_equipped_skill(hero_id, catalog_version, slot_index, skill_id) VALUES (?, ?, ?, ?)",
                (hero_id, version, skill["slot_index"], skill["skill_id"]),
            )

        dice = {die["die_instance_id"]: die for die in hero["owned_dice"]}
        for die in hero["owned_dice"]:
            conn.execute(
                "INSERT INTO hero_die_instance(die_instance_id, hero_id, definition_id, definition_version, "
                "location, acquisition_key, acquired_at) VALUES (?, ?, ?, ?, 'bench', ?, ?)",
                (
                    die["die_instance_id"],
                    hero_id,
                    die["definition_id"],
                    die["definition_version"],
                    die["acquisition_key"],
                    die["acquired_at"],
                ),
            )
        for slot in hero["equipped_dice"]:
            die = dice[slot["die_instance_id"]]
            conn.execute(
                "INSERT INTO hero_equipped_die(hero_id, slot_index, die_instance_id, definition_id, "
                "definition_version) VALUES (?, ?, ?, ?, ?)",
                (
                    hero_id,
                    slot["slot_index"],
                    die["die_instance_id"],
                    die["definition_id"],
                    die["definition_version"],
                ),
            )
        stored_locations = dict(
            conn.execute(
                "SELECT die_instance_id, location FROM hero_die_instance WHERE hero_id = ?", (hero_id,)
            )
        )
        _require(
            stored_locations == {die_id: die["location"] for die_id, die in dice.items()},
            "The die locations in the example do not match its equipped slots.",
        )

        for item in profile["inventory"]:
            conn.execute(
                "INSERT INTO profile_item_balance(profile_id, item_id, quantity, revision) VALUES (?, ?, ?, ?)",
                (profile_id, item["item_id"], item["quantity"], item["revision"]),
            )
        for grant in profile["item_grants"]:
            conn.execute(
                "INSERT INTO item_grant(grant_id, profile_id, item_id, quantity, hero_id, run_id, encounter_id, "
                "granted_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    grant["grant_id"],
                    profile_id,
                    grant["item_id"],
                    grant["quantity"],
                    grant["hero_id"],
                    grant["run_id"],
                    grant["encounter_id"],
                    grant["granted_at"],
                ),
            )
        for quest in profile["completed_profile_quests"]:
            conn.execute(
                "INSERT INTO quest_completion(profile_id, quest_id, qualifier_scope, qualifier_id, completed_at) "
                "VALUES (?, ?, 'profile', ?, ?)",
                (profile_id, quest["quest_id"], profile_id, quest["completed_at"]),
            )
        for quest in hero["hero_quest_completions"]:
            conn.execute(
                "INSERT INTO quest_completion(profile_id, quest_id, qualifier_scope, qualifier_id, completed_at) "
                "VALUES (?, ?, 'hero', ?, ?)",
                (profile_id, quest["quest_id"], hero_id, quest["completed_at"]),
            )
        for upgrade in hero["permanent_upgrades"]:
            conn.execute(
                "INSERT INTO hero_permanent_upgrade(upgrade_id, hero_id, upgrade_kind, effect_json, "
                "source_event_id, earned_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    upgrade["upgrade_id"],
                    hero_id,
                    upgrade["upgrade_kind"],
                    canonical_json(upgrade["effect"]),
                    upgrade["source_event_id"],
                    upgrade["earned_at"],
                ),
            )
        for discovery in profile["vocation_discovery"]:
            conn.execute(
                "INSERT INTO profile_vocation_discovery(profile_id, catalog_version, vocation_id, discovery_state, "
                "clue_count, modified_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    profile_id,
                    version,
                    discovery["vocation_id"],
                    discovery["discovery_state"],
                    discovery["clue_count"],
                    discovery["modified_at"],
                ),
            )

        for item_id, balance, ledger in item_ledger(conn, profile_id):
            _require(balance == ledger, f"Balance of '{item_id}' is {balance} but the ledger says {ledger}.")
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        _require(not violations, f"Foreign key violations after loading the example: {violations}")
        conn.execute("COMMIT")
    except BaseException:
        _rollback(conn)
        raise


def item_ledger(conn: sqlite3.Connection, profile_id: str) -> list[tuple[str, int, int]]:
    """Return ``(item_id, balance, grants minus consumptions)`` for every item of a profile."""
    rows = conn.execute(
        """
        SELECT item_id,
               COALESCE((SELECT quantity FROM profile_item_balance b
                         WHERE b.profile_id = ?1 AND b.item_id = items.item_id), 0),
               COALESCE((SELECT SUM(quantity) FROM item_grant g
                         WHERE g.profile_id = ?1 AND g.item_id = items.item_id), 0)
             - COALESCE((SELECT SUM(quantity) FROM item_consumption c
                         WHERE c.profile_id = ?1 AND c.item_id = items.item_id), 0)
        FROM (SELECT item_id FROM profile_item_balance WHERE profile_id = ?1
              UNION SELECT item_id FROM item_grant WHERE profile_id = ?1
              UNION SELECT item_id FROM item_consumption WHERE profile_id = ?1) AS items
        ORDER BY item_id
        """,
        (profile_id,),
    ).fetchall()
    return [(str(item_id), int(balance), int(ledger)) for item_id, balance, ledger in rows]


# --------------------------------------------------------------------------------------------
# Reference transactions
# --------------------------------------------------------------------------------------------


def grant_item(
    conn: sqlite3.Connection,
    *,
    grant_id: str,
    profile_id: str,
    item_id: str,
    quantity: int = 1,
    hero_id: str | None = None,
    run_id: str | None = None,
    encounter_id: str | None = None,
    now: str | None = None,
) -> bool:
    """Grant an item once per grant id. Return ``False`` when the id was already granted.

    One transaction: the ledger row and the balance change together, or neither does.
    """
    granted_at = now or utc_now()
    conn.execute("BEGIN IMMEDIATE")
    try:
        inserted = conn.execute(
            "INSERT OR IGNORE INTO item_grant(grant_id, profile_id, item_id, quantity, hero_id, run_id, "
            "encounter_id, granted_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (grant_id, profile_id, item_id, quantity, hero_id, run_id, encounter_id, granted_at),
        ).rowcount
        if inserted == 1:
            conn.execute(
                "INSERT INTO profile_item_balance(profile_id, item_id, quantity, revision) VALUES (?, ?, ?, 0) "
                "ON CONFLICT(profile_id, item_id) DO UPDATE SET quantity = quantity + excluded.quantity, "
                "revision = revision + 1",
                (profile_id, item_id, quantity),
            )
        conn.execute("COMMIT")
    except BaseException:
        _rollback(conn)
        raise
    return inserted == 1


def _rejected(conn: sqlite3.Connection, error_code: str, state_revision: int | None) -> dict[str, Any]:
    _rollback(conn)
    return {"result": "rejected", "error_code": error_code, "state_revision": state_revision}


def claim_with_item(
    conn: sqlite3.Connection,
    *,
    profile_id: str,
    hero_id: str,
    target_vocation_id: str,
    item_id: str,
    command_id: str,
    state_revision: int,
    unlock_route_id: str = "route_0",
    quantity: int = 1,
    now: str | None = None,
    fail_after_decrement: bool = False,
) -> dict[str, Any]:
    """Claim a vocation through a route that consumes an item, in one transaction.

    This is the storage half of ``ClaimVocation``. The prerequisite expression (mastery and
    quests) and the choice of route are pure domain checks made before the transaction; they are
    not repeated here. In order:

    1. A command id that was already accepted returns its stored result with ``duplicate`` true
       (same command) or is rejected with ``COMMAND_ID_REUSED`` (different command).
    2. ``REVISION_CONFLICT``, ``PHASE_LOCKED``, ``HERO_NOT_ELIGIBLE``, ``NOT_DISCOVERED``.
    3. The item balance is decremented with a quantity guard: ``ITEM_INSUFFICIENT``.
    4. The claim event, the unlock, the default mastery row, the consumption, the hero revision
       and the command record are written.

    A rejection or an exception rolls everything back and records nothing, so the same command
    id can be sent again. ``fail_after_decrement`` raises ``InjectedFailure`` after step 3.
    """
    timestamp = now or utc_now()
    scope = f"profile:{profile_id}"

    conn.execute("BEGIN IMMEDIATE")
    try:
        seen = conn.execute(
            "SELECT command_sha256, result_json FROM processed_command WHERE command_scope = ? AND command_id = ?",
            (scope, command_id),
        ).fetchone()
        hero = conn.execute(
            "SELECT catalog_version, eligibility_state, revision FROM hero WHERE hero_id = ? AND profile_id = ?",
            (hero_id, profile_id),
        ).fetchone()
        current_revision: int | None = None if hero is None else hero[2]
        params = {
            "profile_id": profile_id,
            "hero_id": hero_id,
            "target_vocation_id": target_vocation_id,
            "catalog_version": None if hero is None else hero[0],
        }
        fingerprint = command_fingerprint("ClaimVocation", params)
        if seen is not None:
            if seen[0] != fingerprint:
                return _rejected(conn, "COMMAND_ID_REUSED", current_revision)
            _rollback(conn)
            replay: dict[str, Any] = json.loads(seen[1])
            replay["duplicate"] = True
            return replay
        if hero is None:
            raise LookupError(f"Profile '{profile_id}' has no hero '{hero_id}'.")
        catalog_version, eligibility_state, revision = hero
        if revision != state_revision:
            return _rejected(conn, "REVISION_CONFLICT", revision)
        in_battle = conn.execute(
            "SELECT 1 FROM run WHERE profile_id = ? AND completed_at IS NULL AND phase = 'battle'",
            (profile_id,),
        ).fetchone()
        if in_battle is not None:
            return _rejected(conn, "PHASE_LOCKED", revision)
        if eligibility_state != "eligible":
            return _rejected(conn, "HERO_NOT_ELIGIBLE", revision)
        discovery = conn.execute(
            "SELECT discovery_state FROM profile_vocation_discovery "
            "WHERE profile_id = ? AND catalog_version = ? AND vocation_id = ?",
            (profile_id, catalog_version, target_vocation_id),
        ).fetchone()
        if discovery is None or discovery[0] != "discovered":
            return _rejected(conn, "NOT_DISCOVERED", revision)

        decremented = conn.execute(
            "UPDATE profile_item_balance SET quantity = quantity - ?, revision = revision + 1 "
            "WHERE profile_id = ? AND item_id = ? AND quantity >= ?",
            (quantity, profile_id, item_id, quantity),
        ).rowcount
        if decremented != 1:
            return _rejected(conn, "ITEM_INSUFFICIENT", revision)
        if fail_after_decrement:
            raise InjectedFailure("Injected failure after the item decrement, before the unlock insert.")

        claim_event_id = append_event(
            conn,
            profile_id=profile_id,
            event_type="VocationClaimed",
            payload={
                "hero_id": hero_id,
                "vocation_id": target_vocation_id,
                "route_id": unlock_route_id,
                "consumed_items": [{"item_id": item_id, "quantity": quantity}],
            },
            created_at=timestamp,
        )
        conn.execute(
            "INSERT INTO hero_vocation_unlock(hero_id, catalog_version, vocation_id, unlock_route_id, "
            "claim_event_id, unlocked_at) VALUES (?, ?, ?, ?, ?, ?)",
            (hero_id, catalog_version, target_vocation_id, unlock_route_id, claim_event_id, timestamp),
        )
        conn.execute(
            "INSERT OR IGNORE INTO hero_vocation_mastery(hero_id, catalog_version, vocation_id) VALUES (?, ?, ?)",
            (hero_id, catalog_version, target_vocation_id),
        )
        consumption_id = f"consume:{claim_event_id}"
        conn.execute(
            "INSERT INTO item_consumption(consumption_id, profile_id, hero_id, item_id, quantity, claim_event_id, "
            "consumed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (consumption_id, profile_id, hero_id, item_id, quantity, claim_event_id, timestamp),
        )
        conn.execute("UPDATE hero SET revision = revision + 1 WHERE hero_id = ?", (hero_id,))
        result: dict[str, Any] = {
            "result": "accepted",
            "duplicate": False,
            "state_revision": state_revision + 1,
            "event_ids": [claim_event_id],
            "claim_event_id": claim_event_id,
            "consumption_id": consumption_id,
            "unlock_route_id": unlock_route_id,
        }
        conn.execute(
            "INSERT INTO processed_command(command_scope, command_id, profile_id, command_type, command_sha256, "
            "result_json, created_at) VALUES (?, ?, ?, 'ClaimVocation', ?, ?, ?)",
            (scope, command_id, profile_id, fingerprint, canonical_json(result), timestamp),
        )
        conn.execute("COMMIT")
    except BaseException:
        _rollback(conn)
        raise
    return result


def reset_profile(conn: sqlite3.Connection, profile_id: str) -> None:
    """Delete a profile and everything that belongs to it (the RESET PROFILE sequence of the DDL)."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("DELETE FROM player_profile WHERE profile_id = ?", (profile_id,))
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"Reset of '{profile_id}' left foreign key violations: {violations}")
        conn.execute("COMMIT")
    except BaseException:
        _rollback(conn)
        raise


# --------------------------------------------------------------------------------------------
# Inspection
# --------------------------------------------------------------------------------------------


def table_names(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    return [str(row[0]) for row in rows]


def profile_keys(conn: sqlite3.Connection, profile_id: str) -> dict[str, list[str]]:
    """The ids that tie rows to a profile: its heroes and its runs. Read this before a reset."""
    heroes = [
        str(row[0]) for row in conn.execute("SELECT hero_id FROM hero WHERE profile_id = ?", (profile_id,))
    ]
    runs = [str(row[0]) for row in conn.execute("SELECT run_id FROM run WHERE profile_id = ?", (profile_id,))]
    return {"hero_id": heroes, "run_id": runs}


def count_profile_rows(
    conn: sqlite3.Connection, profile_id: str, keys: dict[str, list[str]]
) -> dict[str, int]:
    """Count, per table, the rows that name the profile, one of its heroes or one of its runs."""
    counts: dict[str, int] = {}
    for table in table_names(conn):
        if table in SHARED_TABLES:
            continue
        columns = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}
        clauses: list[str] = []
        values: list[str] = []
        if "profile_id" in columns:
            clauses.append("profile_id = ?")
            values.append(profile_id)
        for column, ids in keys.items():
            if column in columns and ids:
                clauses.append(f"{column} IN ({', '.join('?' for _ in ids)})")
                values.extend(ids)
        if not clauses:
            raise RuntimeError(f"Table '{table}' has no column that ties it to a profile.")
        counts[table] = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {' OR '.join(clauses)}", values
        ).fetchone()[0]
    return counts


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(f"Check failed: {message}")


def main() -> int:
    conn = create_database()
    try:
        _expect(tuple(table_names(conn)) == TABLES, "the schema creates exactly the documented tables")
        _expect(conn.execute("PRAGMA integrity_check").fetchall() == [("ok",)], "integrity_check is clean")

        example = read_example()
        load_example(conn, example)
        profile_id = example["profile"]["profile_id"]
        hero_id = example["hero"]["hero_id"]
        revision = example["hero"]["revision"]
        _expect(conn.execute("PRAGMA foreign_key_check").fetchall() == [], "foreign_key_check is clean")
        _expect(
            verify_event_chain(conn, profile_id) == len(example["progression_events"]),
            "the event chain verifies",
        )

        grant = example["profile"]["item_grants"][0]
        again = grant_item(conn, grant_id=grant["grant_id"], profile_id=profile_id, item_id=grant["item_id"])
        _expect(not again, "a repeated grant id grants nothing")

        claim: dict[str, Any] = {
            "profile_id": profile_id,
            "hero_id": hero_id,
            "target_vocation_id": "dragon_knight",
            "item_id": "drake_scale",
            "command_id": "cmd-check-0001",
            "state_revision": revision,
        }
        try:
            claim_with_item(conn, **claim, fail_after_decrement=True)
        except InjectedFailure:
            pass
        else:
            raise RuntimeError("Check failed: the injected failure did not surface")
        _expect(
            item_ledger(conn, profile_id) == [("drake_scale", 1, 1)], "a failed claim leaves the item balance"
        )

        first = claim_with_item(conn, **claim)
        _expect(first["result"] == "accepted" and not first["duplicate"], "the claim is accepted")
        second = claim_with_item(conn, **claim)
        _expect(second["result"] == "accepted" and second["duplicate"], "the repeated command is a replay")
        _expect(item_ledger(conn, profile_id) == [("drake_scale", 0, 0)], "one token was consumed, once")
        _expect(
            verify_event_chain(conn, profile_id) == len(example["progression_events"]) + 1, "one claim event"
        )

        keys = profile_keys(conn, profile_id)
        reset_profile(conn, profile_id)
        left = {table: count for table, count in count_profile_rows(conn, profile_id, keys).items() if count}
        _expect(not left, f"the reset leaves no rows for the profile, found {left}")
        _expect(
            conn.execute("PRAGMA foreign_key_check").fetchall() == [],
            "foreign_key_check is clean after the reset",
        )
    finally:
        conn.close()
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
