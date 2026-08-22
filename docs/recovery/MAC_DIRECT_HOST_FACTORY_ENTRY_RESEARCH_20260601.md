# Mi Band 9 host-reachable factory/debug entry research (2026-06-01)

## Scope

Read-only search for an免-patch host entry that might reach lower-level firmware sensor / factory / uORB paths after the SportXms app/protocol matrix failed to change the 10-sample / ~100 ms packet cadence.

No firmware patching, flashing, OTA write, or factory-mode live write was performed in this pass.

## Inputs

- Mi Fitness JADX tree: `/tmp/mihealth_jadx_20260530/sources`
- Firmware string index: `/tmp/miband9_firmware_deep_index_20260601_2205_repo_tool`
- ROMFS extraction: `/tmp/miband9_romfs_extract_20260601_2205_repo_tool`
- Firmware static diagnostic scan report: `/tmp/miband9_static_diag_scan_report.md`
- Live BLE discovery sanity artifact: `/tmp/miband9_host_entry_ble_discover_20260601_221443`
- Local protocol repo: `/path/to/local-user/workspace/miband9-imu-recovery`

## Bottom line

A real host-reachable Mi Fitness debug/factory command family exists: `hns.e = 13`, sent through `DeviceContact`, which is the same authenticated/encrypted Xiaomi transport family we can already drive from macOS over RFCOMM/SPP.

This is the strongest免-patch host entry found so far.

However, the current static pass still does **not** prove a host command that reaches the firmware's raw IMU factory routines (`OPR_READ_DATA`, `lsm6dso_factory_old_test_*`) or the `uorb_listener -b <latency>` path. The known host commands are log/media/CTA/NFC/brightness/factory-mode style commands; only log/media/CTA reads are plausibly safe-ish, and none are sensor-latency knobs.

## Mi Fitness `hns.e = 13` command family

### Factory test page

Source: `/tmp/mihealth_jadx_20260530/sources/com/xiaomi/fitness/devicesettings/bluttooth/factory/FactoryTestFragment.java`

`FactoryTestFragment` contains a hidden/debug factory page. It sends `hns` packets through `DeviceContact`:

- `doFactoryMode(factoryMode)`
  - lines 54-72
  - `hns.e = 13`
  - `hns.f = 0`
  - payload: `iq9.s(factoryMode)` = `iq9` field 1 varint
  - UI wires modes `2`, `0`, `1`, `4`
  - risk: state-changing / unknown semantics
- `dumpDeviceLog()`
  - lines 75-96
  - `hns.e = 13`
  - `hns.f = 2`
  - likely read/debug-ish, but can trigger log-transfer workload
- `dumpMediaLog()`
  - lines 98-119
  - `hns.e = 13`
  - `hns.f = 4`
  - likely read/debug-ish but heavier than device-log dump
- `setBrightness(value)`
  - lines 193-239
  - `hns.e = 13`
  - `hns.f = 5`
  - payload: `iq9.r(value)` = `iq9` field 6 varint
  - state-changing but reversible; irrelevant to sensor latency

### NFC config upload

Source: `/tmp/mihealth_jadx_20260530/sources/com/xiaomi/fitness/devicesettings/bluttooth/factory/FactoryTestViewModel.java`

- `nfcConfig(fileName, callback)`
  - lines 90-128
  - `hns.e = 13`
  - `hns.f = 1`
  - payload: `iq9.t(kq9.a)` map-like NFC config payload
  - state-changing / not sensor related

### CTA app debug page

Source: `/tmp/mihealth_jadx_20260530/sources/com/xiaomi/fitness/devicesettings/base/cta/DeviceInstallAPPInfoDebugViewModel.java`

- `getCTAAppList()` coroutine body
  - lines 140-166
  - `hns.e = 13`
  - `hns.f = 9`
  - parses returned `iq9.p()` CTA app list
  - read-ish, not sensor related
- `subscribeAppBehavior()`
  - lines 240-243
  - `hns.e = 13`
  - `hns.f = 12`
  - subscription / streaming debug path, not sensor related
- `unSubscribeAppBehavior()`
  - lines 317-320
  - `hns.e = 13`
  - `hns.f = 13`
  - subscription cleanup, not sensor related

