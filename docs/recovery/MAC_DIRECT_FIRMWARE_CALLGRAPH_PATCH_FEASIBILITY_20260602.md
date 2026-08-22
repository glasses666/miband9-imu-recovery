# Mi Band 9 firmware callgraph / patch feasibility pass 1 (2026-06-02)

## Scope

Read-only binary analysis of the Band 9 NFC OTA `vela_ap.bin` found on Windows. This pass does **not** patch, flash, OTA-write, or send any additional live command to the band.

Goal: determine whether the already-proven macOS RFCOMM host path can reach raw/factory/uORB sensor latency controls without patching, and if not, identify the first plausible static patch targets and rollback risks.

## Inputs

- Firmware package: `/tmp/miband9_windows_firmware_20260601_2140/673e64214a0c42412771243b5f3a47bb_upd_miwear.watch.n66nfc.zip`
- Extracted app firmware: `/tmp/miband9_windows_firmware_20260601_2140/extracted/vela_ap.bin`
- `vela_ap.bin` size: `6,742,976` bytes (`0x66e3c0`)
- `vela_ap.bin` SHA-256: `a5cad4c64631741cffdb09f38c0146d7a1c62c93512500799f8bdfc9fe01d4d9`
- Previous live factory gate: `/tmp/miband9_factory_dump_gate_20260602_000631/factory_dump_rfcomm5`
- New static artifacts: `/tmp/miband9_callgraph_probe_20260602_0108/`

## Tooling note

The firmware is not a standard ELF image. `file` reports `DOS executable` because of bytes in the raw image, but the first bytes and successful Thumb decode indicate a raw ARM/Thumb firmware image. Standard objdump does not handle it directly on this host, so this pass uses Capstone via `tools/firmware/firmware_thumb_xref.py`.

The most useful address mapping found in this pass is:

```text
virtual = raw_offset + 0x2c100000
```

Evidence: thousands of PC-relative literal loads point into string pools with this base, including the IMU and MiWear Bluetooth string pools.

## Image shape

High-level layout from byte statistics and string density:

- `0x000000..~0x4bffff`: mostly Thumb code / tables / mixed rodata.
- `0x4d0000..~0x5a0000`: very dense string / function-name / log format pools.
- `0x620000..~0x650000`: additional string/resource tail, including OTA/runtime strings.
- `0x650000..end`: sparse/tail data.

First 16 little-endian words of `vela_ap.bin`:

```text
0xffffffff 0x50000 0x0 0x2876e24c 0x47004814 0xf95af001 0xf3804813 0x48138808 0x880af380 0xf3802000 0xf3bf8814 0xf0008f6f 0xf000f82f 0xf000f88d 0x490df949 0x4b0e4a0d
```

## Raw IMU / batch targets

### LSM6DSO batch calculation

Key strings:

- raw offset `0x4dcf51`: `%s: lsm6dso_batch_calcu, latency:%ld,interval:%ld, batch_num:%lu`
- raw offset `0x4dcf94`: `%s: batch_desired:%ld , latency_us:%ld`

Xrefs with base `0x2c100000` place the relevant code near:

- function start heuristic: `0x53418`
- exact literal refs:
  - `0x53444` -> `0x2c5dcf51` (`lsm6dso_batch_calcu...`)
  - `0x5348a` -> `0x2c5dcf94` (`batch_desired...`)

The key arithmetic in that function includes:

```text
0x53466: udiv r8, r3, r6
0x5346a: mul  r6, r8, r6
0x5347c: ldr  r2, [r5, #0x2c]
0x53480: cmp  r3, r2
0x53482: str  r3, [r5, #0x2c]
```

Interpretation: this is a strong static candidate for the `latency / interval -> batch_num` path. It matches the runtime observation that 100 Hz samples are batched into 10 samples/packet (~100 ms).

### LSM6DSO raw/factory old-test

Key strings:

- `factory old test acc/gyro started`
- `factory old test acc/gyro stop`
- `In lsm6dso_factory_test: %d`
- `In OPR_READ_DATA`
- `raw[%d]:%ld %ld %ld`
- symbol-like names: `lsm6dso_factory_old_test_start/read/stop`

Xrefs with base `0x2c100000` place the main factory/raw code near:

- function start heuristic: `0x534f8`
- exact or near refs:
  - `0x53636` -> `factory old test acc/gyro started`
  - `0x53742` -> `factory old test acc/gyro stop`
  - `0x53764` -> `In lsm6dso_factory_test: %d`
  - `0x53aba` -> `In OPR_READ_DATA`
  - `0x538a0` / `0x538dc` -> `raw[%d]:%ld %ld %ld`

This code contains an operation dispatch around:

```text
0x53790: cmp r3, #4
0x53794: tbh [pc, r3, lsl #1]
```

Interpretation: raw/factory read exists and is structured like a small operation dispatcher, but this pass did not prove a host Bluetooth/protobuf caller reaches it.

### BMI270 / common IMU path

Additional xrefs confirm BMI270 and shared IMU batching are present:

- `# bmi270 batch change to` -> 31 near refs
- `bmi270_batch_calcu` -> 50 near refs
- `bmi270_read_fifo` -> 39 near refs
- `wtm:%ld , batch_min:%ld, interval:%ld` -> 24 near refs
- `bmi270 status, Int cnt...` -> 28 near refs
- `lsm6dso status, Int cnt...` -> 14 near refs

