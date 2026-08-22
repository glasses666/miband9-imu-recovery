# Mi Band 9 macOS direct: SportXms exhaustive variants, HMPro gate, and firmware static index

Date: 2026-06-01

## Verdict

The macOS direct IMU path is still proven through RFCOMM/SPP channel 5:

```text
Mi Band 9 -> macOS IOBluetooth RFCOMM channel 5 -> Xiaomi SPP V2 auth/session -> encrypted SportXms start -> 8/53 IMU -> encrypted SportXms stop -> quiet-after
```

The remaining SportXms/App protobuf surface has now been tested enough to stop guessing there. No tested field changed the observed `10 accel + 10 gyro samples per 8/53 packet` / ~100 ms batch cadence.

The next serious route is firmware/static sensor-service research. This report keeps that step read-only: no firmware patching, no flashing, and no destructive OTA/device writes.

## Safety and redaction

- Raw authkey, nonces, session keys, encrypted session material, app private DB dumps, and device identifiers remain local-only and are not printed here.
- Android private-data files were only inspected for firmware/update metadata, with sensitive values redacted or omitted.
- Firmware work in this pass was read-only static indexing. No patch/flash/OTA start was attempted.

## SportXms variant coverage

Earlier tested variants:

- `selectVersion`: omitted, `2`, `3`, `4`
- `accessoryWearMode`: `0`, `3`
- `sportType`: `810`, `812`

Additional safe matrix tested before this report:

- `selectVersion`: `1`, `5`
- `accessoryWearMode`: `1`, `2`
- hfa field 7 `sportTarget` / `nfa` submessage:
  - target type `1` pace, value `1`
  - target type `2` duration, value `60`
  - target type `3` distance, value `100`
  - target type `4` calories, value `1`
  - target type `5` round count, value `1`
  - target type `6` count, value `1`
  - target type `7` cadence, value `100`
- hfa field 9 `sportLaunchType`: `2`, `6`
- timezone value: `0`

Artifact root:

```text
/tmp/miband9_sportxms_exhaustive_matrix_20260601_205634
```

Observed invariant across successful variants:

- Each run followed `auth -> encrypted start -> short capture -> encrypted stop -> quiet-after`.
- Each successful capture still produced `8/53` IMU packets.
- Each decoded `8/53` packet still carried 10 accel and 10 gyro samples.
- Short-run packet cadence stayed around the same ~100 ms class.
- Final quiet-after showed no residual `8/53` stream.

Conclusion: the tested SportXms protobuf fields are metadata/mode fields, not batch/cadence controls.

## Code changes for sourced variants

The local builders were extended so future sourced variants can be tested without hand-editing encrypted payload hex:

- `tools/miband9ctl/sportxms_812_packet_skeleton.py`
  - added hfa field 7 `sport_target_type` / `sport_target_value`
  - added hfa field 9 `sport_launch_type`
- `tools/mac_direct/build_auth_step3_from_events.py`
  - added `--sportxms-target-type`
  - added `--sportxms-target-value`
  - added `--sportxms-launch-type`
- `tools/miband9ctl/tests/test_sportxms_packet_skeleton.py`
  - added protobuf-fragment tests for field 7 and field 9

These are protocol-construction helpers only; they do not embed any secret material.

## HMProSensorDataProfile gate

Static Mi Fitness/JADX evidence still identifies `HMProSensorDataProfile` as a lower-level candidate:

- Candidate classes:
  - `x6v.java` -> profile-like implementation
  - `n6v.java` -> controller-like wrapper
- Candidate BLE UUIDs:
  - service `0000fee0-0000-1000-8000-00805f9b34fb`
  - control `00000001-0000-3512-2118-0009af100700`
  - data `00000002-0000-3512-2118-0009af100700`
- Candidate command shapes:
  - old config: `[0x01, sensorMask_low8, modeByte]`
  - new config: `[0x01, sensorMask LE32, modeByte]`
  - start: `[0x02]`
  - stop: `[0x03]`
  - watchdog/keepalive: `[0x00]`
- Candidate masks:
  - `GSENSOR = 1`
  - `GYRO = 16`
  - `TIME = 128`
  - accel + gyro = `17`
  - accel + gyro + time = `145`

Safety result:

- No convincing real Mi Band 9 App callsite was found that supplies a validated `sensorMask/modeByte` for this profile.
- A conservative CoreBluetooth discover gate did not see FEE0/control/data at that time.
- Therefore HMPro remains a candidate, not a validated low-latency route. Do not live-write HMPro commands unless a real call-chain or device-visible profile is found.

## Firmware/static index

### Local and Windows firmware artifact search

Read-only search scope included:

- repo working tree and historical recovery artifacts
- `/tmp/mihealth_jadx_20260530` Mi Fitness decompile
- Android Mi Fitness backup tar from the pre-unbind backup
- live rooted Mi Fitness private-data filename inventory, filtered for firmware/update terms
- user Downloads old Windows clue bundle zips and extracted folders
- Windows1 via SSH/Wake-on-LAN, scoped to known Mi Band / Gemini / WeChat / Downloads locations

