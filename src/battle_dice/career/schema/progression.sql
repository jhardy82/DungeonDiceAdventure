-- Battle Dice: Class Evolution persistence schema, FDD v0.2 (schema version 2).
-- Status: SPECIFICATION ONLY. Nothing in the shipped game reads or writes this database yet.
-- Baseline: rules 1.1.1, content 1.3.1, RNG BD-PCG32-v1.
--
-- SQLite version required: 3.38.0 or later.
--   * STRICT tables need 3.37.0. Every table is STRICT so a TEXT column cannot silently hold a
--     number and an INTEGER column cannot hold text.
--   * json_valid() is used in CHECK constraints. The JSON functions are built in by default only
--     from 3.38.0; before that they were a compile-time option.
--   * The reference transactions in tools/class_evolution/check_persistence.py also use UPSERT
--     (3.24.0), which the two requirements above already cover.
--   Checked with SQLite 3.53.1, the library bundled with the repository's Python.
--
-- How to run: execute this whole file once on a new, empty database. It runs in one transaction
-- and sets PRAGMA user_version = 2. Every connection must then execute PRAGMA foreign_keys = ON
-- before any other statement, because SQLite does not store that setting in the file.
--
-- What changed from v0.1 (21 tables, all kept; 3 tables added: hero_die_instance, item_grant,
-- schema_migration). Numbers refer to the v0.1 review defects.
--   2. hero_die_instance holds every owned die with a location ('equipped' or 'bench').
--   3. item_grant is the grant ledger. Its primary key is the reward id, so a repeated reward id
--      cannot be inserted twice.
--   4. progression_event_log has an event_id, belongs to a profile and has an optional run_id.
--      hero_vocation_unlock.claim_event_id and hero_permanent_upgrade.source_event_id reference it.
--   5. item_consumption must name the hero of its claim, and a claim has at most one consumption.
--   6. mastery_award_event cannot hold a challenge point without a base point.
--   7. run_die_upgrade.permanent can only be 0. hero_permanent_upgrade needs a source event.
--   8. run has build_sha256. schema_migration and PRAGMA user_version record the schema version.
--      Every foreign key states its ON DELETE action. See RESET PROFILE at the end of this file.
--   9. run.phase uses the engine's values (battle, upgrade, equipment, victory, defeat).
--
-- Conventions.
--   * Timestamps are UTC text, YYYY-MM-DDTHH:MM:SSZ. They are never part of a hash.
--   * Hashes are 64 lowercase hexadecimal characters (SHA-256).
--   * Canonical JSON is the game's: keys sorted, separators "," and ":", ASCII only
--     (battle_dice.content.loader.canonical_json).
--   * event_hash = SHA-256 of the UTF-8 text
--       previous_event_hash + "\n" + event_id + "\n" + event_type + "\n" + event_json
--     where event_json is canonical JSON. The first event of a profile uses 64 zeros as
--     previous_event_hash. SQLite has no SHA-256 function, so the database checks that the chain
--     is continuous (trigger below) and the application checks the hash values.
--   * A command's state_revision is compared with the revision column of the row it targets
--     (hero.revision for hero commands, run.revision for run commands).
--
-- ON DELETE actions used here.
--   CASCADE    the child row belongs to the parent and goes with it.
--   SET NULL   the child row is a record that outlives the parent.
--   RESTRICT   catalog rows: a catalog that is still referenced cannot be removed.
--   NO ACTION  checked at the end of the statement. Used where a parent and its child are both
--              removed by the same cascading delete, in an order SQLite chooses.

PRAGMA foreign_keys = ON;

BEGIN;

-- --------------------------------------------------------------------------------------------
-- Schema version
-- --------------------------------------------------------------------------------------------

CREATE TABLE schema_migration (
  version INTEGER PRIMARY KEY CHECK(version >= 1),
  description TEXT NOT NULL,
  applied_at TEXT NOT NULL
) STRICT;

-- --------------------------------------------------------------------------------------------
-- Immutable content catalog
-- --------------------------------------------------------------------------------------------

CREATE TABLE content_catalog (
  catalog_version TEXT PRIMARY KEY,
  content_sha256 TEXT NOT NULL
    CHECK(length(content_sha256) = 64 AND content_sha256 NOT GLOB '*[^0-9a-f]*'),
  rules_version TEXT NOT NULL,
  state TEXT NOT NULL CHECK(state IN ('active','retired')),
  installed_at TEXT NOT NULL,
  UNIQUE(catalog_version,content_sha256)
) STRICT;

