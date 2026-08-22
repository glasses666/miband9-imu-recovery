# Mi Band 9 OTA live DFU status no-body attempt

Date: 2026-06-02

Scope: explicitly authorized `live_dfu_status_query only`. No app launch, no firmware metadata, no `prepareTransfer`, no `startTransfer`, no firmware body/chunks, no `validate`, no `upgrade`, no recovery/factory mode.

## Bottom line

The live no-body gate was attempted on both Mac CoreBluetooth and Android ADB/headless phone paths, and stayed fail-closed.

Result: **no DFU V5 status response was obtained**. The Mac path could not reach DFU/FE95 GATT. After the band was put into the on-band “connect new phone” state, the Android path could scan and connect to the band over GATT, discovered normal services including FE95, but did **not** discover the DFU V5 service `00000000-1530-3512-2118-0009AF100700`.

Because the DFU V5 CPT characteristic was never visible, the probes sent **zero OTA-status writes**.

## Static command mapping used

Mi Fitness `NewDfuProfile` (`pm.java`) maps DFU V5 GATT as:

- service: `v4v.C(5424)` → `00000000-1530-3512-2118-0009AF100700`
- CPT characteristic: `v4v.C(5425)` → `00000000-1531-3512-2118-0009AF100700`
- PKT characteristic: `v4v.C(5426)` → `00000000-1532-3512-2118-0009AF100700`

Safe status command only:

- `queryUpgradeStatus` writes one byte `0xD1` to CPT and waits for a CPT notification response.

Blocked/not implemented in this live tool:

- protocol-info `0xD0` unless explicitly added later;
- prepare `0xD2`;
- start-transfer `0xD3`;
- validate `0xD5`;
- upgrade `0xD6`;
- firmware body / PKT writes.

## Live evidence

Policy gate:

```text
python3 tools/firmware/ota_preflight_guard.py \
  --action live_dfu_status_query \
  --allow-live-status \
  --json
# guard_ok=true, dangerous=[]
```

Probe compiled:

```text
swiftc tools/mac_direct/dfu_v5_status_probe.swift -o /tmp/dfu_v5_status_probe
# swiftc_ok=true
```

Attempt 1: normal CoreBluetooth retrieval + scan.

- artifact dir: `/tmp/miband9_ota_live_status_20260602_111213`
- `centralState`: `poweredOn`
- `retrieve_connected_dfu_count`: `0`
- `retrieve_connected_fe95_count`: `0`
- scan result: timeout
- `connected`: `false`
- writes: `[]`
- parsed status: `null`

Attempt 2: known CoreBluetooth peripheral retrieval from earlier local artifacts.

- artifact dir: `/tmp/miband9_ota_live_status_20260602_111458_knownid`
- `centralState`: `poweredOn`
- `retrieve_by_identifier_count`: `1`
- target name resolved locally
- CoreBluetooth connection did not complete before timeout
- writes: `[]`
- event count: `0`
- parsed status: `null`

Mac Bluetooth profiler at the time showed the band connected at the system Bluetooth layer, but as a classic/HID ACL device, not as a CoreBluetooth DFU/FE95 GATT target.

Attempt 3: Android ADB/headless phone path after the band was manually put into on-band state 1 (“connect new phone”).

Build/install/setup evidence:

```text
./gradlew :app:assembleMainlineHfimucli
# BUILD SUCCESSFUL in 40s

python3 -m miband9ctl --json install
# ok=true

python3 -m miband9ctl --json setup
# ok=true
```

Android scan evidence:

```json
{
  "ok": true,
  "device_count": 1,
  "devices": [
    {
      "address": "AA:BB:CC:DD:EE:FF",
      "bond_state": "BONDED",
      "name": "Xiaomi Smart Band 9 test-device"
    }
  ]
}
```

Android DFU status no-body probe evidence:

