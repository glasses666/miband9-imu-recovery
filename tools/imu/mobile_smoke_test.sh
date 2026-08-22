#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
APK="$ROOT/app/build/outputs/apk/mainline/debug/app-mainline-debug.apk"
PKG="nodomain.freeyourgadget.gadgetbridge.hfimu"

if ! command -v adb >/dev/null 2>&1; then
  echo "adb not found" >&2
  exit 1
fi

if [[ ! -f "$APK" ]]; then
  echo "APK not found: $APK" >&2
  echo "Build it first:" >&2
  echo "  JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home ./gradlew --no-daemon :app:assembleMainlineDebug" >&2
  exit 1
fi

echo "== adb devices =="
adb devices -l

state_count="$(adb devices | awk 'NR>1 && $2=="device" {n++} END {print n+0}')"
if [[ "$state_count" -eq 0 ]]; then
  echo "No authorized Android device. Unlock the phone and accept the USB debugging RSA prompt." >&2
  exit 2
fi

echo "== installing recovery APK as $PKG =="
adb install -r "$APK"

echo "== launching recovery app =="
adb shell monkey -p "$PKG" 1 >/dev/null || true

echo "== next steps =="
echo "1. Open Gadgetbridge, enable Intent API debug commands if using tools/imu/send_imu_cmd.py."
echo "2. Pair/connect Xiaomi Smart Band 9 through the recovered Classic/SPP path."
echo "3. Trigger Debug -> Test New Function, or run:"
echo "   python3 tools/imu/send_imu_cmd.py --init"
echo "4. Watch logcat with:"
echo "   adb logcat -v time MI_IMU_RAW_RX:I MI_IMU_STATS:I MI_IMU_PARSE:I AndroidRuntime:E '*:S'"

echo "== starting filtered logcat; Ctrl-C to stop =="
adb logcat -v time MI_IMU_RAW_RX:I MI_IMU_STATS:I MI_IMU_PARSE:I AndroidRuntime:E '*:S'
