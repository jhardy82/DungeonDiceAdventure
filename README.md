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
| `--smoke-test` | Hidden self-check: one seeded run with every frame drawn, exit 0 on success. No window opens. With `--feature class_evolution_v1` it also plays a run with a Guardian from the vocation catalog. |
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
   More heroes meet more and tougher enemies. A melee attack must hit the front row while anyone
   stands there. A class's sheet shows while its add button is pointed at or has the focus ring.
2. Combatants act when their gauge reaches 100; speed fills it each tick. The **Next** row
   forecasts the order.
3. On a hero's activation: **Roll**, mark dice to **Keep**, **Reroll** the rest (2 rerolls),
   choose actions and targets, then **Confirm** the whole plan. Unused dice are discarded.
4. On an enemy's activation its action and targets are revealed first. Eligible heroes may react
   in three stages: **Guard**, **Resource**, **Interrupt**. Each reacting hero has one row; click
   the ally to protect on that row. Then the enemy action resolves.
5. Win Battle 1, apply one required **dice upgrade**, optionally swap one die per hero and change rows,
   then win Battle 2. Every upgrade card changes the die: a card that would only rename a face
   is not offered.

| Class | Scheduling | Passive | Reaction |
|-------|------------|---------|----------|
| Squire | Single Commitment: one action | Steadfast: +1 shield on every Defense die action (self or ally) | Interpose (Guard): +2 shield to a targeted ally |
| Apprentice | Channel and Cast: Resource, then one other action | Arcane Resonance: +1 spell damage at corruption 3+ | Grounding (Resource): ally -1 corruption, self +1 mana |
| Scout | Exploit Combo: Status, then Attack | Exploit Opening: +1 damage to the combo Attack | Disrupt (Interrupt): cancel a basic action, weaken an elite one |

- A yellow **Now ...** line under a die face or a planned action gives the amount that will
  really happen where something changes the printed one: Weaken, a class bonus, or a maximum.
- **Corruption (CR):** from CR 5 on, a hero loses 1 HP at the end of each of its own
  activations (shields do not help). The plan says so before you confirm, and a "!" marks it on
  the hero's card.
- **Enemies** first take an ability that would bring a hero down, then one that puts a status
  on a hero who does not have it. Among the rest, a higher weight is chosen more often.

### Controls

Every screen works with the mouse or with the keyboard alone.

- **Hotkeys** act at once (the table below). **Enter** activates the screen's main button:
  Roll, Confirm, Skip Stage, Begin, Start Battle 2.
- **Tab / Shift+Tab or the arrow keys** move a focus ring from control to control. While a
  control has the ring, Enter or Space activates that control instead. A hotkey or a click takes
  the ring away.
- **Esc** goes back or cancels. During a run it opens a menu: resume, controls, settings, or
  abandon the run.
- **What cannot be undone is asked for once more:** abandoning a run, Retry after a run and a
  bench swap need a second press. Deleting the saved profile is confirmed by a separate button.
- **A number key plans a die and never takes it out of the plan.** Removing is the die's Remove
  button, or `C`. A single legal enemy is aimed at without asking, and the status line says so.
  An ally's number key is its place in the party ("Scout 2" is `2`).
- Point at or focus a control to read what it does; a disabled control shows why it is unavailable.
- Point at or focus a **unit card** to list that unit in the centre panel: every enemy ability,
  every status and what it does, and a hero's dice, reaction and passive.

| Where | Keys |
|-------|------|
| Main menu | `N` new run, `C` controls, `Q` quit |
| Party setup | `1` `2` `3` add Squire / Apprentice / Scout, `B` or `Enter` begin, `D` dice seed (typed, or clicked on a number pad) |
| Hero activation | `R` roll, then reroll unkept; `Z` `X` keep die 1 / 2; `1` `2` plan die 1 / 2; number keys pick a numbered target; `O` swap tie order; `C` clear; `Enter` confirm; `P` pass |
| Reaction window | a row's number uses that hero's reaction; if it asks for an ally, press the ally's number next; `S` skip stage; `A` skip every remaining stage for this enemy action |
| Pacing | `F` battle speed, `M` motion on / off (both also buttons at the top of a battle, and both kept as settings); `Space` step now while resolving |
| During a run | `Esc` menu (cancels a target choice first) |
| Upgrade | `1` `2` `3` select a card, `A` apply, `Enter` start Battle 2 |
| Outcome | `R` retry same party (press twice), `M` modify party |

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
python -m pytest                 # 1328 tests: unit, T01-T16 fixtures, integration, headless UI and graphics, specification
python -m ruff check src tests tools packaging
python -m mypy src/battle_dice tools tests
```

**Playtesting step by step.** `tools/playtest_screen.py` plays the real screens without a window:
it applies key presses and clicks, prints the screen as text with every control and its state,
and saves a screenshot. A session replays exactly, so a finding comes with the steps that
reproduce it. The guide and the roles for playtesters are in `.claude/skills/playtest/`.

```bash
PYTHONPATH=src python tools/playtest_screen.py --session /tmp/session start
PYTHONPATH=src python tools/playtest_screen.py --session /tmp/session do key:n click:add:squire key:b
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
reproduced exactly. A log replays only under the rules version that wrote it (now 1.1.2); logs
written before version 1.1.1 carry no commands and cannot be replayed at all.

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