Associated UI handler: `/tmp/mihealth_jadx_20260530/sources/com/xiaomi/fitness/devicesettings/base/cta/DeviceInstallAPPBehaviorDebugFragment.java`

- Adds a data handler for `type = 13` around line 473.
- Removes it on destroy around line 464.
- This confirms type 13 can return async/debug data, but the observed CTA behavior is app-behavior data, not raw IMU/uORB.

## Protobuf-nano wire shape

`hns.java` / `iq9.java` confirm the encoding used in the local skeleton:

- `hns` field 1 = command type (`e`)
- `hns` field 2 = subtype (`f`)
- `hns` field 15 = `iq9`
- `iq9` field 1 = factory mode value
- `iq9` field 6 = brightness value

Minimal plaintext command bodies:

- factory dump: `08 0d 10 02`
- factory media dump: `08 0d 10 04`
- factory mode 2: `08 0d 10 00 7a 02 08 02`
- brightness 42: `08 0d 10 05 7a 02 30 2a`
- CTA app list: `08 0d 10 09`
- CTA subscribe behavior: `08 0d 10 0c`
- CTA unsubscribe behavior: `08 0d 10 0d`

These are plaintext `hns` bodies only. On the live Mac path they still need the existing auth/session + encryptV2 + RFCOMM/SPP frame wrapping.

## Firmware raw/factory/uORB evidence

Source firmware: `/tmp/miband9_windows_firmware_20260601_2140/extracted/vela_ap.bin`

### uORB listener / report latency

`uorb_listener` is compiled in as a NuttX/NSH-style builtin/diagnostic app:

- `0x4e65a5`: `uorb_listener`
- nearby builtin-style command list:
  - `loadfactoryinfo`
  - `setfactoryinfo`
  - `setlogmask`
  - `setprop`
  - `touchpoint`
  - `uorb_listener`
  - `uorb_unit_test`
  - `watchpoint`
- help strings around `0x507b6d`:
  - `Utility to listen on uORB topics and print the data to the console.`
  - `The listener can be exited any time by pressing Ctrl+C, Esc, or Q.`
  - `uorb_listener <t1,t2,...> -n 1`
  - `[-r <val>] Subscription rate (unlimited if 0), default: 0`
  - `[-b <val>] Subscription maximum report latency in us(unlimited if 0), default: 0`
  - `[-t <val>] Time of listener, in seconds, default: 5`

Relevant uORB paths/topics:

- `/dev/usensor`
- `/dev/uorb/%s%d`
- `/dev/uorb/%s`
- `/dev/uorb/sensor_%s%s%d`
- `sensor_accel`
- `sensor_accel_uncal`
- `sensor_gyro`
- `sensor_gyro_uncal`

Interpretation: `uorb_listener` has exactly the report-latency knob we care about, but it appears to be an internal console/NSH command. No host path to execute it was proven.

### LSM6DSO raw/factory IMU routines

The LSM6DSO driver area contains raw/factory operation strings:

- source clue: `platform/sensors/imu/lsm6dso/lsm6dso.c`
- `factory old test acc/gyro started`
- `factory old test acc/gyro stop`
- `In lsm6dso_factory_test: %d`
- `In OPR_CALIBRATION`
- `raw[%d]:%ld %ld %ld`
- `In OPR_READ_DATA`
- `IN Fill raw data: %d`
- `In OPR_READ_CALDATA`
- `lsm6dso_factory_old_test_start`
- `lsm6dso_factory_old_test_read`
- `lsm6dso_factory_old_test_stop`

Nearby batching/FIFO/latency strings:

- `wtm:%ld , batch_min:%ld, interval:%ld, imu_activat:%d`
- `# bmi270 batch change to :%ld, interval desired:%ld`
- `lsm6dso_batch_calcu, latency:%ld,interval:%ld, batch_num:%lu`
- `batch_desired:%ld , latency_us:%ld`
- `bmi270 status, Int cnt:%llu,interval:%d,wtm:%ld,batch:%d,activated:%d`
- `lsm6dso status, Int cnt:%llu,interval:%d,wtm:%ld,batch:%d,activated:%d`

Interpretation: raw/factory accel+gyro paths definitely exist in firmware, but this pass did **not** prove that Mi Fitness `hns.e=13` factory commands call those exact routines.

## Diagnostic shell / console / CLI clues

