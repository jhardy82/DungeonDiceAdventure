# Battle Dice: Class Evolution, Feature Design Document v0.2

| Field | Value |
|-------|-------|
| Document | BD-FDD-CE-001, version 0.2 |
| Status | **Proposed, awaiting owner approval.** Specification only. |
| Replaces | BD-UNIFIED-FDD-001 v0.1 (the 6,270-line design document reviewed on 2026-11-11) |
| Baseline | Rules `1.1.1`, content `1.3.1`, RNG `BD-PCG32-v1` |
| Feature gate | `class_evolution_v1`, off |
| Date | 2026-11-11 |

## 1. Summary

- **What this is.** The Class Evolution feature lets one hero train a class ("vocation") to
  mastery, unlock stronger vocations, and carry a few learned skills between them. v0.1 described
  14 vocations. v0.2 keeps that design and makes its contract executable and checked.
- **What v0.2 changes.** No design intent. It fixes the five gaps that blocked a build: a stale
  baseline, a catalog the engine could not read, a persistence contract that did not load its own
  example, free-text test cases, and a missing decision record.
- **What v0.2 does not do.** It adds no game code. Nothing in `src/` reads these files. With the
  gate off the game is byte for byte what it was.
- **What is asked of the owner.** Approve this document, and answer the open decisions in
  section 10. No build work starts before that.

## 2. What is in the repository

| Path | What it is | Checked by |
|------|------------|------------|
| `docs/class_evolution/FDD_v0.2.md` | This document | Read by the owner |
| `docs/class_evolution/ADR-CE-001.md` | The decision record v0.1 cites but never defined: one active vocation | Read by the owner |
| `docs/class_evolution/catalog/vocation_catalog.json` | The 14 vocations in the engine's own vocabulary | `tools/class_evolution/validate_catalog.py`, 49 tests |
| `docs/class_evolution/catalog/vocation_catalog.schema.json` | Strict JSON Schema for the catalog | Same |
| `docs/class_evolution/persistence/progression.sql` | The save database: 24 tables | `tools/class_evolution/check_persistence.py`, 73 tests |
| `docs/class_evolution/persistence/example_profile.json` | One worked save that loads into the database | Same |
| `docs/class_evolution/persistence/error_codes.json` | The one list of machine-readable codes | Same |
| `docs/class_evolution/fixtures/acceptance_fixtures.json` | The 40 acceptance cases as structured data, with a schema | Same |
| `tests/spec/` | 122 specification tests; they run in CI with the game's tests | CI on Linux and Windows |

- Run the two checkers by hand with `python tools/class_evolution/validate_catalog.py` and
  `python tools/class_evolution/check_persistence.py`. Both print `OK`.
- The JSON and SQL files are the source of truth. This document summarises them and must not
  contradict them; where it does, the files win and the document is wrong.

## 3. What changed from v0.1, and why

