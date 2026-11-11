# Current Handoff

> This file tracks the context passed from one role to the next. Each role overwrites the "Current Handoff" section when passing work forward. Previous handoffs are preserved in the History section below.

## From: init-project → To: First active role
**Date:** 2026-11-11
**Phase:** Setup → Implementation (the project was already under way)

### Context
Project state initialized on an existing project, so the usual opening questions are answered:

- **What are we building?** Battle Dice, a single-player turn-based dice RPG (Python 3.15,
  pygame-ce), and on top of it Class Evolution: 14 vocations, mastery, unlocks and a save file.
- **What problem does this solve?** The owner's current goal is a fully configurable and
  playable demo of the game with Class Evolution.
- **Who is the target user?** The owner first (to play and tune the demo), then players on
  Windows.

Where things stand:

- `main` holds everything up to Phase 4, step A (the Guardian is playable by the rules).
- Step B is in progress on the work branch: the rules engine can take extra encounters at run
  start and asks "stop or fight on" after battle 2. Still to do in step B: the threat-4 enemy
  table per party size in the catalog, its tests, and the measurement for Checkpoint 1.
- The approved Phase 4 plan (steps A to E, two owner checkpoints) is in
  `docs/DECISION_LOG.md`, section 7.15.

Read first: `README.md`, `docs/DECISION_LOG.md` (sections 7.11 to 7.15),
`docs/class_evolution/FDD_v0.2.md`.

### Open Questions
- What should "fully configurable" cover in the demo? Proposed and not yet answered: a settings
  file with a Settings screen; a Class Evolution tuning file (points per win, rank thresholds,
  third battle, roster limit); demo start presets; base game numbers from a folder.
- Checkpoint 1: Guardian's numbers and the threat-4 table, from measurement.
- Checkpoint 2: pacing (runs needed to master a vocation).
- CE-31: what Duelist's Parry does (asked with the Duelist's wave).

---

## Handoff History
(none yet)
