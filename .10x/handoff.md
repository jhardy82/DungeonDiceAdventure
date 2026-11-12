# Current Handoff

> This file tracks the context passed from one role to the next. Each role overwrites the "Current Handoff" section when passing work forward. Previous handoffs are preserved in the History section below.

## From: implementing engineer (Phase 4, step B) → To: next role
**Date:** 2026-11-12
**Phase:** Implementation

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
- Step B is done: a run can be started with the threat-4 encounter `training_04` as an optional
  third battle; after battle 2 the player stops with a victory or fights on. Its enemy table
  per party size is tuned by measurement (`docs/DECISION_LOG.md`, section 7.16).
- Next is step C: the game opens a save behind the gate, heroes are recruited, a run starts
  with saved heroes and build snapshots, mastery is awarded after each battle, and a hero may
  change vocation between battles. Then screens (D), Field Medic (E) and the demo's settings.
- The approved Phase 4 plan (steps A to E, two owner checkpoints) is in
  `docs/DECISION_LOG.md`, section 7.15.

Read first: `README.md`, `docs/DECISION_LOG.md` (sections 7.11 to 7.15),
`docs/class_evolution/FDD_v0.2.md`.

### Open Questions
- What should "fully configurable" cover in the demo? Asked twice, not answered. Work proceeds
  on an assumption recorded in `decisions.md`; the owner can widen or narrow it.
- Checkpoint 1: Guardian's numbers and the threat-4 table, from measurement.
- Checkpoint 2: pacing (runs needed to master a vocation).
- CE-31: what Duelist's Parry does (asked with the Duelist's wave).

---

## Handoff History

### 2026-11-11: init-project → first active role
Project state initialized on an existing project. `main` held everything up to Phase 4, step A.
