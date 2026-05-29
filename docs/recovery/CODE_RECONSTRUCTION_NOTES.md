# Code Reconstruction Notes

This branch contains the first buildable-style re-port of the lost APK logic back onto the clean Gadgetbridge source tree.

## Implemented in source

- `AbstractBTBRDeviceSupport` / `BtBRQueue`
  - Added optional direct RFCOMM port support.
  - Channel 5 is reached through Android's hidden `BluetoothDevice.createRfcommSocket(int)` reflection path, with UUID fallback.
- `XiaomiConnectionSupport`
  - Added a `sendRawBytes(...)` hook so debug code can write a raw recovered frame through SPP.
- `XiaomiSppSupport`
  - Uses direct RFCOMM channel 5 in this recovery branch.
  - Logs all socket bytes to Android logcat tag `MI_IMU_RAW_RX`.
  - Routes Activity-channel payloads to a local IMU debug broadcast.
  - Exposes `ACTION_DEBUG_IMU_DATA` for the debug Activity.
- `XiaomiSupport`
  - `DebugActivity` → Test New Function now sends the recovered Mi Band 9 RFCOMM init frame.
  - Opens the IMU debug Activity after sending.
- `ImuDebugActivity` + `activity_imu_debug.xml`
  - Minimal recovered live display for accel/gyro/raw/rate data.

## Not yet implemented

- The GameSir/`865F`/`FF12` trigger logic is preserved under `docs/recovery/references/apk-decompiled-critical/` but not yet re-ported into clean source. That should be a separate commit because it is a different BLE side-channel experiment.
- The ADB broadcast receiver expected by `tools/imu/send_imu_cmd.py` is not yet re-ported. For now, the supported trigger is Gadgetbridge DebugActivity → Test New Function.
- Firmware/ODR patching is documentation/tooling only until original firmware and rollback artifacts are recovered.

## Expected first manual verification after Android SDK/device setup

1. Build/install the recovery APK.
2. Pair Mi Band 9 in Gadgetbridge with the Mi Band 9 coordinator.
3. Open Gadgetbridge Debug Activity and press Test New Function.
4. Watch:
   - `adb logcat -s MI_IMU_RAW_RX MI_IMU_STATS Gadgetbridge`
   - `python3 tools/imu/live_imu_forwarder.py`
5. Record whether packets appear, approximate Hz, and whether values contain gyro-like channels.
