# Mac-side ready state — Mi Band 9 HF IMU recovery

Generated: 2026-05-29 10:38 CST

## Bottom line

The Mac side is now ready for the next phone/band test cycle.

The recovery APK builds successfully on Draco, and the recovered app now has two usable debug entry paths:

1. UI / existing debug path:
   - Gadgetbridge Debug menu → Test New Function
   - routes to `XiaomiSupport.onTestNewFunction()`
   - sends the recovered Mi Band 9 RFCOMM init frame
   - opens `ImuDebugActivity`

2. ADB hot command path:
   - `tools/imu/send_imu_cmd.py`
   - sends `nodomain.freeyourgadget.gadgetbridge.SEND_IMU_CMD`
   - app-side `IntentApiReceiver` now parses the `hex` extra and routes raw bytes into the active Xiaomi SPP connection

## Environment fixed on Mac

Android SDK root:

```text
/opt/homebrew/share/android-commandlinetools
```

Installed SDK pieces needed by this repo:

```text
platforms;android-34
build-tools;34.0.0
platform-tools
```

Local Gradle SDK pointer:

```text
local.properties
sdk.dir=/opt/homebrew/share/android-commandlinetools
```

`local.properties` is ignored by git and intentionally not committed.

JDK used for build:

```text
/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home
```

## Build blocker fixed

Initial compile failed because Gadgetbridge 0.83.0 referenced a JitPack commit coordinate that now returns 404:

```text
com.github.Freeyourgadget:greendao:1998d7cd2d21f662c6044f6ccf3b3a251bbad341
```

The `fyg` branch on `Freeyourgadget/greenDAO` still points at that commit, and JitPack resolves:

```text
com.github.Freeyourgadget:greendao:fyg-SNAPSHOT
```

So `GBDaoGenerator/build.gradle` was patched to use `fyg-SNAPSHOT`. This is a pragmatic recovery-build fix; if long-term reproducibility matters, vendor or publish the exact jar later.

## Verified commands

Compile:

```bash
cd <repo>
JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home \
  ./gradlew --no-daemon :app:compileMainlineDebugJavaWithJavac
```

Result:

```text
BUILD SUCCESSFUL
```

Assemble:

```bash
cd <repo>
JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home \
  ./gradlew --no-daemon :app:assembleMainlineDebug
```

Result:

```text
BUILD SUCCESSFUL
```

APK:

```text
<repo>/app/build/outputs/apk/mainline/debug/app-mainline-debug.apk
```

APK SHA-256 after ADB hot-command receiver patch and packet-counter fix:

```text
f121a2707dd643612df44082e3234e1e295ef243444dce973bc6b06dad4c87b8
```

Latest build log:

```text
/tmp/miband9_assemble_mainline_debug_20260529_104257.log
```

## Current device state

`adb devices -l` sees the rooted Android phone but it is not authorized yet:

```text
c8f9a1da unauthorized usb:0-1 transport_id:1
```

The next physical step is simply to unlock the Android phone and accept the USB debugging RSA prompt. Until that is done, Mac cannot install the APK or read logcat from that phone.

## Next physical test sequence

After the phone is authorized and the band is charged:

```bash
cd <repo>
adb devices -l
adb install -r app/build/outputs/apk/mainline/debug/app-mainline-debug.apk
```

Then in Gadgetbridge:

1. Enable Intent API debug commands if using the ADB hot command path.
2. Pair/connect Xiaomi Smart Band 9 via the recovered Classic/SPP path.
3. Trigger Debug → Test New Function, or use:

```bash
python3 tools/imu/send_imu_cmd.py --init
```

Watch logcat:

```bash
adb logcat -v time MI_IMU_RAW_RX:I MI_IMU_STATS:I MI_IMU_PARSE:I AndroidRuntime:E '*:S'
```

Or run the existing forwarder:

```bash
python3 tools/imu/live_imu_forwarder.py
```

## What this proves / does not prove

Proves now:

- The recovery repo is buildable on Mac.
- The restored source compiles.
- The APK assembles.
- The old PC-side hot command script now has an app-side receiver again.

Does not prove yet:

- Phone install works on the rooted Android.
- Band pairs correctly through the recovered Classic/SPP route.
- Channel 5 opens on this phone/Android build.
- `MI_IMU_RAW_RX` appears from a live band.
- Sample rate exceeds the old ~50 Hz ceiling.
- Payload contains real gyro/raw samples rather than another activity-frame variant.