- artifact dir: `/tmp/miband9_android_dfu_status_20260602_124306_addr`
- target: `AA:BB:CC:DD:EE:FF` / `Xiaomi Smart Band 9 test-device`
- `gatt_status`: `0`
- `new_state`: `CONNECTED`
- `service_count`: `10`
- discovered FE95 service: `0000fe95-0000-1000-8000-00805f9b34fb`
- FE95 characteristics: `00000050`, `0000005e`, `0000005f`
- DFU V5 service `00000000-1530-3512-2118-0009AF100700`: missing
- `write_count`: `0`
- `notification_count`: `0`
- `status_parsed`: `false`
- terminal reason: `dfu_v5_service_missing`

Implemented Android command:

```text
command=dfu-status-probe
safe_scope=live_dfu_status_query_only
allowed_write=query_upgrade_status_D1_only
blocked=prepareTransfer,startTransfer,firmware_body,validate,upgrade,recovery,factory
```

The Android command only writes `0xD1` after all of these are true:

1. device GATT connects;
2. DFU V5 service `1530` exists;
3. CPT characteristic `1531` exists;
4. CPT has notify/indicate;
5. CPT has write/write-no-response;
6. CCC descriptor write succeeds.

In this run, gate 2 failed, so **no write was sent**.

## Android Notify-connected rerun

After Notify/NFX was manually connected to the band and showing the device page, the no-body Android probe was rerun without selecting a firmware ZIP or entering the firmware-upgrade UI.

Evidence:

- artifact dir: `/tmp/miband9_notify_connected_dfu_status_20260602_130354`
- Notify/NFX visible state: device page for `小米手环9 Nfc版`, battery `100%`
- no-body guard: `live_dfu_status_query` allowed, dangerous actions still blocked
- target: `AA:BB:CC:DD:EE:FF` / `Xiaomi Smart Band 9 test-device`
- probe result: secondary GATT connect was requested, but did not reach a connected/service-discovered callback while Notify owned the active connection
- terminal reason: `capture_window_elapsed`
- `service_count`: `0`
- `write_count`: `0`
- `notification_count`: `0`
- `status_parsed`: `false`

Interpretation: Notify/NFX being connected proves the app owner/session exists, but a separate debug APK cannot necessarily open a second GATT session to inspect DFU services while Notify owns the connection. This is an **owner-session observability blocker**, not evidence that DFU V5 is absent under Notify.

## Interpretation

This is a safe blocker, not a failed firmware test:

- We did **not** prove the patched ZIP is safe or unsafe.
- We did **not** query `UpgradeStatus.IDLE` because the DFU V5 GATT service was unreachable from the current Mac state, missing from the Android state-1 GATT service list, and not observable from a second Android GATT client while Notify/NFX owned the active connection.
- We did prove the live no-body harness refuses to proceed unless it can see the exact DFU V5 status characteristic.
- No OTA state transition should have occurred because no write was sent.

## 2026-06-03 rerun after local static candidate passed

After the local `20128us` candidate passed the reproduced static gates (`zipfile.testzip`, `vela_ap.bin` CRC/MD5, `ota.json` MD5/CRC/raw-DEFLATE size, AP stride ECDSA), Queen Glasser authorized trying the no-body preflight boundary again.

Safety preflight before live probing:

```text
PYTHONPATH=tools/firmware python3 -m unittest tools/firmware/test_ota_preflight_guard.py
# Ran 4 tests OK

python3 tools/firmware/ota_preflight_guard.py \
  --zip /tmp/miband9_tool_scout/MIBand9_1.3.206_sportxms_20128us_full_local_checks_PASS_NOT_FOR_INSTALL.zip \
  --action read_local_zip --action classify_file --action host_admission_check \
  --json
# firmware5_zip_like=true, sw_version=1.3.206, dangerous=[]

python3 tools/firmware/ota_preflight_guard.py --action firmware_body --json
# exit=2, Blocked by OTA safety gate: firmware_body

python3 tools/firmware/ota_preflight_guard.py --action live_dfu_status_query --allow-live-status --json
# live_no_body=[live_dfu_status_query], dangerous=[]
```

Phone state:

- ADB device: Xiaomi MI 9 SE (`grus`), root available.
- Bluetooth was initially `OFF`; app-level enable failed (`bluetooth_enable_failed`), so Bluetooth was enabled via root `svc bluetooth enable`.
- Bluetooth then showed bonded `Xiaomi Smart Band 9 test-device` and the known band address.
- A regular scan did not find a current Xiaomi advertisement.

