#!/usr/bin/env bash
# Phase 0 of docs/android/PLAN.md, on an Android emulator: install the APK, start the app, read its
# self-check report from the device log, and keep screenshots (upright, with a larger system font,
# sideways). Usage: emulator_check.sh APK OUTPUT_FOLDER
set -uo pipefail
apk="$1"; out="$2"; mkdir -p "$out"

adb install -r "$apk" || { echo "EMULATOR CHECK FAILED: the APK did not install"; exit 1; }
package="$(adb shell pm list packages -3 | tr -d '\r' | sed 's/^package://' | grep -i -m1 battle || true)"
if [ -z "$package" ]; then
  adb shell pm list packages -3
  echo "EMULATOR CHECK FAILED: the app's package was not found after the install"; exit 1
fi
echo "package: $package"

start_app() {
  adb shell am force-stop "$package"
  adb logcat -c
  adb shell monkey -p "$package" -c android.intent.category.LAUNCHER 1 > /dev/null
}

# Waits for the app's report line; prints it. Up to 5 minutes: the first start unpacks the app.
wait_for_report() {
  local started=$SECONDS
  while [ $((SECONDS - started)) -lt 300 ]; do
    line="$(adb logcat -d | tr -d '\r' | grep -m1 'BATTLE DICE SELF-CHECK' || true)"
    if [ -n "$line" ]; then echo "$line"; echo "seconds_until_report: $((SECONDS - started))"; return 0; fi
    sleep 5
  done
  return 1
}

start_app
if ! report="$(wait_for_report)"; then
  adb logcat -d > "$out/logcat_no_report.txt"
  adb exec-out screencap -p > "$out/no_report.png"
  echo "EMULATOR CHECK FAILED: no self-check report within 5 minutes (see logcat_no_report.txt)"; exit 1
fi
echo "$report" | tee "$out/report.txt"
sleep 3
adb exec-out screencap -p > "$out/1_upright.png"
adb logcat -d > "$out/logcat_first_start.txt"

# The system font size, larger: the app must follow it (a go or no-go check).
adb shell settings put system font_scale 1.3
start_app; wait_for_report > /dev/null || true; sleep 3
adb exec-out screencap -p > "$out/2_larger_font.png"
adb shell settings put system font_scale 1.0

# Sideways.
adb shell settings put system accelerometer_rotation 0
adb shell settings put system user_rotation 1
start_app
second="$(wait_for_report || true)"; sleep 3
adb exec-out screencap -p > "$out/3_sideways.png"
adb shell settings put system user_rotation 0
echo "second start: $second" | tee -a "$out/report.txt"

if echo "$report" | grep -q 'BATTLE DICE SELF-CHECK OK'; then
  echo "EMULATOR CHECK OK"; exit 0
fi
echo "EMULATOR CHECK FAILED: the app reported a failed self-check"; exit 1
