#!/usr/bin/env bash
# Phase 0 of docs/android/PLAN.md, on an Android emulator: install the APK, start the app three times
# (upright, with a larger system font, sideways), read its self-check report from the device log each
# time, and keep a screenshot of each. Every start must report a passed self-check. The layout the app
# reports for each start (upright or sideways, and for how much room) is written down, not judged.
# Usage: emulator_check.sh APK OUTPUT_FOLDER
set -uo pipefail
apk="$1"; out="$2"; mkdir -p "$out"
# Seconds: the pause before a screenshot, between two looks at the log, and the longest wait for a report
# (the first start unpacks the app). A test of this script sets them to nothing.
pause="${EMULATOR_CHECK_PAUSE:-3}"; poll="${EMULATOR_CHECK_POLL:-5}"; limit="${EMULATOR_CHECK_LIMIT:-300}"

adb install -r "$apk" || { echo "EMULATOR CHECK FAILED: the APK did not install"; exit 1; }
package="$(adb shell pm list packages -3 | tr -d '\r' | sed 's/^package://' | grep -i -m1 battle || true)"
if [ -z "$package" ]; then
  adb shell pm list packages -3
  echo "EMULATOR CHECK FAILED: the app's package was not found after the install"; exit 1
fi
echo "package: $package"
: > "$out/report.txt"
failed=""

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

# start_and_check NAME: stops the app, starts it, waits for its report, keeps a screenshot and the log.
start_and_check() {
  local name="$1" report
  adb shell am force-stop "$package"
  adb logcat -c
  adb shell monkey -p "$package" -c android.intent.category.LAUNCHER 1 > /dev/null
  if report="$(wait_for_report)"; then
    echo "$name: $report" | tee -a "$out/report.txt"
    echo "$report" | grep -q 'BATTLE DICE SELF-CHECK OK' || failed="$failed $name"
  else
    echo "$name: no self-check report within $limit seconds (see ${name}_logcat.txt)" | tee -a "$out/report.txt"
    failed="$failed $name"
  fi
  sleep "$pause"
  adb exec-out screencap -p > "$out/$name.png"
  adb logcat -d > "$out/${name}_logcat.txt"
  # Which layout the app chose, in its own words (the last one it reported in this start).
  screen="$(tr -d '\r' < "$out/${name}_logcat.txt" | grep -o 'BATTLE DICE SCREEN: .*' | tail -n 1 || true)"
  echo "$name: ${screen:-the app reported no layout}" | tee -a "$out/report.txt"
}

start_and_check 1_upright

# The system font size, larger: the app must follow it (a go or no-go check).
adb shell settings put system font_scale 1.3
start_and_check 2_larger_font
adb shell settings put system font_scale 1.0

# Sideways.
adb shell settings put system accelerometer_rotation 0
adb shell settings put system user_rotation 1
start_and_check 3_sideways
adb shell settings put system user_rotation 0

if [ -z "$failed" ]; then
  echo "EMULATOR CHECK OK: three starts, three passed self-checks" | tee -a "$out/report.txt"; exit 0
fi
echo "EMULATOR CHECK FAILED: no passed self-check at:$failed" | tee -a "$out/report.txt"; exit 1