| # | v0.1 review finding | Resolution in v0.2 | Enforced by |
|--:|---------------------|--------------------|-------------|
| 1 | The baseline was stale: the catalog restored numbers the owner had overruled (for example Steadfast on self only). | Novice vocations are **pointers** to shipped classes (`"definition": "shipped"`). They hold no numbers, so they cannot drift. The catalog states the content version it was written against. | Validator refuses a catalog whose baseline differs from shipped content |
| 2 | The catalog was not executable: 0 of 34 actions had an effects list. | Every face is in the engine's face format. 17 shipped faces are reused by id; 12 new faces are authored. | Faces are built with the game's own content loader |
| 3 | The engine lacks much of what the new vocations need. | Each missing capability is one entry in `engine_gaps` (15 entries), naming who needs it and the engine file. Section 5 groups them by wave. | Validator: anything marked "new" must name a gap, and the reverse |
| 4 | There is not enough game to progress through. | Encounters are marked `shipped` or `to_author`. The validator reports every rank that cannot be trained and every vocation that cannot be unlocked on shipped content. | `TRAINING_DEAD_END`, `UNLOCK_DEAD_END` |
| 5 | The example save did not load into the schema. | Rewritten; it loads, and every hash and derived number in it is checked. | Persistence tests |
| 6 | No table for owned or benched dice. | New table `hero_die_instance`. | Triggers keep location and slots in step |
| 7 | An item reward could be granted twice. | New table `item_grant`, keyed by reward id. | Primary key |
| 8 | Audit links were loose: events had no id, a consumption could name another hero, a "permanent" flag sat on a run-only table. | Events have ids and a hash chain; a claim has at most one consumption, for its own hero; run upgrades can never be permanent. | Constraints and triggers |
| 9 | All 40 fixtures were free text. | 40 structured cases with a schema. 24 are fully specified; 16 need a design decision and say which. | Fixture schema and tests |
| 10 | Four error codes used in fixtures were not in the stated list; some conditions had two names. | One registry of 16 codes. Three v0.1 names are merged. A repeated command is a replay result, not an error. | Fixtures may use registry codes only |
| 11 | The cited record ADR-CE-001 was defined nowhere. | Written: `ADR-CE-001.md`. | Read by the owner |
| 12 | The v0.1 schema accepted 12 of 15 deliberately broken catalogs. | A strict schema plus a validator; 29 seeded violations are each rejected by a test. | Catalog tests |
| 13 | Two mastery rewards always clamp to zero (Ranger +1 speed, Arcanist +1 mana). | Kept as authored, reported as warnings. Open decision 3. | `REWARD_ALWAYS_CLAMPED` |
| 14 | Command envelopes differed from the engine's. | Fixtures use the engine's envelope: `type`, `command_id`, `state_revision`, `params`. | Fixture schema |

## 4. The baseline rule

- **Gate off means identical.** With `class_evolution_v1` off, the replay pin
  `tests/golden/replay_pin.json` reproduces byte for byte. This is fixture CE-01, and it is the
  first gate of every later phase.
- **Novices cannot drift.** Squire, Apprentice and Scout are read from shipped content. When the
  shipped numbers change (as they did in 1.3.0 and 1.3.1), the catalog needs only its baseline
  field updated; the validator fails until that is done.
- **New vocations inherit shipped values where v0.1 is silent:** starting mana and corruption,
  two rerolls, and the suggested row, from the novice family they upgrade from.

## 5. The vocation catalog

### 5.1 Roster and release order

A vocation is released in a wave. No vocation is released before the vocations its prerequisite
names.

| Wave | Vocation | Group | Prerequisite | Schedule | Passive | Engine work needed first |
|-----:|----------|-------|--------------|----------|---------|--------------------------|
| 0 | Squire, Apprentice, Scout | Novice | None | Shipped | Shipped | Inherited skills (for every wave) |
| 1 | Guardian | Advanced | Squire mastered | Shipped (single) | New: ally Defense bonus | 1 new passive |
| 2 | Spellblade | Advanced | Squire and Apprentice mastered | Shipped (resource then attack) | Shipped type | Corruption as a face cost |
| 2 | Ranger | Advanced | Scout mastered | Shipped (status then attack) | Shipped type | None beyond wave 1 |
| 3 | Duelist | Advanced | Squire and Scout mastered | New: two categories in the first slot | New | 1 schedule rule, 1 passive |
| 3 | Arcanist | Advanced | Apprentice mastered | New: slot needs a face tag | New | 1 schedule rule, 1 passive |
| 3 | Shadowbinder | Advanced | Apprentice and Scout mastered | Shipped policy, new combination | New | 1 passive |
| 4 | Champion | Capstone | Guardian and Duelist mastered | Shipped (defense then attack) | New: reaction shield bonus | 1 passive |
| 4 | Archmage | Capstone | Arcanist and Shadowbinder mastered | New: three ordered slots | New type shared with wave 3 | Three dice in the planner and on screen |
| 5 | Hero | Capstone | Champion and Archmage mastered, **or** three advanced mastered and the Trial of the Hero | New: two distinct categories | New: optional heal bonus, once per encounter | 1 schedule rule, 1 passive |
| 5 | Trickster | Secret | Scout mastered and the Crooked Mirror quest, **or** Apprentice mastered and a Jester Mask | New | New: paid reroll | Quests, items, discovery, 1 reaction effect |
| 5 | Dragon Knight | Secret | Spellblade mastered and a Drake Scale (consumed) | Shipped | New | Items, discovery |

