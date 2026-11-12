# Project Status

## Project: Battle Dice
**Current Phase:** Implementation (the project was already under way when this file was created)
**Last Updated:** 2026-11-12 by the implementing engineer (Phase 4 complete)
**Health:** On Track

**Current goal (owner, 2026-11-11):** a fully configurable and playable demo.

## Progress

### Done
- Battle Dice MVP (BD-PRD-MVP-001): single-player dice RPG, rules 1.1.1, content 1.3.1; Windows launcher and standalone build
- Class Evolution specification v0.2, approved 2026-11-11 (`docs/class_evolution/FDD_v0.2.md`)
- Class Evolution Phase 1: hero build seam, slot schedules, vocation catalog, feature gate `class_evolution_v1` (off by default)
- Class Evolution Phase 2: progression rules in memory
- Class Evolution Phase 3: save file (SQLite profile store)
- 39 of 40 acceptance cases decided; 37 run as tests
- Class Evolution Phase 4, step A: the Guardian is playable by the rules (merged, pull request 19)
- Class Evolution Phase 4, step B: encounters from the catalog and the optional third battle; the threat-4 table tuned to 75-77% per party size
- Class Evolution Phase 4, step C (part 1): recruiting, build snapshots at run start, challenge evidence, the run-to-save hand-over, a career-aware simulator; pacing measured
- Class Evolution Phase 4, step D: the screens. The first slice is playable behind the gate (recruit, mastery, career, Guardian, third battle)
- Demo configuration: a settings file and an in-game Settings screen (Class Evolution on or off, third battle, mastery pace, roster size, start presets, seed, animation, window size, profile reset)
- Class Evolution Phase 4, step E: Field Medic works in battle; the Career screen has a skills panel (equip, take off); catalog 0.4.0
- Class Evolution Phase 4: a saved hero changes vocation inside a run, after Battle 1 and before the upgrade (CE-19). The approved Phase 4 plan is built in full
- Fixed: a Guardian's upgrade broke the upgrade screen; an evolved hero had no picture in battle
- A tour of the slice in two runs is in the README, and a test plays it through the screens
- The gate-on self-check also plays a whole run with a Guardian from the vocation catalog; the packaged Windows build must report it

### In Progress
(none: the approved Phase 4 plan is built; the open points below are owner decisions)

### Pending

Role checklist. These are the 10x-Team's own passes; none has been run yet. The work listed
under Done was carried out before the team state existed.

- [ ] CTO: Strategic direction and tech decisions
- [ ] PM: Requirements and scope definition
- [ ] Architect: System design
- [ ] Staff Engineer: Coding standards and patterns
- [ ] EM: Task breakdown and estimation
- [ ] Senior Engineer: Implementation planning
- [ ] SDE: Code implementation
- [ ] DBA: Schema and data modeling
- [ ] Security: Threat model and security review
- [ ] QA: Test strategy and verification
- [ ] DevOps: CI/CD and deployment
- [ ] SRE: Monitoring and reliability

### Blocked
(none)

## Risks
- Two tuning knobs named in the configuration assumption were not built (points per win; the third battle's enemies as a setting); the reasons are in docs/DECISION_LOG.md section 7.19.
- Balance of the Guardian and of the threat-4 fight is measured only by a simulated player; the numbers await an owner decision (Checkpoint 1 of the Phase 4 plan).
- Pacing: reaching the last capstone needs 52 to 104 winning runs on today's content (FDD open decision 5).
- Field Medic made no measurable difference for the simulated player (153 against 152 wins in 240 runs): it rarely has the 2 mana. Whether the cost is right needs a person's play or an owner decision.
- Squire Anchor is learned but does nothing in battle yet; the skills panel says so and does not let it be equipped.
- A hero that masters its class in Battle 2 cannot evolve before the third battle (the only moment for a change inside a run is after Battle 1). An owner decision could open the stop-or-fight-on moment too.
- Never launched on a physical Windows display; no human playtest yet.
