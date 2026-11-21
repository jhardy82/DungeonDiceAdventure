# Battle Dice on Android: plan

Owner decision D-33 (2026-11-21). The evidence behind it is in `docs/DECISION_LOG.md`,
section 7.31. This file is the plan that was approved, kept up to date as phases finish.

## What is being built

- An Android app with **new phone screens**, written in Python with **Flet** (drawn by Flutter).
- The rules, the content, the save and the controller are **kept as they are**. Only
  `src/battle_dice/ui/` and `__main__.py` use pygame; the phone app does not use them.
- The Windows game stays as it is and remains the reference for behaviour.
- The app works **upright and sideways from the start** (owner's choice).
- What the app is for is **not decided** (own phone, a few people, or the Play Store). The plan
  therefore keeps the Play Store possible and does not depend on it.

## Why the current screens cannot simply be packaged

- On a Galaxy S25 Ultra (6.9 inch, 19.5:9) the 1280x720 layout would show typical text 1.4 mm
  high and 97% of controls under 7 mm. Android asks for about 1.9 mm text and 9 mm controls.
- No supported way exists to package a pygame-ce game for Android (2026-11).

## Design rule: screens are data first

- What a phone screen shows (sections, texts, values, which actions are possible and why not)
  is computed in plain Python, without Flet and without pygame, and tested there.
- Flet only draws that data and sends taps back as controller calls.
- If Flet has to be given up, the fallback (a native Android UI in Kotlin, with Chaquopy) draws
  the same data. The fallback is a plan B, not a second product.

## Phases

| Phase | What | State |
|-------|------|-------|
| 0. Walking skeleton | A minimal app (menu, party, one battle) built as an APK on GitHub, started in an emulator there, installed by the owner on the S25 Ultra | Next |
| 1. Groundwork | Python 3.14 allowed and tested beside 3.15; controller messages without key names for touch; screen data in the pygame-free layer | After phase 0 |
| 2. Phone screens, shipped game | Menu, Settings, party setup, battle, upgrade, outcome, pause; each upright and sideways | The main job |
| 3. Class Evolution on the phone | Roster, career, skills, vocation change, the third-battle decision | |
| 4. Android behaviour | Back gesture, resuming a run after the app was closed, cutout and safe areas, icon and name | |
| 5. Play Store | Only on a separate owner decision: signing, developer account, store listing | Not decided |

## Go or no-go after phase 0

Phase 2 starts only if **all** of these hold. If one fails and cannot be fixed, the fallback is
proposed to the owner before any real screen is built.

| Check | How it is shown |
|-------|-----------------|
| The APK builds on GitHub's machines from the repository | A workflow run with the APK as an artifact |
| The app starts in an Android emulator and plays the built-in self-check run through the real controller | The workflow reads the app's report |
| The save file (SQLite) can be written and read inside the app | Part of that report |
| The APK targets the API level Google Play asks for (36) and its native libraries are aligned for 16 KB pages | Checked on the built APK in the workflow |
| The app follows the system font size | A second emulator run with a larger font scale, with a screenshot |
| It starts and plays acceptably on the owner's S25 Ultra | The owner's report |
| Size and start-up time are known | Measured and written here |

## What can and cannot be checked without a phone

- **In the development container:** the screen data (tests), and the Flet screens drawn in a
  browser at phone size (384 x 832 dp upright, 832 x 384 dp sideways), including taps.
- **On GitHub's machines:** the Android build and an emulator run.
- **Only by the owner:** how it looks, feels and performs on the real phone.

## Known facts and unknowns (2026-11-21)

- Flet 1.1.2 (1.0 on 2026-09-14). Its Android builds embed CPython 3.12, 3.13 or 3.14, not 3.15.
  The game's self-checks and all non-screen tests pass on 3.14.
- The content check needs `jsonschema`, which needs a compiled extension (`rpds-py`). Flet's
  package index has it for Android; the fallback route does not.
- The controller's messages name keys ("Reroll (R)", "Esc cancels"). Touch needs other wording.
- `<UNKNOWN>` until phase 0 has measured them: Flet's default target API, 16 KB alignment,
  behaviour with the system font size, start-up time, speed, APK size, GitHub build minutes.

## Identifiers

- The app's Android identifier in the skeleton is a placeholder. It must be chosen by the owner
  before anything is uploaded to a store, because it cannot be changed afterwards.