## Class Evolution (playable behind a switch, off by default)

`docs/class_evolution/FDD_v0.2.md` is the approved design for class evolution: 14 vocations,
mastery, unlocks and a save file. Its **first slice is playable**: a Squire can master its class,
become a Guardian, and fight an optional third, harder battle. It is behind the feature gate
`class_evolution_v1`, which is **off by default**. With the gate off the game is byte for byte
unchanged (the replay pin proves it on every change) and no save file is made.

To play it, either switch it on inside the game (**Main menu, Settings, Class Evolution**), or
start the game with it on:

```
python -m battle_dice --feature class_evolution_v1
```

The environment variable `BATTLE_DICE_FEATURES=class_evolution_v1` does the same. The main
menu's status bar shows that the gate is on.

What changes with the gate on:

- **Party setup** shows your saved heroes. Recruit a Squire, an Apprentice or a Scout (keys 1,
  2, 3); recruiting is free and a roster holds 12 heroes.
- **Every won battle earns mastery** for each hero in the party. The upgrade screen (under its
  heading), the outcome screen and the status line say what was earned, or why nothing was.
- **Career** (the button on a party slot or a roster row) lists what a hero has mastered and
  what it can become. Vocations that are not discovered show as `???`. A vocation the rules
  cannot run yet is marked "Coming later". The numbers on the right are the hero's own as that
  vocation; where its mastery adds something, the vocation's own number is named too
  ("HP 18 (17 +1 mastery)").
- **Skills** (key K on the Career screen) lists the skills a hero has learned and lets you equip
  them between runs. A mastered vocation teaches one. The first that works in battle is the
  Guardian's **Field Medic**: once per battle its Heal may bring a downed ally back at 5 HP, for
  the Heal's own 1 mana. The die says so when it can ("Field Medic: revive at 5 HP"),
  and the downed ally becomes a target. A skill the rules of battle do not know yet is listed
  and cannot be equipped.
- **Changing vocation inside a run.** There are two moments, both between battles:
  - After Battle 1, before you choose the upgrade: the upgrade screen's **Career (C)** button
    lets the selected hero claim a vocation or change to one it has unlocked. The upgrade cards
    are dealt anew for its new dice.
  - After Battle 2, before you stop or fight on: each hero has a **Career** button. No upgrade
    is dealt there, and an upgraded die the hero gives up loses its upgrade.

  Either way the hero fights on with the new vocation's dice, and its health and mana carry
  over in proportion (rounded up). Changing back gives the hero exactly what it had: several
  changes at one such moment gain nothing. During a battle, and after the upgrade is chosen,
  nothing can be changed.
- **After Battle 2** you may end the run with a victory or fight a third battle. Losing it
  loses the run; mastery already earned is kept.
- **The save file** is `saves/profile.sqlite` beside the `logs` folder (the per-user application
  data folder for the packaged build). `--save-dir FOLDER` or `BATTLE_DICE_SAVE_DIR` puts it
  elsewhere. Delete the file to start over.

What is playable today: the three starting classes, Guardian and Ranger. The other nine
vocations are listed and cannot be claimed yet. The numbers of the Guardian and of the third
battle are defaults tuned with a simulated player; no person has played them yet.

The specification is executable and checked in CI:

```
python tools/class_evolution/validate_catalog.py      # the vocation catalog against shipped content
python tools/class_evolution/check_persistence.py     # the save database script and the example save
```

Both print `OK`. The first also lists, as warnings, every rank and vocation that cannot be reached
yet. Of the 40 acceptance cases 37 run as tests (`docs/DECISION_LOG.md`, sections 7.14 to 7.21).

### A tour of the slice in two runs

Both runs start in **Main menu, Settings (S)**. In the group **3. Class Evolution** switch
Class Evolution on. In the group **4. Demo and testing** choose what a **new profile starts
as**. Back in group 3 press **Reset the saved profile**, then **Delete every saved hero** on the
right, so the profile is made with that start. Esc returns to the main menu; **New Run (N)** opens the party setup.

**Run 1: Field Medic and the third battle** (start: *A Guardian with Field Medic*)

1. In the roster on the right, click a hero to put it into the party. Take "Squire 1" (the
   Guardian), the Scout and the Apprentice.
2. Click **Career** on the Guardian's slot, then press **K**: Field Medic is equipped. Esc.
3. **Begin Encounter (B)**. When an ally is down and the Guardian rolls its Heal, the die says
   "Field Medic: revive at 5 HP". Use the die and pick the downed ally. It needs
   1 mana, so the Guardian must not have spent its last mana on its reaction.