CREATE TABLE vocation_def (
  catalog_version TEXT NOT NULL,
  vocation_id TEXT NOT NULL,
  display_name TEXT NOT NULL,
  family TEXT NOT NULL CHECK(family IN ('novice','advanced','capstone','secret')),
  visibility TEXT NOT NULL CHECK(visibility IN ('public','secret')),
  definition_json TEXT NOT NULL CHECK(json_valid(definition_json)),
  PRIMARY KEY(catalog_version,vocation_id),
  FOREIGN KEY(catalog_version) REFERENCES content_catalog(catalog_version) ON DELETE RESTRICT
) STRICT;

CREATE TABLE skill_def (
  catalog_version TEXT NOT NULL,
  skill_id TEXT NOT NULL,
  definition_json TEXT NOT NULL CHECK(json_valid(definition_json)),
  PRIMARY KEY(catalog_version,skill_id),
  FOREIGN KEY(catalog_version) REFERENCES content_catalog(catalog_version) ON DELETE RESTRICT
) STRICT;

-- --------------------------------------------------------------------------------------------
-- Profile and heroes
-- --------------------------------------------------------------------------------------------

CREATE TABLE player_profile (
  profile_id TEXT PRIMARY KEY,
  current_catalog_version TEXT NOT NULL,
  created_at TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 0 CHECK(revision >= 0),
  FOREIGN KEY(current_catalog_version) REFERENCES content_catalog(catalog_version) ON DELETE RESTRICT
) STRICT;

CREATE TABLE hero (
  hero_id TEXT PRIMARY KEY,
  profile_id TEXT NOT NULL,
  catalog_version TEXT NOT NULL,
  origin_vocation_id TEXT NOT NULL,
  active_vocation_id TEXT NOT NULL,
  display_name TEXT NOT NULL,
  eligibility_state TEXT NOT NULL DEFAULT 'eligible' CHECK(eligibility_state IN ('eligible','locked','guest')),
  revision INTEGER NOT NULL DEFAULT 0 CHECK(revision >= 0),
  created_at TEXT NOT NULL,
  UNIQUE(profile_id,hero_id),
  FOREIGN KEY(profile_id) REFERENCES player_profile(profile_id) ON DELETE CASCADE,
  FOREIGN KEY(catalog_version,origin_vocation_id)
    REFERENCES vocation_def(catalog_version,vocation_id) ON DELETE RESTRICT,
  FOREIGN KEY(catalog_version,active_vocation_id)
    REFERENCES vocation_def(catalog_version,vocation_id) ON DELETE RESTRICT
) STRICT;
CREATE INDEX idx_hero_profile ON hero(profile_id);

-- Global discovery is not hero eligibility. A secret may be hidden, hinted, or discovered.
CREATE TABLE profile_vocation_discovery (
  profile_id TEXT NOT NULL,
  catalog_version TEXT NOT NULL,
  vocation_id TEXT NOT NULL,
  discovery_state TEXT NOT NULL CHECK(discovery_state IN ('hidden','hinted','discovered')),
  clue_count INTEGER NOT NULL DEFAULT 0 CHECK(clue_count >= 0),
  modified_at TEXT NOT NULL,
  PRIMARY KEY(profile_id,catalog_version,vocation_id),
  FOREIGN KEY(profile_id) REFERENCES player_profile(profile_id) ON DELETE CASCADE,
  FOREIGN KEY(catalog_version,vocation_id)
    REFERENCES vocation_def(catalog_version,vocation_id) ON DELETE RESTRICT
) STRICT;

-- Every hero earns mastery independently, and progress is retained when switching away.
-- completed_at is set exactly when the vocation is mastered (rank 8).
CREATE TABLE hero_vocation_mastery (
  hero_id TEXT NOT NULL,
  catalog_version TEXT NOT NULL,
  vocation_id TEXT NOT NULL,
  mastery_points INTEGER NOT NULL DEFAULT 0 CHECK(mastery_points >= 0),
  mastery_rank INTEGER NOT NULL DEFAULT 1 CHECK(mastery_rank BETWEEN 1 AND 8),
  completed_at TEXT,
  revision INTEGER NOT NULL DEFAULT 0 CHECK(revision >= 0),
  PRIMARY KEY(hero_id,catalog_version,vocation_id),
  CHECK((completed_at IS NOT NULL) = (mastery_rank = 8)),
  FOREIGN KEY(hero_id) REFERENCES hero(hero_id) ON DELETE CASCADE,
  FOREIGN KEY(catalog_version,vocation_id)
    REFERENCES vocation_def(catalog_version,vocation_id) ON DELETE RESTRICT
) STRICT;

