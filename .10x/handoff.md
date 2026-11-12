# Current Handoff

> This file tracks the context passed from one role to the next. Each role overwrites the "Current Handoff" section when passing work forward. Previous handoffs are preserved in the History section below.

## From: implementing engineer (Phase 4 complete) → To: next role
**Date:** 2026-11-12
**Phase:** Implementation

### Context
- **What are we building?** Battle Dice, a single-player turn-based dice RPG (Python 3.15,
  pygame-ce), and on top of it Class Evolution: 14 vocations, mastery, unlocks and a save file.
- **Current goal (owner):** a fully configurable and playable demo.

Where things stand:

- The first slice is playable behind the gate `class_evolution_v1` (off by default; Main menu,
  Settings switches it on): recruit, earn mastery, master the Squire, become a Guardian (at
  party setup or inside a run after Battle 1), fight the optional third battle, equip Field
  Medic and use it in battle.
- The demo is configured from the Settings screen (`README.md`, section Settings): four groups,
  with the comfort settings the owner chose in D-31 (text size, high contrast, battle speed,
  confirm a pass, help text delay) and the demo options in a group of their own.
- **The approved Phase 4 plan is built in full** (`docs/DECISION_LOG.md`, sections 7.15 to 7.21).
- What comes next is not decided: the open questions below, a person's playtest, or the next
  wave of vocations (FDD section 9).

Read first: `README.md`, `docs/DECISION_LOG.md` (sections 7.15 to 7.30),
`docs/class_evolution/FDD_v0.2.md`.

### Open Questions
- Checkpoint 2: pacing (runs needed to master a vocation).
- Squire Anchor in battle: needs a balance decision before it is built.
- CE-31: what Duelist's Parry does (asked with the Duelist's wave).

---

## Handoff History

### 2026-11-11: init-project → first active role
Project state initialized on an existing project. `main` held everything up to Phase 4, step A.

### 2026-11-12: implementing engineer (Phase 4, step B) → next role
Step B was done (the optional third battle); steps C, D, the demo's settings and step E followed and are merged or in review.

### 2026-11-12: implementing engineer (Phase 4, step E) → next role
Field Medic in battle and the skills panel were done and merged (pull request 25); the vocation change inside a run followed.