Interpretation: both supported IMU drivers have batch/FIFO/status code. The Band 9 unit likely picks one runtime IMU path, but the app-level packet cadence is consistent with the shared batch/FIFO policy.

## uORB / console target

Key strings:

- `uorb_listener`
- `[-b <val>] Subscription maximum report latency in us(unlimited if 0), default: 0`

Xrefs:

- `uorb_listener` appears in a builtin/command-name pool near raw offset `0x4e6578..0x4e65c2` with `setfactoryinfo`, `setlogmask`, `setprop`, `touchpoint`, `uorb_unit_test`, `watchpoint`.
- The long `Subscription maximum report latency` help text had no useful direct xref under the `0x2c100000` base in this pass.

Interpretation: `uorb_listener -b` is real, but still looks like an internal NSH/builtin console utility, not a proven host API.

## Host / Bluetooth path search

Relevant host/Bluetooth strings:

- `miwear_pb_handler` at raw `0x5119fd`
- `rfcomm_send` at raw `0x511a3d`
- `server_recv_cb` at raw `0x511a96`
- `gatts_write_request_callback` around raw `0x50a5c0`

Xrefs with `0x2c100000` confirm these Bluetooth/MiWear functions are referenced in code. Example exact refs:

- `miwear_pb_handler`: `0x11ef96`, `0x11efaa` -> `0x2c6119fd`
- `rfcomm_send`: `0x11d47c`, `0x11d4b0`, `0x11d4f2` -> `0x2c611a3d`
- `server_recv_cb`: `0x11ef58` -> `0x2c611a96`
- `gatts_write_request_callback`: `0x10f3d0`, `0x10f3f0` -> `0x2c60a5c0`

String search around the host path found normal MiWear/System/UI commands, including:

- `receive factory reset`
- `recevice get device info cmd from conn[%d]`
- `recv get today fitness ids from conn[%d]`
- `recv WearPacket type:%d, id:%d, which_payload:%d`
- `spp_tool` strings

But it did **not** find a nearby string bridge from host protobuf/RFCOMM to `lsm6dso_factory_test`, `OPR_READ_DATA`, or `uorb_listener`.

## Current host-path verdict

No免-patch raw IMU/uORB host path has been proven.

Current evidence is split:

- Host-reachable: macOS RFCOMM + Xiaomi auth/session + encrypted protobuf commands are proven.
- Host-reachable debug family: Mi Fitness `hns.e=13` exists, and safe gate `f=2` queued successfully.
- Firmware-internal: `lsm6dso_factory_test`, `OPR_READ_DATA`, raw output, `uorb_listener -b`, batch/FIFO policy all exist.
- Missing bridge: no static or live evidence ties the host debug family to raw IMU/uORB latency knobs.

Do not continue guessing `hns.e=13` subtypes. `hns.e=13 f=0` factory-mode remains state-changing and was not run.

## Patch feasibility first cut

Plausible patch target class:

1. `lsm6dso_batch_calcu` / BMI270 equivalent: force lower `batch_num` or clamp latency/batch desired.
2. Shared FIFO/watermark code: lower watermark `wtm`.
3. uORB subscription/report-latency path: force smaller report latency for the SportXms/IMU subscriber if the subscriber call site is found.

Best current concrete static target:

- raw code vicinity: `0x53418..0x534a0` (`lsm6dso_batch_calcu` candidate)
- candidate arithmetic instruction: `0x53466 udiv r8, r3, r6`

This is **not yet enough to patch safely**. We still need:

- confirm whether the watch uses LSM6DSO or BMI270 in this unit/runtime;
- identify the exact SportXms subscriber/caller feeding `latency_us` or `batch_desired`;
- understand OTA/device-side verification beyond `ota.json` md5 entries;
- prepare rollback/recovery using the original OTA package and failure-mode plan.

## OTA / rollback risk

`ota.json` lists per-file `md5sum` values but no obvious signature file inside the zip. That does **not** prove patched firmware would be accepted: update code or bootloader may still enforce additional checks outside the package manifest.

Package contents are direct files only; no extra `.sig`/certificate file was visible in the zip listing.

Before any patch/flash discussion, required rollback prep:

- preserve original OTA zip and extracted files;
- understand md5 update path and any bootloader/application verification path;
- identify whether Mi Fitness can reinstall/downgrade the same package;
- know recovery behavior if `vela_ap.bin` is rejected or boots partially;
- avoid touching bootloader (`vela_ota.bin`) unless explicitly required.

## Artifacts

- `/tmp/miband9_callgraph_probe_20260602_0108/image_shape_probe.txt`
- `/tmp/miband9_callgraph_probe_20260602_0108/rodata_base_cluster.txt`
- `/tmp/miband9_callgraph_probe_20260602_0108/thumb_xref_targets_base_2c100000.json`
- `/tmp/miband9_callgraph_probe_20260602_0108/thumb_xref_bmi_targets_base_2c100000.json`
- `/tmp/miband9_callgraph_probe_20260602_0108/disasm_key_slices.txt`

## Next recommended action

Continue read-only binary work, but narrow it:

1. Resolve function tables / driver operation tables around the LSM6DSO/BMI270 functions.
2. Find who calls the batch calculation functions and what passes `latency_us`.
3. Find SportXms/uORB subscriber call site, if present.
4. Only then decide whether a one-byte/small-instruction patch could lower batch safely.

No further live command is recommended at this point.