-- One row per vocation a hero has claimed. Novice vocations are claimed when the hero is
-- created. claim_event_id names the VocationClaimed event in progression_event_log (defect 4).
CREATE TABLE hero_vocation_unlock (
  hero_id TEXT NOT NULL,
  catalog_version TEXT NOT NULL,
  vocation_id TEXT NOT NULL,
  unlock_route_id TEXT NOT NULL,
  claim_event_id TEXT NOT NULL UNIQUE,
  unlocked_at TEXT NOT NULL,
  PRIMARY KEY(hero_id,catalog_version,vocation_id),
  UNIQUE(hero_id,claim_event_id),
  FOREIGN KEY(hero_id) REFERENCES hero(hero_id) ON DELETE CASCADE,
  FOREIGN KEY(catalog_version,vocation_id)
    REFERENCES vocation_def(catalog_version,vocation_id) ON DELETE RESTRICT,
  FOREIGN KEY(claim_event_id) REFERENCES progression_event_log(event_id) ON DELETE NO ACTION
) STRICT;

CREATE TABLE hero_skill (
  hero_id TEXT NOT NULL,
  catalog_version TEXT NOT NULL,
  skill_id TEXT NOT NULL,
  acquired_from_vocation_id TEXT NOT NULL,
  learned_at TEXT NOT NULL,
  PRIMARY KEY(hero_id,catalog_version,skill_id),
  FOREIGN KEY(hero_id) REFERENCES hero(hero_id) ON DELETE CASCADE,
  FOREIGN KEY(catalog_version,skill_id) REFERENCES skill_def(catalog_version,skill_id) ON DELETE RESTRICT,
  FOREIGN KEY(catalog_version,acquired_from_vocation_id)
    REFERENCES vocation_def(catalog_version,vocation_id) ON DELETE RESTRICT
) STRICT;

CREATE TABLE hero_equipped_skill (
  hero_id TEXT NOT NULL,
  catalog_version TEXT NOT NULL,
  slot_index INTEGER NOT NULL CHECK(slot_index >= 0),
  skill_id TEXT NOT NULL,
  PRIMARY KEY(hero_id,slot_index),
  UNIQUE(hero_id,catalog_version,skill_id),
  FOREIGN KEY(hero_id,catalog_version,skill_id)
    REFERENCES hero_skill(hero_id,catalog_version,skill_id) ON DELETE CASCADE
) STRICT;

-- --------------------------------------------------------------------------------------------
-- Dice (defect 2)
-- --------------------------------------------------------------------------------------------

-- Every die a hero owns. A die is created on the bench and is never deleted while its hero
-- exists; a vocation change moves dice between 'equipped' and 'bench'. acquisition_key makes a
-- grant idempotent: a starter die uses 'starter:<vocation_id>:<starter slot>', so the same
-- starter cannot be granted twice to one hero.
CREATE TABLE hero_die_instance (
  die_instance_id TEXT PRIMARY KEY,
  hero_id TEXT NOT NULL,
  definition_id TEXT NOT NULL,
  definition_version INTEGER NOT NULL CHECK(definition_version >= 1),
  location TEXT NOT NULL CHECK(location IN ('equipped','bench')),
  acquisition_key TEXT NOT NULL,
  acquired_at TEXT NOT NULL,
  UNIQUE(hero_id,die_instance_id),
  UNIQUE(hero_id,die_instance_id,definition_id,definition_version),
  UNIQUE(hero_id,acquisition_key),
  FOREIGN KEY(hero_id) REFERENCES hero(hero_id) ON DELETE CASCADE
) STRICT;
CREATE INDEX idx_hero_die_instance_hero ON hero_die_instance(hero_id,location);

