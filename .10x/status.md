# Project Status

## Project: Battle Dice
**Current Phase:** Implementation (the project was already under way when this file was created)
**Last Updated:** 2026-11-24 by the implementing engineer (owner decisions D-37 and D-38; rules 1.2.0 and content 1.4.0, decision log 7.43 and 7.44)
**Health:** On Track

**Current goal (owner, 2026-11-11):** a fully configurable and playable demo.

## Progress

### Done
- Battle Dice MVP (BD-PRD-MVP-001): single-player dice RPG, rules 1.2.0 and content 1.4.0 (D-38; before: rules 1.1.2 with the two rule fixes of D-34, content 1.3.1); Windows launcher and standalone build
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
- Owner decisions of 2026-11-12: the Guardian's numbers and the third battle's table accepted as built (D-28); a hero may also change vocation at the stop-or-fight-on decision (D-29, built)
- The demo's configuration (D-31), part 1: Settings in four groups with a demo group, reset to defaults, Settings from the pause menu, the dice seed typed on the New Run screen
- Field Medic at the owner's numbers (D-30): no extra mana, the ally back at 5 HP; catalog 0.5.0. Measured: 316 wins of 480 against 297 without the skill
- The demo's configuration (D-31), part 2a: four new settings: high contrast, battle speed at start, confirm a pass that leaves a die unused, help text delay
- The demo's configuration (D-31), part 2b: text size (Normal, Large). Each frame is measured and a text grows only where it has room; a layout check walks 39 states under three fonts and two window sizes

- Fixes after the playtest by eight AI playtesters (D-34), five batches, all merged: predictions and the battle screen; keys, safeguards and mouse reach; what the Class Evolution screens say; two rule fixes (rules 1.1.2, catalog 0.5.1); remaining information and layout. of 57 findings 44 are fixed, 3 fixed in part, 7 left as they are with a reason, 3 wait for the owner (decision log sections 7.32 to 7.36)

### In Progress
- Android app (D-33): phase 0, the walking skeleton with Flet, is built, and was built and started on GitHub's machines (APK 107.6 MB, target API 36, 16 KB pages, self-check passed at four starts on an emulator, upright and sideways). Open: the owner's install on the phone, a look at the emulator screenshots, and the go or no-go decision (`docs/android/PLAN.md`, "Phase 0, measured")
- D-35 (owner, 2026-11-21): dismissing a hero, recruit names without a class, and the Mastery pace note are built (decision log 7.38); Android phase 1 groundwork: steps 1 (tests on Python 3.14) and 2 (messages worded for touch) are built; step 3 (screen data outside pygame) goes with the phone screens
- Second playtest round by four AI players (2026-11-21): no blocker; the "press again" safeguards rebuilt so a question ends when the player does anything else; 28 of 34 findings fixed, 6 left with a reason (3 of them are questions for the owner) (`docs/PLAYTEST_TEAM_2026-11-21.md`, section 7; decision log 7.40)
- A fifth AI playtester played two whole runs (2026-11-21), one with the third battle: no blocker; 12 findings, 11 fixed. The one defect: an enemy action's number starts again in each battle, and the reaction prompt and the second-reaction question took it for the run's (decision log 7.41; playtest report section 8)
- The Android emulator check failed once on pull request 45 by its own doing: the `monkey` tool that started the app turns the screen. The app is started with `am start` now (decision log 7.40; `docs/android/PLAN.md`, run 9)
- D-36 (owner, 2026-11-22): demo not played yet; the react reason goes with the next rules change; reaction keys stay. Both balance questions are measured (decision log 7.42; `tools/balance_questions.py`): the third battle is harder than Battle 2 without a Guardian at every party size, and the enemies' status-first rule is what holds the win rate at 77%. Options are with the owner
- D-37 and D-38 (owner, 2026-11-24): the enemy rework is built. Rules 1.2.0: an enemy never uses a status ability twice running, and among equally good targets it draws one, so the order of the party no longer decides who is attacked first (measured: the 10 to 18 points an order was worth are gone, at most 1 to 2 remain); the log says why no hero could react. Content 1.4.0 and catalog 0.6.0: new enemy tables per party size and a longer third battle. Each party size wins 76 to 81% of runs on two seed blocks; attacks are 38 to 49% of enemy abilities (were 14 to 49%). Logs of earlier builds no longer replay (decision log 7.44)
- A survey of similar games is in `docs/SURVEY_SIMILAR_GAMES_2026-11-24.md`; its four ideas are questions for the owner
- Every setting the owner chose in D-31 is in
- Waiting for the owner's playtest of the demo (D-32); "Confirm a pass" on by default is confirmed

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
- Field Medic's gain (about 4 points) is measured with one simulated player on four fixed compositions; no person has played it.
- Squire Anchor is learned but does nothing in battle yet; the skills panel says so and does not let it be equipped.
- The spread between parties of one size is wide: after rules 1.2.0 the Apprentice-heavy parties win 32 to 42% and 15 of 55 parties win 95% or more (decision log 7.44, point 4). A question about the classes, for the owner.
- For four and five heroes the third battle is hardly longer than before rules 1.2.0 (4 to 9% more activations), although its table was lengthened.
- Never launched on a physical Windows display; no human playtest yet.