NuttX NSH shell strings exist:

- `NSH command forms:`
- `Builtin Apps:`
- `nsh_consolemain.c`
- `NuttShell (NSH) NuttX-3.6.1`
- shell prompt string: `ap>`

Other relevant clues:

- `bttool`
- BT diagnostic/log/help strings
- `RFCOMM:4` in a BT profile/protocol log enum
- `/dev/pts/%d`
- `/dev/pty%d`

Verdict: there is an embedded NSH/CLI environment and BT diagnostic tooling, but no proven host-exposed console path was found. Treat as internal/debug firmware capability only.

## GATT / SPP / RFCOMM clues

Firmware has substantial MiWear Bluetooth/GATT/SPP/RFCOMM support:

- GATT:
  - `BT_GATT`
  - `GATTS`
  - `GATTC`
  - `android binded, miwear gatt service shouldn't be accessed`
  - `gatts_write_request_callback`
- SPP/RFCOMM:
  - `SPP Connected`
  - `SPP Disconnected`
  - `rfcomm_pty_read_start`
  - `rfcomm_pty_read_stop`
  - `EVENT_SPP_CONNECTED`
  - `EVENT_SPP_DISCONNECTED`
  - `wechat rfcomm server start/stop/disconnect/send data`
  - `rfcomm_send`
  - `btspp://`
  - `bluelet_rfcomm_server_start`

Important caveat: these strings prove Bluetooth plumbing and align with the known macOS RFCOMM channel, but they do not tie NSH/uORB/raw-factory commands to the Xiaomi host protocol.

## HMPro / FEE0 verdict

Mi Fitness still has the HMPro static profile (`x6v` / `n6v`), but no new evidence validates it for Band 9 raw IMU:

- Mac CoreBluetooth sanity pass did not expose HMPro/FEE0:
  - artifact: `/tmp/miband9_host_entry_ble_discover_20260601_221443`
  - `has_fee0 = False`
  - `has_0001_3512 = False`
  - `has_0002_3512 = False`
- Firmware/ROMFS scan did not show meaningful `FEE0` / `af100700` / `3512` code/config hits.
- `3512` firmware hits were font/timezone/resource false positives.
- `HMPro`/`hmpro` firmware hits were watchface/resource false positives.

Verdict: HMPro/FEE0 remains a static App/profile shadow, not a safe live path.

## Gadgetbridge / local protocol verdict

`app/src/main/proto/xiaomi.proto` has a generic `Command` with `type` and `subtype`, plus named System/Health/etc. families, but no first-class `Factory`, `Debug`, `Diagnostic`, `Shell`, `Raw`, `uORB`, or `HMPro` message family equivalent to Mi Fitness `hns.e=13`.

Local Gadgetbridge debug plumbing can send arbitrary protobuf-channel bytes:

- `DeviceService.ACTION_DEBUG_SEND_RAW_PROTOBUF_COMMAND`
- `DeviceCommunicationService` dispatches it to device support
- `XiaomiSupport.onDebugSendRawProtobufCommand()` -> `sendDebugRawProtobufCommand()`
- `XiaomiSppSupport.sendRawProtobufCommandBytes(...)` uses `Channel.ProtobufCommand`
- `XiaomiBleSupport.sendRawProtobufCommandBytes(...)` can use SAR write support

Local macOS protocol tooling has the lower transport pieces (`A5A5`, channel framing, `encryptV2`/`decryptV2`) but intentionally keeps factory `hns` skeletons offline/plaintext only. A live factory-log gate still needs the existing auth/session/encrypted wrapper.

## Added tooling

- `tools/miband9ctl/factory_command_skeleton.py`
  - builds discovered plaintext `hns.e=13` command bodies
  - deliberately warns these are not raw BLE/RFCOMM frames
  - supports factory dump/media dump/mode/brightness and CTA app-list subscribe/unsubscribe skeletons
- `tools/miband9ctl/tests/test_factory_command_skeleton.py`
  - verifies exact `hns` hex for the mapped command bodies

## Risk classification