-- The equipped slots. location in hero_die_instance follows this table through the triggers
-- below, so the two can never disagree.
CREATE TABLE hero_equipped_die (
  hero_id TEXT NOT NULL,
  slot_index INTEGER NOT NULL CHECK(slot_index >= 0),
  die_instance_id TEXT NOT NULL,
  definition_id TEXT NOT NULL,
  definition_version INTEGER NOT NULL CHECK(definition_version >= 1),
  PRIMARY KEY(hero_id,slot_index),
  UNIQUE(hero_id,die_instance_id),
  FOREIGN KEY(hero_id) REFERENCES hero(hero_id) ON DELETE CASCADE,
  FOREIGN KEY(hero_id,die_instance_id,definition_id,definition_version)
    REFERENCES hero_die_instance(hero_id,die_instance_id,definition_id,definition_version)
    ON DELETE CASCADE
) STRICT;

-- --------------------------------------------------------------------------------------------
-- Items and quests
-- --------------------------------------------------------------------------------------------

-- Account inventory is shared, but a consumed secret-class token unlocks only the named hero.
-- For every (profile, item): quantity = SUM(item_grant.quantity) - SUM(item_consumption.quantity)
-- as long as no hero of the profile has been deleted. The application keeps this true; the
-- reference transactions are grant_item and claim_with_item in the checking tool.
CREATE TABLE profile_item_balance (
  profile_id TEXT NOT NULL,
  item_id TEXT NOT NULL,
  quantity INTEGER NOT NULL CHECK(quantity >= 0),
  revision INTEGER NOT NULL DEFAULT 0 CHECK(revision >= 0),
  PRIMARY KEY(profile_id,item_id),
  FOREIGN KEY(profile_id) REFERENCES player_profile(profile_id) ON DELETE CASCADE
) STRICT;

-- Grant ledger (defect 3). grant_id is the reward id, for example
-- 'first_clear:training_04:hero_001:drake_scale'. A second grant with the same id fails on the
-- primary key, so "duplicate reward ids grant zero" is INSERT OR IGNORE followed by a balance
-- update only when a row was inserted. hero_id is the hero that earned the reward, if any; the
-- row outlives that hero so the reward id stays spent.
CREATE TABLE item_grant (
  grant_id TEXT PRIMARY KEY,
  profile_id TEXT NOT NULL,
  item_id TEXT NOT NULL,
  quantity INTEGER NOT NULL CHECK(quantity > 0),
  hero_id TEXT,
  run_id TEXT,
  encounter_id TEXT,
  granted_at TEXT NOT NULL,
  FOREIGN KEY(profile_id) REFERENCES player_profile(profile_id) ON DELETE CASCADE,
  FOREIGN KEY(hero_id) REFERENCES hero(hero_id) ON DELETE SET NULL,
  FOREIGN KEY(run_id) REFERENCES run(run_id) ON DELETE SET NULL
) STRICT;
CREATE INDEX idx_item_grant_profile_item ON item_grant(profile_id,item_id);

-- qualifier_id is the profile id when qualifier_scope is 'profile' and a hero id of this
-- profile when it is 'hero' (trigger below).
CREATE TABLE quest_completion (
  profile_id TEXT NOT NULL,
  quest_id TEXT NOT NULL,
  qualifier_scope TEXT NOT NULL CHECK(qualifier_scope IN ('profile','hero')),
  qualifier_id TEXT NOT NULL,
  completed_at TEXT NOT NULL,
  PRIMARY KEY(profile_id,quest_id,qualifier_scope,qualifier_id),
  CHECK(qualifier_scope <> 'profile' OR qualifier_id = profile_id),
  FOREIGN KEY(profile_id) REFERENCES player_profile(profile_id) ON DELETE CASCADE
) STRICT;

-- Defect 5. UNIQUE(claim_event_id): a claim is consumed for at most once. The composite key
-- (hero_id, claim_event_id) makes the consuming hero the hero of the claim, and the composite
-- key (profile_id, hero_id) makes that hero a hero of the paying profile.
CREATE TABLE item_consumption (
  consumption_id TEXT PRIMARY KEY,
  profile_id TEXT NOT NULL,
  hero_id TEXT NOT NULL,
  item_id TEXT NOT NULL,
  quantity INTEGER NOT NULL CHECK(quantity > 0),
  claim_event_id TEXT NOT NULL UNIQUE,
  consumed_at TEXT NOT NULL,
  FOREIGN KEY(profile_id) REFERENCES player_profile(profile_id) ON DELETE CASCADE,
  FOREIGN KEY(profile_id,hero_id) REFERENCES hero(profile_id,hero_id) ON DELETE CASCADE,
  FOREIGN KEY(hero_id,claim_event_id)
    REFERENCES hero_vocation_unlock(hero_id,claim_event_id) ON DELETE CASCADE
) STRICT;
CREATE INDEX idx_item_consumption_profile_item ON item_consumption(profile_id,item_id);

