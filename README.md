# Battle Dice

Single-player, turn-based tactical fantasy dice RPG. This repository is the MVP vertical slice
defined by **BD-PRD-MVP-001 v1.0.0**: configure a party of 1 to 5 heroes, win two scaled battles
by rolling, keeping and rerolling inspectable dice, counter revealed enemy intent with reactions,
and apply one mandatory dice upgrade between the battles.

- **Runtime:** Python 3.15+ (the newest stable release) and [pygame-ce](https://pyga.me/). Runs from source.
- **Rules engine:** pure Python, deterministic, no pygame import. Seeded by the pinned
  `BD-PCG32-v1` generator.
- **Content:** versioned JSON fixtures, schema-validated before a run can start.

## Quick start

Windows (PowerShell), the primary validation environment:

```powershell
py -3.15 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m battle_dice
```

If PowerShell refuses to run `Activate.ps1` ("running scripts is disabled on this system"), skip
that line and call the environment's Python directly: `.\.venv\Scripts\python.exe -m pip install -e ".[dev]"`,
then `.\.venv\Scripts\python.exe -m battle_dice`. Or use the launcher below, which needs no policy change.

macOS / Linux:

```bash
python3.15 -m venv .venv
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
| `--no-animation` | Start with animation off (reduced motion). `M` toggles it during a battle. |
| `--smoke-test` | Hidden self-check: one seeded run with every frame drawn, exit 0 on success. No window opens. |
| `--version` | Print the rules and content versions. |

## Play on Windows

Two routes. Neither has been launched on a physical Windows display by the author of this
repository; both are built and smoke-tested on a Windows CI runner.

**1. Launcher (from a checkout, needs Python 3.15 or newer).** Double-click `Play-BattleDice.cmd`.
It needs no PowerShell policy change. Or, from a PowerShell prompt:

```powershell
.\scripts\Start-BattleDice.ps1
```

If PowerShell answers "running scripts is disabled on this system", use the `.cmd` file, or run
`powershell -ExecutionPolicy Bypass -File .\scripts\Start-BattleDice.ps1` (the bypass applies to
that one process only).

What the launcher does:

- Finds Python 3.15 or newer (3.15 first): the `py` launcher, `python` on PATH, the standard
  install folders, then the registry. If an older Python comes first on PATH it lists what it
  found; pass the interpreter directly with `-Python C:\path\to\python.exe`.
- Creates `.venv` on first run and installs the game. It installs again only when
  `pyproject.toml` changed, the checkout was moved or renamed, or the game is missing from `.venv`.
- Starts the game. It does not download or install Python and changes no machine settings.
- `-Reinstall` rebuilds `.venv`. If no usable Python is found, the existing `.venv` is kept.

Other options: `-Seed 123`, `-Size 960x540`, `-LogDir PATH`, `-NoLaunch`, and `-SmokeTest`
(runs the hidden self-check instead of opening a window).

Tip: keep the checkout outside OneDrive or other synced folders. Syncing the thousands of files
in `.venv` is slow and can lock files while the game is being installed.

**2. Standalone app (no Python needed).** Open the latest successful **Package (Windows)** run
under the repository's Actions tab (you must be signed in to GitHub), download the
`BattleDice-windows-x64` artifact, unzip it once, and run `BattleDice\BattleDice.exe`.

- The app is **unsigned**, so Windows SmartScreen will warn on first run ("More info", then
  "Run anyway").
- Workflow artifacts expire (90 days by default); re-run the workflow to rebuild.
- Event logs go to `%LOCALAPPDATA%\BattleDice\logs`.
- `BattleDice.exe --smoke-test --smoke-out result.txt` plays one hidden run and writes the result,
  which is how the build is verified. The app has no console window, so `--version` and argument
  errors print nothing; an unexpected crash leaves `crash-<time>.txt` in the log folder.

To build it yourself: `python -m pip install ".[package]"`, then
`python -m PyInstaller packaging/battle_dice.spec --noconfirm` (output in `dist\BattleDice`).

## How to play

1. **New Run**, add 1 to 5 heroes (any mix, duplicates allowed), set each hero's row, **Begin**.
2. Combatants act when their gauge reaches 100; speed fills it each tick. The **Next** row
   forecasts the order.
3. On a hero's activation: **Roll**, mark dice to **Keep**, **Reroll** the rest (2 rerolls),
   choose actions and targets, then **Confirm** the whole plan. Unused dice are discarded.
4. On an enemy's activation its action and targets are revealed first. Eligible heroes may react
   in three stages: **Guard**, **Resource**, **Interrupt**. Each reacting hero has one row; click
   the ally to protect on that row. Then the enemy action resolves.
5. Win Battle 1, apply one required **dice upgrade**, optionally swap one die per hero and change rows,
   then win Battle 2.

| Class | Scheduling | Passive | Reaction |
|-------|------------|---------|----------|
| Squire | Single Commitment: one action | Steadfast: +1 shield on every Defense die action (self or ally) | Interpose (Guard): +2 shield to a targeted ally |
| Apprentice | Channel and Cast: Resource, then one other action | Arcane Resonance: +1 spell damage at corruption 3+ | Grounding (Resource): ally -1 corruption, self +1 mana |
| Scout | Exploit Combo: Status, then Attack | Exploit Opening: +1 damage to the combo Attack | Disrupt (Interrupt): cancel a basic action, weaken an elite one |

### Controls

Every screen works with the mouse or with the keyboard alone.

- **Hotkeys** act at once (the table below). **Enter** activates the screen's main button:
  Roll, Confirm, Skip Stage, Begin, Start Battle 2.
- **Tab / Shift+Tab or the arrow keys** move a focus ring from control to control. While a
  control has the ring, Enter or Space activates that control instead. Hotkeys and clicks never
  move the ring; Esc clears it.
- **Esc** goes back or cancels. During a run it opens a menu: resume, controls, or abandon the run.
- Point at or focus a control to read what it does; a disabled control shows why it is unavailable.
- Point at or focus a **unit card** to list that unit in the centre panel: every enemy ability,
  every status and what it does, and a hero's dice, reaction and passive.

| Where | Keys |
|-------|------|
| Main menu | `N` new run, `C` controls, `Q` quit |
| Party setup | `1` `2` `3` add Squire / Apprentice / Scout, `B` or `Enter` begin |
| Hero activation | `R` roll, then reroll unkept; `Z` `X` keep die 1 / 2; `1` `2` plan die 1 / 2; number keys pick a numbered target; `O` swap tie order; `C` clear; `Enter` confirm; `P` pass |
| Reaction window | a row's number uses that hero's reaction; if it asks for an ally, press the ally's number next; `S` skip stage; `A` skip every remaining stage for this enemy action |
| Pacing | `F` fast mode, `Space` step now while resolving, `M` animation on / off |
| During a run | `Esc` menu (cancels a target choice first) |
| Upgrade | `1` `2` `3` select a card, `A` apply, `Enter` start Battle 2 |
| Outcome | `R` retry same party, `M` modify party |

The number row and the numeric keypad both work for number keys.

## Art

Pixel art, 16x16. Characters, enemies, action icons and dungeon tiles come from
[Tiny Dungeon](https://kenney.nl/assets/tiny-dungeon) by Kenney (CC0). The d4 / d6 / d8 dice and
the Weaken and Speed Up icons were drawn for this project. Every file and its source is listed in
`src/battle_dice/ui/assets/manifest.json`; credits are in `src/battle_dice/ui/assets/CREDITS.md`.

- Sprites are scaled by whole numbers only, so pixels stay sharp at any window size.
- Animation (dice tumble, floating numbers, eased HP bars, a pulse on the acting unit) is
  presentation-only: it reads the event log and never changes rules state or seeded replays.
- Text and shape cues are unchanged; art is added to them, never used instead of them.

## Tests and checks

```bash
python -m pytest                 # 860 tests: unit, T01-T16 fixtures, integration, headless UI and graphics, specification
python -m ruff check src tests tools packaging
python -m mypy src/battle_dice tools tests
```

UI tests run headless (`SDL_VIDEODRIVER=dummy` is set by the tests). CI runs the same checks on
Linux and Windows, and fails if line coverage of the rules engine, content loader and random
numbers drops below 90% (measured: 97%; PRD target: at least 80%):

```bash
python -m pytest -W error --cov=battle_dice.core --cov=battle_dice.content --cov=battle_dice.rng --cov=battle_dice.career --cov-fail-under=90
```

| Folder | Contents |
|--------|----------|
| `tests/unit` | RNG golden vectors, content tables and validation, command envelope, timeline, dice, planning, targeting, effects, enemy AI, purity, regression tests from the MVP review, forced-roll tests of the simulated player and the playtest personas |
| `tests/fixtures` | One module per PRD fixture, `test_t01_solo_basic.py` to `test_t16_seed_replay.py` |
| `tests/integration` | Full two-battle runs for every party size, invariants after every command, both outcomes; run-log replay and three runs pinned by hash |
| `tests/ui` | Scripted mouse run at 1280x720 and keyboard-only run at 960x540 through every screen; every documented key; reaction panel, pause menu and readable text at both sizes; sprite manifest, licences, whole-number scaling and animation |
| `tests/spec` | Class Evolution specification (not game code): the vocation catalog against shipped content, the save database script, the example save, the code registry and the 40 acceptance fixtures |

## Headless simulation and replay

```bash
battle-dice-sim --seeds 40 --policy heuristic --jobs 4 --out sim_results/heuristic.json
battle-dice-sim --seeds 20 --policy random
```

The simulator plays complete runs for every class composition of the requested party sizes and
reports wins and losses by party size and composition plus engine transition latency. Its output
is a measurement, not a balance claim: the heuristic policy is a scripted player (its version is
recorded in the output as `policy_version`), not human play. `--content-dir PATH` measures a candidate fixture set
from a folder without touching the shipped content. See `docs/DECISION_LOG.md` section 7 for the
recorded results and the per-party-size table chosen from them.

`python tools/playtest_scenarios.py --seeds 80 --jobs 4` plays twelve scripted personas (a
newcomer, a player who never rerolls, one who never reacts, and so on) and reports what each habit
is worth. `docs/PLAYTEST.md` has the method, the scenarios, the findings and a session script
for testing with a person.

Every finished run writes a JSONL event log: a header line (seed, rules and content identity,
the ordered commands, the final hashes), then one event per line with sequence number, tick,
actor, before/delta/after, RNG stream and draw index. The file alone reproduces the run:

```bash
battle-dice-replay logs/run-123-1.jsonl      # or: python -m battle_dice.replay_cli LOG [LOG ...]
```

It replays the commands on a fresh rules engine and checks the rules version, the content hash,
the event-log hash, the final-state hash and every event line. Exit code 0 means every log
reproduced exactly. Logs written before version 1.1.1 carry no commands and cannot be replayed.

Three fixed-seed runs are pinned by hash in `tests/golden/replay_pin.json`, so unintended drift
between builds or platforms fails a test. After an intended rules or content change, bump the
version and run `python tools/update_replay_pin.py`.

## Project layout

```
src/battle_dice/
  rng.py              BD-PCG32-v1: PCG-XSH-RR 64/32, SHA-256 stream derivation, unbiased bounded draws
  content/            JSON fixtures, JSON Schema, loader with cross-reference validation
    class_evolution/    the vocation catalog and its schema (read only when the gate is on)
    vocations.py        catalog validator; hero builds from the catalog
  features.py         feature gates: launch settings, all off by default
  career/             Class Evolution progression: the rules (claims, vocation changes, mastery, skills,
                      dice, discovery) and the SQLite save store (not called by the game yet)
  core/               pure rules engine (no pygame)
    engine.py           single mutation path: transactional, idempotent command handling
    timeline.py         speed-driven action-gauge scheduler
    build.py            a hero's class data for one run (the only place the rules read it from)
    schedule.py         action schedules as ordered slots
    planning.py         plan validation, mana projection, legal-plan enumeration
    targeting.py        formation rules, offensive retarget, defensive cancel
    effects.py          damage, shields, statuses, mana, corruption, revival
    enemy_ai.py         priority tiers, seeded weighted choice, target selection
    reactions.py        Guard / Resource / Interrupt stages, elite resistance
    progression.py      encounters, recovery, upgrade offers, bench swap
    view.py             read-only snapshots and generated rules text
    replay.py           export and verify deterministic replays
  app/controller.py   application state machine (menus, drafts, pause menu, feedback), no pygame
  replay_cli.py       battle-dice-replay: verify finished-run logs
  sim/                heuristic and random policies, seed-matrix runner
  ui/                 pygame-ce presentation: toolkit, screens, app shell
  ui/assets/          16x16 pixel-art sprites, manifest.json, CREDITS.md
tools/                build_sprites.py: rebuilds the sprite set from Kenney's Tiny Dungeon pack
                      update_replay_pin.py: regenerates the pinned-run hashes after an intended change
scripts/              Start-BattleDice.ps1 launcher (Windows)
packaging/            PyInstaller entry point and spec for the standalone app
                      class_evolution/: command lines for the catalog validator and the save-database check
docs/DECISION_LOG.md  interpretations, authored catalogs, deviations, measured evidence
docs/class_evolution/ Class Evolution FDD v0.2: approved design; being built behind a gate that is off
```

Changing balance means editing `src/battle_dice/content/data/*.json` (bump `content_version`,
run `python tools/update_replay_pin.py`, rerun the tests, add a decision-log entry). No numeric balance value is hard-coded in the engine.

## Class Evolution (in development, not in the game)

`docs/class_evolution/FDD_v0.2.md` is the approved design for class evolution: 14 vocations,
mastery, unlocks and a save database. **It is not playable yet.** The feature gate
`class_evolution_v1` is off by default, and with it off the game is byte for byte unchanged (the
replay pin proves it on every change). The specification is executable and checked in CI:

```
python tools/class_evolution/validate_catalog.py      # the vocation catalog against shipped content
python tools/class_evolution/check_persistence.py     # the save database script and the example save
```

Both print `OK`. The first also lists, as warnings, every rank and vocation that cannot be reached
on shipped content yet. The build follows the phases in section 9 of the document. Phases 1 to 3
are done: the rules can run an evolved hero, decide claims, vocation changes, mastery, skills and
dice, and save all of it to a file. No screen offers any of it yet, and the game itself does not
open a save file yet. Of the 40 acceptance cases 35 run as tests; the other five wait for Phase 4
or a later wave (`docs/DECISION_LOG.md`, section 7.14).

The gate is a launch setting. Switching it on changes nothing you can see today; it only hands the
vocation catalog to the rules engine, and the main menu's status bar says so:

```
python -m battle_dice --feature class_evolution_v1
```

The environment variable `BATTLE_DICE_FEATURES=class_evolution_v1` does the same.

## Scope

In scope: the two-battle loop, three classes, three enemy archetypes, d4 / d6 / d8 dice, the
action-gauge timeline, staged reactions, Poison, Weaken, mana, corruption, shields, downing and
explicit revival, recovery, one mandatory upgrade and one optional swap per hero.

Deferred: save and resume across restarts, d10 / d12 / d20, class unlocks and levelling,
procedural encounters, signed installers and published releases, controller support, audio, and a
pixel-art reskin of panels and buttons.
