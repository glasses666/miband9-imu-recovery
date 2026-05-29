# Static audit — recovered Mi Band 9 SPP/IMU debug path

Generated: 2026-05-29 10:42 CST

## Verdict

Static/build audit passes for the Mac-side continuation node.

The recovered source is now stronger than the first APK-oracle port because it includes:

- buildable Android SDK configuration
- fixed JitPack dependency resolution for `GBDaoGenerator`
- app-side ADB raw-byte command receiver
- safer raw-byte dispatch with exception handling
- separate packet-rate and total-packet counters
- one-command install/logcat smoke helper

## Verified

Command:

```bash
JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home \
  ./gradlew --no-daemon :app:assembleMainlineDebug
```

Result:

```text
BUILD SUCCESSFUL
```

APK:

```text
app/build/outputs/apk/mainline/debug/app-mainline-debug.apk
sha256 f121a2707dd643612df44082e3234e1e295ef243444dce973bc6b06dad4c87b8
```

Static checks:

```text
git diff --check: clean
python3 -m py_compile tools/imu/send_imu_cmd.py tools/imu/live_imu_forwarder.py: clean
bash -n tools/imu/mobile_smoke_test.sh: clean
```

## Code path map

### Connection path

- `MiBand9Coordinator.getConnectionType()` returns `BT_CLASSIC`.
- `XiaomiSupport.createConnectionSpecificSupport()` selects `XiaomiSppSupport` for `BT_CLASSIC`.
- `XiaomiSppSupport` constructs `AbstractBTBRDeviceSupport(LOG, 1024, 5)`.
- `BtBRQueue` uses reflective `createRfcommSocket(int)` when a direct port is provided.

### Init/debug-send path

UI path:

```text
DebugActivity → GBApplication.deviceService().onTestNewFunction()
→ GBDeviceService ACTION_TEST_NEW_FUNCTION
→ DeviceCommunicationService
→ ServiceDeviceSupport
→ XiaomiSupport.onTestNewFunction()
→ sendDebugRawBytes(MI_BAND9_IMU_RFCOMM_INIT)
```

ADB hot command path:

```text
adb shell am broadcast -a nodomain.freeyourgadget.gadgetbridge.SEND_IMU_CMD --es hex <hex>
→ IntentApiReceiver
→ GBApplication.deviceService().onDebugSendRawBytes(bytes)
→ GBDeviceService ACTION_DEBUG_SEND_RAW_BYTES
→ DeviceCommunicationService
→ ServiceDeviceSupport
→ XiaomiSupport.onDebugSendRawBytes(bytes)
→ XiaomiSppSupport.sendRawBytes(bytes)
```

### Receive/log path

```text
BtBR socket read
→ XiaomiSppSupport.onSocketRead(data)
→ Log.i("MI_IMU_RAW_RX", hexdump(data))
→ protocol parser
→ Activity channel handler
→ handleImuData(payload)
→ LocalBroadcast ACTION_DEBUG_IMU_DATA
→ ImuDebugActivity UI
```

## Intent/API caveat

The ADB hot command receiver is guarded by Gadgetbridge's existing debug-command preference:

```text
intent_api_allow_debug_commands
```

If this is disabled, `tools/imu/send_imu_cmd.py` will broadcast successfully at the Android shell level but the app will ignore it and log:

```text
Intent API Allow Debug Commands not allowed
```

On the rooted phone, this can be toggled in-app first. If needed later, use root/ADB to set the app preference only after confirming the installed package/data path.

## Remaining static risks

1. Activity-channel classification is broad.

   `XiaomiSppSupport` still treats Activity-channel payloads as candidate IMU payloads. This is intentional for early raw visibility but not enough for final proof. The first live capture must classify payload structure before claiming real IMU.

2. Packet/sec is not sample/sec.

   Counters now separate packet window rate and total packets, but final parser still needs sample count per packet and gyro field validation.

3. JitPack `fyg-SNAPSHOT` is build-pragmatic, not ideal provenance.

   It restores buildability because the pinned commit coordinate currently 404s. For a durable public/reproducible repo, vendor or publish the exact greenDAO jar and pin by hash.

4. ADB device is present but unauthorized.

   Current `adb devices -l` saw:

   ```text
   c8f9a1da unauthorized usb:0-1 transport_id:1
   ```

   No install/logcat action can proceed until the phone accepts the USB debugging RSA prompt.

## Helper added

```text
tools/imu/mobile_smoke_test.sh
```

It performs:

1. authorized-device check
2. APK install
3. next-step prompt
4. filtered logcat for `MI_IMU_RAW_RX`, `MI_IMU_STATS`, `MI_IMU_PARSE`, and `AndroidRuntime`

It intentionally does not try to force phone authorization or modify rooted app preferences.