-- --------------------------------------------------------------------------------------------
-- Runs
-- --------------------------------------------------------------------------------------------

-- phase holds the engine's RunPhase values (src/battle_dice/core/models.py). The FDD v0.1 names
-- map as follows: PARTY_SETUP = the profile has no run with completed_at IS NULL;
-- PREPARATION = 'upgrade' and 'equipment' (which of the two allows a vocation change is an open
-- decision, fixture CE-19); COMBAT = 'battle'; OUTCOME = 'victory' or 'defeat'.
-- content_sha256 must be the hash of the pinned catalog row. build_sha256 is the hash of the
-- party build frozen by StartRun: SHA-256 of the canonical JSON list of [hero_id, build_sha256]
-- pairs of the first encounter's snapshots, ordered by hero_id. The pinned columns never change
-- (trigger below).
CREATE TABLE run (
  run_id TEXT PRIMARY KEY,
  profile_id TEXT NOT NULL,
  catalog_version TEXT NOT NULL,
  content_sha256 TEXT NOT NULL
    CHECK(length(content_sha256) = 64 AND content_sha256 NOT GLOB '*[^0-9a-f]*'),
  rules_version TEXT NOT NULL,
  rng_version TEXT NOT NULL,
  seed_decimal TEXT NOT NULL,
  build_sha256 TEXT NOT NULL
    CHECK(length(build_sha256) = 64 AND build_sha256 NOT GLOB '*[^0-9a-f]*'),
  phase TEXT NOT NULL CHECK(phase IN ('battle','upgrade','equipment','victory','defeat')),
  revision INTEGER NOT NULL DEFAULT 0 CHECK(revision >= 0),
  started_at TEXT NOT NULL,
  completed_at TEXT,
  CHECK((completed_at IS NOT NULL) = (phase IN ('victory','defeat'))),
  FOREIGN KEY(profile_id) REFERENCES player_profile(profile_id) ON DELETE CASCADE,
  FOREIGN KEY(catalog_version,content_sha256)
    REFERENCES content_catalog(catalog_version,content_sha256) ON DELETE RESTRICT
) STRICT;
CREATE INDEX idx_run_profile ON run(profile_id);

CREATE TABLE encounter_build_snapshot (
  run_id TEXT NOT NULL,
  encounter_id TEXT NOT NULL,
  hero_id TEXT NOT NULL,
  vocation_id TEXT NOT NULL,
  build_json TEXT NOT NULL CHECK(json_valid(build_json)),
  build_sha256 TEXT NOT NULL
    CHECK(length(build_sha256) = 64 AND build_sha256 NOT GLOB '*[^0-9a-f]*'),
  PRIMARY KEY(run_id,encounter_id,hero_id),
  FOREIGN KEY(run_id) REFERENCES run(run_id) ON DELETE CASCADE,
  FOREIGN KEY(hero_id) REFERENCES hero(hero_id) ON DELETE CASCADE
) STRICT;

-- Defect 7. A run upgrade is never permanent: the column is kept from v0.1 and can only be 0.
-- The upgraded die must be a die of that hero.
CREATE TABLE run_die_upgrade (
  run_id TEXT NOT NULL,
  upgrade_id TEXT NOT NULL,
  hero_id TEXT NOT NULL,
  die_instance_id TEXT NOT NULL,
  override_json TEXT NOT NULL CHECK(json_valid(override_json)),
  permanent INTEGER NOT NULL DEFAULT 0 CHECK(permanent = 0),
  applied_at TEXT NOT NULL,
  PRIMARY KEY(run_id,upgrade_id),
  FOREIGN KEY(run_id) REFERENCES run(run_id) ON DELETE CASCADE,
  FOREIGN KEY(hero_id) REFERENCES hero(hero_id) ON DELETE CASCADE,
  FOREIGN KEY(hero_id,die_instance_id)
    REFERENCES hero_die_instance(hero_id,die_instance_id) ON DELETE CASCADE
) STRICT;

