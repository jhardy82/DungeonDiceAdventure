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