Android direct-address no-body probe:

- artifact: `/tmp/miband9_live_dfu_probe_20260603/dfu22df08bf0.logcat.txt`
- command: guarded `dfu-status-probe`, direct known band address, `seconds=12`, `capture_ms=6000`
- allowed write: `query_upgrade_status_D1_only`
- blocked: `prepareTransfer,startTransfer,firmware_body,validate,upgrade,recovery,factory`
- result: `gatt_connect_requested` but no service-discovery callback before capture window elapsed
- final counters:

```text
candidate_count=1
service_count=0
write_count=0
notification_count=0
status_parsed=false
reason=capture_window_elapsed
```

Mac CoreBluetooth no-body rerun:

- artifact: `/tmp/miband9_live_dfu_probe_20260603/mac_dfu_v5_status_probe_correct.json`
- command: `/tmp/dfu_v5_status_probe 'Xiaomi' 18`
- result:

```text
centralState=poweredOn
retrieve_connected_dfu_count=0
retrieve_connected_fe95_count=0
scanFound=false
retrieveConnectedFound=false
connected=false
writes=[]
events=[]
parsedStatus=null
finish_reason=timeout
```

Official Mi Fitness status-only probe:

Static evidence from Mi Fitness 3.52.0 decompile:

- `DeviceSender.getOtaStatus(...)` sends contact packet `hns.e=2, hns.f=90`.
- This path carries no firmware file path, no MD5, no size, no ZIP body, and does not instantiate an OTA executor.
- Dangerous paths remain separate:
  - `DeviceSender.prepareOta(...)` sends `hns.e=2, hns.f=5` with firmware version/MD5/size/change-log fields.
  - `DeviceSender.startOta(...)` constructs `HyOtaExecutor` or `GeneralOtaExecutor` and starts file transfer.
  - `BluetoothOtaManager.startUpgrade(...)` can call `prepareOta(...)` and then `startOta(...)`; therefore it is not a no-body boundary.

Guarded Frida run:

- artifacts:
  - `/tmp/miband9_live_dfu_probe_20260603/mihealth_get_ota_status_guarded_v2.out`
  - `/tmp/miband9_live_dfu_probe_20260603/mihealth_device_get_ota_status_guarded_v2.out`
- target processes:
  - `com.mi.health`
  - `com.mi.health:device`
- hard-blocked before calling status:
  - `DeviceSender.prepareOta`
  - `DeviceSender.startOta`
  - `DeviceSender.notifyForceUpgrade`
  - `BluetoothOtaManager.startUpgrade`
  - `BluetoothOtaManager.prepareOta`
  - `GeneralOtaExecutor.start`
  - `HyOtaExecutor.start`
- called only: `DeviceSender.getOtaStatus(...)` / `hns.e=2, f=90`
- result in both processes:

```text
errors=[-6]
status=null
dangerousCalls=[]
```

Bluetooth evidence at the same time showed the band was still bonded but disconnected, and a scan did not find a current Xiaomi advertisement. Interpretation: official status-only `f=90` was safe to call under hooks, but returned a connectivity/session error (`-6`). This is still not a package admission result.

After the run, phone Bluetooth was restored to `OFF`.

Interpretation: the stronger local static artifact did **not** change the live boundary. No DFU/update status response was obtained, and no OTA-status byte/body was written in Android, Mac, or official Mi Fitness status-only reruns. This remains a reachability/session-state blocker, not evidence that the patched package is accepted or rejected.

## Next gate

To actually query DFU V5 status, the band must expose the DFU V5 service, not just normal FE95/HID/battery/heart-rate GATT services. Safer next options:

1. Find the exact official/app-session pre-DFU transition that makes service `00000000-1530-3512-2118-0009AF100700` appear, then stop before firmware transfer.
2. Re-run this Android no-body probe after that transition and verify it still only sends `0xD1`.
3. Do not use Notify/Mi Fitness UI to flash or test local ZIP behavior yet.