-- Defect 7. A permanent upgrade names the event that awarded it; one event awards one upgrade.
CREATE TABLE hero_permanent_upgrade (
  upgrade_id TEXT PRIMARY KEY,
  hero_id TEXT NOT NULL,
  upgrade_kind TEXT NOT NULL,
  effect_json TEXT NOT NULL CHECK(json_valid(effect_json)),
  source_event_id TEXT NOT NULL UNIQUE,
  earned_at TEXT NOT NULL,
  FOREIGN KEY(hero_id) REFERENCES hero(hero_id) ON DELETE CASCADE,
  FOREIGN KEY(source_event_id) REFERENCES progression_event_log(event_id) ON DELETE NO ACTION
) STRICT;

-- Unique award identity prevents class-farming/replay duplication for an encounter.
-- Defect 6: a row is either an award (base 1, challenge 0 or 1, no denial reason) or a denial
-- (base 0, challenge 0, a denial reason from the error-code registry).
-- A run that has award rows cannot be deleted on its own (NO ACTION): the awards are the
-- evidence for the mastery points. The run goes when its profile is reset.
CREATE TABLE mastery_award_event (
  event_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  encounter_id TEXT NOT NULL,
  hero_id TEXT NOT NULL,
  catalog_version TEXT NOT NULL,
  vocation_id TEXT NOT NULL,
  base_points INTEGER NOT NULL CHECK(base_points IN (0,1)),
  challenge_points INTEGER NOT NULL CHECK(challenge_points IN (0,1)),
  threat_rating INTEGER NOT NULL CHECK(threat_rating BETWEEN 0 AND 5),
  denial_reason TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(run_id,encounter_id,hero_id,vocation_id),
  CHECK(challenge_points <= base_points),
  CHECK((base_points = 0) = (denial_reason IS NOT NULL)),
  FOREIGN KEY(run_id) REFERENCES run(run_id) ON DELETE NO ACTION,
  FOREIGN KEY(hero_id) REFERENCES hero(hero_id) ON DELETE CASCADE,
  FOREIGN KEY(catalog_version,vocation_id)
    REFERENCES vocation_def(catalog_version,vocation_id) ON DELETE RESTRICT
) STRICT;
CREATE INDEX idx_mastery_award_hero ON mastery_award_event(hero_id,vocation_id);
CREATE INDEX idx_quest_completion_lookup ON quest_completion(profile_id,quest_id);

-- --------------------------------------------------------------------------------------------
-- Idempotency and audit
-- --------------------------------------------------------------------------------------------

-- Only accepted commands are stored, as in the shipped engine. command_scope is
-- 'profile:<profile_id>' for class evolution commands. A repeated command id with the same
-- command_sha256 returns result_json again with "duplicate": true and has no second effect.
-- command_sha256 = SHA-256 of the canonical JSON of {"type": ..., "params": ...}.
CREATE TABLE processed_command (
  command_scope TEXT NOT NULL,
  command_id TEXT NOT NULL,
  profile_id TEXT NOT NULL,
  command_type TEXT NOT NULL,
  command_sha256 TEXT NOT NULL
    CHECK(length(command_sha256) = 64 AND command_sha256 NOT GLOB '*[^0-9a-f]*'),
  result_json TEXT NOT NULL CHECK(json_valid(result_json)),
  created_at TEXT NOT NULL,
  PRIMARY KEY(command_scope,command_id),
  FOREIGN KEY(profile_id) REFERENCES player_profile(profile_id) ON DELETE CASCADE
) STRICT;
CREATE INDEX idx_processed_command_profile ON processed_command(profile_id);

-- Defect 4. One hash-chained log per profile. event_id is '<profile_id>:<event_seq>'. run_id is
-- NULL for an event outside a run (for example a claim during party setup).
CREATE TABLE progression_event_log (
  profile_id TEXT NOT NULL,
  event_seq INTEGER NOT NULL CHECK(event_seq >= 0),
  event_id TEXT NOT NULL UNIQUE,
  run_id TEXT,
  event_type TEXT NOT NULL,
  event_json TEXT NOT NULL CHECK(json_valid(event_json)),
  previous_event_hash TEXT NOT NULL
    CHECK(length(previous_event_hash) = 64 AND previous_event_hash NOT GLOB '*[^0-9a-f]*'),
  event_hash TEXT NOT NULL
    CHECK(length(event_hash) = 64 AND event_hash NOT GLOB '*[^0-9a-f]*'),
  created_at TEXT NOT NULL,
  PRIMARY KEY(profile_id,event_seq),
  FOREIGN KEY(profile_id) REFERENCES player_profile(profile_id) ON DELETE CASCADE,
  FOREIGN KEY(run_id) REFERENCES run(run_id) ON DELETE SET NULL
) STRICT;
CREATE INDEX idx_progression_event_run ON progression_event_log(run_id);

