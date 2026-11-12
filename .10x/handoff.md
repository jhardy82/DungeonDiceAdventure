# Current Handoff

> This file tracks the context passed from one role to the next. Each role overwrites the "Current Handoff" section when passing work forward. Previous handoffs are preserved in the History section below.

## From: implementing engineer (Phase 4, step E) → To: next role
**Date:** 2026-11-12
**Phase:** Implementation

### Context
- **What are we building?** Battle Dice, a single-player turn-based dice RPG (Python 3.15,
  pygame-ce), and on top of it Class Evolution: 14 vocations, mastery, unlocks and a save file.
- **Current goal (owner):** a fully configurable and playable demo.

Where things stand:

- The first slice is playable behind the gate `class_evolution_v1` (off by default; Main menu,
  Settings switches it on): recruit, earn mastery, master the Squire, become a Guardian, fight
  the optional third battle, equip Field Medic and use it in battle.
- The demo is configured from the Settings screen (`README.md`, section Settings).
- Step E is done: Field Medic in battle and the skills panel (`docs/DECISION_LOG.md`, 7.20).
- Next: the vocation change inside a run, after recovery and before the mandatory upgrade
  (acceptance case CE-19). It is the last rule of the approved Phase 4 plan (section 7.15).

Read first: `README.md`, `docs/DECISION_LOG.md` (sections 7.15 to 7.20),
`docs/class_evolution/FDD_v0.2.md`.

### Open Questions
- What should "fully configurable" cover in the demo? Asked twice, not answered. Work proceeds
  on an assumption recorded in `decisions.md`; the owner can widen or narrow it.
- Checkpoint 1: Guardian's numbers and the threat-4 table, from measurement.
- Checkpoint 2: pacing (runs needed to master a vocation).
- Field Medic's cost: the simulated player can rarely pay it (section 7.20).
- Squire Anchor in battle: needs a balance decision before it is built.
- CE-31: what Duelist's Parry does (asked with the Duelist's wave).

---

## Handoff History

### 2026-11-11: init-project → first active role
Project state initialized on an existing project. `main` held everything up to Phase 4, step A.

### 2026-11-12: implementing engineer (Phase 4, step B) → next role
Step B was done (the optional third battle); steps C, D, the demo's settings and step E followed and are merged or in review.