- `hns.e=13 f=2` device-log dump: likely read/debug-ish, but may trigger a log-transfer flow and extra device workload.
- `hns.e=13 f=4` media-log dump: likely read/debug-ish, but may trigger a larger media-log transfer.
- `hns.e=13 f=9` CTA app list: read-ish but not sensor related.
- `hns.e=13 f=12/13` CTA subscribe/unsubscribe: subscription/debug behavior path; not sensor related.
- `hns.e=13 f=0` factory mode `0/1/2/4`: **state-changing / risky** until mode semantics are known.
- `hns.e=13 f=1` NFC config upload: **state-changing / not sensor related**.
- `hns.e=13 f=5` brightness: state-changing but reversible; irrelevant to sensor latency.

## Recommended next gate

1. Do **not** live-run factory mode `0/1/2/4`, NFC config, or any unknown subtype.
2. If a live gate is desired, first run only `hns.e=13 f=2` device-log dump through the existing macOS auth/RFCOMM wrapper, with:
   - short timeout,
   - capture-only artifact,
   - no SportXms start,
   - no factory mode change,
   - no log/media/factory fuzzing,
   - parse only response status / packet type locally.
3. If the dump response contains firmware task logs, inspect whether `sensor`, `uorb`, `lsm6dso`, `batch`, `watermark`, or `factory` strings surface in the returned artifact.
4. Only if logs reveal a command dispatcher or factory-mode semantics should we consider a separate explicit approval for factory-mode live tests.

## Live gate: `hns.e=13 f=2` device-log dump

A single approved live gate was run through the proven macOS RFCOMM/SPP path:

- artifact: `/tmp/miband9_factory_dump_gate_20260602_000631/factory_dump_rfcomm5`
- transport: macOS IOBluetooth RFCOMM channel 5
- sequence: auth/session -> encrypted `hns.e=13 f=2`
- no SportXms start
- no factory mode
- no NFC config / brightness / media dump / subtype fuzzing
- short capture window after the dump command was queued

Redacted summary:

```json
{
  "connected": true,
  "auth_step3_queued": true,
  "factory_dump_queued": true,
  "notification_count": 7,
  "frame_count": 11,
  "unique_frame_count": 11,
  "encrypted_protobuf_decoded_count": 5,
  "command_type_subtype_counts": {
    "2/42": 1,
    "10/3": 1,
    "17/7": 2,
    "18/0": 1
  },
  "keyword_hit_counts": {},
  "plaintext_lengths": [4, 12, 13],
  "finish_reason": "post_auth_complete"
}
```

Interpretation:

- The command was queued successfully after auth.
- The capture window did not show a decoded `13/*` response.
- No decrypted plaintext contained the target keywords `sensor`, `uorb`, `lsm6dso`, `bmi270`, `batch`, `watermark`, `factory`, `OPR`, `raw`, `wtm`, `latency`, `gyro`, or `accel`.
- The observed decoded packets match the same background metadata families seen in earlier encrypted sanity runs, not a useful log payload.

This live gate therefore does **not** prove a safe host path to raw IMU/uORB/factory sensor routines.

## Current conclusion

The免-patch host-entry search found a real type-13 factory/debug family, but not a proven raw-IMU/uORB command path. Current evidence supports this split:

- host-reachable: `hns.e=13` debug/factory family over DeviceContact / encrypted Xiaomi transport;
- firmware-internal: `uorb_listener`, NSH console, LSM6DSO raw factory old-test, `OPR_READ_DATA`;
- live-tested safe-ish bridge: `hns.e=13 f=2` device-log dump was queued but did not return sensor/uORB/factory evidence in the short capture window;
- unproven/risky bridge: factory mode `hns.e=13 f=0` modes `0/1/2/4` remain state-changing and should not be run without a separate risk decision.

Do not keep guessing type-13 subtypes. The next branch is read-only binary call-graph / patch-and-rollback feasibility. Patch/flash remains out of scope until explicit authorization, original firmware package/signing understanding, and rollback/recovery are prepared.

## Verification

```text
PYTHONPATH=tools/miband9ctl:tools/mac_direct python3 -m unittest discover -s tools/miband9ctl/tests
Ran 63 tests ... OK

PYTHONPATH=tools/miband9ctl python3 -m unittest tools/miband9ctl/tests/test_factory_command_skeleton.py
Ran 8 tests ... OK

swiftc tools/mac_direct/rfcomm_auth_probe.swift -o /tmp/rfcomm_auth_probe_factory_gate
OK
```
