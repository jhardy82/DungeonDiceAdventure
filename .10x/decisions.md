# Project Decisions

> This file is the shared brain of the 10x-Team. Every role reads it before acting and writes to it after deciding. Append only — never delete or overwrite another role's decisions.

## Project: Battle Dice
Started: 2026-11-11

> **Decisions made before this file existed** are in `docs/DECISION_LOG.md` (D-01 to D-27, with
> the evidence for each) and, for Class Evolution, in `docs/class_evolution/FDD_v0.2.md`
> (sections 8 and 10) and `docs/class_evolution/ADR-CE-001.md`. They stay there and still hold.
> New decisions are appended below.

---

<!-- Decisions are appended below by each role. Format:
### [Date] — [Role]: [Decision Title]
- **Decision:** What was decided
- **Why:** Business/technical justification
- **Alternatives considered:** What else was evaluated
- **Trade-offs accepted:** What we're giving up
- **Impacts:** Which roles/components this affects
-->

### 2026-11-12 — Engineer: what "fully configurable" covers in the demo (assumption)
- **Decision:** Until the owner says otherwise, "fully configurable" means three things: (1) a
  settings file in the user's data folder with an in-game Settings screen (Class Evolution on or
  off, fixed or random seed, animation, window size, save folder, reset the profile), with launch
  flags overriding it; (2) a Class Evolution tuning file (mastery points per win, points per
  rank, the third battle and its enemies per party size, roster limit), validated on load and
  recorded with each run; (3) demo start presets for a new profile (fresh; a Squire one win from
  mastery; Guardian unlocked; Guardian mastered with Field Medic).
- **Why:** The owner's goal of 2026-11-11 is "a fully configurable and playable demo". The
  question of what configurable should cover was put to the owner twice and not answered, and
  the goal says not to wait. These three parts are the ones a demo needs to be shown and tuned
  without editing code.
- **Alternatives considered:** Also loading the base game's classes, dice, enemies and
  encounters from a folder. Left out for now: such runs fall outside the balance evidence and
  the replay pin.
- **Trade-offs accepted:** The scope may be wider or narrower than the owner meant; it is cheap
  to add or drop a part later because each is separate.
- **Impacts:** App and UI (settings, Settings screen), career rules (tuning), save (presets), docs.

### 2026-11-12 — Engineer: what of the configuration assumption was built, and what was not
- **Decision:** Built: the settings file, the Settings screen, Class Evolution on or off inside the
  game, the third battle on or off, mastery pace (normal, fast, very fast), roster size, four
  start presets, profile reset, seed, animation, window size. Not built: points per win as a
  setting, the third battle's enemy table as a setting, a separate tuning file.
- **Why:** The save's award rows allow 0 or 1 point, so more points per win needs a schema
  change; the pace setting changes how many points a rank needs instead. The enemy table is in
  the catalog whose hash a run's record pins, so a setting that edits it would break replay.
- **Alternatives considered:** Migrating the save schema for larger awards; a second encounter
  source with its own hash for a tuned table.
- **Trade-offs accepted:** The owner tunes the third battle by editing `vocation_catalog.json`
  (validated), not from the Settings screen.
- **Impacts:** Settings, save link, docs (`docs/DECISION_LOG.md`, section 7.19).

### 2026-11-12 — Engineer: the threat-4 table goes in as a default, not as a settled balance decision
- **Decision:** The enemy table of the optional third battle (`training_04`) is the one tuned by
  measurement in `docs/DECISION_LOG.md`, section 7.16 (75-77% for parties with a Guardian, per
  party size). The Guardian keeps its v0.1 numbers. Both stay open owner decisions.
- **Why:** The approved plan put these numbers to the owner at Checkpoint 1. The goal changed to
  a playable, configurable demo; waiting would block every later step, and the tuning file lets
  the owner change them without code.
- **Alternatives considered:** Stopping for Checkpoint 1 as planned.
- **Trade-offs accepted:** The demo ships numbers the owner has not approved. They are labelled
  as defaults and measured only by a simulated player.
- **Impacts:** Vocation catalog, balance evidence, the demo's tuning file.

### 2026-11-12 — Engineer: how Field Medic works, and what the skills panel offers
- **Decision:** Field Medic applies to any Healing face with one ally as its target that the
  hero rolls and that cannot revive; once per encounter it may be used on a downed ally for 1
  more mana, bringing the ally back at 1 HP. Skills are equipped on the Career screen between
  runs. A skill the rules of battle do not know (today: Squire Anchor) is listed and cannot be
  equipped.
- **Why:** The owner decided that Field Medic works in battle in the first slice (D-27). The
  catalog says "one equipped Healing face" without a way to choose one, and fixture CE-29 shows
  the revival as an option on the face.
- **Alternatives considered:** Letting the player mark one face for the skill (more screens,
  no gain while a Guardian has one Healing face); letting Squire Anchor be equipped with a
  warning.
- **Trade-offs accepted:** The reading is the builder's. Measured with the simulated player the
  skill changes nothing (it rarely has the 2 mana); the cost was not tuned.
- **Impacts:** Rules (`core/skills.py`), vocation catalog 0.4.0, save link, Career screen, docs
  (`docs/DECISION_LOG.md`, section 7.20).
