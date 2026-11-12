# Battle Dice MVP: Decision Log

Contract: **BD-PRD-MVP-001 v1.0.0** (2026-11-09). Rules version `1.1.1`, content version `1.3.1`,
RNG `BD-PCG32-v1`.

This log records (1) how gaps and contradictions between *delegated default* (DD) statements in
the PRD were resolved, (2) implementation choices the PRD left open, and (3) measured evidence.
No **approved (A)** requirement was altered. Every numeric value lives in
`src/battle_dice/content/data/*.json`, not in engine code. DD values are as authored in the PRD
except where an owner decision below says otherwise (D-01, D-08, D-10, D-18, D-19, D-21).

Changing any entry below is a content/rules change: bump the version, rerun the acceptance
tests, and add an entry here.

## 1. Interpretations of the PRD

| ID | PRD area | Decision | Reason |
|----|----------|----------|--------|
| D-01 | 8.1 / 8.2 Steadfast | **Owner decision, 2026-11-09 (rules 1.1.0):** +1 shield on every Defense **die** action the Squire takes, on itself or an ally. The Interpose reaction is not a die action and gets no bonus. | Supersedes the 1.0.0 reading (self only). The PRD prose says "its own selected Defense die actions (not to Guard reactions)"; the owner chose that broader reading over the face table's "if self". |
| D-02 | 5.4 reroll | A reroll rerolls **all** unkept dice. | Q71 is approved (A) and wins over the "selected unkept die" sentence. |
| D-03 | 5.5 Channel and Cast | The second action must be a **non-Resource** category (Attack, Defense, Healing, Status). Resource + Resource is not a legal two-action plan. | "Any other legal category" read as "other than Resource". Narrower reading. |
| D-04 | 9.2 / 9.3 stack cap | **Changed in rules 1.1.1 (MVP review, 2026-11-10).** At the cap, each further stack refreshes the stack with the **least time left** (the oldest on a tie) to the applied duration, only if that raises it; the refreshed stack then counts as the newest. | Rules 1.0-1.1.0 tried only the oldest stack. With mixed durations (a duration-3 face next to duration-2 faces, reachable after the upgrade) the application did nothing while a newer stack was about to expire, and it disagreed with D-05. Choosing the shortest stack is the only rule under which "applying changes nothing" is exactly D-05. |
| D-05 | 14.4 "unrefreshable cap" | A status application is illegal for the AI only when the target is at the stack cap **and** every stack already has at least the applied duration. | With D-04 as of rules 1.1.1 that is exactly when applying changes nothing; a test checks the two against each other for every combination of durations. |
| D-06 | 14.4 priority 20 | Granted when at least one eligible target has **zero** stacks of the status the action applies (and for War Cry while no speed modifier is active). | The PRD says "its proposed target" but targets are chosen after the action; this is the equivalent test. |
| D-07 | 6.2 / 9.2 Poison at start | If Poison downs or defeats the actor at activation start, the activation ends immediately. A downed hero's status durations are **not** decremented for that activation. | 10: "do not tick activation-based effects while downed". |
| D-08 | 12.1 enemy ranges | **Owner decision, 2026-11-09 (rules 1.1.0):** Dirty Trick is **ranged** and can reach back-row heroes. Slash and Strike are melee. Shadow Bolt, Poison Dart, Corrupt Mark and Blight Wave are ranged. | Supersedes the 1.0.0 reading (Dirty Trick melee). The PRD gives ranges only for damage. |
| D-09 | 7.3 Interpose | The Squire may choose **itself** when it is one of the targeted heroes. | Otherwise a solo Squire could never demonstrate the Guard archetype (12.2). |
| D-10 | 11.2 optional swap | **Owner decision, 2026-11-09 (rules 1.1.0):** at most **one swap per hero** per run, value `max_swaps_per_hero` in `balance.json`. A hero that has swapped cannot swap again, including back. The upgraded die stays locked (approved requirement). | Supersedes the 1.0.0 reading (one swap per run, party-wide). |
| D-11 | 11.2 Sharpen | Each die offers Sharpen on one face chosen by the rewards stream. Poison/Weaken faces gain +1 duration, capped at the face power cap (5). | The PRD does not say which face; a deterministic seeded choice keeps "three cards". |
| D-12 | 11.2 Imbue | Imbue may replace **any** face (including a Blank); the face index comes from the rewards stream. | "Replace one face". |
| D-13 | 9.6 Speed Up | Re-applying while active refreshes the duration; it never stacks. The AI treats a repeat as illegal (14.4). | "Stacking is not used in the MVP". |
| D-14 | 12.1 Corrupt Mark | Legal even if every target is at the corruption cap; the AI only *prefers* targets with room. | 14.4 lists it as a preference, not a legality rule. |
| D-15 | 5.7 area effects | At resolution an area action hits the committed targets that are still eligible; if none remain it is cancelled. | Consistent with "committed targets" plus fallback. |
| D-20 | 14.4 area actions | **Rules 1.1.1.** An area enemy action that also applies a status keeps every eligible target; the status legality filter (D-05) no longer removes heroes from its damage. Such an action is illegal only when it would do nothing at all (no status would change and it has no other effect). | The filter used to drop a hero at an unrefreshable cap from the committed targets, so that hero also escaped the damage. No shipped action is affected (Blight Wave carries no status). |
| D-16 | 7.2 cooldowns | No enemy ability cooldowns are authored, so none are implemented. | The PRD mentions cooldowns only as a general possibility. Deferred (F). |
| D-17 | 9.4 enemy mana | Mana costs are charged to heroes only. Enemies have no mana pool. | 9.4: "Enemies in the initial fixtures do not use player mana pools". |
| D-18 | 13 runtime | **Python 3.15 or newer is required** (`requires-python = ">=3.15"`), replacing the PRD's delegated default of "Python 3.12+". CI, the lint target and the type-check target are pinned to the 3.15 line, so new 3.15.x patches are picked up but 3.16 is not adopted automatically. | Owner direction (2026-11-09): use the newest stable Python. 3.15.2 was the newest stable build in GitHub's `actions/python-versions` manifest on that date; 3.16 was alpha only. |
| D-19 | 12.2 encounter scaling | **Owner decision, 2026-11-09 (content 1.2.0):** the per-party-size encounter table is retuned so the scripted informed player wins 70-85% of runs at every party size. See section 7.1 for the exact changes and measurements. | The PRD calls the 12.2 tables "initial balance fixtures" to be adjusted after simulation. Informed play won 95-100% before the change. |
| D-21 | 8.1-8.3 class fixtures, 12.2 encounter scaling | **Owner decision, 2026-11-10 (content 1.3.0):** class balance change. Squire Strike 2 to 3 and Jab 1 to 2; Apprentice health 9 to 12; Scout speed 13 to 10 and health 10 to 9; Disrupt mana cost 1 to 2; enemy health raised per party size. The owner's gate was: every party size inside 70-85% on a block of seeds not used for tuning. See section 7.8. | Under simulated player version 2 the 1.2.1 table was outside the band (95.6% at party size 2), all-Squire parties won 0-1% at sizes 3 to 5 and parties with two or more Scouts about 100% (sections 7.2 and 7.6). |
| D-22 | 8.1 Squire fixtures (bench die) | **Owner decision, 2026-11-11 (content 1.3.1):** the Squire's bench die is now **Vanguard d4** (Strike 3, Jab 2, Jab 2, Blank), replacing Bulwark d4 (Guard 2, Guard 2, Tend 1, Blank). The Apprentice and Scout bench dice are unchanged. See section 7.9, including a correction to the numbers the choice was made on. | Playtest finding 3: swapping the bench die in changed nothing (+0.8 points). The owner asked for a true sidegrade to be designed and measured first, then chose this one. |
| D-23 | Class Evolution (beyond the MVP PRD) | **Owner decision, 2026-11-11:** FDD v0.2 (`docs/class_evolution/`) is approved and built in phases behind the feature gate `class_evolution_v1`, a launch setting that is off by default. With the gate off the game stays byte for byte identical. See section 7.11. | The owner asked for the design to be evaluated, chose a reconciled specification as the first step, then approved it. |
| D-25 | Class Evolution fixtures CE-18, CE-25, CE-35, CE-40 | **Owner decisions, 2026-11-11:** a vocation may equip its own dice plus its family's; run upgrades are kept as history after a run; with the gate on a run takes saved heroes with a build snapshot in its log; gate on with starting classes stays byte for byte identical to gate off. See section 7.12. | Asked before Phases 3 and 4. The dice answer differs from the fixture's first assumption (own dice only), so that fixture's notes and one rule changed. |
| D-26 | Class Evolution fixtures CE-09, CE-29, CE-30, CE-32, CE-36 | **Owner decisions, 2026-11-11:** an undiscovered secret vocation shows in the career tree as an anonymous `???` entry (not the fixture's first assumption, which was not to show it); a refused action plan carries a machine-readable code beside its text; event hashes and the canonical encoding stay as built, with times in no hash; the available encounters are the ones the catalog marks shipped, at its ratings (threat 1 and threat 3). One fixture stays open: CE-31. Rules, content and the replay pin are unchanged. | Section 7.14 |
| D-27 | Class Evolution Phase 4 (first playable slice) | **Owner decisions, 2026-11-11:** heroes are recruited at party setup, free, with a roster of at most 12; the threat-4 fight is an **optional third battle** after battle 2 (stop with a victory or fight on; losing it is a defeat); it is tuned so an informed player with a Guardian in the party wins 70-85% per party size; Guardian's mastery skill Field Medic works in battle in this slice, as its last step. The plan in five steps (A to E) with two checkpoints was approved the same day. | Section 7.15 |
| D-28 | Class Evolution: Checkpoint 1 | **Owner decision, 2026-11-12:** the Guardian's numbers and the third battle's enemy table are **accepted as built** (section 7.16: Guardian a sidegrade of the Squire, 80.2% against 81.4% wins; third battle 75-77% per party size for parties with a Guardian). They can be changed later with new measurements. | Section 7.24 |
| D-29 | Class Evolution: a second moment for a vocation change | **Owner decision, 2026-11-12:** a hero may also claim a vocation or change to one at the decision to stop or fight on after Battle 2. This goes beyond fixture CE-19, which names the upgrade only. | Section 7.24 |
| D-30 | Class Evolution: Field Medic's numbers | **Owner decision, 2026-11-12, after the measurement:** the revival costs what the Heal costs (no extra mana) and the ally comes back at **5 HP**; still once per encounter. Measured: 316 wins of 480 against 297 without the skill. This replaces the catalog's "revive to 1 HP ... if it costs +1 mana". | Section 7.25 |
| D-31 | The demo's configuration | **Owner decisions, 2026-11-12, after the research:** Settings is grouped (Display and comfort, Play aids, Class Evolution, Demo and testing), the four demo options sit in the last group; the dice seed is chosen on the New Run screen and can be typed; new settings: text size, high contrast, battle speed at start, confirm before passing with an unused die, tooltip delay, Settings from the pause menu, reset all settings to defaults. No audio, controller, remapping or difficulty settings. | Section 7.26 |

## 2. Content authored under delegation

The PRD names the Reforge and Imbue catalogs but does not enumerate them. These are new DD
content in `upgrades.json` and can be rebalanced like any other fixture.

| Class | Reforge (replaces a Blank) | Imbue (replaces any face) |
|-------|----------------------------|---------------------------|
| Squire | Jab (1 melee), Brace (+2 shield), Resolve (+1 mana) | Heavy Blow (3 melee), Bulwark (+4 shield) |
| Apprentice | Spark (1 ranged spell, +1 corruption), Minor Ward (+1 shield), Trickle (+1 mana) | Arc Surge (4 ranged spell, 2 mana, +1 corruption), Deep Focus (+3 mana) |
| Scout | Nick (1 ranged), Duck (+1 shield), Breath (+1 mana) | Volley (1 ranged to all enemies), Crippling Shot (Weaken 1 for 3 activations) |

Face names for the authored starting dice (for example "Strike", "Guard", "Channel", "Shot") are
display labels added for the UI; their numbers are exactly the PRD tables.

## 3. Engine and architecture choices

| ID | Choice |
|----|--------|
| E-01 | One mutation path: `Engine.submit(Command)`. The engine deep-copies state before a handler runs and restores that copy on rejection, so state, RNG positions and the event sequence are unchanged. Holders of object references must re-read after a rejected command; the UI only ever uses snapshots. |
| E-02 | `LOCK_PLAN` is a real step. Rerolling ends once `SetActionPlan` is accepted; the UI keeps the draft locally and submits `SetActionPlan` + `CommitActionPlan` on Confirm. |
| E-03 | Automatic transitions advance one step per `AdvancePhase`, so a UI can pace them. `run_until_input()` loops for headless use. |
| E-04 | A reaction window with no eligible reaction is skipped automatically and logged (`reaction_stage_skipped`, reason "no eligible reaction"). |
| E-05 | The event sequence is continuous across both battles; `timeline_tick` restarts at 0 for Battle 2. |
| E-06 | Hero IDs are `h01`..`h05` by party slot. Enemy IDs are `b<battle>_e<nn>` ordered by archetype ID, then spawn order. |
| E-07 | The weighted enemy draw is always consumed, even when the top tier holds a single action, so the enemy stream position does not depend on tier size. |
| E-08 | `Engine.force_draws()` queues forced bounded results for a stream. It exists only for fixtures (11.2: "fixture tests can force a known catalog order"); forced draws are logged as `<stream>:forced` and do not advance the PCG stream. |
| E-09 | Rules text shown to the player is generated from face data (`view.describe_face`), so it cannot drift from behaviour. |
| E-10 | The golden RNG vectors in `tests/golden/rng_vectors.json` are locked to the current rules version (label 1.1.1; the vectors are unchanged because the RNG algorithm is unchanged). The raw generator is also checked against the published PCG32 reference output (seed 42, sequence 54). |
| E-11 | Rule fixtures (T01-T13, T15 and the engine unit tests) run on the shipped rules data with the encounter table frozen at its rules-1.1.0 values (`tests/golden/encounters_mechanics.json`), so a balance retune does not rewrite tests about rules. The shipped table itself is asserted exactly in `unit/test_content.py` and `fixtures/test_t14_party_scaling.py`, and full-run, replay, simulator and UI tests use the shipped content. |
| E-12 | **Owner direction, 2026-11-10: use the most updated Node.** The game has no Node code; Node is only the runtime of the GitHub Actions used in CI. They are pinned to their newest majors, all of which run on Node 24: `actions/checkout@v7`, `actions/setup-python@v7`, `actions/upload-artifact@v7` (previously `v4` / `v5` / `v4` on Node 20, end of life 2026-04-30). Node 26 is the newest Node LTS, but no released major of these actions declares a `node26` runtime, so Node 24 is the newest the project can select. |
| E-13 | **Command and view safety (MVP review, 2026-11-10).** `Engine.do()` skips ids a replayed log already used, so it works on an engine rebuilt by `replay()`. A command id resubmitted with the same type and parameters is acknowledged as a duplicate; reused for a different command it is rejected. The command log stores its own copy of each command's parameters and the handler gets another, so neither the caller nor the state can change the log. Snapshots and controller views are copies: changing one cannot change the state or the content (tested by emptying every container in a snapshot). |
| E-14 | **Stricter content validation (content 1.2.1).** The loader now rejects, before a run can start: a reaction-only effect (`interrupt`) on a die face or enemy action; a Poison or Weaken stack cap below 1; the same die listed twice on a class; a revival that restores 0 HP; a tag the engine does not know (a misspelled `interruptible` used to make an action silently unreactable); an executable face with target scope `none`; a reaction effect that reactions do not implement, or one missing its amount or its resisted values; encounter overrides that leave an enemy with no weighted action; a `power` override on an action whose effect has its own `amount`; and inverted speed or party-size limits. Each case has a test. |
| E-15 | **Keys nothing read were removed (content 1.2.1).** `statuses.*.default_duration` is gone: durations live on the faces that apply a status. `statuses.speed_up.stack_cap` is fixed at 1 in the schema, because Speed Up never stacks (D-13). `upgrades.mandatory_upgrades_per_run` was already fixed at 1 in the schema. |
| E-16 | **Run logs are replayable (PRD 14.5).** The JSONL header carries the ordered commands, so the file alone reproduces the run. `battle-dice-replay LOG` (or `python -m battle_dice.replay_cli`) replays it on a fresh engine and checks the rules version, the content hash, the event-log hash, the final-state hash and every event line. Logs written before this change have no commands and say so when verified. |
| E-17 | **Pinned runs.** `tests/golden/replay_pin.json` records the hashes of three fixed-seed heuristic runs on the shipped content. Every test run on Linux and Windows compares against it, so unintended drift in rules, content or random-number use fails. An intended change bumps a version and regenerates the pin with `python tools/update_replay_pin.py`. The pinned runs are played by the heuristic player, so the pin also records `policy_version` and is regenerated when that player's decisions change (section 7.6); rules and content versions are not bumped for that. |
| E-18 | Status follow-up events (`status_applied`, `status_refreshed`) carry the affected combatant in `id`, as every other follow-up event does, and the stack in `status_id`. Before, the stack id overwrote `id`, so the event's after-state was empty. |

## 4. Deviations from the plan

| ID | Deviation |
|----|-----------|
| V-01 | The PRD text is **not** vendored into `docs/`. It was supplied as pasted text with tab-separated tables, and a retyped copy could not be guaranteed byte-faithful to the owner's canonical document. The owner should add the canonical file as `docs/BD-PRD-MVP-001.md`. |
| V-02 | The rules engine orchestrator (`core/engine.py`) is committed with WP-06, where all of its dependencies exist, rather than as a skeleton in WP-02. Unit tests that need the engine land with WP-06; the T01-T16 fixtures and integration tests land with WP-08. |
| V-03 | **Scope added by the owner, 2026-11-09:** Windows packaging, which the PRD lists as outside the MVP. Two routes ship: a source launcher (`scripts/Start-BattleDice.ps1`, `Play-BattleDice.cmd`) and a PyInstaller one-folder build produced by the `Package (Windows)` workflow. Not included: code signing, an installer, or published releases. The app is unsigned and is distributed only as a workflow artifact. |
| V-04 | **Scope added by the owner, 2026-11-09:** a pixel-art graphics pass with animation, using Kenney CC0 packs. The PRD lists original art as not required. Characters, enemies, action icons and dungeon tiles are from Kenney's Tiny Dungeon (CC0). The pack has no goblin and no polyhedral dice, so the Goblin is a recoloured Tiny Dungeon tile and the d4 / d6 / d8 dice plus the Weaken and Speed Up icons are original. Panels and buttons keep the existing flat style; a pixel-art UI reskin is not included. |
| V-05 | **MVP review, 2026-11-10.** The owner asked for a full review, then chose to build all of it: the UI fix pass, test hardening, replayable logs, launcher fixes, and every latent engine and content defect; and asked for a class-balance tuning proposal before any content change. The owner authorised merging the resulting pull requests. Findings that were judged design questions rather than defects are listed in section 8 and were not changed. |
| V-06 | **Launcher behaviour (2026-11-10).** A usable Python is found before an existing `.venv` is removed, so a failed `-Reinstall` keeps the install. Python 3.15 or newer is accepted (3.15 is tried first; free-threaded and 32-bit builds are skipped because pygame-ce may have no wheel for them). The install record includes the checkout folder and the launcher checks that the game imports, so a moved checkout or a `.venv` without the game is repaired. `-SmokeTest` runs the hidden self-check through the normal start-up path. `Play-BattleDice.cmd` pauses on any non-zero exit code. Verified only on the Windows CI runner. |

## 5. Presentation choices (section 13, DD)

| ID | Choice |
|----|--------|
| U-01 | Layout is authored on a 1280x720 logical canvas and scaled uniformly, letterboxed, to the window. The window is resizable and clamped to at least 960x540. |
| U-02 | Immediate-mode widgets: each frame is rebuilt from an engine snapshot, and input is routed to the widgets of the last drawn frame. Rendering never mutates state or draws random numbers (covered by a test). |
| U-03 | The plan is a local draft in the controller until Confirm, which sends `SetActionPlan` then `CommitActionPlan`. Rerolling removes drafted actions on rerolled dice. |
| U-04 | Automatic combat steps play on a 260 ms timer (25 ms in fast mode). This deliberate pacing is outside the engine latency target. |
| U-05 | State is never conveyed by color alone: numeric HP/SH/MP/CR, text tags (ACTING, DOWNED, TARGET n, KEPT, IN PLAN), a hatch pattern on disabled controls, and a ring plus pointer on the focused control. Disabled controls show their reason in the status bar on hover or focus, and when activated. |
| U-06 | A system sans-serif is used when available, with pygame's bundled font as fallback. Text is truncated with an ellipsis rather than overflowing. |
| U-07 | Run seeds come from the clock in the application layer (or `--seed`). The rules engine never reads the clock. |
| U-08 | `--smoke-test` plays one seeded run with no window and exits 0 on success. Menus are driven by real key events, the pause menu is opened and closed, a unit card is pointed at so the inspect panel is drawn, and every frame of the run is drawn; battle decisions come from the heuristic policy sent straight to the engine, so the run reliably reaches the upgrade and outcome screens. It fails on any frame whose drawing raised, on any visit to the error screen, and on a missing sprite. It is the verification step for packaged builds (content, pygame-ce and sprites load inside the frozen app). It does not prove a bundled-font fallback: the runner has system fonts. |
| U-09 | A packaged (frozen) build writes event logs to `%LOCALAPPDATA%\\BattleDice\\logs`, because its own folder may be read-only. From source the default stays `./logs`. |
| U-10 | Sprites are 16x16 and are scaled by whole numbers only (nearest-neighbour); panels and text keep the fractional UI scale. Card and planner slots are sized so characters draw at 2x at both 960x540 and 1280x720. |
| U-11 | Art lives in `ui/assets` with a manifest (file, source pack, tile number, any modification) and a credits file. The mapping from class or enemy to sprite is presentation data, not rules content, so the content hash and replays do not change. Tests fail if a file is unlisted, uncredited, or not CC0. |
| U-12 | Animation reads the engine's event log and frame time only. It never calls the engine or its random streams (covered by a test). `M` and `--no-animation` turn it off; fast mode shortens it. The dice tumble cycles through the die's own faces by elapsed time and then shows the real result. |
| U-13 | A missing sprite draws a visible placeholder box and is recorded, never raising. The smoke test fails if any sprite is missing, so packaged builds prove the art was bundled. |
| U-14 | **Focus and Enter (MVP review, 2026-11-10).** Only Tab and the arrow keys move the focus ring. Hotkeys and clicks do not, and a click clears it. With a ring, Enter or Space activates the ringed control; with none, Enter activates the screen's default button. A ringed control with nothing to do (a unit card outside targeting) does not swallow Enter. Esc runs the screen's cancel action, or clears the ring when there is none. Before this, any hotkey or click moved the ring, so Enter repeated the last control instead of confirming. |
| U-15 | **Reaction panel.** One row per reacting hero (at most five) with that reaction's eligible allies as buttons on the row; a reaction that needs no ally shows its effect there instead. Mouse: one click on the ally. Keyboard: the row's number, then the ally's number; Esc cancels the choice. The earlier one-row-per-pair list ran off the panel with five heroes and showed at most four allies. |
| U-16 | **Leaving a run.** Esc or the Menu button opens a pause menu in battle and on the upgrade screen: resume, controls, abandon to party setup, abandon to the main menu. Nothing advances while it is open. An abandoned run writes no event log. Esc still cancels a target choice first. |
| U-17 | **Status bar.** A message that arrived since the last frame is shown until the pointer or the focus moves to a different control; after that the hot control's help text returns. Before, the tooltip of the button just used hid the reason a click was refused. |
| U-18 | **Readable rules text.** Pointing at or focusing a unit card replaces the combat log with an inspect panel: stats, every status stack with what it does, and the full ability list (enemies) or dice, reaction and passive (heroes). Die face rules wrap onto a second line instead of being cut. Unit cards sum status stacks per kind and pick the longest form that fits (`PSN x3 (1-2)`, then `PSN 3(1-2)`, then `P3(1-2)`); the gauge number gives way before the status text can overlap it, and the gauge bar always stays. Names keep their trailing number when shortened. Font widths differ widely between machines (DejaVu Sans is about 40% wider than Liberation Sans), so these layouts are chosen by measuring the text, and the text-fit tests run under the machine's own font, DejaVu Sans where installed, and pygame's bundled font. |
| U-19 | While a die tumbles the planner shows "Rolling ..." and no face name or rules text, so it never states a face that was not rolled. The buttons act on the real result throughout. |
| U-20 | A log file name that already exists gets a numeric suffix, so a second session with the same `--seed` does not overwrite the first log. An unexpected crash of the main loop writes `crash-<time>.txt` in the log folder and exits 1. Faults while editing the plan, routing input or animating reach the error screen instead of closing the window. |
| U-21 | **Forecast line (playtest finding 1).** Where an action will not produce its printed amount, a yellow "Now ..." line says what it will produce and why: "Now deals 0 (Weaken -1)", "Now +4 shield (Steadfast +1)", "Now deals 2 (Exploit Opening +1)". It appears on the rolled die, on the plan line and, for a weakened enemy, in the intent panel. `core/view.py` `action_forecast` calls the engine's own `damage_breakdown` and `shield_bonus`; unit tests compare every forecast with the resolved amount. A combo bonus is forecast on the plan line only, because it depends on the plan and assumes the first action resolves. |
| U-22 | **One-time guidance (finding 2).** The first roll of a run explains Reroll and Keep; the first reaction prompt explains what a reaction is. The outcome screen adds a tip when no reroll, or no reaction, was used in the whole run. |
| U-23 | **Skip All (finding 5).** In a reaction window, A declines every remaining stage of the current enemy action; S still skips one stage. The engine is sent the same `SkipReactionStage` commands, so logs and replays are unchanged in kind. |
| U-24 | **Swap warning (finding 4).** Swapping out a die larger than the bench die warns first and needs a second press. The engine rule (any equipped die may be swapped out) is unchanged. |
| U-25 | Small fixes (findings 7 to 9): the status bar names rules and content versions separately; a reaction decision sets its own status line; a die in the plan is no longer labelled "will reroll". |

## 6. Acceptance evidence

500 automated tests pass on the reference environment (Linux container, Python 3.15.2,
pygame-ce 2.5.8, jsonschema 4.26.0, pytest 9.2.0): 240 unit, 78 fixture, 49 integration,
133 headless UI and graphics, with warnings treated as errors. `ruff` 0.17.4 is clean, and
`mypy` 2.4.1 is clean over the whole package, the tools and the tests (75 files).

Line coverage of the rules engine, content loader and random numbers (`battle_dice.core`,
`battle_dice.content`, `battle_dice.rng`) is 97% against the PRD target of at least 80%. CI fails
below 90%.

An earlier version of the suite passed on Python 3.12 before the floor was raised to 3.15; older
versions are no longer installable (an install attempt on 3.12.3 is refused with "does not
satisfy Python>=3.15").

Dependency minimums were raised to the versions verified on 3.15: `pygame-ce>=2.5.8` (its
`cp315` wheels include `win_amd64`), `ruff>=0.17.4`, `mypy>=2.4`.

The MVP review (2026-11-10) applied twelve deliberate bugs to a copy of the engine. The suite of
that time missed eleven of them. The tests added since are listed against the criteria below and
in `unit/test_review_fixes.py`; the result of re-running those bugs is in section 8.

| Criterion | Evidence |
|-----------|----------|
| AC-01 party 1-5, duplicates, rows | `unit/test_commands.py` (party size and row tests) |
| AC-02 exact dice and stats, distinct scheduling | `unit/test_content.py`, `fixtures/test_t02_three_class_combo.py` |
| AC-03 faces, frequencies, probabilities, seeded rolls | `unit/test_content.py`, `unit/test_dice_and_planning.py` |
| AC-04 keep / reroll | `unit/test_dice_and_planning.py`, `unit/test_commands.py` |
| AC-05 class caps, plan lock, discard | `unit/test_dice_and_planning.py` |
| AC-06 deterministic timeline, speed change keeps gauge | `unit/test_timeline.py`, `fixtures/test_t11_speed_reorder.py`, `unit/test_review_fixes.py` (War Cry resolved with a non-zero gauge) |
| AC-07 action speed orders standard actions only | `unit/test_dice_and_planning.py` (free-policy tests) |
| AC-08 formation targeting | `unit/test_targeting_effects.py` |
| AC-09 retarget and cancel | `fixtures/test_t07_target_fallback.py`, `unit/test_review_fixes.py` (area action with no target left) |
| AC-10 intent reveal and stage windows | `unit/test_enemy_ai.py`, `fixtures/test_t05_reaction_stages.py` |
| AC-11 Guard, Resource, Interrupt, charges, elite resistance | `fixtures/test_t05_reaction_stages.py`, `fixtures/test_t06_interrupt_resistance.py` |
| AC-12 shields, Poison, Weaken, mana, corruption | `unit/test_targeting_effects.py`, `fixtures/test_t08_poison_lethal.py`, `fixtures/test_t10_corruption_tradeoff.py` |
| AC-13 revival and final-party-down defeat | `fixtures/test_t09_revival.py`, `fixtures/test_t15_terminal_edges.py` |
| AC-14 both battles per party size, mandatory upgrade | `fixtures/test_t14_party_scaling.py`, `fixtures/test_t13_upgrade_swap.py`, `unit/test_review_fixes.py` (shipped Slash, Shadow Bolt and Strike damage resolved on the shipped table) |
| AC-15 bench swap keeps the upgrade | `fixtures/test_t13_upgrade_swap.py` |
| AC-16 recovery, persistence, restart | `fixtures/test_t12_two_battle_persistence.py`, `integration/test_replay_logs.py` (retry through the controller starts clean) |
| AC-17 both outcomes, no soft locks or negative resources | `integration/test_full_runs.py` (invariants checked after every command) |
| AC-18 seed replay | `fixtures/test_t16_seed_replay.py`, `integration/test_replay_logs.py` (log file replay, tamper detection, pinned hashes across platforms) |
| AC-19 mouse and keyboard, supported resolutions, disabled reasons | `ui/test_ui_smoke.py`, `ui/test_ui_flow.py` (every documented key, Enter after hotkeys and clicks, reaction panel at both sizes, pause menu, text never cut off) |

Not verified here: the game has not been launched on a physical Windows display. The engine,
content and headless UI tests run on a Windows CI runner; interactive feel, font rendering and
window behaviour on Windows remain to be confirmed by the owner.

### 6.1 Validation sweep (2026-11-10)

Every check that can run in the reference container was run against `main` plus this change, and
each finding was fixed, not suppressed:

| Check | Result |
|-------|--------|
| `mypy` over the whole package, `tools/` and `tests/` (75 files) | Clean. 22 findings fixed in `ui/screens.py` and `tools/update_replay_pin.py` (default-argument lambdas replaced by `functools.partial`, two variables typed as float, one colour tuple); 24 in tests (missing None checks, annotations). Two `type: ignore` comments in the rules engine were removed by narrowing the types instead. |
| `ruff check` over the repository | Clean. |
| `pytest -W error` (500 tests, warnings are errors) | Pass. |
| Coverage of engine, content loader and random numbers | 97.27% (floor 90%). Whole package: 96%. |
| Random-play fuzz: 2,200 runs (`battle-dice-sim --policy random --seeds 40`) | No engine fault, no negative resource, every run ends. |
| Wheel and source archive built; wheel installed in a clean environment | `battle-dice --smoke-test`, `--version`, `battle-dice-sim` and `battle-dice-replay` all run from the installed copy; content, schema, sprites and credits are in the wheel. |
| Workflow files and all 11 JSON data files | Parse; content also passes schema and cross-reference validation at load. |
| Documented versions, test counts and the replay pin | Match the code (rules 1.1.1, content 1.2.1, player 2, 500 tests). |
| Latest runs on `main` | CI and the Windows package workflow both green. |

CI now enforces the wider checks: `mypy src/battle_dice tools tests`, `pytest -W error`, and a
step that builds the wheel and runs the game from the installed copy on Linux and Windows.

Not checkable in this container, and so still resting on the Windows workflow or the owner:
the PowerShell launcher (linted and exercised only on the Windows runner), the PyInstaller build
(Windows runner), and a real display. `ruff format` is not adopted by this project (the code is
hand-formatted at 110 columns), so its report is not a finding.

## 7. Measured balance and latency (not balance claims)

Command: `battle-dice-sim --seeds 40 --policy <policy> --jobs 4`. Seeds 0-39, every class
composition for each party size (55 compositions, 2,200 runs per policy), heroes in their
suggested rows. **Heuristic policy, version 1** (used for sections 7.1 to 7.5): keeps the dice in
its best-scoring plan if that plan scores at least 2.0, otherwise rerolls everything; always reacts
when it can. **Version 2** (section 7.6) replaced it on 2026-11-10. **Random policy:** uniformly
random legal decisions. All are scripted players, not human playtesting. Result files record
`policy_version`.

### 7.1 Owner decision D-19: per-party-size encounter table (content 1.2.0, 2026-11-09)

- **Target set by the owner:** an informed player wins 70-85% of full runs, judged per party size.
- **Change:** only the per-size overrides in `encounters.json`. Base enemy stats, the AI priority
  rule and every hero number stay as authored. Rules version stays 1.1.0.
  - All sizes: Slash, Shadow Bolt and Strike +1 damage.
  - Enemy HP: +50% for sizes 1 and 5, +33% for sizes 2-4 (rounded up).
  - Enemy speed: +2 for sizes 3-5.

| Party size | Runs | Rules 1.1.0, heuristic | Content 1.2.0, heuristic | Content 1.2.0, random |
|-----------:|-----:|-----------------------:|-------------------------:|----------------------:|
| 1 | 120 | 100.0% | 75.8% | 31.7% |
| 2 | 240 | 99.2% | 82.9% | 20.4% |
| 3 | 400 | 94.8% | 74.5% | 6.0% |
| 4 | 600 | 97.3% | 74.7% | 8.8% |
| 5 | 840 | 96.4% | 74.8% | 4.3% |
| All | 2,200 | 96.9% | 75.6% | 9.1% |

The 1.2.0 figures were re-measured on the shipped content and match the approved proposal for
every composition.

### 7.2 What the average hides

Win rate depends far more on party make-up than on party size. On content 1.2.0:

| Party size | Weakest composition | Strongest | Compositions under 50% | Compositions at 100% |
|-----------:|---------------------|-----------|-----------------------:|---------------------:|
| 1 | Apprentice, 45% | Scout, 100% | 1 of 3 | 1 |
| 2 | Squire + Squire, 35% | Scout + Squire, 100% | 1 of 6 | 4 |
| 3 | three Squires, 0% | Scout + Scout + Squire, 100% | 3 of 10 | 4 |
| 4 | four Squires, 0% | two Scouts + two Squires, 100% | 3 of 15 | 7 |
| 5 | Apprentice + four Squires, 0% | three Scouts + two Squires, 100% | 5 of 21 | 8 |

- All-Squire parties lose because they have little damage and cannot reach the back row until
  the front row falls. Parties with Scouts stay near 100%.
- Uninformed (random) play now wins about 9% overall, down from about 50% on rules 1.0.0.
- Closing the gap between compositions needs class-level changes (Squire damage, Apprentice
  durability, Scout strength). The owner chose not to do that in this pass.

### 7.3 Candidates measured before the proposal (rules 1.1.0, global changes, heuristic, 20 seeds)

| Candidate | Overall | Size 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|---|
| Enemy setup priority 20 -> 10 (40 seeds) | 97.4% | 100.0 | 95.0 | 97.2 | 97.2 | 97.9 |
| Disrupt cost 1 -> 2 (40 seeds) | 96.9% | no outcome changed in any composition |  |  |  |  |
| HP +33% | 93.8% | 100.0 | 95.0 | 90.0 | 93.0 | 95.0 |
| HP +50% | 92.3% | 100.0 | 89.2 | 89.5 | 92.3 | 93.3 |
| Damage +1 | 95.2% | 95.0 | 96.7 | 92.0 | 95.0 | 96.4 |
| Speed +2 | 93.2% | 100.0 | 92.5 | 89.5 | 93.0 | 94.3 |
| Damage +1, speed +2 | 86.6% | 70.0 | 72.5 | 85.0 | 88.0 | 92.9 |
| HP +33%, damage +1, speed +2 | 74.9% | 51.7 | 57.5 | 73.0 | 74.3 | 84.5 |
| HP +33%, damage +1, setup priority 10 | 57.5% | 56.7 | 53.3 | 56.0 | 59.0 | 58.3 |

No single global change put every party size in the band, which is why the table is per size.

### 7.4 Latency

2,298,146 engine transitions in the 40-seed heuristic run on rules 1.1.1 and content 1.2.1:
median 0.18 ms, p95 0.40 ms, maximum 96 ms on the reference container, against the proposed
target of under 100 ms. The per-size win rates of that run are identical to section 7.1, so the
1.1.1 rule fixes did not move the measured balance.

- The figure includes the policy's own decision time averaged over the commands it sent. From
  player version 2 on, the simulator counts time inside engine commands only (section 7.6).
- The maximum is a single transition and depends on what else the machine is doing: an
  independent rerun under load recorded 290 ms. The median and p95 are the stable figures.
- It was not measured on the Windows target machine.

### 7.5 History

On rules 1.0.0 (20 seeds) the heuristic won 60/60, 119/120, 187/200, 293/300 and 407/420 for
sizes 1-5 and the random policy won 41/60, 58/120, 103/200, 159/300 and 212/420.

### 7.6 Simulated player version 2 (2026-11-10, owner decision: fix the player before retuning)

**Why.** The review of class balance found that version 1 played some classes badly, so its win
rates understated them:

- It threw away usable dice. A weakened Strike or a Guard on a healthy ally scored under its keep
  threshold of 2.0, so the whole roll was rerolled and could come up blank.
- It ignored the Squire's Steadfast +1 and the Scout's combo bonus when scoring a plan.
- It chose upgrades by kind (reforge, then sharpen, then imbue), so imbue faces were almost
  never taken.

**What version 2 does** (`src/battle_dice/sim/policies.py`, `POLICY_VERSION = 2`):

| Part | Rule |
|------|------|
| Keep or reroll | Exact look-ahead. Every possible roll of the hero's dice is scored by its best plan; the dice kept are the subset with the highest expected score over the rerolls left. Scoring a roll that has not happened uses a copy of the turn and changes nothing in the engine. |
| Scoring | The engine's own amounts (Steadfast, combo bonus), applied in resolution order, so two actions are not both credited with one kill and a status on an enemy the same plan defeats counts for nothing. Shield value is weighted 0.75. |
| Upgrades | The offer that raises its die's average face value the most, whatever its kind. |
| Reactions | Unchanged from version 1: always react, on the most pressed target. |

It still values the current activation only. It is a better player, not an optimal one, and it is
not human play.

**Acceptance rule, fixed before measuring.** Version 2 against version 1 on seeds 0-79, all 55
compositions (4,400 runs per content set), on the shipped content and on the class set proposed
to the owner ("REC": Strike 3, Apprentice health 11, Scout speed 10 and health 9, Disrupt cost 2,
more enemy health). Pass = overall win rate higher on both; no party size lower by more than 3
points; no composition lower by more than 15 points.

| Party size | Shipped 1.2.1, v1 | Shipped 1.2.1, v2 | REC, v1 | REC, v2 |
|-----------:|------------------:|------------------:|--------:|--------:|
| 1 | 75.0% | 80.4% | 77.5% | 90.8% |
| 2 | 82.9% | 95.6% | 79.2% | 94.2% |
| 3 | 74.0% | 79.6% | 78.9% | 91.9% |
| 4 | 74.5% | 80.8% | 76.2% | 88.5% |
| 5 | 75.1% | 83.3% | 76.3% | 92.1% |
| **All** | **75.6%** | **83.1%** | **77.1%** | **91.2%** |

- **Result: pass.** The largest drop for any composition is 10 points (one Squire + three
  Apprentices on shipped content, 84% to 74%); the largest gains are 60 points or more (two
  Squires, 36% to 96%; four Squires + one Scout, 26% to 89%).
- With every new part switched off, the rewritten code reproduces version 1 exactly on all 55
  compositions, so the comparison measures the parts and not the rewrite.

**Each part alone** (others off, seeds 0-39, change in overall win rate):

| Part | Shipped | REC | Kept |
|------|--------:|----:|------|
| Look-ahead keep rule | +2.9 | +5.8 | Yes |
| Engine amounts in scoring | +0.5 | +6.9 | Yes, with shield weight 0.75 |
| Upgrades by value | +3.1 | +6.1 | Yes |
| Reactions by value (react only when it prevents more than the mana is worth; hold mana for a revival) | +0.6 | -0.5 | **No** |

- **Reactions by value was removed.** Inside the full player it changed the overall rate by +0.2
  (shipped) and -0.6 (REC), both within the noise of about 1.3 points. The rule said a part that
  does not raise the win rate is removed. Consequence: the player still spends Interpose at the
  shield cap (section 8).
- **Shield weight.** With shields scored at their old weight, counting Steadfast made the player
  guard too much: five Squires on REC fell from 51% (v1) to 35%, a 16-point drop that failed the
  rule. Weights measured on all 55 compositions: 1.0 gave 83.2% / 91.4% overall, 0.75 gave
  83.1% / 91.2% with five Squires at 61%, and 0.5 (seeds 0-39 only) was lower overall and cost
  two Squires + two Apprentices 28 points. 0.75 is used.

**What this says about balance.**

- Shipped content is now **outside the owner's 70-85% band at party size 2** (95.6%) under the
  better player, and near its top at sizes 4 and 5. The retune in progress will bring it back.
- All-Squire parties still win 0-1% at sizes 3, 4 and 5 on shipped content, and parties with two
  or more Scouts still win about 100%. Those are class weaknesses, not player flaws.
- The REC set wins about 91% under version 2, so its enemy health figures are too low and are
  being re-derived.

**Latency under version 2.** 2,143,188 engine transitions in the 40-seed run on shipped content:
median 0.17 ms, p95 0.31 ms, maximum 110 ms, counting time inside engine commands only. The run
takes about 3.3 minutes with four workers (version 1: about 2.5).

### 7.7 Scenario-based playtest (2026-11-10)

`docs/PLAYTEST.md` records a scenario-based playtest of rules 1.1.1 and content 1.2.1: twelve
scripted personas (`src/battle_dice/sim/personas.py`, run by `tools/playtest_scenarios.py`), one
first session played through the real screens, and five forced tactical situations. It changed no
game behaviour. Its nine findings (previews that show base numbers and not the real ones, a
newcomer win rate of 8%, between-battle choices that do not change outcomes, an unguarded die
swap, reaction-prompt fatigue, risk-free rerolls and three small screen defects) await owner
decisions. No person has play-tested the game; the document contains a session script for that.

Owner decisions on the findings (2026-11-10): fix findings 1, 2, 4, 5, 7, 8 and 9 (done, U-21 to
U-25; re-test in `docs/PLAYTEST.md` section 8); measure options for findings 3 and 6 after the
class balance retune and propose them. Still an owner decision: whether Interpose should be
offered at the shield cap (a rule change).

### 7.8 Owner decision D-21: class balance change (content 1.3.0, 2026-11-10)

**What changed** (`classes.json`, `dice.json`, `encounters.json`; damage and speed of enemies are
unchanged):

| Class or reaction | Value | 1.2.1 | 1.3.0 |
|-------------------|-------|------:|------:|
| Squire | Strike damage (Iron d6, two faces) | 2 | 3 |
| Squire | Jab damage (Oath d4) | 1 | 2 |
| Apprentice | Health | 9 | 12 |
| Scout | Speed | 13 | 10 |
| Scout | Health | 10 | 9 |
| Disrupt | Mana cost | 1 | 2 |

| Party size | Battle 1 enemy health | Battle 2 enemy health |
|-----------:|-----------------------|-----------------------|
| 1 | goblin 9 to 12 | captain 14 to 18 |
| 2 | goblin 8 to 14, hex adept 10 to 18 | captain 14 to 25, goblin 8 to 14 |
| 3 | goblins 8 to 10, hex adept 10 to 13 | captain 16 to 22, goblin 8 to 10, hex adept 10 to 13 |
| 4 | goblins 8 to 10, hex adepts 10 to 12 | captain 19 to 24, goblins 8 to 10, hex adept 10 to 12 |
| 5 | goblins 9 to 11, hex adepts 11 to 13 | captain 24 to 29, goblins 9 to 11, hex adepts 11 to 13 |

The face ids `sq_strike_2` and `sq_jab_1` became `sq_strike_3` and `sq_jab_2`. Heavy Blow stays
at damage 3: at 4, party size 3 measured 91.0% and 87.8% on the two report blocks and size 4
88.5% and 84.0% (the owner's condition was that every size stays in the band).

**Result** (simulated player version 2, official runner, 55 compositions, 40 seeds per block).
Seeds 100-139 were used for tuning and are not reported. Seeds 300-339 were used for nothing
before this table; they are the owner's gate.

| Party size | Seeds 300-339 (gate) | Seeds 0-39 | Seeds 40-79 | All three (120 runs per party) | 1.2.1 under the same player |
|-----------:|---------------------:|-----------:|------------:|-------------------------------:|----------------------------:|
| 1 | 79.2% | 76.7% | 77.5% | 77.8% | 80.4% |
| 2 | 73.8% | 77.9% | 75.8% | 75.8% | 95.6% |
| 3 | 79.0% | 82.8% | 77.2% | 79.7% | 79.6% |
| 4 | 76.5% | 81.0% | 79.7% | 79.1% | 80.8% |
| 5 | 78.1% | 82.1% | 80.2% | 80.2% | 83.3% |

- **Gate: passed.** Every party size is inside 70-85% on every block.
- **Spread between compositions** (120 runs each): one composition at or below 40% (five
  Squires, 16%) and one at 100% (one Squire + three Scouts). Content 1.2.1 under the same player
  had 8 and 33.

| Single-class party, sizes 1 to 5 | 1.2.1 | 1.3.0 |
|----------------------------------|-------|-------|
| All Squire | 100 / 96 / 1 / 0 / 0 | 93 / 88 / 62 / 53 / 16 |
| All Apprentice | 41 / 78 / 26 / 28 / 34 | 65 / 80 / 52 / 56 / 81 |
| All Scout | 100 / 100 / 100 / 100 / 100 | 75 / 62 / 91 / 99 / 98 |

**Five Squires: a preregistered test of why they lose** (owner's instruction: use the reasoning
skills; 80 runs per cell; hypotheses, thresholds and the decision rule were fixed before running;
a difference under 10 points counted as noise, 20 or more as support).

- Already known from existing results: 66 of 67 five-Squire defeats were in Battle 2, where two
  back-row hex adepts cannot be reached until 51 health of front row is cleared.
- Validity check passed: the unchanged candidate reproduced 13 of 80 exactly, and four Squires
  stayed at 45 of 80 in every variant that did not touch size 4.

| Hypothesis | Test | Five Squires | Verdict |
|------------|------|-------------:|---------|
| Baseline | | 16% | |
| The scripted player plays them badly | Other habits: always attack 30%, shield weight 0.5 29%, shield weight 1.0 18%, never react 0%, always defend 0% | 30% at best | Inconclusive (+14) |
| Battle 2 front-row wall | Captain 29 to 23 at size 5 | 45% | Survived |
| Attrition from Battle 1 | Full recovery between battles | 86% | Survived |
| Weaken keeps damage too low | Weaken penalty 0 | 100% | Survived |
| Captain's area attack scales with party size | Blight Wave power 0 | 22% | Refuted |

- **Reading.** Weaken is the dominant mechanism, attrition second, the front-row wall third.
  The first two are rule changes and were outside this change.
- **The front-row fix was tried and not adopted.** Moving health from the captain to the hex
  adepts at size 5 (captain 25, hex adepts 15, same total) lifted five Squires to 42% on the
  tuning seeds, but it made every other party stronger too: size 5 measured 85.1%, 88.8% and
  86.4% on the three blocks, outside the band. Variants that added health back dropped five
  Squires to 32-38%. The rule fixed beforehand required both, so the fix was dropped.
- **Known limit:** a party of five Squires wins about 16%. Options for the owner later: a rule
  change to Weaken (for example a shorter duration on slow heroes) or to recovery between battles.

**Confirmation.** The official runner on the packaged content reproduces the table above
party by party on all three blocks. Engine latency in those runs: median 0.17-0.18 ms, p95
0.27-0.30 ms, maximum 97 ms.

**Effect on the playtest findings** (personas on 1.3.0, `docs/PLAYTEST.md` section 9): the
upgrade choice is now worth 7.5 points (was 1.2) and careless rerolling costs 22.5 (was 4.0); the
bench die still changes nothing (+0.8). A newcomer still wins about 9%.

**Margins are thin.** One enemy health point moved five Squires by 20 points in tuning. Rule
fixtures are unaffected by this change: they use class, dice and encounter numbers frozen in
`tests/golden/`.

### 7.9 Owner decision D-22: Vanguard d4 as the Squire's bench die (content 1.3.1, 2026-11-11)

**What changed.** One die. Nothing else in the rules or the numbers moved.

| Squire bench die | Faces | Role |
|------------------|-------|------|
| 1.3.0: Bulwark d4 | Guard 2, Guard 2, Tend 1, Blank | More defense, which the Squire's starting dice already have |
| 1.3.1: Vanguard d4 | Strike 3, Jab 2, Jab 2, Blank | All attack: trades the Oath d4's shields and mana for damage |

The face `Tend 1` (heal 1, cannot revive) is no longer on any shipped die. Rule fixtures that
need ordinary healing (T07, T09, T13) keep using Bulwark d4 from the frozen dice in
`tests/golden/`, so the rule is still tested.

**Result on the packaged content (the firm numbers).** The simulated player (version 2) swaps
each Squire's Vanguard d4 in for the Oath d4 before Battle 2. It is compared with the same player
who never swaps, on the 35 party compositions that contain a Squire, seeds 0-79 (80 runs per
party and side).

| Parties with | Parties | Runs per side | Never swaps | Swaps to Vanguard | Change | Firm? |
|--------------|--------:|--------------:|------------:|------------------:|-------:|-------|
| One Squire | 15 | 1,200 | 91.6% | 91.6% | 0.0 | No effect |
| Two Squires | 10 | 800 | 86.6% | 84.4% | -2.2 | Inside the margin |
| Three or more Squires | 10 | 800 | 66.9% | 73.9% | **+7.0** | Yes (three standard errors) |
| All 35 | 35 | 2,800 | 83.1% | 84.5% | +1.4 | Inside the margin |

| Single party (80 runs per side) | Never swaps | Swaps | Change |
|---------------------------------|------------:|------:|-------:|
| Scout and four Squires | 63.7% | 80.0% | +16.3 |
| Three Squires | 60.0% | 75.0% | +15.0 |
| Five Squires | 16.2% | 30.0% | +13.8 |
| Apprentice and three Squires | 66.2% | 77.5% | +11.2 |
| Four Squires | 51.2% | 58.8% | +7.5 |
| Two Squires (no one else) | 90.0% | 77.5% | -12.5 |

- **Reading:** Vanguard is a real choice, but a narrow one. Parties with three or more Squires
  lack damage and win more with it. The party of exactly two Squires needs the Oath d4's shields
  and mana and loses with it. For every other party the swap makes no measurable difference.
- One party's change has a margin of about 11 points at 80 runs per side, so only the group rows and the
  largest single-party rows are firm. The two-Squire loss points the same way in all three
  samples taken (-35.0, -17.5, -7.5).

**How the die was chosen, and a correction.** The owner's instruction was "design a true
sidegrade first". Nine designs were measured, three per class, with the same method on seeds
0-39 only (40 runs per party, 1,400 per cell).

| Class | Design (faces) | Never swaps | Swaps | Change | Parties up 10+ | Parties down 10+ |
|-------|----------------|------------:|------:|-------:|---------------:|-----------------:|
| Squire | Support: Brace 2, Brace 2, Tend 2, Tend 2 | 84.1% | 82.8% | -1.4 | 4 | 5 |
| Squire | **Vanguard: Strike 3, Jab 2, Jab 2, Blank** | 84.1% | 85.4% | +1.2 | 4 | 4 |
| Squire | Wall: Guard 3, Guard 3, Blank, Blank | 84.1% | 85.4% | +1.2 | 4 | 2 |
| Apprentice | Spark 2, Spark 2, Trickle 1, Blank | 80.7% | 82.3% | +1.6 | 3 | 1 |
| Apprentice | Ward 2, Ward 2, Cleanse 2, Channel 2 | 80.7% | 81.9% | +1.2 | 4 | 1 |
| Apprentice | Arcane Bolt 3, Trickle 1, Blank, Blank | 80.7% | 84.5% | +3.8 | 7 | 1 |
| Scout | Poison 1, Poison 1, Hamstring 1, Blank | 85.3% | 93.5% | +8.2 | 16 | 0 |
| Scout | Cover 2, Cover 2, Focus 1, Quick Shot 1 | 85.3% | 77.5% | -7.8 | 0 | 12 |
| Scout | Shot 2, Shot 2, Blank, Blank | 85.3% | 93.0% | +7.7 | 15 | 0 |

- **What this table can support:** the Scout designs are pure upgrades or a pure downgrade
  (about 8 points, every party the same way), so the Scout bench die is unchanged. The Apprentice
  designs are small upgrades at most, so that die is unchanged too.
- **Correction (2026-11-11).** The Vanguard row was presented to the owner as "4 parties up, 4
  down", with two Squires 95% to 60% and two Squires with three Scouts 78% to 58%. That reading
  was too strong. At 40 runs a party moves by 10 points or more by chance about one time in four
  (27% at an 85% win rate), so 4 up and 4 down out of 35 is what no effect at all would also
  show. The 80-run measurement above replaces it: the gain for Squire-heavy parties held, the
  two-Squire loss held at a smaller size, and the other losses did not reproduce.
- The same caution applies to the "parties up" and "parties down" columns of the other Squire
  and Apprentice rows: they are not evidence of a trade-off on their own.

**Why the confirmation run did not reproduce the first sample exactly.** The first sample kept
the die id `bulwark_d4` with new faces. Dice are rolled in id order, and `vanguard_d4` sorts
after `iron_d6` where `bulwark_d4` sorted before it, so the same seed now gives different rolls.
The two are separate samples of the same design, not a regression: on seeds 0-39 the first
sample gave +1.2 overall and the shipped die gives +0.9.

**The balance gate is unaffected.** The official runner on the packaged content, seeds 300-339,
gives the same result for all 55 parties as content 1.3.0 (per size: 79.2 / 73.8 / 79.0 / 76.5 /
78.1%). The standard simulated player never swaps.

**Limits.** All figures are for the scripted player. Whether human players find the choice
interesting is `<UNKNOWN>`; that needs the human playtest.

**Owner confirmation (2026-11-11).** Shown the 80-run figures and the correction above, the
owner chose to keep Vanguard d4.

### 7.10 Class Evolution: specification v0.2 added, no game code (2026-11-11)

- **What was added.** `docs/class_evolution/` (the design document `FDD_v0.2.md`, the decision
  record `ADR-CE-001.md`, the vocation catalog, the save database script, an example save, the
  code registry and 40 acceptance fixtures), two checkers in `tools/class_evolution/`, and 122
  specification tests in `tests/spec/`.
- **What it is not.** Game code. Nothing under `src/` reads these files, the feature gate is off,
  and the replay pin is unchanged by this addition.
- **Why now.** The owner's first step for the feature was a reconciled specification, approved
  before any build work. The original document (v0.1) could not be built as written: its
  baseline was stale, its catalog had no executable effects, its example save did not load into
  its own database, and its 40 fixtures were free text.
- **How it stays true.** The catalog names the content version it was written against, and the
  validator fails when shipped content moves on. The example save's content hash must equal the
  replay pin's. These run in CI with every other test.
- **Status:** approved by the owner on 2026-11-11 (decision D-23).

### 7.11 Owner decision D-23: FDD v0.2 approved; Class Evolution Phase 1 (2026-11-11)

| Question put to the owner | Answer |
|---------------------------|--------|
| Approve FDD v0.2 as the basis for building? | Approved; start Phase 1 |
| Guardian cannot reach its last rank on shipped encounters | Author one threat-4 training encounter in the first slice |
| New vocations are weaker than the classes they evolve from | Retune each wave by measurement when it is built |
| Pacing (52 to 104 winning runs to Hero) | Measure in the first slice, then bring options |
| Where the feature gate lives (fixture CE-01) | A launch setting, off by default; content files and their hash untouched |

**Phase 1, part A: one seam for a hero's class data** (`src/battle_dice/core/build.py`).

- **Before:** about 20 places in the rules read `content.class_def(hero.archetype_id)`. An evolved
  hero is not a shipped class, so each would have needed a special case.
- **After:** every hero has a `HeroBuild`, resolved once at `StartRun`; the rules read
  `engine.build(hero_id)` and nothing else. Today a build is always a shipped class.
- **Builds are not part of the hashed run state.** They are derived from the `StartRun` command
  and the content, so a replay rebuilds them, and the final state hash cannot move.
- **Evidence that nothing changed:** `tools/update_replay_pin.py` rewrites the pin file to the
  same bytes; the content files are untouched; all earlier tests pass unchanged.
- **Guard:** a test fails if any rule reads the class table directly again.

**Phase 1, part B: schedules as ordered slots** (`src/battle_dice/core/schedule.py`).

- **Before:** the planner hard-coded two shapes: one action, or two actions with one fixed first
  category. Five of the catalog's ten schedules fit neither.
- **After:** every schedule is a list of slots. Each slot accepts some categories and may require
  a face tag. One action is always legal. Several actions are legal when they fill every slot in
  order (a class combo), or, for schedules without an order, when each fits a slot of its own.
- The shipped `scheduling` blocks in `classes.json` are read into this model unchanged; the
  messages a player sees are word for word the same.
- **Evidence that nothing changed:** the replaced code is kept in `tests/unit/test_schedule.py`
  as a reference. For the three shipped schedules and the test-only "free" policy, every
  multiset of up to four faces in every player order is decided, worded and ordered identically
  (about 1.3 million cases). The replay pin is rewritten to the same bytes.
- **Not switched on:** the five catalog schedules marked `new` stay listed as engine gaps. The
  planner can now express them, but their screens, the simulated player and their passives are
  delivered with their waves.
- **Open question for the Archmage wave (new):** for a three-slot schedule, v0.1 says "three
  actions only as Resource, Attack, then Healing or Defense; otherwise one". The model follows
  that literally, so two of the three actions is not a legal plan. Whether "Resource then Attack"
  alone should be legal is a design decision for wave 4.

**Phase 1, part C: the catalog in the package, builds from it, and the gate.**

- **The gate** (`src/battle_dice/features.py`): `--feature class_evolution_v1`, or the environment
  variable `BATTLE_DICE_FEATURES`. Off by default; nothing is stored between launches; an
  unknown name is refused. `--version`, the smoke-test line and the main-menu status bar name an
  enabled gate, so a log or a screenshot always shows the mode.
- **The catalog and its validator moved into the package** (`content/class_evolution/`,
  `content/vocations.py`), so the wheel and the Windows build contain them. With the gate off the
  game never imports that module (checked in a fresh interpreter). The catalog is not one of the
  six content documents and is not part of the content hash.
- **Builds from the catalog.** `load_vocation_catalog` validates the catalog, then resolves each
  playable vocation to a `HeroBuild` using the game's own content loader. A vocation that needs
  a listed engine gap is refused by name.

| Vocation | Playable by the rules today? | What it still needs |
|----------|------------------------------|---------------------|
| Squire, Apprentice, Scout | Yes (the shipped classes themselves) | Nothing |
| Ranger | **Yes** | Nothing in the rules; screens and tuning come with its wave |
| Guardian | No | Passive: Defense die bonus on another ally |
| Spellblade | No | A face that costs corruption; descriptive face tags |
| Duelist, Arcanist, Shadowbinder | No | Their new schedule shapes switched on, and their passives |
| Champion, Archmage, Hero, Trickster, Dragon Knight | No | As listed in the catalog's `engine_gaps` |

- **The engine** takes the catalog as an optional second argument. Without it, an evolved
  vocation is an unknown class, as before.
- **A run records the catalog only when it used it.** With an evolved hero in the party,
  `RUN_STARTED` and the exported record carry the catalog's version and hash, and a replay
  refuses a different catalog. A party of shipped classes produces the identical events, final
  state and record with the gate on or off (checked on the three pinned parties). This settles
  fixture CE-01 and is the behaviour fixture CE-40 assumes.
- **Evidence that nothing changed with the gate off:** the replay pin is rewritten to the same
  bytes, the content files are untouched, and the official runner on seeds 300-339 gives the
  same result for all 55 parties.
- **First evolved hero, in tests only:** parties with a Ranger play full runs under the same
  invariants as every other run and replay exactly from their records. No screen offers a
  Ranger; a player cannot reach one yet.
- **Not a balance claim:** Squire and Ranger won 10 of 10 trial runs with the v0.1 numbers. The
  Ranger is retuned by measurement with its wave, as decided.

**Phase 1 is complete with part C** (pull requests 12, 13 and 14, merged 2026-11-11). The
standalone Windows build passed its smoke test with the gate on.

**Owner decisions for Phase 2 (2026-11-11).**

| Fixture | Question | Answer |
|---------|----------|--------|
| CE-19, CE-39 | When may a hero change vocation inside a run? | After recovery and before the mandatory upgrade; also at party setup; never during a battle or after the upgrade |
| CE-24 | What is recorded for a lost battle? | A zero-point mastery row with the reason `ENCOUNTER_NOT_WON` |
| CE-28 | A skill with no die face it can act on | Refused with `NO_LEGAL_FACE`; the skill stays learned |
| CE-10 | Can discovery move backwards? | No: hidden, hinted, discovered, only forward; each distinct clue counts once |

Ten fixtures still needed a decision at that point; four more were decided later the same day
(D-25), leaving six (CE-09, 29, 30, 31, 32, 36). The three codes v0.2 proposed are marked approved
in the registry.

### 7.12 Class Evolution Phase 2: progression rules in memory (2026-11-11)

**What was built** (`src/battle_dice/career/`): the rules that decide claims, vocation changes,
previews, mastery awards, inherited skills and discovery. The state is held in memory; nothing is
saved and nothing in the game calls it yet. It follows the rules engine's contract: a rejected
command returns one code and changes nothing, a repeated command id returns the stored result, and
every change runs on a copy that replaces the state only on success.

**Gate: the fully specified rule fixtures pass as executable tests.**

| Check | Result |
|-------|--------|
| Acceptance fixtures run against the rules (`tests/spec/test_class_evolution_rules.py`) | 27 of 27 pass (28 since the dice decision below) |
| The other 13 fixtures | Each is named with where it is checked or which phase will run it; a test fails if a fixture is neither run nor accounted for |
| Twenty deliberate rule breaks, one at a time (threat floor ignored, wrong route, no rollback, and so on) | Each makes at least one fixture fail |
| Line coverage of the new package | 100%; it now counts toward the CI coverage floor |
| Replay pin and content files | Unchanged; the game does not import the package |

**This build's own readings, where the fixtures and v0.1 are silent.** Each has a test whose name
says so. None changes an approved rule; the owner can overrule any of them.

| # | Situation | What this build does |
|--:|-----------|----------------------|
| 1 | Claiming a vocation the hero already has; changing to the active vocation; unequipping an empty slot | Accepted, and nothing changes: no event, no new revision |
| 2 | Equipping a skill the hero has not learned, or a native-only skill | Rejected with `PREREQUISITE_UNMET` |
| 3 | A skill tied to melee or ranged faces on dice without such a face | Rejected with `NO_LEGAL_FACE`, like the Healing case the owner decided |
| 4 | Skills that no longer fit after a change of vocation (capacity or face) | Unequipped in slot order; the change event lists them |
| 5 | A mastery award for a mastered vocation, for a hero that was not deployed, or for an encounter that never awards mastery | Nothing is recorded |
| 6 | Claiming during a run | Allowed in every phase except battle (a claim does not alter the build in play) |
| 7 | A skill's rank is reached by an award | The skill is learned at once and a `SkillLearned` event follows the award event |
| 8 | A prerequisite that counts mastered vocations and is not met | Reported as `MASTERED_COUNT_AT_LEAST` with the current count |

**Owner decisions for Phases 3 and 4 (D-25, 2026-11-11), and what was built for the dice one.**

| Fixture | Answer | Built now |
|---------|--------|-----------|
| CE-18 | A vocation may equip its own dice, plus its family's | Yes: see below; the fixture now runs (28 of 40) |
| CE-25 | Run upgrades are kept as history, no longer applied | With Phase 3 |
| CE-35 | Saved heroes enter a run with a build snapshot in the log | With Phase 4 |
| CE-40 | Gate on with starting classes: byte for byte identical | Already tested on the three pinned parties |

- **The dice rule as built** (`CareerCatalog.may_equip`, `EquipDie`): "family" is the starting
  class a vocation grew from. On a change of vocation the new vocation's own starting dice take
  the slots and the dice that were equipped go to the bench. A family die may then be put back;
  a die of any other vocation, an unknown die or a slot that does not exist is refused with
  `INCOMPATIBLE_DIE`. A starting class may equip only its own dice. A die swap that takes away
  the only face a skill needs unequips that skill.
- **This is my reading of the answer.** The other possible default, "family dice stay equipped
  when the vocation changes", would change fixture CE-18 and one rule.
- **Catalog validator:** a vocation's face rules now cover its family's dice too (for example
  "every Attack face a Ranger can roll is ranged"). No shipped family die breaks a rule.
- **Risk:** each evolved vocation has more possible loadouts, so the balance surface grows.
  Loadouts are sampled, not enumerated, when a wave is tuned.

**Not in Phase 2:** saving (Phase 3); item grants and quest completion as events, the screens,
and the rules engine calling these rules (Phase 4). Discovery signals are applied when given;
nothing raises them automatically yet.

### 7.13 Class Evolution Phase 3: saving the career state (2026-11-11)

**What was built** (`src/battle_dice/career/store.py`): a SQLite save store over the approved
24-table schema, which moved into the package (`career/schema/progression.sql`). The rules of
Phase 2 are unchanged: they decide in memory, and the store writes what they decided. After an
accepted change the difference between the state before and after is written in one
`BEGIN IMMEDIATE` transaction. If that fails, nothing is in the file and the memory state is put
back. A rejected command, a replay and a preview write nothing. The game does not open a save
file yet.

**Gate: rollback, repeated-command and migration fixtures pass.**

| Check | Result |
|-------|--------|
| The 28 rule fixtures, run again through the save file (`tests/spec/test_class_evolution_store.py`) | 28 of 28: same result as in memory, and the file holds exactly the result after it is closed and reopened |
| CE-38, with a real failure inside the SQLite transaction, at both fault points | The file and the memory are as they were; the same command id then succeeds once |
| CE-33, repeated command and repeated award after a reopen | Answered from the file; nothing written |
| CE-34, a save of another catalog version | Refused with `CONTENT_MIGRATION_REQUIRED`; no row of the save changes |
| CE-25, run upgrades after the run ends | Rows kept, no longer applied (owner decision) |
| Event log | The hash chain verifies on every load; a changed event is detected |
| Schema version | An older save is backed up through SQLite's own backup call, then migrated in one transaction; a failed migration leaves the old version; a newer save and a file that is not a save are refused |
| Twenty deliberate breaks of the store, one at a time | Each makes at least one test fail |
| Line coverage of `battle_dice.career` | 99% |
| Replay pin and content files | Unchanged; the game loads no career module and creates no save file |

**This build's own readings for saving.** Each has a test. The owner can overrule any of them.

| # | Situation | What this build does |
|--:|-----------|----------------------|
| 1 | "Each distinct clue counts once" must survive a restart, and the schema has no column for the clues seen | A new clue that shows nothing new is logged as a `DiscoveryClueCounted` event; on load the event log says which clues were counted. No schema change |
| 2 | A hero is saved for the first time | Each vocation it has is claimed by a logged event, as the schema requires, and every item held is recorded as a grant |
| 3 | A save written with another catalog version is opened | The new catalog is installed beside the old one, the old one is marked retired, and the profile is refused until a migration exists |
| 4 | The schema's run row needs a seed and a build hash | Phase 3 writes stand-in values; the real ones arrive when the game starts runs from saved heroes (Phase 4) |
| 5 | A hero's health, mana and corruption inside a run | Not saved; the run owns them |
| 6 | A mastery award names a run that is not in the save | Refused; nothing is written |

**Not in Phase 3:** the game opening a save (the gate decides that in Phase 4), screens, item
grants and quest completion as events, build snapshots at run start (CE-35).

### 7.14 Owner decision D-26: five fixtures decided before Phase 4 (2026-11-11)

**The answers**

| Fixture | Question | Answer | Same as the fixture assumed? |
|---------|----------|--------|------------------------------|
| CE-09 | How does the career tree show a secret vocation that is not discovered? | As an anonymous `???` entry | **No.** It assumed the vocation is not shown at all |
| CE-29, CE-30 | Does a refused action plan get a code? | Yes, beside the text; the text stays | It had no assumption |
| CE-32 | What does an event hash cover, and how is a payload encoded? | As built | Yes |
| CE-36 | Which encounters count as available, at which ratings? | The ones the catalog marks shipped, at its ratings | Yes |

**What was built**

- **Career tree** (`career_tree_view` in `src/battle_dice/career/service.py`). A discovered
  vocation is listed with its id, name, group, whether the hero has unlocked it, whether it is
  active, and the hero's rank. A **hidden** secret is an entry with the label `???` and nothing
  else; every hidden entry is identical and they come last, so neither content nor position says
  which secret it is. A **hinted** secret is the label plus its clue. Building the view changes
  nothing. No screen shows it before Phase 4.
- **Plan codes** (`PLAN_CODES` in `src/battle_dice/core/planning.py`). Eleven codes, one for each
  way `SetActionPlan` or `CommitActionPlan` can refuse a plan. `CommandResult.code` carries the
  code beside `reason`; the app's plan preview carries it as `problem_code`. The registry lists
  them under a new kind, `plan_rejection`, with the order of the checks. They do not depend on
  the gate. Other refusals of the rules engine still have text and no code.
- **Reachability** (`available_threat` and `training_dead_end_details` in
  `src/battle_dice/content/vocations.py`). The validator's check can now be asked about a named
  set of encounters, and returns each dead end as data (group, rank, required and available
  threat). The lines it prints are unchanged.
- **A run-started event** (`StoredCareerService.begin_run`). The save could end a run but had
  no way to start one outside an import. A run id is used once.

**Evidence**

- **35 of the 40 acceptance fixtures now run as tests** (32 before). New: CE-09 and CE-36
  (`tests/spec/test_class_evolution_rules.py`) and CE-32
  (`tests/spec/test_class_evolution_determinism.py`).
- **CE-32.** The session is recorded on every test run: a hero claims Ranger and changes to it,
  a run with seed 12345 (Squire in front, Ranger behind) is played by the heuristic player and
  won in both battles, and each battle's mastery awards are applied. It is then replayed twice
  from the record into new save files with different clocks.
  - The 11 progression events are byte for byte the same in all three, hashes included, while
    every stored time differs.
  - Apart from its time columns the whole save is the same, row for row, in all three.
  - The run ends in the same state hash and the same event hash, and replays from its record.
  - Three commands that must be refused were sent before every step of the run (1,128 while
    recording, 1,155 in each replay). They drew 0 random numbers and changed nothing.
  - The awards follow the rules: battle 1 (threat 1) gives the Squire a point and gives the
    Ranger a zero award with `UNDER_THREAT_CAP`; battle 2 (threat 3) gives each a point.
- **CE-09.** With both secrets hidden the view lists the 12 public vocations and two identical
  `???` entries, and none of 9 forbidden strings (ids, names, the item and quest that unlock
  them, both clues) appears anywhere in it. With a hint, the Trickster's entry shows its clue
  and still no id, name or group.
- **CE-36.** With the fixture's pool, and with the catalog as it stands, the highest available
  threat is 3 and every advanced vocation has exactly one dead end: rank 7, which needs threat 4.
  With a threat-4 encounter added to the pool the dead end is gone.
- **CE-29 and CE-30 cannot run yet**: they name Champion dice, and the engine cannot build a
  Champion before wave 4. `tests/unit/test_plan_codes.py` checks every one of the eleven codes,
  the order of the checks, and the two fixtures' situations on today's content: a heal without
  the revival tag is refused on a downed ally with `TARGET_DOWNED` while Rally and Mend are
  accepted; Mend on a downed ally with too little mana is refused with `INSUFFICIENT_MANA`,
  mana stays at 0 and the ally stays down.
- 860 tests pass (819 before). Lint and type checks are clean. Coverage of the rules, content
  and career code is 97%.
- The replay pin and the six content files are unchanged, and the smoke test passes with and
  without the gate.
- The simulator on seeds 300 to 339 (2,200 runs) gives the result it gave before this change,
  composition by composition: 1,703 wins (77.4%). Adding codes changed no decision of the engine.
- **Deliberate breaks.** 25 breaks of the new code were applied one at a time (a wrong code, a
  dropped code, a hidden entry that shows its group, a hint that shows a name, a pool that is
  ignored, a time inside an event hash, a rejected command that leaves a random draw, and so
  on). All 25 now fail at least one test. That took two corrections:
  - **22 were caught at first.** Two misses were gaps in the new tests, now closed: no test had
    a hero one rank short of mastery, and an off-by-one in the required threat gave the same
    number for the one rank the test looked at. The third miss was a badly chosen break: the
    engine's rollback undoes it by design, so it changed nothing. It was replaced by one that
    does survive the rollback.
  - **The harness itself was wrong on its first run.** It reported 25 of 25, but from the sixth
    break on every run failed on the same unrelated test. Cause: a same-size edit put back
    within one second left a stale bytecode file behind. The harness now runs without bytecode
    files and starts with a control run that must pass.
  - The harnesses of sections 7.12 and 7.13 had the same flaw, so both were run again the same
    way. Their results stand: 20 of 20 rule breaks and 20 of 20 store breaks are caught, each
    by a test that fits the break.

**Found while testing**

- The event log refuses any change to a stored event, including its time (a database trigger).
  My first test tried to rewrite a time to show that hashes ignore it, and the file refused. The
  test now shows the same thing from the three sessions: same hashes, different times.
- One row of a new save is stamped by SQLite's own clock, not by the store's: the baseline entry
  of the migration list, written by the schema script. It is in no hash and no rule reads it.
  Left as it is.

**This build's own readings, open to correction**

- A **hinted** secret shows its clue. The decision named the hidden state; showing the clue at
  the hinted state is what the catalog's `clue` field is for.
- Hidden entries come **last**, after hinted ones, rather than at their place in the catalog.
- A target that is down is refused with `TARGET_DOWNED` whether it is an ally or an enemy.
- The number of `???` entries tells a player how many secrets are still hidden (two at first).
  That follows from the decision; it is stated here because it is information.

**Still not executable, and why**

| Fixture | Waits for |
|---------|-----------|
| CE-19 | Phase 4: the rules engine and owned dice together |
| CE-29, CE-30 | The Champion's wave (4); CE-29 also needs inherited skills in battle (Phase 4) |
| CE-31 | A decision on Duelist's Parry, asked with the Duelist's wave (3) |
| CE-35 | Phase 4: `StartRun` with saved heroes and build snapshots |

### 7.15 Class Evolution Phase 4: decisions, steps, and step A (2026-11-11)

**Owner decisions (D-27)**

| Question | Answer | The option I recommended? |
|----------|--------|---------------------------|
| How does a player get saved heroes? | Recruit at party setup; free; at most 12 heroes | Yes |
| Where is the threat-4 fight played? | An optional third battle after battle 2 | **No** (a harder run chosen at setup) |
| How hard is it? | 70-85% for an informed player with a Guardian in the party, per party size | Yes |
| Field Medic in battle in this slice? | Yes, as the slice's last step | Yes |

**Why the threat-4 fight needs its own numbers per party size.** The v0.1 line-up (two captains
and a hex adept) was played as battle 2 by today's parties, with each party size's shipped
numbers for a captain and a hex adept (55 compositions, seeds 300 to 319, heuristic player):

| Party size | 1 | 2 | 3 | 4 | 5 |
|-----------|--:|--:|--:|--:|--:|
| Runs won, shipped battle 2 | 73% | 73% | 76% | 75% | 78% |
| Runs won, v0.1 threat-4 line-up instead | 0% | 0% | 24% | 87% | 100% |

One fixed fight cannot serve five party sizes. The shipped battles have a table per party size
for the same reason (D-19).

**The approved steps**

| Step | What | Proves |
|------|------|--------|
| A | Guardian playable by the rules; measured against the Squire | This section |
| B | Encounters from the catalog; the optional third battle in the engine | A run of three battles; old runs identical |
| Checkpoint 1 | Owner decides Guardian's numbers and the threat-4 table, from measurement | Balance evidence for the first evolved vocation |
| C | Saved heroes in real runs: recruit, build snapshots (CE-35), vocation change between battles (CE-19), awards, a career-aware simulator | 37 of 40 acceptance cases |
| Checkpoint 2 | Owner decides pacing, from measured runs-to-mastery | FDD open decision 5 |
| D | Screens | Playable |
| E | Field Medic in battle; the build panel | The whole loop |

Rules for every step: with the gate off the game is byte for byte unchanged; with the gate on a
plain `StartRun` is unchanged too (CE-40), because everything new is asked for by new optional
parameters or new commands; the run's hashed state gains nothing that shows while unused.

**Step A: what was built**

- Passive type `ally_defense_die_bonus` in the one place the Squire's passive is applied
  (`shield_bonus`, `src/battle_dice/core/effects.py`): +1 shield on a Defense die action that
  targets another ally. Nothing on the Guardian itself, nothing on a reaction. The action
  preview and the simulated player's plan scoring call the same function; the simulated
  player's face valuation counts the bonus only while another ally stands.
- Catalog 0.3.0: the passive `bulwark` is marked `existing` and its engine gap is removed
  (14 gaps left). The catalog schema now lets this passive type be either. Nothing else in the
  catalog changed: every Guardian number is still the v0.1 number.
- The rules can now run five vocations: the three starting classes, Ranger and Guardian.

**Step A: evidence**

- 19 new tests (`tests/unit/test_guardian.py`): the build; +1 on another ally (Heavy Guard 4
  gives 5); +0 on itself; a Squire in the same party keeps its own bonus on itself; nothing on
  the heal face; Guardian Ward gives exactly 3; ten whole runs with every invariant held; a run
  replays exactly and pins the catalog; without the catalog a Guardian is an unknown class.
- 878 tests pass (860 before: 19 new, and one old case that said the Guardian is refused is
  gone). Lint and type checks are clean; coverage is 97%.
- The replay pin and the six content files are unchanged. With the gate off the simulator on
  seeds 300 to 339 (2,200 runs) gives the stored reference exactly: 1,703 wins (77.4%).
- Eleven deliberate breaks of the new code (the bonus on the Guardian itself, on any face, on
  a reaction, the Squire losing its own, the simulated player counting it when alone, and so
  on) each fail a fitting test. Run without bytecode files and with a control run.

**Step A: Guardian against Squire, measured (no number changed)**

Every shipped composition with at least one Squire (35 of the 55) was played on the two shipped
battles twice: as it is, and with one Squire replaced by a Guardian. Heuristic player, seeds 300
to 339, so 40 runs per composition and 1,400 runs per column.

| Party size | Compositions | With the Squire | With a Guardian instead | Difference |
|-----------|-------------:|----------------:|------------------------:|-----------:|
| 1 | 1 | 97.5% (39/40) | 100.0% (40/40) | +2.5 |
| 2 | 3 | 84.2% (101/120) | 84.2% (101/120) | 0.0 |
| 3 | 6 | 86.2% (207/240) | 80.8% (194/240) | -5.4 |
| 4 | 10 | 81.8% (327/400) | 84.0% (336/400) | +2.2 |
| 5 | 15 | 77.7% (466/600) | 75.3% (452/600) | -2.3 |
| All | 35 | 81.4% (1,140/1,400) | 80.2% (1,123/1,400) | -1.2 |

- **Reading:** on today's battles the v0.1 Guardian is about as strong as the Squire it replaces.
  No party size differs by more than about one and a half standard errors. It is a sidegrade
  in win rate, not an upgrade and not the clear downgrade I expected from its passive alone
  (its 17 health against 14, its heavier guards and its 3-shield reaction make up for it).
- **Limits of this measurement:** one simulated player, which may not use a Guardian as well
  as a person would; shipped battles only (the threat-4 fight does not exist yet); the
  Guardian's row was always the front.
- Whether an evolved vocation should be stronger than its starting class is a design choice.
  It is put to the owner at Checkpoint 1, with the threat-4 table.

### 7.16 Class Evolution Phase 4, step B: the optional third battle (2026-11-12)

**What was built**

- **Encounters from the catalog** (`EncounterSource` in `src/battle_dice/core/build.py`, beside
  the build source). The vocation catalog implements it. The rules engine takes the catalog for
  both, so nothing new has to be passed in.
- **The threat-4 fight `training_04` is authored in the catalog**, with its own enemies for each
  party size, in the shape of the shipped encounter table. The validator checks it with the
  shipped content loader, so an authored fight cannot hold anything a shipped one could not.
  An authored encounter counts as available (CE-36, extended). Catalog version 0.3.0.
- **The run:** `StartRun` takes an optional `encounters` list. Without it a run is the run the
  game has always had. With `["training_04"]`:
  - winning battle 2 no longer ends the run. The party recovers by the rule used after battle
    1, and the run waits in a new phase, `continue`;
  - `EndRun` ends it there with a victory; `ContinueRun` starts the third battle;
  - a formation change is allowed while it waits. No second upgrade and no die swap;
  - winning battle 3 is the victory; losing it is a defeat.
- The run's start event and its exported record name the extra encounters and pin the catalog,
  also when every hero is a starting class. A replay refuses a different catalog.
- The simulated players know the decision: the heuristic player fights on or stops as it is
  told; the random player picks either.

**Kept unchanged, and how that is known**

- The run's hashed state has no new field. The extra encounters are kept beside the hero
  builds, outside the state, and are rebuilt from `StartRun` on replay. The only new value in
  the state is the phase name `continue`, which a run without extra encounters never reaches.
- The replay pin and the six content files are unchanged. With the gate off the simulator on
  seeds 300 to 339 (2,200 runs) gives the stored reference exactly: 1,703 wins (77.4%).
- The save keeps its five run phases. The engine's `continue` is saved as `equipment` (between
  battles, every build fixed); the mapping is one tested function.

**The threat-4 table, tuned by measurement**

Target (owner, D-27): an informed player with a Guardian in the party wins 70-85%, per party
size. Measured as: of the runs that enter the third battle, the share that win it. Parties: the
35 shipped compositions with a Squire, one Squire replaced by a Guardian. Heuristic player that
always fights on.

| Party size | Enemies (health) | Seeds 300-339 | Seeds 400-439 | Both |
|-----------|------------------|--------------:|--------------:|-----:|
| 1 | Captain (18) | 78% (31/40) | 76% (29/38) | 76.9% |
| 2 | Captain (23), Hex Adept (13) | 75% (76/101) | 78% (84/108) | 76.6% |
| 3 | 2 Captains (13), Hex Adept (10) | 77% (149/194) | 75% (139/186) | 75.8% |
| 4 | 2 Captains (17), Goblin (8), Hex Adept (9) | 75% (252/336) | 74% (241/324) | 74.7% |
| 5 | 2 Captains (16), Goblin (8), 2 Hex Adepts (9) | 72% (327/452) | 78% (354/451) | 75.4% |

- Captain's Strike is 4, Goblin's Slash 3 and Hex Adept's Shadow Bolt 4 at every size, as in
  the shipped battle 2. The line-up keeps the v0.1 idea (two captains and a hex adept) from
  party size 3 up.
- **How it was reached:** four candidates. The first, close to the v0.1 line-up at shipped
  health, won 21-51%. Each next one lowered health. The fourth was inside the band on the
  first seed block; the second block put party size 3 at 68% over both, so its captains went
  from 14 to 13 health and that size was measured again on both blocks.
- **The same parties with the Squire kept** (seeds 300-339): 67%, 80%, 69%, 72%, 73% for sizes
  1 to 5. So at threat 4, too, the Guardian is about as strong as the Squire.
- **What it does not show:** parties made mostly of Squires and a Guardian almost never win
  the third battle (a Guardian with three Squires: 2 of 29). Those are the weak parties of the
  base game as well. One simulated player; no person has played it.

**Status of the numbers.** The plan put this table and the Guardian's numbers to the owner at
Checkpoint 1. The owner's goal changed on 2026-11-11 to a fully configurable and playable demo,
so the table above goes in as the default without waiting, and the demo's tuning file (a later
step) lets the owner change it without code. It stays an open owner decision.

**Evidence**

- 913 tests pass (878 before). Lint and type checks are clean; coverage is 97%.
- 29 new tests for the run (`tests/integration/test_third_battle.py`): the decision and what
  is allowed while it waits; stopping; fighting on with the right enemies for the party size;
  winning and losing battle 3; five refused starts and one late refusal that leave nothing
  behind; ten whole runs
  with every invariant held; exact replay and a refused replay with another catalog; a
  rejected command at the decision changes nothing.
- Catalog tests: the authored fight loads for every party size; six new seeded violations
  (no enemies, enemies on an unauthored fight, a missing party size, an unknown enemy, an
  unknown action, an enemy that cannot act) are each rejected.
- With the fight taken away again the validator reports exactly the old dead end (Guardian
  rank 7), so the test of fixture CE-36 still proves its case.
- **Deliberate breaks:** 22 breaks of the new code, one at a time (the run ending after
  battle 2, no recovery, a second upgrade, the wrong enemies, the wrong party size's table, an
  unknown encounter accepted, no pin, an authored fight not counted or not checked, and so
  on). 21 were caught at first. The one miss was a gap in the tests: nothing made a start
  fail after its encounters were noted, so the clean-up was never exercised. A test for it
  was added; all 22 are caught now. Run without bytecode files and with a control run.

**This build's own readings, open to correction**

- The party recovers when battle 2 is won, before the decision, so the player decides with the
  real numbers in front of them. (The plan said "the same recovery as after battle 1"; it did
  not say when.)
- Mastery is awarded per won battle (step C). Points from battles 1 and 2 are therefore kept
  when battle 3 is lost; a lost third battle costs the run's victory and nothing else.

### 7.17 Class Evolution Phase 4, step C (part 1): saved heroes in real runs (2026-11-12)

**What was built**

- **Recruiting** (career command `RecruitHero`). A recruit is one of the three starting
  classes, gets the next free hero id and a name from its class ("Squire 1"), and has all
  three starting classes unlocked, as every hero in the acceptance fixtures does. Refused at 12
  heroes with the new registry code `ROSTER_FULL`, inside a run with `PHASE_LOCKED`. The
  save writes a recruited hero in the same transaction as its events.
- **Build snapshots at run start** (fixture CE-35). A party entry of `StartRun` may carry a
  `hero` object: the saved hero's id, name, stats with mastery bonuses, dice, bench and
  equipped skills. The engine builds the hero from its vocation plus the snapshot and refuses
  what a run cannot hold (a stat below the vocation's own, a die that does not exist for the
  hero, the wrong number of dice, the same hero twice). The snapshot is in the command log and
  in the run's start event, so a replay needs the log and the pinned catalog only.
- **Bonus-challenge evidence** (`src/battle_dice/career/evidence.py`), counted from a
  battle's events for the five playable vocations. No engine state was added.
- **The hand-over** (`src/battle_dice/app/progression.py`): opens the save and makes the
  profile on first use; builds party entries from saved heroes; reports run start, each
  battle's result as one mastery award per saved hero, the run's phase, and its end. A run left
  unfinished is closed as a defeat when the next one starts. Run ids come from the save, so the
  same seed can be played twice.
- **A career-aware simulator** (`src/battle_dice/sim/career.py`): plays runs with saved heroes
  and keeps going until a hero has mastered its vocation.

**Kept unchanged, and how that is known**

- A `StartRun` without `hero` objects is the shipped command (CE-35 sends exactly that). The
  replay pin and the six content files are unchanged.
- The run's hashed state gains one key, `hero_id`, on the party entries of saved heroes only.
- Nothing in the game uses any of this yet. The app still opens no save; that comes with the
  screens (step D).

**Pacing, measured (FDD open decision 5; the plan's Checkpoint 2)**

Heuristic player, 8 new profiles per row, the first hero a Squire. Runs until the Squire is
mastered, then (as a Guardian) until the Guardian is mastered.

| Party | Third battle | Runs to master the Squire (least / median / most) | Then runs to master the Guardian |
|-------|--------------|---------------------------------------------------:|---------------------------------:|
| Squire, Scout | Fought every run | 4 / 6 / 7 | 13 / 17 / 20 |
| Squire, Scout | Never | 8 / 10 / 12 | Cannot finish |
| Squire, Scout, Apprentice | Fought every run | 4 / 5 / 6 | 14 / 17 / 17 |
| Squire, Scout, Apprentice | Never | 8 / 9 / 11 | Cannot finish |
| Squire, Scout, Apprentice, Scout | Fought every run | 4 / 5 / 6 | 12 / 13 / 14 |
| Squire, Scout, Apprentice, Scout | Never | 8 / 9 / 10 | Cannot finish |

- **Reading:** with the third battle a player masters the Squire in about 5 runs and the
  Guardian in about 15 more, so about 20 runs to the first mastered evolved vocation. Without
  the third battle the Squire takes about twice as long and the Guardian stops at rank 7,
  because its last rank needs threat 4.
- Why the third battle helps so much: battle 1 (threat 1) stops awarding a starting class from
  rank 4 on, so later runs earn from battle 2 and the third battle only.
- **Limits:** one simulated player; three party shapes; the hero measured is the Squire. The
  decision itself (keep the v0.1 thresholds or change them) stays with the owner. The demo's
  tuning file will let the points per win and the thresholds be changed without code.

**Evidence**

- 959 tests pass (913 before). Lint and type checks are clean; coverage is 97%.
- 36 of the 40 acceptance cases run as tests (CE-35 is new).
- New tests: recruiting (`tests/unit/test_recruit.py`), snapshots
  (`tests/unit/test_snapshot.py`), evidence (`tests/unit/test_evidence.py`) and the
  hand-over (`tests/integration/test_progression_link.py`), which plays the whole loop
  through a save file: a Squire is mastered, becomes a Guardian with its +1 health, and plays on.
- **Deliberate breaks:** 30 breaks of the new code, one at a time. 29 were caught at first. The
  one miss changed nothing for any plan the tests used (a plan of three actions exposes it); a
  test for that was added and all 30 are caught. Run without bytecode files and with a control
  run.

**This build's own readings, open to correction**

- A recruit has all three starting classes unlocked (as in every fixture), not only its own.
- Shields are attributed first in, first out per target, because the log does not say whose
  shield absorbed a hit.
- "Another ally" in the two shield challenges does not include the hero itself.
- A run the player leaves unfinished is recorded as a defeat.
- A hero in the party without a snapshot earns nothing (it is not a saved hero).

**Still to do in step C:** the vocation change inside a run, after recovery and before the
upgrade (CE-19).

### 7.18 Class Evolution Phase 4, step D: the screens; the first slice is playable (2026-11-12)

**What a player can do now** (with `--feature class_evolution_v1`; the gate stays off by default)

1. Recruit heroes at party setup and take up to five of them into a run.
2. Win battles; every saved hero earns mastery, and the screens say what was earned or why not.
3. After Battle 2, end the run with a victory or fight the third, threat-4 battle.
4. Open a hero's career: what it has mastered, what it can claim, what is hidden (`???`).
5. Master the Squire, claim the Guardian, make it the active vocation, and fight as one.

**What was built**

- **The app opens the save** behind the gate, in `saves/profile.sqlite`. A save that cannot be
  opened leaves a working game without saved heroes and says so. The file is closed when the
  game ends.
- **Party setup with saved heroes** (`draw_roster_setup`): party slots, the roster, recruit
  buttons (keys 1, 2, 3 as before), a Career button per hero.
- **The career screen** (`draw_career`): the tree built earlier, with for each vocation where
  the hero stands, what it still needs, and Claim or Make active. A vocation the rules cannot
  run yet is "Coming later": it can be read about and not taken, so no hero can be put into a
  state the game cannot play.
- **Stop or fight on** (`draw_continue`): the party after recovery, what Battle 2 earned, and
  the two choices.
- **Awards on the existing screens:** a status line when a battle ends, and a panel on the
  outcome screen.
- **The self-check** (`--smoke-test --feature class_evolution_v1`) now walks this flow: it
  recruits by key, opens and leaves the career screen, plays three battles and checks that the
  results reached the save. Its logs and its save stay inside its own temporary folder.
- New launch flag `--save-dir`.

**Defects the new tests found in this step, all fixed before the commit**

| Found by | Defect |
|----------|--------|
| The warning-as-error test run | The save's database connection was never closed |
| A test that recruits six heroes | Recruiting was blocked once the party was full, although the recruit should wait in the roster |
| The text-fit test, and a test that selects every vocation | Selecting a vocation the rules cannot run yet (Champion, Hero) crashed the career screen |
| The text-fit test under the widest font | Two labels were cut off: a button's second line, and the one-line mastery summary with five heroes |
| Two older tests | With the logs redirected to a temporary folder the save was written **beside** that folder, into the system's temporary directory. The rule is now: a log folder the caller chose keeps its save inside itself. The stray file was removed |

**A reading of decision CE-40, stated because this step touches it**

- CE-40 says: with the gate on and starting classes only, the replay pin must match byte for
  byte. That holds and is tested: the rules engine gives the same bytes for the same commands
  whether or not it is handed the catalog.
- A run started **from the app** with the gate on is a different run by design. Its start
  command names saved heroes with their builds (decision CE-35) and offers the third battle
  (D-27), and its run id comes from the save. An older test that compared the app's events
  with and without the gate now checks exactly that difference and that the battle itself is
  the same.

**Evidence**

- 989 tests pass (959 before). Lint and type checks are clean; coverage of the rules, content
  and career code is 97% (the app and screens are outside that figure; their tests are below).
- 29 new screen tests (`tests/ui/test_evolution_ui.py`): the gate (no save and no save code
  loaded while it is off, in a fresh interpreter); recruiting, the roster, the party; the
  career screen including a mastered Squire becoming a Guardian and fighting as one; awards;
  both choices after Battle 2; **no text cut off at 1280x720 and 960x540 under three fonts**;
  a drawing fault on each new screen reaches the error screen.
- The replay pin and the six content files are unchanged. The rules engine, the simulated
  player and the content were not touched in this step.
- **Deliberate breaks:** 26 breaks of the new screen and controller code. 23 were caught at
  first. Two misses were test gaps (adding the same hero twice by a direct call; the Career
  button of the second slot), now closed. The third no longer changes anything, because of
  the safer save location above. Run without bytecode files and with a control run.

**Not verified**

- No person has played it. The screens were checked by tests and by reading screenshots made
  in this session, not on a physical display.
- Windows: the standalone build with the gate on is checked by its workflow (it now opens a
  save inside the packaged app for the first time).

**Still to do for the slice:** the vocation change inside a run (CE-19), Field Medic in battle,
the build panel (skills and family dice), and the demo's settings.

### 7.19 The demo's configuration: a settings file and a Settings screen (2026-11-12)

**Why.** The owner's goal of 2026-11-11 is a fully configurable and playable demo. What
"configurable" should cover was put to the owner twice and not answered, so this follows the
assumption recorded in `.10x/decisions.md`. It can be widened or narrowed.

**What a player can change now, from Main menu, Settings**

| Setting | Values | Takes effect |
|---------|--------|--------------|
| Class Evolution | Off (default), On | At once: the save is opened or closed and the party setup changes |
| Third battle | Offered, Not offered | At the next run |
| Mastery pace | Normal, Fast, Very fast | At once: heroes are re-ranked from their points, with an event in the save's log |
| Roster size | 6, 12, 24 (1 to 50 in the file) | At once |
| New profile starts as | Fresh; a Squire one win from mastery; a Guardian at rank 1; a mastered Guardian | When a profile is made or reset |
| Dice seed | A new one each run, Fixed | At the next run |
| Animation | On, Off | At once |
| Window size | Four sizes | At once |

Plus **Reset the saved profile**, which asks twice.

**How it is built**

- `src/battle_dice/settings.py`: one JSON file. A launch flag wins over an environment
  variable, which wins over the file, which wins over the default. A file that cannot be read,
  or a value that is not allowed, never stops the game: the default is used and the problem is
  named on the main menu. Reading never creates the file; it is written when a setting changes.
- **Class Evolution stays off by default.** Switching it on in the screen does what the launch
  flag does. A gate forced by a launch flag cannot be switched off inside.
- **Mastery pace** does not change points per win. The save's award rows allow 0 or 1 base
  point and 0 or 1 bonus point and nothing else, so a faster pace asks for fewer points
  instead: every rank's points are divided (by 2 or 4, rounded up, still rising with each
  rank). When a save is opened, every rank is made to agree with its points under the current
  pace; a change is one `RanksRederived` event in the log. What a hero has claimed stays claimed.
- **Start presets** go through the career rules: heroes are recruited, mastery is handed out by
  a trusted event `MasteryGranted` that names its reason, and the Guardian is claimed like any
  other. So a save always says which mastery was earned and which was handed out.

**Asked for in the assumption and not built, with the reason**

| Not built | Why |
|-----------|-----|
| Points per win as a setting | The save's award rows allow 0 or 1 point. More would need a change of the approved save schema and a migration. The pace setting gives the same effect on how long mastery takes |
| The third battle's enemies as a setting | The enemy table is part of the vocation catalog, and a run's record pins the catalog's hash so it can be replayed. A table edited by a setting would make such records unreplayable. Its numbers stay in `vocation_catalog.json`, where the validator checks them |
| A separate tuning file | The tuning that was built lives in the one settings file, so there is one place to look |
| Base game numbers from a folder | Left out as decided in the assumption: such runs fall outside the balance evidence and the replay pin |

**Evidence**

- 1038 tests pass (989 before). Lint and type checks are clean.
- New tests: the settings file (defaults, round trip, 15 values that are not allowed, where the
  file lives); the pace table and that a faster pace masters a Squire in fewer runs; the four
  presets; re-ranking with its log event; the Settings screen (every setting changes, is saved
  and takes effect; Class Evolution on and off inside the game; launch flags win; reset asks
  twice; **no text cut off at both sizes under three fonts**; a drawing fault reaches the error
  screen).
- With default settings the game is the shipped game: a test compares a controller made with
  no settings and one made with default settings and a settings path. The replay pin and the
  six content files are unchanged.
- **Deliberate breaks:** 26 breaks of the new code, each caught by a fitting test. Run without
  bytecode files and with a control run.

**Not verified:** no person has used the Settings screen; it was checked by tests and by
screenshots made in this session.

### 7.20 Class Evolution Phase 4, step E: Field Medic in battle, and the skills panel (2026-11-12)

**Owner decision (D-27):** Field Medic works in battle in the first slice, as its last step.

**The rule as built**

- A hero with **Guardian Field Medic** equipped may use a Healing face that cannot revive on a
  **downed** ally. Used so, the action costs **1 more mana**, brings the ally back at **1 HP**,
  and is named "Heal (Field Medic)" in the plan, the log and the record.
- **Once per encounter.** The use is counted on the hero and cleared when the next battle is
  built. Two such revivals cannot be planned in one activation.
- On a standing ally the face is what it always was, and the skill stays ready.
- Refusals use the plan codes of section 7.14: too little mana is `INSUFFICIENT_MANA` ("Heal
  (Field Medic) needs 2 mana but only 1 will be available"); a downed ally without the skill, or
  after its use, is `TARGET_DOWNED`.
- It does not create a new action and does not change a face that already revives.

**Readings that are mine, written here so they can be changed**

| Question | Reading | Why |
|----------|---------|-----|
| Which face does it apply to? | Any Healing face with one ally as its target that the hero rolls | Fixture CE-29 shows it as an option on the face; the catalog says "one equipped Healing face" and names no way to choose one |
| When is the use spent? | When the action resolves. A revival that is cancelled or loses its target is not spent | The same moment the mana is paid |
| Where is a skill equipped? | On the Career screen, between runs | The career rules already lock a build during a run |

**How it is built**

- `src/battle_dice/core/skills.py` is the one place that knows the skill. The plan, the die's
  target list, the resolution and the simulated player all ask it.
- **The hashed state.** The per-encounter counter is a new field on a combatant. It is left out
  of the plain form while empty, so a run that never uses a skill hashes exactly as before. The
  replay pin and the six content files are unchanged; the gate-off simulator on seeds 300 to 339
  is identical to the stored reference (1703 of 2200).
- A hero's equipped skills reach the run in its build snapshot (section 7.17), so a record
  replays from the command log and the pinned catalog alone.
- **Catalog 0.4.0:** `guardian_field_medic` is marked `existing` and leaves the engine gap
  `inherited_skills`. A test holds the catalog and the rules to the same list. The catalog's
  hash changes, so a record of an evolved run made with catalog 0.3.0 no longer verifies; that
  is what the pin is for.

**The skills panel**

- Career screen, key **K**: the skills a hero has learned, who teaches each, what it costs in
  capacity, and Equip or Take off. A skill is free while the vocation that teaches it is active.
- Every reason an Equip button is off is written in the row: not in this version yet, too
  little capacity, no face it can work on, or a run is under way.
- **Squire Anchor is listed and cannot be equipped.** The rules of battle do not know it, and
  a hero should not spend capacity on something that does nothing.
- The start preset "a mastered Guardian" now has Field Medic equipped.
- In battle the die says "Field Medic: revive for 2 mana" while the skill can be used, and the
  downed ally is a target.

**Found and fixed on the way**

- **An evolved hero had no picture in battle** (the card, the turn order, the intent panel and
  the outcome screen asked for a picture named after the vocation). It now uses the picture of
  the class it grew from, as the party setup already did. Present since step D.
- A long plan line was cut off under the widest font. Plan lines are now set smaller before
  they are cut.
- **A Guardian's upgrade broke the upgrade screen.** Once the upgrade was applied to a Guardian
  die, the screen looked the die up in the shipped content, did not find it, and the game went
  to its error screen. So a run with a Guardian could not get past the upgrade when the
  Guardian's die was chosen. Present since step D; no test played a Guardian through the
  upgrade. The screen now asks the run for the die, and a test plays it.
- The combat log named an evolved hero's dice by their ids ("guardian_d6"). It now uses their
  names.

**Not built, and why**

| Not built | Why |
|-----------|-----|
| Putting a family die back (the plan's build panel) | No hero owns dice of its own in the playable slice; a hero fights with its vocation's starting dice. There is nothing to put back until a later wave gives heroes dice |
| Squire Anchor in battle | The plan closes the skill gap for this one skill kind. Anchor on top of the Guardian's own passive needs a balance decision first |
| Fixtures CE-29 and CE-30 as written | They need the Champion. Their situation (a revival that costs more than the hero has) is tested with the Guardian |

**Measured (simulated player, not a balance claim)**

Guardian parties of sizes 2 to 5, one fixed composition each, seeds 500 to 559, third battle
always fought, the same seeds with and without the skill:

| Party size | Wins without | Wins with | Revivals used |
|------------|--------------|-----------|---------------|
| 2 | 46 of 60 | 46 of 60 | 0 |
| 3 | 46 of 60 | 45 of 60 | 2 |
| 4 | 35 of 60 | 35 of 60 | 3 |
| 5 | 26 of 60 | 26 of 60 | 5 |

- **No measurable effect for this player:** 153 wins without, 152 with, in 240 runs each.
- **Why:** in 120 of these runs (seeds 500 to 539, sizes 2 to 4) the Guardian had a rolled Heal
  in front of it with an ally down at 128 keep-or-reroll decisions, and had the 2 mana at 4 of
  them. It used the skill 4 times. The simulated player spends mana on its reaction as soon as
  it can and never saves it.
- A person who keeps 2 mana back may get more from it. Whether the cost should be lower is an
  owner decision with these numbers; nothing was tuned.
- These are whole-run rates of four fixed compositions with heroes at their catalog numbers.
  They are not the measure the third battle's table was tuned on (section 7.16).

**Evidence**

- 1071 tests pass (1038 before). Lint and type checks are clean. Core coverage 97%.
- New tests: the rule (12 tests: the revival, once per encounter, ready again next battle, the
  two refusal codes, faces it must not change, an unknown skill, the hashed state, replay, two
  revivals in one plan, the simulated player); the save link (the skills view, equip and take
  off by slot, capacity away from the vocation, the skill inside a real run, eight whole runs
  with replay); the screens (the panel, equip and take off with the save's events, the lock
  during a run, every refusal's wording, the die's note, the revival played through the screen,
  pictures, **no text of the new parts cut off at both sizes under three fonts**).
- Both self-checks pass; the gate-on one now opens the skills panel.
- **Deliberate breaks:** 39 breaks of the new code. 36 were caught at first. Two misses were
  test gaps (taking off a skill that is not in the first slot; the Career screen reopening on
  the skills), now closed. The third was not a break: it changed nothing a player could see, and
  was replaced by one that is. All 39 are caught. Run without bytecode files and with a control
  run.

**Not verified:** no person has played it; checked by tests and by screenshots made in this
session.

**Still to do for the slice:** the vocation change inside a run (CE-19); done in section 7.21.

### 7.21 Class Evolution Phase 4: a vocation change inside a run (2026-11-12)

**Owner decision (fixture CE-19, decided 2026-11-11):** inside a run a hero may change vocation
after recovery and before the mandatory upgrade, so the upgrade cards are offered for the new
vocation's dice. Changing is also allowed at party setup, and never during a battle or after
the upgrade.

**The rule as built**

- New engine command **`ChangeVocationInRun`** (hero, target vocation, the hero's build snapshot
  as that vocation). Accepted only in the run phase `upgrade`, only for a saved hero.
- **Health and mana carry over** by the career rule: `ceil(current * new maximum / old
  maximum)`, at most the new maximum. A hero at 0 HP stays down. The one formula now serves the
  career rules and the run (`core.build.convert_pool`).
- The hero gets the new vocation's dice, bench, speed, passive, reaction and schedule.
- **Its upgrade offers are drawn anew** for the new dice, from the same reward stream. Offers
  of other heroes stay. An offer for a die that left is void.
- The upgrade is then chosen on a die of the new vocation, and that die is locked against a
  swap, as for every upgrade.
- The command is in the run's log with its snapshot, so a record replays from the log and the
  pinned catalog. A run that started with shipped classes names the catalog once a hero evolves.

**Who decides what**

| Question | Decided by |
|----------|-----------|
| May this hero be that vocation, now? | The career rules (`ChangeVocation`, their own command). They allow it in the run phase `upgrade` and lock it in battle and after the upgrade |
| What does the hero look like in the run afterwards? | The run, from the snapshot it is sent |
| What if the run refuses after the career rules agreed? | The hero is put back to what it was, and the player is told why |

The two commands have different names on purpose. A test holds them apart.

**In the game**

- The upgrade screen has a **Career (C)** button for the selected hero (with Class Evolution
  on). Before the upgrade is chosen, the Career screen lets the hero claim a vocation or change
  to one; the screen says that it fights on with the new dice and that health and mana carry
  over.
- After the change the upgrade screen shows the new dice and their cards.
- Once the upgrade is chosen, and during a battle, the Career screen can be looked at and
  nothing can be changed; every disabled button says why.
- A hero that is not in the party may change at that moment too; the run is not touched.
- The mastery point of the next battle goes to the vocation the hero then fights as.

**A limit of today's content, for the owner**

- The only moment for a change inside a run is after Battle 1. A hero that masters the Squire
  **in Battle 2** cannot become a Guardian before the third battle: after Battle 2 there is no
  upgrade, only the decision to stop or fight on.
- The start preset "a Squire one win from mastery" shows this: Battle 1 is too easy for its
  rank and gives no point; the mastering win is Battle 2.
- Option: also allow the change at the stop-or-fight-on decision. That is a new rule (CE-19
  names the upgrade only), so it is not built. It needs an owner decision.

**Readings that are mine**

| Question | Reading | Why |
|----------|---------|-----|
| May a hero change back before the upgrade? | Yes, any number of times while the upgrade is not chosen | CE-19 sets the window, not a count; each change is in the log |
| May a vocation be claimed at that moment? | Yes | The career rules lock a claim during a battle only |
| Corruption | Kept, at most the new maximum | The career rule for a change says the same |

**Evidence**

- 1110 tests pass (1071 before). Lint and type checks are clean. Core coverage 97%.
- Replay pin, the six content files and the vocation catalog unchanged. Gate-off simulator on
  seeds 300 to 339 identical to the stored reference (1703 of 2200). Both self-checks pass.
- New tests: the engine rule (the change and what it carries over, the offers, the upgrade on
  the new die and its lock, a downed hero, changing back, the refusals (each changes nothing),
  malformed commands, replay of a really played run, the catalog pin); the save link (the save
  and the run agree, the award goes to the new vocation, a hero outside the party, a refusal by
  the run is undone); the screens (the whole flow from the upgrade screen, the locks, **no text
  cut off at both sizes under three fonts**, no Career button with Class Evolution off).
- Acceptance case CE-19 is now run by tests: **37 of 40** (28 here, 7 elsewhere, 3 wait: CE-29
  and CE-30 for the Champion, CE-31 for a decision).
- **Deliberate breaks:** 40 breaks of the new code. 35 were caught at first. Four misses were
  test gaps, now closed: mana that was refilled instead of carried over (after recovery it is
  always full, so the first test could not tell); a build left changed by a change that fails
  half way; a pool above its new maximum; an upgrade card that stayed selected for a die the
  hero no longer has. The fifth changed nothing a player can reach and was replaced by one
  that does. All 40 are caught. Run without bytecode files and with a control run.
- **Found by the suite:** the first name of the engine's command was `ChangeVocation`, the name
  the career rules already use for theirs. A specification test refused it. It is now
  `ChangeVocationInRun`.

**Not verified:** no person has played it; checked by tests and by screenshots made in this
session.

**The approved Phase 4 plan (section 7.15) is now built in full.** Open with the owner:
Checkpoint 1 (the Guardian's numbers, the third battle's table), Checkpoint 2 (pacing), Field
Medic's cost, Squire Anchor in battle, the change at the stop-or-fight-on decision.

### 7.22 A tour of the slice, played by a test (2026-11-12)

**Why.** The owner's goal is a demo that can be shown. Everything the first slice can do is
reachable from the screens, but nothing said in which order to click to see it.

- `README.md` has **a tour in two runs**: Field Medic and the third battle; becoming a Guardian
  inside a run. Each starts from Main menu, Settings, with one of the start presets.
- `tests/ui/test_demo_tour.py` **plays both runs through the screens as they are written**:
  every button and key the reader is told to use is clicked or pressed. Battles are won by
  arrangement, so the tour does not depend on the dice. A third test holds the README to the
  names the screens use.
- The start preset once shown as "A mastered Guardian" is now shown as **"A Guardian with Field
  Medic"**, which says what it is for. A longer name was cut off under the widest font; the
  existing fit test caught it.
- **Whole runs with a Guardian, drawn step by step.** The simulated player plays a Guardian
  party from the first roll to the outcome on three seeds, and every step is drawn. The defect
  of section 7.20 (a Guardian's upgrade broke the upgrade screen) existed because no test had
  played an evolved hero through a run; with that fix taken out again, two of the three seeds
  fail.
- 1116 tests pass (1110 before).

### 7.23 The self-check plays an evolved hero, in the packaged build too (2026-11-12)

**Why.** `--smoke-test --feature class_evolution_v1` is the one check that runs inside the
packaged Windows build. It recruited fresh heroes, so it never built a hero from the vocation
catalog. A Guardian's dice, its picture, its upgrade cards and the third battle were therefore
never exercised in the packaged app.

- The gate-on self-check now has a second half: a new profile with a mastered Guardian (Field
  Medic equipped), a Scout and an Apprentice plays a whole run with every step drawn. A drawing
  fault, the error screen, a run that does not reach the outcome, or a result that does not
  reach the save fails the check.
- Its report line ends with `evolved_run=victory` or `evolved_run=defeat`. The packaging
  workflow fails when the packaged app's report does not carry it.
- Its logs and its save stay in the self-check's temporary folder, as before.
- The mandatory upgrade is put on the Guardian's own die, so the upgrade screen has to show a
  die that is not in the shipped content, and the Guardian's picture is asked for by name.
- **Checked by breaking it:** with the upgrade-screen fix of section 7.20 taken out the
  self-check fails; with the picture of an evolved hero taken away it fails. A first version
  let the simulated player choose the upgrade and passed both breaks, because the player
  happened to upgrade another hero's die. That is why the upgrade is now chosen on purpose.
- The gate-off self-check is unchanged.
- Time: about 20 seconds here for the gate-on check (about 7 before).

### 7.24 Four owner answers of 2026-11-12, and what followed

The owner was asked four questions through the ask tool and answered all four.

| Question | Answer | What followed |
|----------|--------|---------------|
| Is the Settings screen the "configurable" scope you meant? | "Research a more logical set of configuration options" | Researched (section 7.26); a proposal goes to the owner before anything is built |
| May a hero change vocation at the stop-or-fight-on decision too? | Yes (D-29) | Built, below |
| What should Field Medic's revival cost? | Measure the options first | Measured (section 7.25); nothing changed |
| The Guardian's numbers and the third battle's table | Accepted as built (D-28) | Recorded; no change to the game |

**D-29 as built: the second moment for a change**

- `ChangeVocationInRun` is accepted in the run phase `continue` as well as `upgrade`.
- At that decision **no upgrade is dealt**: no offers are drawn and the reward stream is not
  touched. Health and mana carry over by the same rule.
- **An upgraded die the hero gives up loses its upgrade** (the rule of the approved plan: an
  upgrade belongs to its die). The Career screen says so before the change.
- The career rules lock a build by the saved run phase. The save has no phase of its own for
  this decision; it was saved as `equipment` (every build fixed) and is now saved as `upgrade`
  (a build may change). The approved save schema is unchanged.
- The stop-or-fight-on screen has a **Career** button for each hero and shows each hero's
  vocation. Key C opens the first hero's career.
- A hero that masters its class in Battle 2 can now become the next vocation before the third
  battle, which was the limit named in section 7.21.

**Evidence**

- 1128 tests pass (1116 before). Lint and type checks are clean.
- Replay pin, content and catalog unchanged. Gate-off simulator on seeds 300 to 339 identical
  to the stored reference (1703 of 2200). Both self-checks pass.
- New tests: the rule at the decision (what carries over, no cards dealt, the upgrade that
  leaves, stop or fight on afterwards, a run of shipped classes is offered nothing new, replay
  of a really played run); the save link (the save and the run agree, locked again in battle
  3); the screen (the whole flow, a die the hero no longer holds is still named, **no text cut
  off at both sizes under three fonts**).
- **Deliberate breaks:** 16 breaks of the new code, each caught by a fitting test. Run without
  bytecode files and with a control run.

**Not verified:** no person has played it.

### 7.25 Field Medic: what its cost and its revival health are worth (measured 2026-11-12)

**Asked by the owner:** measure the options before anything changes. Nothing was changed for
the measurement. **Owner decision afterwards (D-30, 2026-11-12): 1 mana, back at 5 HP.** It is
built as its own change.

**Method.** Guardian parties of sizes 2 to 5, one fixed composition each, seeds 500 to 619
(120 per size, 480 runs per option), third battle always fought, informed simulated player.
Every option was run on the same seeds, from a frozen copy of the source.

| Revival | Wins of 480 | Times used | Runs won that the party without the skill lost | Runs lost that it won | Net |
|---------|-------------|-----------|-----------------------------------------------|----------------------|-----|
| No skill equipped | 297 | 0 | | | |
| 2 mana, back at 1 HP (**as built**) | 295 | 25 | 2 | 4 | -2 |
| 1 mana, 1 HP | 290 | 94 | 9 | 16 | -7 |
| 2 mana, 3 HP | 295 | 25 | 2 | 4 | -2 |
| 1 mana, 3 HP | 298 | 90 | 16 | 15 | +1 |
| 2 mana, 5 HP | 302 | 25 | 8 | 3 | +5 |
| 1 mana, 5 HP | 316 | 92 | 28 | 9 | +19 |
| 2 mana, 9 HP | 311 | 26 | 15 | 1 | +14 |
| 2 mana, 1 HP, and the player skips its reaction to keep 2 mana | 160 | 250 | 37 | 174 | -137 |
| 1 mana, 1 HP, and the player skips its reaction to keep 1 mana | 236 | 275 | 35 | 96 | -61 |

**What the numbers say**

- **The cost is not the lever.** At 1 HP the skill does nothing for this player at either
  cost; used more often (1 mana) it is slightly worse, because the Guardian spends its one
  action on an ally that falls again.
- **The health on revival is the lever.** At 5 HP the skill starts to pay; at 1 mana and 5 HP
  it wins 19 more runs than it loses (about 4 points on 480 runs).
- **Saving mana for it is a clear loss.** The Guardian's reaction (3 shield for 1 mana) is
  worth much more than a revival.
- These are whole-run rates of four fixed compositions with one simulated player. They show
  direction, not a balance target. A change is an owner decision; the catalog says "revive to
  1 HP once per encounter if it costs +1 mana".

### 7.26 Research: a more logical set of configuration options (2026-11-12)

**Asked by the owner.** The research was done by a research agent of this session with web
access; its sources are listed here as it reported them. **Owner decisions afterwards (D-31,
2026-11-12):** the demo options get a group of their own at the bottom of Settings; the seed
is chosen on the New Run screen; the small set of comfort and play-aid settings is built.
Each is built as its own change.

**What the sources say (as reported, one line each)**

- Xbox Accessibility Guidelines 101 and 102: scalable text and a high-contrast option.
- XAG 107 and the Game Accessibility Guidelines (basic): remapping, text size and colour
  options are the most-missed; adjustable game speed and saved settings are basic.
- XAG 108: difficulty presets, changeable at any time; single-player games pausable.
- XAG 114, 115 and 117: labelled groups with context help; confirmation for destructive
  actions and a reset to defaults; a way to switch off motion and flashes.
- Options-menu write-ups: reachable from the main menu and the pause menu, applied at once,
  kept outside the save, with a reset to defaults; a dependent option sits beside its parent,
  greyed with its reason.
- Comparable games (Slay the Spire, Into the Breach, Slice & Dice, Celeste): comfort options
  live in Settings; seed, difficulty and modifiers are chosen when a run is started;
  rule-changing or debug switches sit apart and are labelled.
- Not opened or not verified: no GDC talk; Monster Train's and Dice Legacy's menus.

**Audit of today's eight rows**

| Row | What it is | Proposal |
|-----|-----------|----------|
| Class Evolution | Game mode | Keep, in a group of its own with the profile reset |
| Third battle | Run rule | Move to a demo group; the player already decides after Battle 2 |
| Mastery pace | Pacing aid | Move to the demo group |
| Roster size | Profile capacity | Move to the demo group |
| New profile starts as | Demo preset | Move to the demo group, beside the reset that applies it |
| Dice seed | Run option | Move to the New Run screen, with a seed that can be typed |
| Animation | Comfort | Keep, first group, named "Motion and flashes" |
| Window size | Display | Keep, first group |

**Proposed structure (not built)**

| Group | Options | State |
|-------|---------|-------|
| 1. Display and comfort | Window size; Motion and flashes | Exist |
| | Text size (Normal, Large); High contrast; Battle speed at start | New, small; text size needs a layout check on every screen |
| 2. Play aids | Confirm before passing with an unused die; Tooltip delay; Controls (the help screen) | New, small; help screen exists |
| 3. Run options (New Run screen) | Dice seed, random or typed | Toggle exists; typed entry new |
| | Difficulty presets | Large: needs balance work; not proposed for the demo |
| 4. Class Evolution | On or off; Reset the saved profile | Exist |
| 5. Demo and testing | Mastery pace; New profile starts as; Roster size; Third battle | Exist; greyed with the reason while Class Evolution is off |
| Whole screen | Open Settings from the pause menu; Reset all settings to defaults | New, small |

Guidance also recommends audio controls, subtitles, key remapping and controller support. The
game has no audio and no controller support; remapping is not small. None is proposed.

### 7.27 Field Medic: no extra mana, back at 5 HP (owner decision D-30, built 2026-11-12)

**Decision.** After the measurement of section 7.25 the owner chose: the revival costs what
the Heal costs, and the ally comes back at 5 HP. Still once per encounter.

**What changed**

| Before | Now |
|--------|-----|
| The revival cost the Heal's mana + 1 (2 for the Guardian) | It costs the Heal's own mana (1 for the Guardian) |
| The ally came back at 1 HP | The ally comes back at 5 HP, never more than its maximum |
| The die said "Field Medic: revive for 2 mana" | It says "Field Medic: revive at 5 HP"; the cost is the die's own and is in the plan |

- The two numbers are in one place, `src/battle_dice/core/skills.py`. A test names them as the
  owner's decision.
- **Vocation catalog 0.5.0:** the skill's description says what it now does. The catalog's
  hash changes, so a record of an evolved run made with catalog 0.4.0 no longer verifies.
- Everything else about the skill is as in section 7.20: which face, when the use is spent,
  the refusal codes, the hashed state.
- Gate off: unchanged. Replay pin and the six content files unchanged.

**Confirmed with the game's own numbers** (nothing patched; the same 480 seeds as section 7.25):
316 wins of 480 with the skill against 297 without it; 28 runs won that were lost without it, 9
lost that were won; used 92 times. Run by run the same as the measured option "1 mana, 5 HP".

| Party size | Wins without | Wins with |
|------------|--------------|-----------|
| 2 | 89 of 120 | 91 of 120 |
| 3 | 90 of 120 | 93 of 120 |
| 4 | 63 of 120 | 68 of 120 |
| 5 | 55 of 120 | 64 of 120 |

**Evidence**

- 1131 tests pass (1128 before). Lint and type checks are clean.
- Tests changed to the decided numbers, and new ones: the two numbers as the owner's decision;
  a revival never gives more health than the ally can hold; the catalog's description carries
  the decided numbers; 1 mana pays for the revival and 0 does not.
- A longer die note ("... 5 HP, 1 mana") was cut off under the widest font; the fit test caught
  it, so the note is the shorter one.

**Not verified:** no person has played it. The gain is measured with one simulated player on
four fixed compositions.

### 7.28 The configuration as decided (D-31), part 1: groups, the seed on the New Run screen (2026-11-12)

**Owner decisions (D-31).** The demo options get a group of their own at the bottom of
Settings; the dice seed is chosen on the New Run screen; a small set of comfort and play-aid
settings is built. This section is the structure; the new settings follow in their own change.

**What changed**

| Before | Now |
|--------|-----|
| One flat list of eight settings | Four groups, in this order: Display and comfort, Play aids, Class Evolution, Demo and testing (keys 1 to 4) |
| Mastery pace, start preset, roster size and third battle mixed with player settings | In "Demo and testing", greyed with the reason while Class Evolution is off |
| "Reset the saved profile" at the bottom of the list | A row of the group Class Evolution |
| The dice seed was a Settings row: random, or a fixed seed the game drew | **On the party setup: "Dice seed (D)"**, random or a seed the player types |
| Settings only from the main menu | Also from the pause menu of a run |
| No way back to the defaults | "Reset all settings to defaults", asked twice |
| "Animation" | "Motion and flashes" |
| The controls help only from the main menu and the pause menu | Also a row of "Play aids"; it returns to the Settings |

**How it is built**

- **From the pause menu** the run waits and nothing advances. Display and comfort apply at
  once. Class Evolution, the demo group and both resets are locked with the reason "Not during
  a run": each would close the save and with it the run. A command sent anyway is refused.
- **The typed seed.** While a seed is typed every key belongs to the entry: digits (also the
  number pad), Backspace, Enter, Esc. The number keys add no hero and B begins no run until the
  entry ends. A seed is 0 to 2^64 - 1; more is refused with the range. Leaving the screen ends
  the entry; beginning the run takes what was typed. The seed is kept in the settings file as
  before, and the `--seed` launch flag still wins and locks the control.
- **Reset to defaults** keeps the save folder (a place, not a preference) and the saved
  heroes. Class Evolution goes off with it, as its default says.
- The settings file has the same fields as before. No rule of a battle is touched; the replay
  pin and the content are unchanged.

**Evidence**

- 1137 tests pass (1131 before). Lint and type checks are clean.
- The existing Settings tests were rewritten for the groups. New tests: the groups and their
  order; the help from the Settings and back; reset to defaults (asked twice, cancelled by
  anything else, the heroes kept); the Settings from the pause menu with every lock and every
  refused command; the typed seed (digits and number pad, keys of the screen silent meanwhile,
  Backspace, Enter, Esc, too large, leaving, beginning, the file, the launch flag); **no text
  cut off at both sizes under three fonts**, including a seed of 20 digits.
- The README's tour was changed to the groups, and the test that plays it follows.
- **Deliberate breaks:** 39 breaks of the new code. 38 were caught at first; the one miss was a
  test gap (choosing a group that does not exist), now closed. Run without bytecode files and
  with a control run.
- **Found by the Windows check, fixed:** the new "Saved profile" row drew the save file's path
  as a wrapped paragraph. A path has no spaces to wrap at, so on Windows (a long path) it stood
  on a line of its own and was cut without its "Save file:" label. It is one labelled line
  again. The failure was reproduced here with a long folder name before the fix; that test stays.

**Not verified:** no person has used the screens; checked by tests and by screenshots made in
this session.

## 8. Known limits after the MVP review (2026-11-10)

Verified again after the fixes: the twelve deliberate bugs from the review were re-applied one
at a time to a copy of the current source and the whole suite was run against each.

- Eleven now fail at least one test (before the review work, one did).
- The twelfth cannot be caught by any test: it removes a call to `legal_revival_pending`, which
  always returns false, because no revival can be pending once no hero is standing. The game
  behaves the same with or without it.

Reported by the review and left as they are, because they are design questions or cannot be
checked here. Each needs an owner decision or a real Windows display.

| Item | State |
|------|-------|
| Intent, reaction and status ids restart in Battle 2 | Event `seq` is continuous (E-05); a log reader must key on `seq` or on battle plus id. |
| Two Scouts can both Disrupt one elite action | The reductions add. The PRD does not say whether the reduction is per intent or per reaction. |
| Interpose is offered when the ally is already at the shield cap | It then costs mana and the charge for no gain. Grounding has a "must change something" guard; Interpose does not. The simulated player takes it anyway (section 7.6). |
| A back-row Squire can never Interpose | By data (`requires_row: front`); the panel says so when it applies. |
| A kept die can be un-kept before a later reroll | "Keep" is a per-reroll mark, as the Keep tooltip states. |
| Key meanings change when the outcome screen appears | `M` toggles animation in battle and is Modify Party on the outcome screen; there is no input pause between them. |
| Class balance | Changed in content 1.3.0 (D-21, section 7.8): every party size is at 74-83% and one composition is at or below 40%. Still weak: five Squires (16%; about 30% when they swap to the Vanguard bench die, section 7.9), and all-Apprentice parties at sizes 3 and 4 (52-56%). Still strong: Scout-heavy parties at sizes 4 and 5 (98-100%). All figures are for the scripted player. |
| Windows display | Never launched on a physical Windows display. Window resize while dragging, font rendering and behaviour at 125% or 150% scaling are unverified. |
| Python install manager | Whether its `py` command downloads a missing Python on request is `<UNKNOWN>` here; the launcher itself never downloads or installs Python. |
| Class Evolution | The first slice (Squire to Guardian, the third battle) is playable behind a gate that is off by default (sections 7.11 to 7.18). Nine of the 14 vocations cannot be played yet. The Guardian's numbers and the third battle's table are defaults measured with a simulated player and await an owner decision. 36 of the 40 acceptance cases run as tests; one question is open (CE-31). No person has played it. Whether the design is balanced or enjoyable is `<UNKNOWN>` until a playable slice exists. On shipped encounters the six advanced vocations (Guardian first) cannot reach their last rank, and Champion, Archmage, Hero and Dragon Knight cannot be trained at all; the validator lists each case. |
| Type checking | Closed on 2026-11-10: `mypy` now covers the whole package (including `ui/`), `tools/` and `tests/` with no findings, and CI runs it that way. The one relaxation is for tests only: `union-attr` is off there, because a test that reads optional engine state fails with an AttributeError when it is None, which is the signal wanted. |