-- --------------------------------------------------------------------------------------------
-- Triggers: rules a CHECK or a foreign key cannot express
-- --------------------------------------------------------------------------------------------

-- A hero can only switch to a vocation that this hero has claimed.
CREATE TRIGGER trg_hero_active_vocation_unlocked
BEFORE UPDATE OF active_vocation_id ON hero
WHEN NOT EXISTS (
  SELECT 1 FROM hero_vocation_unlock
  WHERE hero_id = NEW.hero_id AND catalog_version = NEW.catalog_version
    AND vocation_id = NEW.active_vocation_id)
BEGIN
  SELECT RAISE(ABORT, 'active vocation is not unlocked for this hero');
END;

-- A hero-scoped quest completion must name a hero of the same profile, and goes with that hero.
CREATE TRIGGER trg_quest_completion_hero_exists
BEFORE INSERT ON quest_completion
WHEN NEW.qualifier_scope = 'hero' AND NOT EXISTS (
  SELECT 1 FROM hero WHERE hero_id = NEW.qualifier_id AND profile_id = NEW.profile_id)
BEGIN
  SELECT RAISE(ABORT, 'hero-scoped quest completion names no hero of this profile');
END;

CREATE TRIGGER trg_hero_delete_quest_completion
AFTER DELETE ON hero
BEGIN
  DELETE FROM quest_completion
  WHERE profile_id = OLD.profile_id AND qualifier_scope = 'hero' AND qualifier_id = OLD.hero_id;
END;

-- Dice: a new die starts on the bench; equipping is an insert into hero_equipped_die.
CREATE TRIGGER trg_die_instance_starts_on_bench
BEFORE INSERT ON hero_die_instance
WHEN NEW.location <> 'bench'
BEGIN
  SELECT RAISE(ABORT, 'a new die instance starts on the bench; equip it through hero_equipped_die');
END;

-- Dice: location must agree with hero_equipped_die.
CREATE TRIGGER trg_die_instance_location_matches_slots
BEFORE UPDATE OF location ON hero_die_instance
WHEN (NEW.location = 'equipped') <> EXISTS (
  SELECT 1 FROM hero_equipped_die
  WHERE hero_id = NEW.hero_id AND die_instance_id = NEW.die_instance_id)
BEGIN
  SELECT RAISE(ABORT, 'die location must match hero_equipped_die; change the equipped slots instead');
END;

-- Dice: owner and definition never change (a die is never reforged into another die).
CREATE TRIGGER trg_die_instance_identity_immutable
BEFORE UPDATE OF die_instance_id, hero_id, definition_id, definition_version, acquisition_key
ON hero_die_instance
BEGIN
  SELECT RAISE(ABORT, 'a die instance keeps its owner and definition');
END;

-- Dice: never deleted while the hero exists. When the hero itself is deleted (also by a profile
-- reset) the hero row is already gone when this trigger runs, so the cascade passes.
CREATE TRIGGER trg_die_instance_never_deleted
BEFORE DELETE ON hero_die_instance
WHEN EXISTS (SELECT 1 FROM hero WHERE hero_id = OLD.hero_id)
BEGIN
  SELECT RAISE(ABORT, 'die instances are moved to the bench, never deleted');
END;

CREATE TRIGGER trg_equipped_die_insert_sets_location
AFTER INSERT ON hero_equipped_die
BEGIN
  UPDATE hero_die_instance SET location = 'equipped'
  WHERE hero_id = NEW.hero_id AND die_instance_id = NEW.die_instance_id;
END;

CREATE TRIGGER trg_equipped_die_delete_sets_location
AFTER DELETE ON hero_equipped_die
BEGIN
  UPDATE hero_die_instance SET location = 'bench'
  WHERE hero_id = OLD.hero_id AND die_instance_id = OLD.die_instance_id;
END;

