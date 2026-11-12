# Project Status

## Project: Battle Dice
**Current Phase:** Implementation (the project was already under way when this file was created)
**Last Updated:** 2026-11-12 by the implementing engineer (Phase 4, step B)
**Health:** On Track

**Current goal (owner, 2026-11-11):** a fully configurable and playable demo.

## Progress

### Done
- Battle Dice MVP (BD-PRD-MVP-001): single-player dice RPG, rules 1.1.1, content 1.3.1; Windows launcher and standalone build
- Class Evolution specification v0.2, approved 2026-11-11 (`docs/class_evolution/FDD_v0.2.md`)
- Class Evolution Phase 1: hero build seam, slot schedules, vocation catalog, feature gate `class_evolution_v1` (off by default)
- Class Evolution Phase 2: progression rules in memory
- Class Evolution Phase 3: save file (SQLite profile store)
- 39 of 40 acceptance cases decided; 35 run as tests
- Class Evolution Phase 4, step A: the Guardian is playable by the rules (merged, pull request 19)
- Class Evolution Phase 4, step B: encounters from the catalog and the optional third battle; the threat-4 table tuned to 75-77% per party size

### In Progress
- Class Evolution Phase 4, step C: saved heroes in real runs

### Pending
- Phase 4, step D: screens (party setup with saved heroes, career screen, award panel, stop or fight on)
- Phase 4, step E: Field Medic in battle and the build panel
- Demo configuration (assumed scope, see decisions.md): a settings file with a Settings screen; a Class Evolution tuning file; demo start presets

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
- Class Evolution is not playable yet: no screen offers it and the game opens no save file.
- Balance of the Guardian and of the threat-4 fight is measured only by a simulated player; the numbers await an owner decision (Checkpoint 1 of the Phase 4 plan).
- Pacing: reaching the last capstone needs 52 to 104 winning runs on today's content (FDD open decision 5).
- Never launched on a physical Windows display; no human playtest yet.
