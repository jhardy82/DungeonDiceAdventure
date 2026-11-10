# Battle Dice MVP: Decision Log

Contract: **BD-PRD-MVP-001 v1.0.0** (2026-11-09). Rules version `1.1.0`, content version `1.2.0`,
RNG `BD-PCG32-v1`.

This log records (1) how gaps and contradictions between *delegated default* (DD) statements in
the PRD were resolved, (2) implementation choices the PRD left open, and (3) measured evidence.
No **approved (A)** requirement was altered. Every numeric value lives in
`src/battle_dice/content/data/*.json`, not in engine code. DD values are as authored in the PRD
except where an owner decision below says otherwise (D-01, D-08, D-10, D-18, D-19).

Changing any entry below is a content/rules change: bump the version, rerun the acceptance
tests, and add an entry here.

## 1. Interpretations of the PRD

| ID | PRD area | Decision | Reason |
|----|----------|----------|--------|
| D-01 | 8.1 / 8.2 Steadfast | **Owner decision, 2026-11-09 (rules 1.1.0):** +1 shield on every Defense **die** action the Squire takes, on itself or an ally. The Interpose reaction is not a die action and gets no bonus. | Supersedes the 1.0.0 reading (self only). The PRD prose says "its own selected Defense die actions (not to Guard reactions)"; the owner chose that broader reading over the face table's "if self". |
| D-02 | 5.4 reroll | A reroll rerolls **all** unkept dice. | Q71 is approved (A) and wins over the "selected unkept die" sentence. |
| D-03 | 5.5 Channel and Cast | The second action must be a **non-Resource** category (Attack, Defense, Healing, Status). Resource + Resource is not a legal two-action plan. | "Any other legal category" read as "other than Resource". Narrower reading. |
| D-04 | 9.2 / 9.3 stack cap | At the cap, the oldest stack is refreshed to the applied duration **only if that raises it**, and the refreshed stack then counts as the newest. | Makes "refresh the oldest" rotate through stacks instead of touching the same one forever. |
| D-05 | 14.4 "unrefreshable cap" | A status application is illegal for the AI only when the target is at the stack cap **and** every stack already has at least the applied duration. | Follows from D-04: that is exactly when applying changes nothing. |
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
| D-16 | 7.2 cooldowns | No enemy ability cooldowns are authored, so none are implemented. | The PRD mentions cooldowns only as a general possibility. Deferred (F). |
| D-17 | 9.4 enemy mana | Mana costs are charged to heroes only. Enemies have no mana pool. | 9.4: "Enemies in the initial fixtures do not use player mana pools". |
| D-18 | 13 runtime | **Python 3.15 or newer is required** (`requires-python = ">=3.15"`), replacing the PRD's delegated default of "Python 3.12+". CI, the lint target and the type-check target are pinned to the 3.15 line, so new 3.15.x patches are picked up but 3.16 is not adopted automatically. | Owner direction (2026-11-09): use the newest stable Python. 3.15.2 was the newest stable build in GitHub's `actions/python-versions` manifest on that date; 3.16 was alpha only. |
| D-19 | 12.2 encounter scaling | **Owner decision, 2026-11-09 (content 1.2.0):** the per-party-size encounter table is retuned so the scripted informed player wins 70-85% of runs at every party size. See section 7.1 for the exact changes and measurements. | The PRD calls the 12.2 tables "initial balance fixtures" to be adjusted after simulation. Informed play won 95-100% before the change. |

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
| E-10 | The golden RNG vectors in `tests/golden/rng_vectors.json` are locked to the current rules version (label updated to 1.1.0; the vectors are unchanged because the RNG algorithm is unchanged). The raw generator is also checked against the published PCG32 reference output (seed 42, sequence 54). |
| E-11 | Rule fixtures (T01-T13, T15 and the engine unit tests) run on the shipped rules data with the encounter table frozen at its rules-1.1.0 values (`tests/golden/encounters_mechanics.json`), so a balance retune does not rewrite tests about rules. The shipped table itself is asserted exactly in `unit/test_content.py` and `fixtures/test_t14_party_scaling.py`, and full-run, replay, simulator and UI tests use the shipped content. |
| E-12 | **Owner direction, 2026-11-10: use the most updated Node.** The game has no Node code; Node is only the runtime of the GitHub Actions used in CI. They are pinned to their newest majors, all of which run on Node 24: `actions/checkout@v7`, `actions/setup-python@v7`, `actions/upload-artifact@v7` (previously `v4` / `v5` / `v4` on Node 20, end of life 2026-04-30). Node 26 is the newest Node LTS, but no released major of these actions declares a `node26` runtime, so Node 24 is the newest the project can select. |