CREATE TRIGGER trg_equipped_die_update_sets_location
AFTER UPDATE OF hero_id, die_instance_id ON hero_equipped_die
WHEN OLD.hero_id <> NEW.hero_id OR OLD.die_instance_id <> NEW.die_instance_id
BEGIN
  UPDATE hero_die_instance SET location = 'bench'
  WHERE hero_id = OLD.hero_id AND die_instance_id = OLD.die_instance_id;
  UPDATE hero_die_instance SET location = 'equipped'
  WHERE hero_id = NEW.hero_id AND die_instance_id = NEW.die_instance_id;
END;

-- Run pins never change (defect 8: content, rules, RNG, seed and build are fixed at StartRun).
CREATE TRIGGER trg_run_pins_immutable
BEFORE UPDATE OF run_id, profile_id, catalog_version, content_sha256, rules_version, rng_version,
  seed_decimal, build_sha256, started_at ON run
BEGIN
  SELECT RAISE(ABORT, 'run pins are immutable');
END;

-- Event log: events are appended in order and each one links to the hash of the one before.
CREATE TRIGGER trg_progression_event_chain
BEFORE INSERT ON progression_event_log
WHEN NEW.event_seq <> (
       SELECT COALESCE(MAX(event_seq) + 1, 0) FROM progression_event_log
       WHERE profile_id = NEW.profile_id)
  OR NEW.previous_event_hash <> COALESCE(
       (SELECT event_hash FROM progression_event_log
        WHERE profile_id = NEW.profile_id AND event_seq = NEW.event_seq - 1),
       '0000000000000000000000000000000000000000000000000000000000000000')
BEGIN
  SELECT RAISE(ABORT, 'progression event breaks the sequence or the hash chain');
END;

-- Event log: append only. run_id is the one column that may change (SET NULL when a run goes).
CREATE TRIGGER trg_progression_event_immutable
BEFORE UPDATE OF profile_id, event_seq, event_id, event_type, event_json, previous_event_hash,
  event_hash, created_at ON progression_event_log
BEGIN
  SELECT RAISE(ABORT, 'progression events are append only');
END;

INSERT INTO schema_migration(version, description, applied_at)
VALUES (2, 'Class Evolution FDD v0.2 baseline schema', strftime('%Y-%m-%dT%H:%M:%SZ', 'now'));

PRAGMA user_version = 2;

COMMIT;

-- --------------------------------------------------------------------------------------------
-- Not enforced by the database (the domain service checks these before it writes)
-- --------------------------------------------------------------------------------------------
--   * mastery_rank agrees with mastery_points and the catalog thresholds.
--   * Equipped inherited skills fit the active vocation's inheritance capacity, and each skill
--     has an eligible die face.
--   * Equipped dice are compatible with the active vocation and fit its dice capacity.
--   * Hash values are correct (SQLite has no SHA-256 function). The database checks their shape
--     and the continuity of the event chain only.
--   * PRAGMA user_version equals MAX(schema_migration.version). A PRAGMA cannot be constrained;
--     the application compares the two when it opens the database.
--   * profile_item_balance.quantity equals grants minus consumptions (see the table comment).
--   * A hero's active vocation is unlocked at the moment the hero row is inserted. The trigger
--     covers every later change.
--
-- --------------------------------------------------------------------------------------------
-- RESET PROFILE (defect 8)
-- --------------------------------------------------------------------------------------------
-- Every row that belongs to a profile hangs off player_profile through ON DELETE CASCADE, so a
-- reset is one delete inside a transaction. Catalog rows (content_catalog, vocation_def,
-- skill_def) and schema_migration are shared and stay.
--
--   PRAGMA foreign_keys = ON;          -- once per connection, outside any transaction
--   BEGIN IMMEDIATE;
--   DELETE FROM player_profile WHERE profile_id = :profile_id;
--   PRAGMA foreign_key_check;          -- must return no rows; otherwise ROLLBACK
--   COMMIT;
--
-- To keep the same profile id, insert a new player_profile row after the delete, inside the
-- same transaction.
--
-- Deleting one hero:  DELETE FROM hero WHERE hero_id = :hero_id;
--   Removes the hero's mastery, unlocks, skills, dice, consumptions, snapshots, run upgrades,
--   permanent upgrades, mastery awards and hero-scoped quest completions. Its item grants stay
--   with hero_id set to NULL, and the profile's events stay.
-- Deleting one run:   DELETE FROM run WHERE run_id = :run_id;
--   Removes its snapshots and run upgrades and sets run_id to NULL in its events and grants.
--   It fails while the run has mastery_award_event rows.
