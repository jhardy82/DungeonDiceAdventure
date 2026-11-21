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
| 0. Walking skeleton | A minimal app (menu, party, one battle) built as an APK on GitHub, started in an emulator there, installed by the owner on the S25 Ultra | Built, and built and started on GitHub (see "Phase 0, as built" and "Phase 0, measured"). Open: the owner's install on the phone |
| 1. Groundwork | Python 3.14 tested beside 3.15; controller messages without key names for touch; screen data in the pygame-free layer | Started on the owner's decision of 2026-11-21 (D-35). Steps 1 and 2 are done (see "Phase 1, step by step") |
| 2. Phone screens, shipped game | Menu, Settings, party setup, battle, upgrade, outcome, pause; each upright and sideways | The main job |
| 3. Class Evolution on the phone | Roster, career, skills, vocation change, the third-battle decision | |
| 4. Android behaviour | Back gesture, resuming a run after the app was closed, cutout and safe areas, icon and name | |
| 5. Play Store | Only on a separate owner decision: signing, developer account, store listing | Not decided |

## Phase 0, as built (2026-11-21)

| Part | Where | What it is |
|------|-------|------------|
| A self-check without a screen | `src/battle_dice/app/selfcheck.py` | One whole run with saved heroes through the real controller, played by the simulated player; the save is written, closed and read again. Prints one line that starts with `BATTLE DICE SELF-CHECK` |
| The phone screens as data | `src/battle_dice/phone/screens.py` | Menu, party and one battle as plain data, and what each tap does. No toolkit is imported. Messages lose their key hints ("Roll the dice (R)." becomes "Roll the dice.") |
| The app | `android/src/main.py`, `android/pyproject.toml` | Flet draws that data: upright in one column, sideways with the buttons on the right. On start it runs the self-check and shows its line on the menu |
| The build | `.github/workflows/android.yml` | Copies the game's package into the app without the pygame screens, runs the self-check on Python 3.14, builds the APK, reads its size, processor types and 16 KB alignment, starts it on an emulator, reads the self-check from the device log, and keeps screenshots: upright, with a larger system font, sideways |
| The checks of a built APK | `android/tools/check_apk.py`, `android/tools/emulator_check.sh` | Used by the build |

- **Checked in the development container:** 13 tests (a whole battle played by taps alone; refused
  taps; the self-check; no pygame loaded in a fresh interpreter; the APK check on made-up
  libraries). The app was started in a browser at 384 x 832 and 832 x 384 and tapped through
  menu, party and the start of a battle; the self-check line showed Python 3.14.6 and 2.6 to 2.9
  seconds.
- **Not checkable there:** everything that needs the Android build. The container cannot reach
  the servers the build needs, so the build runs on GitHub (next section).
- The app's identifier (`dev.battledice`) is a placeholder.

## Phase 0, measured on GitHub (2026-11-21)

Seven runs of the workflow "Android (walking skeleton)" on pull request 42 (the seventh, on the
commit that wrote this section, passed like the sixth), and two more on pull request 44. All
numbers are from their logs.

| What | Measured |
|------|----------|
| The build | Passed at the first attempt. The whole job took about 8 minutes (the Android build step itself 290 seconds); 10 to 12 minutes since Gradle runs one worker at a time (see the faults below) |
| APK size | 107.6 MB for two processor types together (`arm64-v8a` for phones, `x86_64` for the emulator); 128 native libraries |
| 16 KB pages | Every native library is aligned for 16 KB pages, inside the library and inside the APK |
| API levels | Target 36 (what Google Play asks for), minimum 24 (Android 7.0) |
| Screen orientation | The app's manifest fixes none |
| Python inside the app | 3.14.10 |
| The self-check inside the app | Passed at every start: a whole run (3 battles, 1,424 events, the same as on the desktop), 3 heroes saved, the save read back, pygame not loaded |
| Time, emulator | The self-check run itself 4 to 12 seconds (ten readings); from the tap on the icon to the report 10 to 21 seconds (the script looks every 5 seconds). An emulator on a shared build machine is not a phone; the phone's time is not known |
| Layout | Upright: the app reports 411 x 891 dp. Turned sideways while it runs: 891 x 411 dp and the sideways layout; the screenshot is 3120 x 1440. Started while the device is held sideways (its screen free to turn): the same, 891 x 411 dp, screenshot 3120 x 1440 |

**Three faults the runs found, and what was done.** None of them was caught by the check that
was meant to catch it; each was found by reading the log.