Key result:

- The Mac-side imported Windows clue bundle did not contain the real firmware image.
- Windows1 did contain a real Mi Band 9 NFC OTA package:
  - Windows path: `C:\Users\user\Downloads\673e64214a0c42412771243b5f3a47bb_upd_miwear.watch.n66nfc.zip`
  - Local copied artifact: `/tmp/miband9_windows_firmware_20260601_2140/673e64214a0c42412771243b5f3a47bb_upd_miwear.watch.n66nfc.zip`
  - Size: `43,934,358` bytes
  - SHA-256: `8f8a20a8c690de2cd4e1bc6ddd3969e00fe9d55970ba0ccf4445a908ace37c23`
  - `ota.json`: `magic_string=n66`, `sw_version=1.3.210`, `firmware_type=all`
- Mi Fitness private data contained update preference/cache keys and firmware-version strings, but no cached firmware package URL or downloaded package file.
- External storage paths checked on the rooted Android phone did not contain a `miwear.watch.n66*` firmware package under the Mi Fitness download/cache paths.

Extracted OTA entries:

- `vela_ap.bin` — `6,742,976` bytes; `section_type=main_app`, `file_type=DOS`
- `app.bin` — `28,860,416` bytes
- `system.bin` — `3,320,832` bytes
- `vela_ota.bin` — `663,408` bytes; `section_type=main_bootloader`, `file_type=DOS`
- `vendor.bin` — `673,792` bytes
- `recovery.bin`, `i18n.bin`, `font.bin`, `quickapp.bin`, `misc.bin`, `watchface.bin`
- `version` — `res.version=1.0.2`

Local firmware index artifacts:

```text
/tmp/miband9_firmware_static_index_20260601_2110
/tmp/miband9_windows_firmware_20260601_2140
```

The first artifact contains redacted local metadata such as MMKV string summaries and hashes, not raw auth/session materials. The second contains the copied firmware zip, extracted files, and string-index hits from the firmware package.

### Product identity from local config

Mi Fitness product config identifies Mi Band 9 family entries:

- `miwear.watch.n66cn` -> 小米手环9
- `miwear.watch.n66nfc` -> 小米手环9 NFC版
- `miwear.watch.n66tc` -> 小米手环9 陶瓷特别版
- `miwear.watch.n67cn` -> 小米手环9 Pro

For the observed Band 9 entries, `ota_type` is `2`, so the normal Band 9 path uses the `CheckUpdateRequest` / `BluetoothOtaManager` flow rather than the X5/whippet `ota_type == 3` flow.

### Official app OTA path from decompiled Mi Fitness

A read-only unauthenticated probe of the normal Band 9 endpoint was attempted with model `miwear.watch.n66cn` and firmware version `1.3.206`; it returned HTTP `401 Unauthorized`, so obtaining the package likely requires the App's signed/authenticated request context or a captured official update response. A separate whippet/X5-shape request for `watch.n66cn` returned a successful HTTP envelope but an application error indicating the product library was absent, which matches the local product config: Band 9 `n66*` uses `ota_type=2`, not the X5 `ota_type=3` path.

For Bluetooth wearable devices, the App flow is:

1. `UpdateHelper.doUpdateRequest()` gets the current `WearableDeviceModel`.
2. For Bluetooth devices, it calls `readWatchInfo()` and requires `WatchInfo.firmwareVersion`.
3. It calls `requestLatestVersion(deviceModel, firmwareVersion, productDevice, ...)`.
4. For `ota_type != 3`, it calls:

```text
https://hlth.io.mi.com/healthapp/device/latest_ver
```

via `CheckupdateService.getLatestVersion(...)`.

The response model is `LatestVersion`, whose relevant fields include:

- `safe_url` -> full firmware package URL
- `diff_safe_url` -> diff package URL, if present
- `md5` / `diff_md5`
- `version`
- `changeLog`
- `fileSize`

Download behavior in `BluetoothOtaManager`:

- firmware file destination:

```text
Download/<DeviceModelExtKt.getModel(currentDevice)>/<md5><processName>
```

- `LatestVersion.getUrl()` chooses `diff_safe_url` if present, else `safe_url`.
- `LatestVersion.getMD5()` chooses `diff_md5` if `diff_safe_url` is present, else `md5`.

OTA send behavior in `DeviceSender`:

- `prepareOta(...)` builds hns command `e=2`, `f=5` with firmware version/md5/size/changelog metadata.
- `startOta(...)` uses either `HyOtaExecutor` or `GeneralOtaExecutor` depending on OTA mode.
- Related system/OTA queries include hns `e=2/f=90` and `e=2/f=14`, but these are upgrade-status/settings paths, not IMU batch-rate controls.

Conclusion: the official App OTA code gives the next path to obtain a firmware package (`safe_url`/`diff_safe_url`), but it is not itself a low-latency sensor configuration path.

## Firmware research implications

Because a real Band 9 NFC firmware package is now available locally from Windows1, the next firmware step is static indexing, still read-only:

