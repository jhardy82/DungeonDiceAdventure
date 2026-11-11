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

Ten fixtures still need a decision (CE-09, 18, 25, 29, 30, 31, 32, 35, 36, 40); each is settled in
the phase that first needs it. The three codes v0.2 proposed are marked approved in the registry.

### 7.12 Class Evolution Phase 2: progression rules in memory (2026-11-11)

**What was built** (`src/battle_dice/career/`): the rules that decide claims, vocation changes,
previews, mastery awards, inherited skills and discovery. The state is held in memory; nothing is
saved and nothing in the game calls it yet. It follows the rules engine's contract: a rejected
command returns one code and changes nothing, a repeated command id returns the stored result, and
every change runs on a copy that replaces the state only on success.

**Gate: the fully specified rule fixtures pass as executable tests.**

| Check | Result |
|-------|--------|
| Acceptance fixtures run against the rules (`tests/spec/test_class_evolution_rules.py`) | 27 of 27 pass |
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

**Not in Phase 2:** saving (Phase 3); owned dice, item grants and quest completion as events,
the screens, and the rules engine calling these rules (Phase 4). Discovery signals are applied
when given; nothing raises them automatically yet.

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
| Class Evolution | Specification only (section 7.10). Whether the design is balanced or enjoyable is `<UNKNOWN>` until a playable slice exists. On shipped encounters the six advanced vocations (Guardian first) cannot reach their last rank, and Champion, Archmage, Hero and Dragon Knight cannot be trained at all; the validator lists each case. |
| Type checking | Closed on 2026-11-10: `mypy` now covers the whole package (including `ui/`), `tools/` and `tests/` with no findings, and CI runs it that way. The one relaxation is for tests only: `union-attr` is off there, because a test that reads optional engine state fails with an AttributeError when it is None, which is the signal wanted. |
