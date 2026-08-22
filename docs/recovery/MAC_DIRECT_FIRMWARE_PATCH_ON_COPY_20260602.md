# Mi Band 9 SportXms latency patch-on-copy experiment (2026-06-02)

## Scope

Local-only patch-on-copy experiment for the SportXms report-latency literal identified in `vela_ap.bin`.

This pass did **not** connect to the band, did **not** OTA-write, did **not** flash, did **not** enter factory mode, and did **not** modify the original firmware package.

## What this proves / does not prove

This experiment proves:

1. The candidate patch can be represented as a tiny 4-byte literal edit in a copy of `vela_ap.bin`.
2. The local OTA ZIP can be repacked with an updated `ota.json` MD5 for `vela_ap.bin`.
3. The repacked ZIPs are structurally readable by standard ZIP checks.
4. The known SportXms xref helper sees the patched start-subscription latency values at the expected accel/gyro callsites.

This experiment does **not** prove the band will accept the modified package, and it does **not** prove flashing cannot brick the band. Bootloader/app-level verification, anti-rollback, partial-write behavior, and recovery path still need separate evidence before any live write.

## Inputs

- Original OTA ZIP: `/tmp/miband9_windows_firmware_20260601_2140/673e64214a0c42412771243b5f3a47bb_upd_miwear.watch.n66nfc.zip`
- Original OTA SHA-256: `8f8a20a8c690de2cd4e1bc6ddd3969e00fe9d55970ba0ccf4445a908ace37c23`
- Original `vela_ap.bin`: `/tmp/miband9_windows_firmware_20260601_2140/extracted/vela_ap.bin`
- Artifact directory: `/tmp/miband9_patch_on_copy_20260602_022409`

## Patch target

- raw offset: `0x17cc00`
- original value: `0x000186a0` = `100000 us`
- original bytes: `a0 86 01 00`

This literal is loaded by the `ActSport` SportXms start path for both accel and gyro subscriptions:

```text
0x17ca28 subscribe sensor_accel r2=100 r3=100000
0x17ca36 subscribe sensor_gyro  r2=100 r3=100000
```

## Generated variants

### Conservative variant: 20000 us

- patched value: `0x00004e20` = `20000 us`
- patched bytes: `20 4e 00 00`
- repacked ZIP: `/tmp/miband9_patch_on_copy_20260602_022409/mi_band9_n66nfc_sportxms_latency_20000us_patch_on_copy.zip`
- repacked ZIP SHA-256: `36f5ed2a8af93b7d22a71aa1ce13c4003eba2321ce437e5f30a00dce0cb13262`
- patched `vela_ap.bin` SHA-256: `1b4b06ed578037aac4d69db26482e44ccc50d7265ff68dc7c6a6ee0284fc8eec`
- patched `vela_ap.bin` MD5: `949df76a6241ce08ad628146501e8680`

Xref verification:

```text
0x17ca28 subscribe sensor_accel r2=100 (0x64) r3=20000 (0x4e20)
0x17ca36 subscribe sensor_gyro  r2=100 (0x64) r3=20000 (0x4e20)
0x17cb58 subscribe sensor_accel r2=100 (0x64) r3=200000 (0x30d40)
0x17cb66 subscribe sensor_gyro  r2=100 (0x64) r3=200000 (0x30d40)
```

### Aggressive variant: 10000 us

- patched value: `0x00002710` = `10000 us`
- patched bytes: `10 27 00 00`
- repacked ZIP: `/tmp/miband9_patch_on_copy_20260602_022409/mi_band9_n66nfc_sportxms_latency_10000us_patch_on_copy.zip`
- repacked ZIP SHA-256: `831d2085ba5a467e8f878f8cf26703d71697bd60098c858797c6a578b423dfc6`
- patched `vela_ap.bin` SHA-256: `a3be3420326edcda4638236d7ff5f57ce99046e8339e271f3fd55ceaa5829dfd`
- patched `vela_ap.bin` MD5: `d7dbe55644cb42d1b12976dc58e37dca`

Xref verification:

```text
0x17ca28 subscribe sensor_accel r2=100 (0x64) r3=10000 (0x2710)
0x17ca36 subscribe sensor_gyro  r2=100 (0x64) r3=10000 (0x2710)
0x17cb58 subscribe sensor_accel r2=100 (0x64) r3=200000 (0x30d40)
0x17cb66 subscribe sensor_gyro  r2=100 (0x64) r3=200000 (0x30d40)
```

## OTA structure and checksum result

Original OTA files: `13` entries.

Repacked variants:

```text
10000us: zip testzip=None, all ota.json MD5 entries match, suspicious signature files=[]
20000us: zip testzip=None, all ota.json MD5 entries match, suspicious signature files=[]
```

Interpretation:

- The package-level `ota.json` MD5 gate can be made self-consistent after patching `vela_ap.bin`.
- No obvious `.sig`, `signature`, `cert`, `pem`, `rsa`, or similar signature file exists inside the ZIP.
- This is **not** proof that device-side bootloader/application verification is absent. It only means the visible ZIP-level manifest can be updated locally.

## Tooling added

- `tools/firmware/patch_sportxms_latency_literal.py`
  - creates patch-on-copy OTA packages;
  - verifies the original literal value before patching;
  - updates only the local `ota.json` MD5 entry for `vela_ap.bin`;
  - writes summary JSON for reproducibility.
- `tools/firmware/find_sportxms_latency_subscribers.py`
  - now has a narrow fallback verifier for the known SportXms callsites when Capstone is unavailable on bare macOS/Xcode Python.

## Risk verdict

Current risk posture:

- Patch point quality: **good** — one 4-byte literal on the SportXms start path.
- Local OTA self-consistency: **good** — repacked ZIPs pass standard ZIP checks and `ota.json` MD5 checks.
- Brick-risk proof: **not achieved** — no live acceptance, no bootloader verification evidence, no rollback test.

Do not flash these packages yet.

## Recommended next step before any live write

1. Investigate the actual OTA delivery path and whether the band checks only `ota.json` MD5 or also an app/bootloader signature/hash outside the ZIP.
2. Prepare rollback/recovery evidence:
   - whether the original same-version package can be resent;
   - what happens on rejected package before write;
   - whether `vela_ota.bin` / bootloader has recovery behavior;
   - how to avoid partial-write boot failure.
3. If a live experiment is eventually approved, use the `20000us` variant first, not `10000us`, because it is less aggressive.

## Verification commands

```text
python3 -m py_compile tools/firmware/find_sportxms_latency_subscribers.py tools/firmware/patch_sportxms_latency_literal.py

python3 tools/firmware/patch_sportxms_latency_literal.py \
  /tmp/miband9_windows_firmware_20260601_2140/673e64214a0c42412771243b5f3a47bb_upd_miwear.watch.n66nfc.zip \
  --out-dir /tmp/miband9_patch_on_copy_20260602_022409 \
  --latency-us 20000 \
  --latency-us 10000

python3 tools/firmware/find_sportxms_latency_subscribers.py \
  /tmp/miband9_patch_on_copy_20260602_022409/patched_20000us/vela_ap.bin \
  --start 0x160000 --end 0x1a0000

python3 tools/firmware/find_sportxms_latency_subscribers.py \
  /tmp/miband9_patch_on_copy_20260602_022409/patched_10000us/vela_ap.bin \
  --start 0x160000 --end 0x1a0000
```