## 4. Deviations from the plan

| ID | Deviation |
|----|-----------|
| V-01 | The PRD text is **not** vendored into `docs/`. It was supplied as pasted text with tab-separated tables, and a retyped copy could not be guaranteed byte-faithful to the owner's canonical document. The owner should add the canonical file as `docs/BD-PRD-MVP-001.md`. |
| V-02 | The rules engine orchestrator (`core/engine.py`) is committed with WP-06, where all of its dependencies exist, rather than as a skeleton in WP-02. Unit tests that need the engine land with WP-06; the T01-T16 fixtures and integration tests land with WP-08. |
| V-03 | **Scope added by the owner, 2026-11-09:** Windows packaging, which the PRD lists as outside the MVP. Two routes ship: a source launcher (`scripts/Start-BattleDice.ps1`, `Play-BattleDice.cmd`) and a PyInstaller one-folder build produced by the `Package (Windows)` workflow. Not included: code signing, an installer, or published releases. The app is unsigned and is distributed only as a workflow artifact. |
| V-04 | **Scope added by the owner, 2026-11-09:** a pixel-art graphics pass with animation, using Kenney CC0 packs. The PRD lists original art as not required. Characters, enemies, action icons and dungeon tiles are from Kenney's Tiny Dungeon (CC0). The pack has no goblin and no polyhedral dice, so the Goblin is a recoloured Tiny Dungeon tile and the d4 / d6 / d8 dice plus the Weaken and Speed Up icons are original. Panels and buttons keep the existing flat style; a pixel-art UI reskin is not included. |

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
| U-08 | `--smoke-test` plays one seeded run through the real UI with no window and exits 0 on success. It is the verification step for packaged builds: it proves the bundled content, pygame-ce and fonts load inside the frozen app. |
| U-09 | A packaged (frozen) build writes event logs to `%LOCALAPPDATA%\\BattleDice\\logs`, because its own folder may be read-only. From source the default stays `./logs`. |
| U-10 | Sprites are 16x16 and are scaled by whole numbers only (nearest-neighbour); panels and text keep the fractional UI scale. Card and planner slots are sized so characters draw at 2x at both 960x540 and 1280x720. |
| U-11 | Art lives in `ui/assets` with a manifest (file, source pack, tile number, any modification) and a credits file. The mapping from class or enemy to sprite is presentation data, not rules content, so the content hash and replays do not change. Tests fail if a file is unlisted, uncredited, or not CC0. |
| U-12 | Animation reads the engine's event log and frame time only. It never calls the engine or its random streams (covered by a test). `M` and `--no-animation` turn it off; fast mode shortens it. The dice tumble cycles through the die's own faces by elapsed time and then shows the real result. |
| U-13 | A missing sprite draws a visible placeholder box and is recorded, never raising. The smoke test fails if any sprite is missing, so packaged builds prove the art was bundled. |

## 6. Acceptance evidence

295 automated tests pass on the reference environment (Linux container, Python 3.15.2,
pygame-ce 2.5.8, jsonschema 4.26.0, pytest 9.2.0): 148 unit, 78 fixture, 37 integration,
32 headless UI and graphics. `ruff` 0.17.4 and `mypy` 2.4.1 are clean with their 3.15 targets.

