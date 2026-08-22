# Mi Band 9 OTA no-body preflight guard

Date: 2026-06-02

Scope: local/static guard and ZIP classifier only. No app launch, no band connection, no firmware metadata send, no `prepareTransfer`, no body/chunks, no `validate`, no `upgrade`, no recovery/factory mode.

## Bottom line

The first attempt after the 米环 / Notify audit is deliberately fail-closed:

- Added `tools/firmware/ota_preflight_guard.py`.
- Added `tools/firmware/test_ota_preflight_guard.py`.
- The helper can classify a local OTA ZIP as Vela/Xiaomi-style (`ota.json` / `ota.sh`) and print an OTA gate map.
- The helper refuses dangerous update actions by default.
- It does **not** contain live Bluetooth/app-control code.

## Gate map

| Gate | Current status | Meaning |
|---|---|---|
| `host_file_admission` | local safe | Read local ZIP, parse `ota.json`, inspect visible MD5 fields. |
| `dfu_status_query` | live no-body, requires explicit authorization | Query device update/DFU status only; no firmware metadata/body. |
| `prepare_transfer` | blocked by default | `prepareTransfer(type,totalSize,crc32,maxChunkSize,mode)` can move the device into update negotiation. |
| `body_transfer` | blocked by default | `startTransfer` and chunk/body writes are firmware transfer. |
| `validate_upgrade_recovery` | blocked by default | `validate`, `upgrade`, recovery, and factory mode are post-body / boot-risk operations. |

## Why prepare is not “just status”

From the previous read-only audits:

- Mi Fitness DFU V5 flow:
  - query `UpgradeStatus.IDLE`
  - `prepareTransfer(...)`
  - `startTransfer`
  - chunks
  - `validate`
  - `upgrade`
- Notify local firmware path still enters a device update request and file-transfer path after local file admission:
  - `e6/c.java:4219-4231` `p2(...)` → update preflight/request
  - `e6/c.java:2835-2841` `N2(...)` → transfer helper
  - `r8/c.java:58-60` `B2(2,...)` → file transfer command path
  - `r8/d.java` → chunk/request/finish loop

So the safe first live gate, if later authorized, is only **DFU/update status query**. `prepareTransfer` is not part of the current safe boundary.

## Verification performed

```text
python3 -m py_compile tools/firmware/ota_preflight_guard.py tools/firmware/test_ota_preflight_guard.py
PYTHONPATH=tools/firmware python3 -m unittest tools/firmware/test_ota_preflight_guard.py
# result: 4 tests OK
```

Actual patched ZIP classification test:

```text
python3 tools/firmware/ota_preflight_guard.py \
  --zip /tmp/miband9_patch_on_copy_20260602_022409/mi_band9_n66nfc_sportxms_latency_20000us_patch_on_copy.zip \
  --json

firmware5_zip_like True
sw_version 1.3.210
entry_count 13
dangerous []
```

Dangerous action block test:

```text
python3 tools/firmware/ota_preflight_guard.py --action firmware_body --json
# exit=2
# Blocked by OTA safety gate: firmware_body
```

## Current authorization boundary

Allowed now:

- local ZIP classification
- static code/documentation mapping
- fail-closed guard tests

Not allowed without a new explicit live authorization:

- launch Notify / Mi Fitness / 米环 app
- connect the band for OTA
- query live DFU/update status
- send firmware metadata
- call `prepareTransfer`
- transfer chunks/body
- validate
- upgrade
- recovery/factory mode

## Next possible live step, if explicitly authorized

A controlled no-body run should be named narrowly, for example:

```text
live_dfu_status_query only:
- connect/auth through the already-proven safe transport
- query update/DFU status
- write local redacted JSON artifact
- stop before prepareTransfer
```

Abort conditions:

- any command builder tries to include file path/size/crc/body
- any path asks for `prepareTransfer`, `startTransfer`, `validate`, `upgrade`, recovery, or factory mode
- status response is malformed or indicates non-idle/unknown update state
- local auth/session mismatch or unexpected device identity
