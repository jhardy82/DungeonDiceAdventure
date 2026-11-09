# Battle Dice

Single-player, turn-based tactical fantasy dice RPG. This repository is the MVP vertical slice
defined by **BD-PRD-MVP-001 v1.0.0**: configure a party of 1 to 5 heroes, win two scaled battles
by rolling, keeping and rerolling inspectable dice, counter revealed enemy intent with reactions,
and apply one mandatory dice upgrade between the battles.

- **Runtime:** Python 3.12+ and [pygame-ce](https://pyga.me/). Runs from source.
- **Rules engine:** pure Python, deterministic, no pygame import. Seeded by the pinned
  `BD-PCG32-v1` generator.
- **Content:** versioned JSON fixtures, schema-validated before a run can start.

## Quick start

Windows (PowerShell), the primary validation environment:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m battle_dice
```

macOS / Linux:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m battle_dice
```

Options:

| Option | Meaning |
|--------|---------|
| `--seed N` | Use root seed `N` for every run, so dice and enemy choices repeat exactly. |
| `--size 1280x720` | Window size. Minimum supported is `960x540`; the window is resizable. |
| `--log-dir PATH` | Folder for JSONL event logs (default `./logs`, or `BATTLE_DICE_LOG_DIR`). |

## How to play

1. **New Run**, add 1 to 5 heroes (any mix, duplicates allowed), set each hero's row, **Begin**.
2. Combatants act when their gauge reaches 100; speed fills it each tick. The **Next** row
   forecasts the order.
3. On a hero's activation: **Roll**, mark dice to **Keep**, **Reroll** the rest (2 rerolls),
   choose actions and targets, then **Confirm** the whole plan. Unused dice are discarded.
4. On an enemy's activation its action and targets are revealed first. Eligible heroes may react
   in three stages: **Guard**, **Resource**, **Interrupt**. Then the enemy action resolves.
5. Win Battle 1, apply one required **dice upgrade**, optionally swap one die and change rows,
   then win Battle 2.

| Class | Scheduling | Passive | Reaction |
|-------|------------|---------|----------|
| Squire | Single Commitment: one action | Steadfast: +1 shield on own Defense die targeting itself | Interpose (Guard): +2 shield to a targeted ally |
| Apprentice | Channel and Cast: Resource, then one other action | Arcane Resonance: +1 spell damage at corruption 3+ | Grounding (Resource): ally -1 corruption, self +1 mana |
| Scout | Exploit Combo: Status, then Attack | Exploit Opening: +1 damage to the combo Attack | Disrupt (Interrupt): cancel a basic action, weaken an elite one |

### Controls

Every screen works with the mouse or with the keyboard alone. `Tab` / `Shift+Tab` or the arrow
keys move focus, `Enter` or `Space` activates, `Esc` goes back or cancels. Hover or focus a
control to read what it does; a disabled control shows why it is unavailable.

| Where | Keys |
|-------|------|
| Main menu | `N` new run, `C` controls, `Q` quit |
| Party setup | `1` `2` `3` add Squire / Apprentice / Scout, `B` begin |
| Hero activation | `R` roll, then reroll unkept; `Z` `X` keep die 1 / 2; `1` `2` plan die 1 / 2; number keys pick a numbered target; `O` swap tie order; `C` clear; `Enter` confirm; `P` pass |
| Reaction window | number keys use a listed reaction, `S` skip stage |
| Pacing | `F` fast mode, `Space` (nothing focused) step now |
| Upgrade | `1` `2` `3` select a card, `A` apply, `Enter` start Battle 2 |
| Outcome | `R` retry same party, `M` modify party |

## Tests and checks

```bash
python -m pytest                 # 268 tests: unit, T01-T16 fixtures, integration, headless UI
python -m ruff check src tests
python -m mypy src/battle_dice/core src/battle_dice/rng.py src/battle_dice/content src/battle_dice/sim src/battle_dice/app
```

UI tests run headless (`SDL_VIDEODRIVER=dummy` is set by the tests). CI runs the same three
commands on Linux and Windows.

| Folder | Contents |
|--------|----------|
| `tests/unit` | RNG golden vectors, content tables, command envelope, timeline, dice, planning, targeting, effects, enemy AI, purity |
| `tests/fixtures` | One module per PRD fixture, `test_t01_solo_basic.py` to `test_t16_seed_replay.py` |
| `tests/integration` | Full two-battle runs for every party size, invariants after every command, both outcomes |
| `tests/ui` | Scripted mouse run at 1280x720 and keyboard-only run at 960x540 through every screen |

## Headless simulation and replay

```bash
battle-dice-sim --seeds 20 --policy heuristic --out sim_results/heuristic.json
battle-dice-sim --seeds 20 --policy random
```

The simulator plays complete runs for every class composition of the requested party sizes and
reports wins and losses by party size and composition plus engine transition latency. Its output
is a measurement, not a balance claim. See `docs/DECISION_LOG.md` for recorded results.

Every finished run writes a JSONL event log (header line, then one event per line with sequence
number, tick, actor, before/delta/after, RNG stream and draw index). A run is fully reproducible
from its seed, content version and ordered command log; see `battle_dice.core.replay`.

## Project layout

```
src/battle_dice/
  rng.py              BD-PCG32-v1: PCG-XSH-RR 64/32, SHA-256 stream derivation, unbiased bounded draws
  content/            JSON fixtures, JSON Schema, loader with cross-reference validation
  core/               pure rules engine (no pygame)
    engine.py           single mutation path: transactional, idempotent command handling
    timeline.py         speed-driven action-gauge scheduler
    planning.py         class scheduling, plan validation, action-speed order
    targeting.py        formation rules, offensive retarget, defensive cancel
    effects.py          damage, shields, statuses, mana, corruption, revival
    enemy_ai.py         priority tiers, seeded weighted choice, target selection
    reactions.py        Guard / Resource / Interrupt stages, elite resistance
    progression.py      encounters, recovery, upgrade offers, bench swap
    view.py             read-only snapshots and generated rules text
    replay.py           export and verify deterministic replays
  app/controller.py   application state machine (menus, drafts, feedback), no pygame
  sim/                heuristic and random policies, seed-matrix runner
  ui/                 pygame-ce presentation: toolkit, screens, app shell
docs/DECISION_LOG.md  interpretations, authored catalogs, deviations, measured evidence
```

Changing balance means editing `src/battle_dice/content/data/*.json` (bump `content_version`,
rerun the tests, add a decision-log entry). No numeric balance value is hard-coded in the engine.

## Scope

In scope: the two-battle loop, three classes, three enemy archetypes, d4 / d6 / d8 dice, the
action-gauge timeline, staged reactions, Poison, Weaken, mana, corruption, shields, downing and
explicit revival, recovery, one mandatory upgrade and one optional swap.

Deferred: save and resume across restarts, d10 / d12 / d20, class unlocks and levelling,
procedural encounters, packaged releases, controller support, art and audio.