| Run | What happened | Cause | What was done |
|-----|---------------|-------|---------------|
| 1 | Reported as passed. The log showed the app's second start saying "SELF-CHECK FAILED: the heroes or what they earned did not reach the save" | The self-check kept its save between starts and found the first check's heroes beside its own. On a phone, every start after the first would have shown a failed check. The game's own save was not involved | The self-check starts from nothing each time (it removes what an earlier check left, only in a folder that carries its own marker). The emulator script requires a passed self-check at every start |
| 2 and 5 | Run 2 was reported as passed; the app's own log line showed the start named "sideways" laid out upright (411 x 891). Run 5, with the check made strict, failed there | The emulator's display stayed upright when the screen was locked sideways **before** the app started: in run 5 the screenshot was 1440 x 3120. The app laid out for the screen it was given. Why that emulator does not turn in this case is not known | The script names the layout each start must report and writes the screenshot's size beside the app's line; on a wrong layout it prints what the device says about its rotation. Sideways is now shown two ways that work: the screen turned while the app runs, and the device held sideways (motion sensor, screen free to turn) before the app starts. Run 6 passed both |
| 4 | The build failed in Gradle: "Unable to determine the current character ... '\0'" in the task that downloads Python for `x86_64`. Nothing that goes into the APK had changed | A race in the build plugin (serious_python_android 6.1.3, read from its source): four download tasks run side by side and share one file of download marks; one read it while another wrote it | The workflow lets Gradle run one worker at a time. A passing build does not prove a race gone; the reasoning rests on the plugin's source and the error text. If it shows again, it is a fault of the build tool to report there |
| 8 (pull request 44) | The fourth start (the device held sideways before the app starts) came up upright, after two runs in which it had passed | The script's own doing. The report's rotation facts showed "auto-rotate: 0" although the script had just switched it on: the rotation lock of the third start, just ended, switched it off once more a moment later. Whether that happens depends on timing | The script frees the rotation through the window manager, then asks the device until it says the screen is free, and only then holds it sideways. Tested against a stand-in device that takes the setting back once |

**Not shown:** an app started while the screen is *locked* sideways (see runs 2 and 5). On a
phone that is an unusual setting; the owner's phone can show it in a minute.

**Not judged by anyone yet:** the screenshots (upright, larger font, sideways twice). They are
in the run's artifact `battle-dice-android-emulator`. The development container cannot download
artifacts, so they have not been looked at; whether the app follows the system font size is
therefore still open (see the table below).

## Phase 1, step by step

Groundwork that any phone toolkit needs. It changes nothing a desktop player sees.

| Step | What | State |
|------|------|-------|
| 1. The code runs on the phone's Python | The whole suite (1,406 tests, warnings as errors) and both self-checks run on Python 3.14 in a job of their own on every pull request. Lint treats 3.14 as the oldest Python the code must run on, and the type check runs a second time as 3.14 | Done |
| 2. Messages without key names | A controller made with `touch=True` words everything it says for a finger: "Roll the dice (R)." becomes "Roll the dice.", "Press again to ..." becomes "Tap again to ...", "press its number or click it" becomes "tap it" (`src/battle_dice/app/wording.py`). The phone app asks for it. A desktop controller says its messages as written | Done |
| 3. Screen data outside pygame | What each desktop screen works out while drawing (rows, labels, reasons) moves into the pygame-free layer, screen by screen, as the phone screens need it | With phase 2 |

- **What "tested beside 3.15" means.** The desktop game still asks for Python 3.15
  (`requires-python`, the launcher, the README): that is the owner's stack decision and is not
  changed. The code is kept runnable on 3.14 and proven so by the tests, because the Android
  app embeds 3.14. The 3.14 job runs from the source tree, as the Android build takes the
  package from the source tree too.
- **Measured before the job was added:** on Python 3.14.6 in the development container all
  1,382 tests of that moment passed with warnings as errors (290 seconds), both self-checks
  passed, and lint and the type check were clean when told the code is for 3.14. Nothing in the
  code had to change.
- **How step 2 is kept true.** A test reads every message in the source of the controller and
  the other toolkit-free modules, and fails when one still names a key, a press or a click after
  it was worded for touch. On its first run it found a message I had missed (the help for
  typing a seed: "Enter sets it, Esc cancels."). A second test plays a whole battle by taps and
  collects everything the touch controller says.
- **Not covered by step 2:** the labels of buttons. Those belong to each front end: the desktop
  screens write "Roll  (R)", the phone screens write "Roll".

## Go or no-go after phase 0

Phase 2 starts only if **all** of these hold. If one fails and cannot be fixed, the fallback is
proposed to the owner before any real screen is built.

| Check | How it is shown | State on 2026-11-21 |
|-------|-----------------|---------------------|
| The APK builds on GitHub's machines from the repository | A workflow run with the APK as an artifact | **Holds** |
| The app starts in an Android emulator and plays the built-in self-check run through the real controller | The workflow reads the app's report | **Holds**: at four starts in each of two runs of pull request 42 |
| The save file (SQLite) can be written and read inside the app | Part of that report | **Holds** |
| The APK targets the API level Google Play asks for (36) and its native libraries are aligned for 16 KB pages | Checked on the built APK in the workflow | **Holds** |
| The app follows the system font size | A second emulator run with a larger font scale, with a screenshot | **Open:** the screenshot exists; nobody has looked at it |
| It starts and plays acceptably on the owner's S25 Ultra | The owner's report | **Open:** only the owner can do this |
| Size and start-up time are known | Measured and written here | **Holds** for the emulator (107.6 MB; see above). The phone's start-up time is open |

Four of seven hold, one more for the emulator only. The decision is the owner's, after the
install on the phone.

**How the owner installs it.** On GitHub: the repository, "Actions", the newest run of "Android
(walking skeleton)", the artifact `battle-dice-android-apk`. Unpack it and copy
`battle-dice-android.apk` to the phone. Android asks once to allow installs from that source.
The APK is signed with a debug key: fine for trying it, not for the Play Store.

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