- **Change from the wave list agreed on 2026-11-11.** Champion moved from the second wave to the
  fourth: it requires a mastered Duelist, which is a third-wave vocation. Hero and the two secret
  vocations became a fifth wave. The validator now fails any catalog that releases a vocation
  before its prerequisites (`UNLOCK_DEAD_END`).

### 5.2 Counts

| Item | Count | Of which new to the engine |
|------|------:|---------------------------:|
| Vocations | 14 | 11 |
| Dice | 23 | 23 (novice dice stay in shipped content) |
| Faces | 29 used | 12 authored, 17 shipped faces reused by id |
| Schedules | 10 | 5 |
| Passives | 11 | 9 need a new engine type |
| Reactions | 8 authored, plus 3 shipped reused | 1 needs a new effect |
| Inherited skills | 14 | All (no skill system exists) |
| Encounters | 7 | 5 to author (2 map to the shipped battles) |
| Items and quests | 2 and 2 | All |

### 5.3 Engine gaps (15)

| Needed from wave | Gap | Needed by |
|-----------------:|-----|-----------|
| 0 | Inherited skills: learn, equip within a capacity, apply to a face | Every vocation's rank reward |
| 1 | Passive: Defense die bonus on another ally only | Guardian |
| 2 | A face that costs corruption, the way faces cost mana | Spellblade |
| 2 | Three descriptive face tags from v0.1 (no rule reads them yet) | Spellblade, Dragon Knight, Trickster |
| 3 | Schedule: more than one category allowed in the first slot | Duelist, Trickster |
| 3 | Schedule: a slot that requires a face tag | Arcanist |
| 3 | Passive: attack bonus keyed on which category opened the combo | Duelist |
| 3 | Passive: bonus mana on a Resource die | Arcanist |
| 3 | Passive: remove own corruption when a sequence completes | Shadowbinder, Archmage |
| 4 | Schedule: three ordered slots | Archmage |
| 4 | Passive: extra shield on the hero's own Guard reaction | Champion, Dragon Knight |
| 5 | Schedule: two actions of different categories | Hero |
| 5 | Passive: optional heal bonus with a once-per-encounter counter | Hero |
| 5 | Passive: a reroll bought with mana and corruption | Trickster |
| 5 | Reaction effect: corruption added to the reacting hero | Trickster |

### 5.4 Mastery

- Eight ranks per vocation. One point per eligible win, plus one for the vocation's bonus
  challenge. Points to master: novice 14, advanced and secret sidegrade 24, capstone and secret
  prestige 35.
- **Anti-farming:** each rank has a minimum encounter threat. A win below it awards nothing and
  records the reason `UNDER_THREAT_CAP`.
- Permanent stat rewards are capped per hero: health +2, mana +1, speed +1.

### 5.5 Unlock routes

- A hero unlocks a vocation by satisfying one **route** of its prerequisite.
- **One rule for route ids,** used by the catalog, the save, the fixtures and later the engine:
  the alternatives of a prerequisite whose top level is `any` are `route_0`, `route_1`, ... in
  catalog order. Every other vocation has the single route `route_0`.
- A released catalog may add an alternative at the end. It may never reorder or remove one,
  because saved unlocks record the route id.
- Only Hero and Trickster have two routes.

## 6. The persistence contract

