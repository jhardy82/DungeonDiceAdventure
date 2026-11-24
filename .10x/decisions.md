# Project Decisions

> This file is the shared brain of the 10x-Team. Every role reads it before acting and writes to it after deciding. Append only — never delete or overwrite another role's decisions.

## Project: Battle Dice
Started: 2026-11-11

> **Decisions made before this file existed** are in `docs/DECISION_LOG.md` (D-01 to D-27, with
> the evidence for each) and, for Class Evolution, in `docs/class_evolution/FDD_v0.2.md`
> (sections 8 and 10) and `docs/class_evolution/ADR-CE-001.md`. They stay there and still hold.
> New decisions are appended below.

---

<!-- Decisions are appended below by each role. Format:
### [Date] — [Role]: [Decision Title]
- **Decision:** What was decided
- **Why:** Business/technical justification
- **Alternatives considered:** What else was evaluated
- **Trade-offs accepted:** What we're giving up
- **Impacts:** Which roles/components this affects
-->

### 2026-11-12 — Engineer: what "fully configurable" covers in the demo (assumption)
- **Decision:** Until the owner says otherwise, "fully configurable" means three things: (1) a
  settings file in the user's data folder with an in-game Settings screen (Class Evolution on or
  off, fixed or random seed, animation, window size, save folder, reset the profile), with launch
  flags overriding it; (2) a Class Evolution tuning file (mastery points per win, points per
  rank, the third battle and its enemies per party size, roster limit), validated on load and
  recorded with each run; (3) demo start presets for a new profile (fresh; a Squire one win from
  mastery; Guardian unlocked; Guardian mastered with Field Medic).
- **Why:** The owner's goal of 2026-11-11 is "a fully configurable and playable demo". The
  question of what configurable should cover was put to the owner twice and not answered, and
  the goal says not to wait. These three parts are the ones a demo needs to be shown and tuned
  without editing code.
- **Alternatives considered:** Also loading the base game's classes, dice, enemies and
  encounters from a folder. Left out for now: such runs fall outside the balance evidence and
  the replay pin.
- **Trade-offs accepted:** The scope may be wider or narrower than the owner meant; it is cheap
  to add or drop a part later because each is separate.
- **Impacts:** App and UI (settings, Settings screen), career rules (tuning), save (presets), docs.

### 2026-11-12 — Engineer: what of the configuration assumption was built, and what was not
- **Decision:** Built: the settings file, the Settings screen, Class Evolution on or off inside the
  game, the third battle on or off, mastery pace (normal, fast, very fast), roster size, four
  start presets, profile reset, seed, animation, window size. Not built: points per win as a
  setting, the third battle's enemy table as a setting, a separate tuning file.
- **Why:** The save's award rows allow 0 or 1 point, so more points per win needs a schema
  change; the pace setting changes how many points a rank needs instead. The enemy table is in
  the catalog whose hash a run's record pins, so a setting that edits it would break replay.
- **Alternatives considered:** Migrating the save schema for larger awards; a second encounter
  source with its own hash for a tuned table.
- **Trade-offs accepted:** The owner tunes the third battle by editing `vocation_catalog.json`
  (validated), not from the Settings screen.
- **Impacts:** Settings, save link, docs (`docs/DECISION_LOG.md`, section 7.19).

### 2026-11-12 — Engineer: the threat-4 table goes in as a default, not as a settled balance decision
- **Decision:** The enemy table of the optional third battle (`training_04`) is the one tuned by
  measurement in `docs/DECISION_LOG.md`, section 7.16 (75-77% for parties with a Guardian, per
  party size). The Guardian keeps its v0.1 numbers. Both stay open owner decisions.
- **Why:** The approved plan put these numbers to the owner at Checkpoint 1. The goal changed to
  a playable, configurable demo; waiting would block every later step, and the tuning file lets
  the owner change them without code.
- **Alternatives considered:** Stopping for Checkpoint 1 as planned.
- **Trade-offs accepted:** The demo ships numbers the owner has not approved. They are labelled
  as defaults and measured only by a simulated player.
- **Impacts:** Vocation catalog, balance evidence, the demo's tuning file.

### 2026-11-12 — Engineer: how Field Medic works, and what the skills panel offers
- **Decision:** Field Medic applies to any Healing face with one ally as its target that the
  hero rolls and that cannot revive; once per encounter it may be used on a downed ally for 1
  more mana, bringing the ally back at 1 HP. Skills are equipped on the Career screen between
  runs. A skill the rules of battle do not know (today: Squire Anchor) is listed and cannot be
  equipped.
- **Why:** The owner decided that Field Medic works in battle in the first slice (D-27). The
  catalog says "one equipped Healing face" without a way to choose one, and fixture CE-29 shows
  the revival as an option on the face.
- **Alternatives considered:** Letting the player mark one face for the skill (more screens,
  no gain while a Guardian has one Healing face); letting Squire Anchor be equipped with a
  warning.
- **Trade-offs accepted:** The reading is the builder's. Measured with the simulated player the
  skill changes nothing (it rarely has the 2 mana); the cost was not tuned.
