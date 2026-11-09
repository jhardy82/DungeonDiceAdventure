# Battle Dice MVP: Decision Log

Contract: **BD-PRD-MVP-001 v1.0.0** (2026-11-09). Rules version `1.0.0`, content version `1.0.0`,
RNG `BD-PCG32-v1`.

This log records (1) how gaps and contradictions between *delegated default* (DD) statements in
the PRD were resolved, (2) implementation choices the PRD left open, and (3) measured evidence.
No **approved (A)** requirement was altered. Every DD numeric value is implemented exactly as
authored and lives in `src/battle_dice/content/data/*.json`, not in engine code.

Changing any entry below is a content/rules change: bump the version, rerun the acceptance
tests, and add an entry here.

## 1. Interpretations of the PRD

| ID | PRD area | Decision | Reason |
|----|----------|----------|--------|
| D-01 | 8.1 / 8.2 Steadfast | +1 shield only when the Squire's own Defense **die** action targets **itself**. Guard on an ally and the Interpose reaction get no bonus. | The face table ("+1 if self") is more specific than the prose. Narrower reading. |
| D-02 | 5.4 reroll | A reroll rerolls **all** unkept dice. | Q71 is approved (A) and wins over the "selected unkept die" sentence. |
| D-03 | 5.5 Channel and Cast | The second action must be a **non-Resource** category (Attack, Defense, Healing, Status). Resource + Resource is not a legal two-action plan. | "Any other legal category" read as "other than Resource". Narrower reading. |
| D-04 | 9.2 / 9.3 stack cap | At the cap, the oldest stack is refreshed to the applied duration **only if that raises it**, and the refreshed stack then counts as the newest. | Makes "refresh the oldest" rotate through stacks instead of touching the same one forever. |
| D-05 | 14.4 "unrefreshable cap" | A status application is illegal for the AI only when the target is at the stack cap **and** every stack already has at least the applied duration. | Follows from D-04: that is exactly when applying changes nothing. |
| D-06 | 14.4 priority 20 | Granted when at least one eligible target has **zero** stacks of the status the action applies (and for War Cry while no speed modifier is active). | The PRD says "its proposed target" but targets are chosen after the action; this is the equivalent test. |
| D-07 | 6.2 / 9.2 Poison at start | If Poison downs or defeats the actor at activation start, the activation ends immediately. A downed hero's status durations are **not** decremented for that activation. | 10: "do not tick activation-based effects while downed". |
| D-08 | 12.1 enemy ranges | Slash, Strike and **Dirty Trick** are melee. Shadow Bolt, Poison Dart, Corrupt Mark and Blight Wave are ranged. | The PRD gives ranges only for damage. Dirty Trick is a Goblin (front-row skirmisher) ability; treating it as melee keeps back-row heroes protected, the narrower reading. |
| D-09 | 7.3 Interpose | The Squire may choose **itself** when it is one of the targeted heroes. | Otherwise a solo Squire could never demonstrate the Guard archetype (12.2). |
| D-10 | 11.2 optional swap | At most **one swap per run** (party-wide), value `max_swaps_per_run` in `balance.json`. | Literal reading of "swap zero or one equipped die". |
| D-11 | 11.2 Sharpen | Each die offers Sharpen on one face chosen by the rewards stream. Poison/Weaken faces gain +1 duration, capped at the face power cap (5). | The PRD does not say which face; a deterministic seeded choice keeps "three cards". |
| D-12 | 11.2 Imbue | Imbue may replace **any** face (including a Blank); the face index comes from the rewards stream. | "Replace one face". |
| D-13 | 9.6 Speed Up | Re-applying while active refreshes the duration; it never stacks. The AI treats a repeat as illegal (14.4). | "Stacking is not used in the MVP". |
| D-14 | 12.1 Corrupt Mark | Legal even if every target is at the corruption cap; the AI only *prefers* targets with room. | 14.4 lists it as a preference, not a legality rule. |
| D-15 | 5.7 area effects | At resolution an area action hits the committed targets that are still eligible; if none remain it is cancelled. | Consistent with "committed targets" plus fallback. |
| D-16 | 7.2 cooldowns | No enemy ability cooldowns are authored, so none are implemented. | The PRD mentions cooldowns only as a general possibility. Deferred (F). |
| D-17 | 9.4 enemy mana | Mana costs are charged to heroes only. Enemies have no mana pool. | 9.4: "Enemies in the initial fixtures do not use player mana pools". |

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
| E-10 | The golden RNG vectors in `tests/golden/rng_vectors.json` are locked to rules version 1.0.0. The raw generator is also checked against the published PCG32 reference output (seed 42, sequence 54). |