1. Treat `/tmp/miband9_windows_firmware_20260601_2140/extracted/vela_ap.bin` as the primary code binary.
2. Index archive structure, strings, and likely symbols/constants.
3. Focus on:
   - sensor chip / driver strings
   - `ODR`, `FIFO`, `watermark`, `batch`, `report interval`
   - `SportXms`, `HMPro`, `GSENSOR`, `GYRO`, `8/53`-adjacent constants
   - Vela/NuttX sensor abstractions and service packetization paths
4. Do not patch or flash without a separate explicit authorization and rollback plan.

Initial string index already showed `vela_ap.bin` contains concrete IMU driver and batching traces, including `bmi270`, `lsm6dso`, `sensors/sensor.c`, FIFO/watermark/batch/ODR logs, and strings such as `lsm6dso_batch_calcu, latency:%ld,interval:%ld, batch_num:%lu`.

### Deep read-only firmware index pass

Additional local artifacts:

```text
/tmp/miband9_firmware_deep_index_20260601_2205_repo_tool
/tmp/miband9_romfs_extract_20260601_2205_repo_tool
```

New read-only helper scripts added under `tools/firmware/`:

- `index_firmware_strings.py` — extracts printable strings with offsets and keyword/context summaries.
- `extract_romfs.py` — lists and optionally extracts Vela/NuttX ROMFS resource images.

High-signal `vela_ap.bin` findings:

- The main code image contains Vela/NuttX/uORB sensor plumbing:
  - `/dev/usensor`
  - `/dev/uorb/%s`
  - `/dev/uorb/sensor_%s%s%d`
  - `sensor_accel`, `sensor_accel_uncal`, `sensor_gyro`, `sensor_gyro_uncal`
- Concrete IMU drivers are present:
  - `platform/sensors/imu/bmi270/bmi270.c`
  - `platform/sensors/imu/lsm6dso/lsm6dso.c`
- Function-name strings show the expected driver seams:
  - `bmi270_imu_set_interval`, `lsm6dso_imu_set_interval`
  - `imu_set_odr`
  - `bmi270_imu_batch`, `lsm6dso_imu_batch`
  - `bmi270_read_fifo`, `lsm6dso_read_fifo`
  - `cal_imu_frame_length`
  - `simplify_timestamp_resampling`
- The batching/watermark logging is explicit:
  - `wtm:%ld , batch_min:%ld, interval:%ld, imu_activat:%d`
  - `# bmi270 batch change to :%ld, interval desired:%ld`
  - `lsm6dso_batch_calcu, latency:%ld,interval:%ld, batch_num:%lu`
  - `batch_desired:%ld , latency_us:%ld`
  - `bmi270 status, Int cnt:%llu,interval:%d,wtm:%ld,batch:%d,activated:%d`
  - `lsm6dso status, Int cnt:%llu,interval:%d,wtm:%ld,batch:%d,activated:%d`
- There is an embedded `uorb_listener` diagnostic CLI with:
  - `[-r <val>] Subscription rate`
  - `[-b <val>] Subscription maximum report latency in us`
  - `[-t <val>] Time of listener`

ROMFS extraction findings:

- `app.bin`, `system.bin`, and `vendor.bin` are valid ROMFS images and were extracted read-only.
- `vendor.bin/sensor/` contains sensor config blobs/files:
  - `bmi270_cfg.txt` (`Device: bmi270`, `Length: 8192`)
  - `gh3020_cfg.txt`
  - `sx9373_cfg.txt`
- `app.bin` is mostly UI/resource content; no SportXms batch/rate config file or host-visible low-latency knob was found there.
- `system.bin/startup/startup.conf` is UI startup animation config (`frame_rate=50`), unrelated to IMU cadence.

Interpretation:

- The 10-sample / ~100 ms `8/53` cadence now has a plausible firmware-level explanation: the IMU driver stack calculates `batch_num` from requested latency and interval, sets FIFO watermark (`wtm`), then publishes through uORB / SportXms plumbing.
- This supports the earlier App/protocol result: SportXms start fields are metadata; the latency floor is likely controlled below that layer by firmware sensor batching, FIFO watermark, or uORB subscription report-latency policy.
- A non-patch route may exist only if a host-reachable command can call the firmware's raw/factory/uORB path with lower report latency. Static strings show factory/raw-test seams (`factory old test acc/gyro`, `OPR_READ_DATA`, raw output formats), but no validated app/RFCOMM command path has been identified yet.

## Current stop condition

Protocol/App layer stop condition has been reached:

- SportXms App fields were exhaustively covered within sourced/safe limits.
- HMPro lacks a validated live callsite/profile gate.
- No app/protocol low-latency knob was found.

Firmware acquisition stop condition is cleared for the NFC package and the first deep read-only index pass is complete. A follow-up host-entry pass found Mi Fitness' `hns.e=13` factory/debug family and documented it in `MAC_DIRECT_HOST_FACTORY_ENTRY_RESEARCH_20260601.md`; it is the strongest免-patch host entry so far, but the sensor-relevant subcommand is not proven yet. If no raw/factory/uORB command path exists, changing the 10-sample batch likely requires binary patching, which remains out of scope until a separate explicit authorization and rollback plan.