4. Win Battle 1, choose an upgrade, win Battle 2. Then choose **Fight On (F)** for the third battle.

**Run 2: becoming a Guardian inside a run** (start: *A Guardian at rank 1*)

1. In the party setup, add "Squire 1" and click **Career** on its slot. Select **Squire** and
   press **Make active**: the hero is a Squire again and keeps the Guardian unlocked. Esc.
2. Add the Scout and begin. Win Battle 1.
3. On the upgrade screen press **Career (C)** and select **Guardian**. The panel on the right
   says what the change would do ("If made active now: HP 15/15 -> 18/18, ..."). Press
   **Make active**: the status line gives the hero's health, mana, dice and bench die. Esc.
4. The upgrade cards are now for the Guardian's dice. Choose one and fight Battle 2 as a
   Guardian.

## Settings

**Main menu, Settings (S)**, or **Settings (S)** in the pause menu of a run. The settings are in
four groups (keys 1 to 4). Each button moves its setting to the next value; the change is saved
at once and takes effect at once.

| Group | Setting | Values | What it does |
|-------|---------|--------|--------------|
| 1. Display and comfort | Window size | 960x540, 1280x720 (default), 1600x900, 1920x1080 | The window can also be dragged to any size |
| | Text size | Normal (default), Large | Large draws text about 15% larger wherever the whole text still fits. The layout stays as it is, so a text with no room keeps its normal size; nothing is cut off to make room |
| | High contrast | Off (default), On | White text on black, bright borders, no picture behind the battle. Every text colour has at least 7:1 contrast |
| | Motion and flashes | On (default), Off | Reduced motion. `M` and the button at the top of a battle change this setting too |
| | Battle speed | Normal (default), Fast | How fast a battle plays. `F` and the button at the top of a battle change this setting too |
| 2. Play aids | Confirm a pass | On (default), Off | Pass asks once more when a die could still act |
| | Help text delay | None (default), Short, Long | How long the pointer rests on a control before its help shows. Why a control is off always shows at once |
| | Controls | (opens the help) | Mouse and keyboard controls, and how a turn works |
| 3. Class Evolution | Class Evolution | Off (default), On | Saved heroes, mastery, vocations and the third battle. Off is the game as shipped, with no save file |
| | Saved profile | Reset the saved profile | Deletes every saved hero and starts again from the chosen start. A second button, **Delete every saved hero**, has to confirm it; the first button again cancels |
| 4. Demo and testing | Mastery pace | Normal (default), Fast, Very fast | How many points a rank needs. Fast asks for about half; Very fast for one point a rank |
| | New profile starts as | Fresh (default); A Squire one win from mastery; A Guardian at rank 1; A Guardian with Field Medic (mastered, the skill equipped) | What a new or reset profile holds. Lets the evolution be shown in minutes |
| | Roster size | 6, 12 (default), 24 | How many heroes a profile may hold (1 to 50 in the file) |
| | Third battle | Offered (default), Not offered | The optional third battle after Battle 2 |

- **Demo and testing** holds aids for showing and testing Class Evolution. They need Class
  Evolution on, and say so while it is off. They do not change the rules of a battle.
- **Reset all settings to defaults** (bottom right) asks once more: press it again. Your saved
  heroes are kept.
- **From the pause menu** the run waits. Groups 1 and 2 apply at once; groups 3 and 4 and both
  resets are locked until the run is over, because they would close the save.
- **The dice seed is chosen when you start a run**, not here: on the party setup, **Dice seed
  (D)** is random by default. Press D (or click it), type digits or click them on the number
  pad that opens, and press Enter (or **Set**) to fix a seed; press D again for a random one.
  The same seed, party and choices give the same run.
- The settings are kept in `settings.json`: in the working folder when run from source, in
  `%LOCALAPPDATA%\BattleDice` for the packaged build. `--settings FILE` or the environment
  variable `BATTLE_DICE_SETTINGS` uses another file. The file is plain JSON and may be edited
  by hand; it also holds `save_dir`, the folder of the save file.
- A launch flag (`--seed`, `--size`, `--no-animation`, `--feature`, `--save-dir`) wins
  over the file for that launch. A value the game does not allow is replaced by its default and
  named on the main menu; the game always starts.
- Nothing here changes the rules of a battle, the shipped content or the numbers of a class.

## Scope

In scope: the two-battle loop, three classes, three enemy archetypes, d4 / d6 / d8 dice, the
action-gauge timeline, staged reactions, Poison, Weaken, mana, corruption, shields, downing and
explicit revival, recovery, one mandatory upgrade and one optional swap per hero.

Deferred: save and resume across restarts, d10 / d12 / d20, class unlocks and levelling,
procedural encounters, signed installers and published releases, controller support, audio, and a
pixel-art reskin of panels and buttons.