## 4. Deviations from the plan

| ID | Deviation |
|----|-----------|
| V-01 | The PRD text is **not** vendored into `docs/`. It was supplied as pasted text with tab-separated tables, and a retyped copy could not be guaranteed byte-faithful to the owner's canonical document. The owner should add the canonical file as `docs/BD-PRD-MVP-001.md`. |
| V-02 | The rules engine orchestrator (`core/engine.py`) is committed with WP-06, where all of its dependencies exist, rather than as a skeleton in WP-02. Unit tests that need the engine land with WP-06; the T01-T16 fixtures and integration tests land with WP-08. |

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

## 6. Acceptance evidence

268 automated tests pass on the reference environment (Linux container, Python 3.12.3,
pygame-ce 2.5.8): 144 unit, 78 fixture, 36 integration, 10 headless UI. `ruff` and `mypy` are clean.

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

Command: `battle-dice-sim --seeds 20 --policy <policy>`. Seeds 0-19, every class composition for
each party size (55 compositions, 1,100 runs per policy), heroes in their suggested rows,
content 1.0.0.

| Party size | Runs | Heuristic policy wins | Random policy wins |
|-----------:|-----:|----------------------:|-------------------:|
| 1 | 60 | 60 (100.0%) | 41 (68.3%) |
| 2 | 120 | 119 (99.2%) | 58 (48.3%) |
| 3 | 200 | 187 (93.5%) | 103 (51.5%) |
| 4 | 300 | 293 (97.7%) | 159 (53.0%) |
| 5 | 420 | 407 (96.9%) | 212 (50.5%) |

- **Heuristic policy:** keeps the dice in its best-scoring plan, rerolls the rest, always reacts
  when it can. **Random policy:** uniformly random legal decisions.
- **Reading:** legal parties of every size can win under informed play, and uninformed play loses
  about half the time, so losses are possible. This is two scripted policies over 20 seeds, not
  human playtesting.
- **Latency:** 791,204 engine transitions, median 0.25 ms, p95 0.45 ms on the reference
  container, against the proposed target of under 100 ms. The figure includes the policy's own
  decision time averaged over the commands it sent, so the engine alone is faster. It was not
  measured on the Windows target machine.

### Observations for the owner (no fixture was changed)

1. **Solo runs never lost to the heuristic in this sample (60 of 60).** A lone hero faces one
   Goblin and then a reduced Captain, and can out-shield or out-pace their damage.
2. **The exact AI policy in 14.4 front-loads setup actions.** Priority 20 beats priority 10, so a
   Goblin uses Dirty Trick whenever a reachable hero has no Weaken, a Hex Adept uses Poison Dart
   whenever a hero has no Poison, and the Captain opens with War Cry. Enemy damage in the first
   activations is therefore low. This is implemented exactly as specified.
3. **Disrupt cancels a basic action outright for 1 mana once per Scout activation**, and the
   Scout is the fastest unit, which removes a large share of Battle 1 enemy actions.

If a tighter challenge is wanted, candidates to evaluate with the simulator are the priority-20
rule, Disrupt's cost, and the solo encounter stats. Each would be a versioned content or rules
change with the acceptance tests rerun.