Before the move to 3.15 the same suite also passed on Python 3.12.3 and 3.13; those versions are
no longer installable because of the 3.15 floor (an install attempt on 3.12.3 is refused with
"does not satisfy Python>=3.15").

Dependency minimums were raised to the versions verified on 3.15: `pygame-ce>=2.5.8` (its
`cp315` wheels include `win_amd64`), `ruff>=0.17.4`, `mypy>=2.4`.

| Criterion | Evidence |
|-----------|----------|
| AC-01 party 1-5, duplicates, rows | `unit/test_commands.py` (party size and row tests) |
| AC-02 exact dice and stats, distinct scheduling | `unit/test_content.py`, `fixtures/test_t02_three_class_combo.py` |
| AC-03 faces, frequencies, probabilities, seeded rolls | `unit/test_content.py`, `unit/test_dice_and_planning.py` |
| AC-04 keep / reroll | `unit/test_dice_and_planning.py`, `unit/test_commands.py` |
| AC-05 class caps, plan lock, discard | `unit/test_dice_and_planning.py` |
| AC-06 deterministic timeline, speed change keeps gauge | `unit/test_timeline.py`, `fixtures/test_t11_speed_reorder.py` |
| AC-07 action speed orders standard actions only | `unit/test_dice_and_planning.py` (free-policy tests) |
| AC-08 formation targeting | `unit/test_targeting_effects.py` |
| AC-09 retarget and cancel | `fixtures/test_t07_target_fallback.py` |
| AC-10 intent reveal and stage windows | `unit/test_enemy_ai.py`, `fixtures/test_t05_reaction_stages.py` |
| AC-11 Guard, Resource, Interrupt, charges, elite resistance | `fixtures/test_t05_reaction_stages.py`, `fixtures/test_t06_interrupt_resistance.py` |
| AC-12 shields, Poison, Weaken, mana, corruption | `unit/test_targeting_effects.py`, `fixtures/test_t08_poison_lethal.py`, `fixtures/test_t10_corruption_tradeoff.py` |
| AC-13 revival and final-party-down defeat | `fixtures/test_t09_revival.py`, `fixtures/test_t15_terminal_edges.py` |
| AC-14 both battles per party size, mandatory upgrade | `fixtures/test_t14_party_scaling.py`, `fixtures/test_t13_upgrade_swap.py` |
| AC-15 bench swap keeps the upgrade | `fixtures/test_t13_upgrade_swap.py` |
| AC-16 recovery, persistence, restart | `fixtures/test_t12_two_battle_persistence.py`, `fixtures/test_t13_upgrade_swap.py` |
| AC-17 both outcomes, no soft locks or negative resources | `integration/test_full_runs.py` (invariants checked after every command) |
| AC-18 seed replay | `fixtures/test_t16_seed_replay.py` |
| AC-19 mouse and keyboard, supported resolutions, disabled reasons | `ui/test_ui_smoke.py` |

Not verified here: the game has not been launched on a physical Windows display. The engine,
content and headless UI tests run on a Windows CI runner; interactive feel, font rendering and
window behaviour on Windows remain to be confirmed by the owner.

## 7. Measured balance and latency (not balance claims)

Command: `battle-dice-sim --seeds 40 --policy <policy> --jobs 4`. Seeds 0-39, every class
composition for each party size (55 compositions, 2,200 runs per policy), heroes in their
suggested rows. **Heuristic policy:** keeps the dice in its best-scoring plan, rerolls the rest,
always reacts when it can. **Random policy:** uniformly random legal decisions. Both are scripted
players, not human playtesting.

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

2,298,146 engine transitions in the 1.2.0 heuristic run: median 0.14 ms, p95 0.29 ms on the
reference container, against the proposed target of under 100 ms. The figure includes the
policy's own decision time averaged over the commands it sent. It was not measured on the
Windows target machine.

### 7.5 History

On rules 1.0.0 (20 seeds) the heuristic won 60/60, 119/120, 187/200, 293/300 and 407/420 for
sizes 1-5 and the random policy won 41/60, 58/120, 103/200, 159/300 and 212/420.