- **Storage:** one SQLite database per installation, schema version 2. It needs SQLite 3.38 or
  later (checked with 3.53.1, the library bundled with the project's Python).
- **Owner decision carried out:** all 21 tables of v0.1 are kept, with the revision design, and
  three are added.

| Group | Tables |
|-------|--------|
| Catalog | `content_catalog`, `vocation_def`, `skill_def` |
| Profile and heroes | `player_profile`, `hero`, `profile_vocation_discovery` |
| Progress | `hero_vocation_mastery`, `hero_vocation_unlock`, `hero_skill`, `hero_equipped_skill` |
| Dice | **`hero_die_instance`** (new), `hero_equipped_die` |
| Items and quests | `profile_item_balance`, **`item_grant`** (new), `item_consumption`, `quest_completion` |
| Runs | `run`, `encounter_build_snapshot`, `run_die_upgrade`, `hero_permanent_upgrade`, `mastery_award_event` |
| Commands and audit | `processed_command`, `progression_event_log` |
| Schema | **`schema_migration`** (new) |

- **What the database enforces** (constraints and 13 triggers): every table is `STRICT`; every
  foreign key states what happens on delete; a hero's active vocation must be unlocked; a die
  never disappears and its location matches its slot; a run's pinned versions and hashes cannot
  change; the event log is append-only and its chain is continuous; a reward id grants once.
- **What it cannot enforce** (the domain service must check before it writes):
  - The mastery rank agrees with the points and the catalog thresholds.
  - Equipped skills fit the vocation's capacity, and each has an eligible die face.
  - Equipped dice are compatible with the active vocation.
  - Hash values are correct. SQLite has no SHA-256 function; the database checks shape and
    continuity only.
  - The item balance equals grants minus consumptions.
- **Reset:** deleting the profile row removes everything that belongs to it, in one transaction.
  The exact statements are at the end of `progression.sql`.

## 7. Commands and error codes

- Commands use the engine's envelope: `type`, `command_id`, `state_revision`, `params`.
- **A rejected command returns exactly one code and changes nothing:** no row, no revision, no
  random draw.
- **A repeated command is not an error.** The same `command_id` sent again unchanged returns the
  stored result with `duplicate: true`. This replaces v0.1's `DUPLICATE_COMMAND`.
- When several conditions fail at once, the registry's `check_order` says which is reported.

| Kind | Codes |
|------|-------|
| Command rejection | `PHASE_LOCKED`, `NOT_DISCOVERED`, `HERO_NOT_ELIGIBLE`, `PREREQUISITE_UNMET`, `ITEM_INSUFFICIENT`, `CAPACITY_EXCEEDED`, `INCOMPATIBLE_DIE`, `NO_LEGAL_FACE`, `REVISION_CONFLICT`, `UNSUPPORTED_SECONDARY_VOCATION`, `COMMAND_ID_REUSED` (proposed) |
| Award denial | `UNDER_THREAT_CAP`, `ENCOUNTER_NOT_WON` (proposed) |
| Load failure | `CONTENT_MIGRATION_REQUIRED` |
| Content validation | `TRAINING_DEAD_END`, `UNLOCK_DEAD_END` (proposed) |

- Three codes are marked proposed because v0.1 did not name them. Approving this document
  approves them.

## 8. Acceptance fixtures

- 40 cases, CE-01 to CE-40: 21 at priority P0, 19 at P1.
- Each case is: given this state, when this one command or trusted event is applied, then this
  result and state.
- **24 are fully specified.** They become executable tests in Phases 2 and 3.
- **16 need a design decision.** Each states its assumption, so it can be confirmed or changed.

| Case | The question |
|------|--------------|
| CE-01 | Where does the feature gate live (content file, settings or build flag), and is the save database opened at all while it is off? |
| CE-09 | Does a hidden secret vocation show as an anonymous placeholder in the career tree, or not at all? |
| CE-10 | Does discovery only move forward, and what does the clue count count? |
| CE-18 | Which dice fit which vocation? The case assumes a die fits only a vocation named in its tags. |
| CE-19 | Is changing vocation allowed before the mandatory upgrade, after it, or both? The case assumes before. |
| CE-24 | Which reason is recorded for a lost encounter? The case proposes `ENCOUNTER_NOT_WON`. |
| CE-25 | Are a run's upgrade rows deleted at run end, or kept as history and no longer applied? The case assumes kept. |
| CE-28 | Is equipping a skill with no eligible face rejected (assumed) or accepted and shown as inert? |
| CE-29 | Which code or reason does a face disabled for lack of mana carry? |
| CE-30 | Does an illegal action plan get a registry code? The shipped engine rejects it with free text. |
| CE-31 | What exactly does Duelist's Parry reaction do in the engine? |
| CE-32 | Which fields are left out of every hash, and what is the canonical encoding of progression events? |
| CE-35 | How do evolved heroes enter `StartRun` (class ids today, hero ids with build snapshots later)? |
| CE-36 | Which encounters count as available, and what are their threat ratings? |
| CE-39 | May a vocation change happen before recovery? Otherwise "a downed hero stays down" is unreachable. |
| CE-40 | With the gate on and a fresh profile, must the replay pin match exactly, final state hash included? |

## 9. Phased plan and gates

| Phase | What | Gate to pass |
|------:|------|--------------|
| 0 | This document | Owner approves v0.2 |
| 1 | Foundations, gate off: a resolved per-hero build passed in at run start; schedules generalised to ordered slots; the catalog loaded through the validator | Replay pin byte-identical; every existing test passes |
| 2 | Progression rules in memory: prerequisites, discovery, claims, mastery awards, stat caps, skill budget | The fully specified rule fixtures pass |
| 3 | Persistence: the profile store behind an interface; transactions, idempotent commands, migration and backup | Rollback, repeated-command and migration fixtures pass |
| 4 | Vertical slice: Squire to Guardian, end to end. Roster and vocation screens, award after victory, switch between battles | Playable; pacing measured with the simulator |
| 5 | Roster in waves 2 to 5 (section 5.1) | Each wave inside the 70-85% band on a sampled matrix |
| 6 | Release: instrumentation, sampled balance report, all P0 and P1 fixtures | v0.1 section 10.1 gates |

- Every phase leaves the game shippable with the gate off.
- The first playable evolution arrives before the expensive engine work of waves 3 to 5.

## 10. Open decisions for the owner

1. **Guardian cannot reach rank 8 on shipped encounters.** Its last rank-up needs a threat-4
   encounter; shipped battles stop at threat 3. Options: author one threat-4 training encounter
   as part of the first slice, or lower the advanced threat floor to 3.
2. **Guardian's passive as written in v0.1 is weaker than the Squire's shipped Steadfast.**
   Guardian: +1 shield on a Defense die that targets another ally. Squire (shipped): +1 on any
   Defense die, self or ally. An evolution that loses power needs a retune before it is built.
3. **New vocations' numbers were tuned against the old novices.** Examples: Arcanist health 9
   against Apprentice 12; Ranger speed 14 against Scout 10; two mastery rewards that always
   clamp to zero. Proposal: retune each wave by measurement when it is built, as was done for
   the three novice classes.
4. **The 16 fixtures in section 8.**
5. **Pacing.** By the thresholds above, reaching Hero by the lineage route needs 208 mastery
   points for one hero: 52 to 104 winning runs on two-battle content. Options: shrink the
   thresholds, add encounters, or award more per win.

## 11. Risks

| Risk | Why it matters | Mitigation |
|------|----------------|------------|
| Pacing | 52 to 104 winning runs to the last capstone | Open decision 5; measure in Phase 4 before the roster grows |
| Balance surface | 3 classes give 55 party compositions; 14 vocations give 11,627 before skills | Sample the matrix per wave; do not enumerate |
| Engine cost of waves 3 to 5 | 4 new schedule rules (5 new schedules), 8 of the 9 new passives, three-dice planner | One wave at a time behind the gate |
| The specification is not evidence of fun | It makes the contract checkable, nothing more | Phase 4 slice and a human playtest |

## 12. What is not known

- Whether the feature is balanced or enjoyable: `<UNKNOWN>` until Phase 4.
- Whether the thresholds in v0.1 suit this game's run length: `<UNKNOWN>`; see open decision 5.
- Whether the 16 assumed answers in section 8 match the owner's intent: `<UNKNOWN>` until
  answered.