- **Impacts:** Rules (`core/skills.py`), vocation catalog 0.4.0, save link, Career screen, docs
  (`docs/DECISION_LOG.md`, section 7.20).

### 2026-11-12 — Engineer: the vocation change inside a run, and its one moment
- **Decision:** A saved hero may change vocation inside a run in the run phase `upgrade` only
  (after Battle 1's recovery, before the upgrade is chosen), as the owner decided for fixture
  CE-19. The career rules decide whether the hero may; the run is then told with its own
  command, `ChangeVocationInRun`, which carries the hero's build snapshot. Health and mana carry
  over in proportion (rounded up); the upgrade offers are drawn anew for the new dice. A hero
  may change back while the upgrade is not chosen, and may claim a vocation at that moment.
- **Why:** CE-19 and the approved Phase 4 plan. Two command names because the career rules
  already had `ChangeVocation` with other parameters.
- **Alternatives considered:** Also opening the stop-or-fight-on decision after Battle 2 for a
  change. Not built: CE-19 names the upgrade only.
- **Trade-offs accepted:** A hero that masters its class in Battle 2 cannot evolve before the
  third battle. Put to the owner as an open question.
- **Impacts:** Rules engine (command, event), save link, upgrade and Career screens, docs
  (`docs/DECISION_LOG.md`, section 7.21).

### 2026-11-12 — Owner: Checkpoint 1 accepted; a second moment for a vocation change
- **Decision:** (D-28) The Guardian's numbers and the third battle's enemy table are accepted as
  built. (D-29) A hero may also claim or change vocation at the decision to stop or fight on
  after Battle 2.
- **Why:** Asked through the ask tool on 2026-11-12; the owner chose both.
- **Alternatives considered:** A stronger Guardian; keeping the numbers as open defaults;
  keeping the change to the moment after Battle 1 only.
- **Trade-offs accepted:** D-29 goes beyond acceptance case CE-19. At that decision no upgrade
  is dealt, and an upgraded die the hero gives up loses its upgrade.
- **Impacts:** Rules engine, the saved run phase for that decision (now `upgrade`), the
  stop-or-fight-on screen, docs (`docs/DECISION_LOG.md`, section 7.24).

### 2026-11-12 — Owner: research the configuration, measure Field Medic first
- **Decision:** The owner did not confirm the built Settings as the "configurable" scope and
  asked for research into a more logical set of options. For Field Medic's cost the owner asked
  for measurements before any change.
- **Why:** The owner's answers of 2026-11-12.
- **What exists now:** the research and a proposed structure (`docs/DECISION_LOG.md`, 7.26);
  the measurement (7.25: the revival's health is the lever, not its cost).
- **Open:** the owner's choice of what to build from the proposal, and of a Field Medic change.
- **Impacts:** Settings and New Run screens (when chosen), the skill's numbers (when chosen).

### 2026-11-12 — Owner: Field Medic's numbers, and the shape of the demo's configuration
- **Decision:** (D-30) Field Medic: no extra mana, the ally comes back at 5 HP, once per
  encounter. (D-31) Settings is grouped, with the demo options in a group of their own at the
  bottom; the dice seed is chosen on the New Run screen and can be typed; the small set of new
  settings is built (text size, high contrast, battle speed at start, confirm before passing
  with an unused die, tooltip delay, Settings from the pause menu, reset all to defaults).
- **Why:** The owner's answers of 2026-11-12, after the measurement and the research the owner
  had asked for (`docs/DECISION_LOG.md`, sections 7.25 and 7.26).
- **Alternatives considered:** Field Medic as built or at 2 mana and 5 HP; demo options behind
  launch flags only; the seed left in Settings; regrouping without new settings; key remapping.
- **Trade-offs accepted:** No difficulty presets, no remapping, no audio or controller settings
  in the demo. Text size needs a layout check on every screen.
- **Impacts:** `core/skills.py` and the vocation catalog; Settings, New Run and pause screens;
  the settings file; docs.

### 2026-11-12 — Owner: how the demo is judged; "Confirm a pass" on by default (D-32)
- **Decision:** The owner plays the demo and judges it against the goal "a fully configurable
  and playable demo". The play aid "Confirm a pass" stays on by default.
- **Why:** Every setting of D-31 is merged and all automated checks pass on Linux and Windows,
  but no person has played the demo; a playtest is the one check the implementing agent cannot do.
- **Alternatives considered:** Accept the demo on the automated evidence alone; keep building
  first. "Confirm a pass" off by default.
- **Trade-offs accepted:** The goal stays open until the owner has played. Pass needs two
  presses while a die could still act, unless the player turns the aid off.
- **Impacts:** No code. What the owner reports after playing decides the next work.

### 2026-11-21 — Owner: an Android app with new phone screens, built with Flet (D-33)
- **Decision:** Build a real Android app. Keep rules, content, save and controller; build new
  phone screens with Flet, starting with a walking skeleton and a go or no-go check. The app
  works upright and sideways from the start. What the app is for is not decided.
- **Why:** On a Galaxy S25 Ultra the desktop screens would show text 1.4 mm high and 97% of
  controls under 7 mm, and no supported way exists to package a pygame-ce game for Android. A
  spike showed the controller runs under Flet without pygame and can be checked at phone size.
- **Alternatives considered:** A browser build as a trial; a phone layout inside the pygame
  screens; a native Android UI in Kotlin with Chaquopy (kept as the fallback); Kivy.
- **Trade-offs accepted:** Flet is young (1.0 in September 2026) and its Play Store compliance
  is not confirmed; Android runs Python 3.14, not 3.15; two arrangements for every screen.
- **Impacts:** A new app folder and a new Android workflow; the pygame-free layer gains screen
  data for the phone; `docs/android/PLAN.md`; later the Python floor and the wording of messages.

### 2026-11-21 — Owner: what is fixed after the playtest by the team (D-34)
- **Decision:** Fix every defect and every case of missing information that needs no design
  decision. Keep the single-target shortcut, say that it happened, and never let a number key
  remove a planned action. "Abandon Run" and "Retry" ask once more; the profile reset is
  confirmed by a separate button elsewhere. Fix both rule faults: a vocation change converts
  health from what the hero had when the change window opened, and an upgrade card that would
  change nothing is not offered.
- **Why:** Eight AI playtesters found about 45 different things in 7,374 actions; seven are
  high. Four were replayed and their causes read in the code.
- **Alternatives considered:** Only the high findings; none before the owner has played.
  Always asking for a target. One "press again" for all three safeguards. Leaving the rules.
- **Trade-offs accepted:** The rules version goes up and the replay pin changes with the rule
  fixes; the balance is measured again. The Android skeleton waits until the fixes are in.
- **Impacts:** Battle, upgrade, settings and outcome screens; controller; `core/build.py` and
  `core/progression.py` for the rules; five pull requests. Not decided: dismissing a hero,
  starting classes, what a slower mastery pace does to a vocation already opened.

### 2026-11-21 — Owner: three open playtest findings and Android after the skeleton (D-35)
- **Decision:** A hero can be dismissed (asked once more; not in the party, not during a run).
  Recruits get names that say no class ("Recruit 1"); saved heroes keep their names. A vocation a
  hero has opened stays open when a slower Mastery pace takes the rank it needed, and the Career
  screen says so. Android phase 1 groundwork starts while the owner tries the APK.
- **Why:** A full roster was a dead end; "Squire 1" listed as a Scout misled; a setting must not
  take progress away. The groundwork is needed by any phone toolkit.
- **Alternatives considered:** Leaving the roster as it is, or only raising its limit. Recruits
  with only their own class open (a rule change). Locking the pace once used, or closing the
  vocation again. Waiting for the phone test, or pausing Android.
- **Trade-offs accepted:** The save gets its first real migration (schema 3). A dismissed
  hero's rows stay in the save as history. Old and new hero names exist side by side.
- **Impacts:** Career rules and store, controller, Career and party screens, README; the go or
  no-go for the phone screens stays with the owner.

### 2026-11-22 — Owner: what the second and the whole-run playtests left open (D-36)
- **Decision:** The demo is not played yet, so the goal stays open. Both balance impressions of
  the AI playtests are measured with the simulator and brought back with numbers and options: the
  third battle with and without a Guardian, and how often enemies attack. The reason for "no hero
  could react" goes into the event log with the next rules change. Reaction rows stay numbered
  from 1 in each stage.
- **Why:** One party and one seed is an impression; a balance change needs win rates per party
  size against the 70-85% target. A rules version for one log field alone is not worth a new
  replay pin. A second reaction is already asked for once more, which guards the costly slip.
- **Alternatives considered:** Leaving both balance questions; a rules version now; keys by the
  hero's place.
- **Trade-offs accepted:** The log keeps saying "no hero could react" without the reason for now.
- **Impacts:** Simulator runs only; no content or rule changes until the owner chooses from the
  options.

### 2026-11-24 — Owner: the balance questions after the measurements (D-37)
- **Decision:** Make the third battle last longer (more enemy health, weaker hits), tuned per
  party size. Rework the enemies' choice now: "never a status twice running", with a new enemy
  table per party size at 70-85%. Measure the effect of the order of the heroes further before
  anything is said or changed. Both tables come back to the owner before they go into the game.
- **Why:** The owner chose against my recommendations (leave the third battle; decide the attacks
  after playing): enemies that mostly weaken and poison, and a third battle decided in a few
  blows, are not the game wanted. The order effect rests on one sample.
- **Alternatives considered:** Leaving both; deciding after the owner's own playtest; tuning the
  third battle for parties without a Guardian; saying the order rule on the party screen at once.
- **Trade-offs accepted:** A new rules version and a new content version, so a new replay pin;
  every balance figure measured so far is measured again. The demo changes before the owner has
  played it.
- **Impacts:** `core/enemy_ai.py`, the encounter tables, the third battle's table in the catalog,
  the simulator reference, the docs that quote win rates. The reason for "no hero could react"
  goes into the event log with the same rules version (D-36).
