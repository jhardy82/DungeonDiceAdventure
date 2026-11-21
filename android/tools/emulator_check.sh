#!/usr/bin/env bash
# Phase 0 of docs/android/PLAN.md, on an Android emulator: install the APK and start the app four times:
# upright, with a larger system font, turned sideways while it runs, and started while the device is held
# sideways (as a phone in a hand, turning its screen by itself). Each start must report a passed self-check
# in the device log, and the app must report the layout that fits: upright, upright, sideways, sideways.
# A screenshot and the device log of each start are kept.
# Usage: emulator_check.sh APK OUTPUT_FOLDER
set -uo pipefail
apk="$1"; out="$2"; mkdir -p "$out"
# Seconds: between two looks at the log, the longest wait for the self-check report (the first start
# unpacks the app), the longest wait for the layout, and the pause before a screenshot. A test of this
# script sets them to nothing.
poll="${EMULATOR_CHECK_POLL:-5}"; limit="${EMULATOR_CHECK_LIMIT:-300}"; settle="${EMULATOR_CHECK_SETTLE:-30}"; pause="${EMULATOR_CHECK_PAUSE:-3}"

adb install -r "$apk" || { echo "EMULATOR CHECK FAILED: the APK did not install"; exit 1; }
package="$(adb shell pm list packages -3 | tr -d '\r' | sed 's/^package://' | grep -i -m1 battle || true)"
if [ -z "$package" ]; then
  adb shell pm list packages -3
  echo "EMULATOR CHECK FAILED: the app's package was not found after the install"; exit 1
fi
echo "package: $package"
: > "$out/report.txt"
no_check=""; wrong_layout=""
say() { echo "$1" | tee -a "$out/report.txt"; }

# turn_screen 1 (sideways) or 0 (upright). Two ways of saying it: which one an emulator obeys differs.
turn_screen() {
  adb shell settings put system accelerometer_rotation 0
  adb shell settings put system user_rotation "$1"
  adb shell cmd window user-rotation lock "$1" > /dev/null 2>&1 || true
}

# hold_device 1 (sideways) or 0 (upright): what the device's motion sensor feels, with the screen free to
# turn by itself. A screen locked sideways before an app starts stayed upright on the build's emulator
# (pull request 42, runs 2 and 5: the screenshots were upright), so the fourth start is done this way.
hold_device() {
  adb shell settings put system accelerometer_rotation 1
  if [ "$1" = 1 ]; then adb emu sensor set acceleration 9.81:0:0 > /dev/null; else adb emu sensor set acceleration 0:9.81:0 > /dev/null; fi
}

# What the device says about its screen's rotation: printed when a layout is not the expected one.
rotation_facts() {
  echo "    auto-rotate: $(adb shell settings get system accelerometer_rotation | tr -d '\r'), user rotation: $(adb shell settings get system user_rotation | tr -d '\r')"
  adb shell dumpsys window displays | tr -d '\r' | grep -i -m8 -E "rotation|orientation" | sed 's/^ */    /' || true
}

# Waits for the app's report line and prints it with the seconds it took.
wait_for_report() {
  local started=$SECONDS line
  while :; do
    line="$(adb logcat -d | tr -d '\r' | grep -m1 'BATTLE DICE SELF-CHECK' || true)"
    if [ -n "$line" ]; then echo "$line seconds_until_report=$((SECONDS - started))"; return 0; fi
    [ $((SECONDS - started)) -ge "$limit" ] && return 1
    sleep "$poll"
  done
}

# The layout the app reported last in this start, in its own words ("BATTLE DICE SCREEN: layout=...").
layout_now() { adb logcat -d | tr -d '\r' | grep -o 'BATTLE DICE SCREEN: .*' | tail -n 1 || true; }

# Width x height of a PNG file: a screenshot shows which way the display was turned.
picture_size() {
  python3 -c 'import struct, sys
head = open(sys.argv[1], "rb").read(24)
print("%dx%d" % struct.unpack(">II", head[16:24]) if head[:4] == b"\x89PNG" and len(head) == 24 else "not readable")' "$1" 2>/dev/null || echo "not readable"
}

# start_and_check NAME LAYOUT [after|held]: stops the app, starts it, waits for its self-check report,
# waits for the app to report LAYOUT, and keeps a screenshot and the device log. "after": the screen is
# turned sideways once the app has reported. "held": the device is held sideways before the app starts.
# Either is undone at the end.
start_and_check() {
  local name="$1" expected="$2" turn="${3:-}" report screen started
  adb shell am force-stop "$package"
  if [ "$turn" = held ]; then hold_device 1; sleep "$pause"; fi
  adb logcat -c
  adb shell monkey -p "$package" -c android.intent.category.LAUNCHER 1 > /dev/null
  if report="$(wait_for_report)"; then
    say "$name: $report"
    echo "$report" | grep -q 'BATTLE DICE SELF-CHECK OK' || no_check="$no_check $name"
  else
    say "$name: no self-check report within $limit seconds (see ${name}_logcat.txt)"
    no_check="$no_check $name"
  fi
  [ "$turn" = after ] && turn_screen 1
  started=$SECONDS
  while :; do
    screen="$(layout_now)"
    case "$screen" in *"layout=$expected "*) break ;; esac
    [ $((SECONDS - started)) -ge "$settle" ] && break
    sleep "$poll"
  done
  sleep "$pause"
  adb exec-out screencap -p > "$out/$name.png"
  adb logcat -d > "$out/${name}_logcat.txt"
  say "$name: ${screen:-the app reported no layout} (expected $expected; the screenshot is $(picture_size "$out/$name.png"))"
  case "$screen" in *"layout=$expected "*) ;; *) wrong_layout="$wrong_layout $name"; rotation_facts | tee -a "$out/report.txt" ;; esac
  [ "$turn" = after ] && turn_screen 0
  if [ "$turn" = held ]; then hold_device 0; adb shell settings put system accelerometer_rotation 0; fi
  return 0
}

start_and_check 1_upright upright

# The system font size, larger: the app must follow it (a go or no-go check; the screenshot shows it).
adb shell settings put system font_scale 1.3
start_and_check 2_larger_font upright
adb shell settings put system font_scale 1.0

start_and_check 3_sideways sideways after
start_and_check 4_started_sideways sideways held

if [ -z "$no_check$wrong_layout" ]; then
  say "EMULATOR CHECK OK: four starts, four passed self-checks, the layout followed the screen"; exit 0
fi
[ -n "$no_check" ] && say "EMULATOR CHECK FAILED: no passed self-check at:$no_check"
[ -n "$wrong_layout" ] && say "EMULATOR CHECK FAILED: not the expected layout at:$wrong_layout"
exit 1
