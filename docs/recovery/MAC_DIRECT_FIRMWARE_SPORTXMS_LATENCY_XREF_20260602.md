# Mi Band 9 SportXms latency/uORB xref pass (2026-06-02)

## Scope

Read-only continuation of the firmware callgraph / patch feasibility work after Mac-direct RFCOMM SportXms IMU succeeded and App/protocol-level SportXms variants failed to change the `10 samples / ~100 ms` packet cadence.

No hand-band live write, firmware patching, flashing, OTA write, or factory-mode entry was performed in this pass.

## Inputs

- Firmware: `/tmp/miband9_windows_firmware_20260601_2140/extracted/vela_ap.bin`
- Address model: raw Thumb image, `virtual = raw_offset + 0x2c100000`
- Prior callgraph report: `docs/recovery/MAC_DIRECT_FIRMWARE_CALLGRAPH_PATCH_FEASIBILITY_20260602.md`
- New helper: `tools/firmware/find_sportxms_latency_subscribers.py`
- Artifact: `/tmp/miband9_sportxms_latency_xref_20260602_021445/`

## Bottom line

The SportXms/uORB IMU subscriber callsite is now identified.

For `ActSport` start of sport types `0x32a` / `0x32c` (the family that includes the already proven `812` SportXms path), firmware subscribes both accel and gyro uORB descriptors through the same subscription wrapper with:

- `r2 = 0x64` (`100`, matching the observed 100 Hz stream)
- `r3 = 0x186a0` (`100000 us` report latency)

That explains the live behavior: `100 Hz` sampling plus `100000 us` max report latency yields about `10` samples batched per packet.

The cleanest patch target, if patching is ever authorized, is therefore the **SportXms subscription latency literal/callsite**, not the lower-level LSM6DSO/BMI270 driver arithmetic.

## Key wrapper interpretation

The small wrapper cluster around raw `0x16b348` / `0x16b374` is used widely by activity/algo code to subscribe/unsubscribe uORB-like sensor descriptors:

- `0x16b348`: subscribe/configure wrapper
- `0x16b374`: unsubscribe/disable wrapper
- `0x16b398`: flagged subscribe/configure variant

Observed call shape:

```text
r0 = owning activity/algo object
r1 = sensor descriptor table entry
r2 = requested rate / interval selector
r3 = max report latency in microseconds
stack[0] = extra flag / mode (usually 0 in this path)
```

This is inferred from repeated callers and the constants passed to `sensor_accel`, `sensor_gyro`, `sensor_ppgd`, etc. It aligns with the lower-level driver log strings already found:

```text
lsm6dso_batch_calcu, latency:%ld,interval:%ld, batch_num:%lu
batch_desired:%ld , latency_us:%ld
```

## Primary ActSport evidence

Relevant callsite slice: `/tmp/miband9_sportxms_latency_xref_20260602_021445/miband9_actsport_sensor_refs_17c9_17cc.txt`

### Start path

Function area: raw `0x17c9d2` (`ActSport` start/pause/resume/stop state handler).

On start, after checking the sport type against `0x32a` / `0x32c`, it subscribes accel and gyro:

```text
0x17ca0e: movw r2, #0x32a
0x17ca12: ldrh r3, [r5, #8]
0x17ca14: cmp r3, r2
0x17ca18: cmp.w r3, #0x32c

0x17ca1e: movs r2, #0x64
0x17ca20: ldr  r3, [pc, #0x1dc]  ; literal 0x17cc00 = 0x186a0
0x17ca22: ldr  r1, [pc, #0x1e0]  ; sensor_accel descriptor 0x506c64
0x17ca28: bl   #0x16b348         ; subscribe sensor_accel, rate 100, latency 100000 us

0x17ca2c: movs r2, #0x64
0x17ca2e: ldr  r3, [pc, #0x1d0]  ; literal 0x17cc00 = 0x186a0
0x17ca30: ldr  r1, [pc, #0x1d4]  ; sensor_gyro descriptor 0x506cb4
0x17ca36: bl   #0x16b348         ; subscribe sensor_gyro, rate 100, latency 100000 us
```

Generated helper output:

```text
0x17ca28 subscribe   sensor_accel r2=100 (0x64) r3=100000 (0x186a0)
0x17ca36 subscribe   sensor_gyro  r2=100 (0x64) r3=100000 (0x186a0)
```

### Pause / stop path

Pause and stop use the unsubscribe wrapper with the same accel/gyro descriptors and rate selector:

```text
0x17cb08 unsubscribe sensor_accel r2=100 (0x64) r3=0 (0x0)
0x17cb14 unsubscribe sensor_gyro  r2=100 (0x64) r3=0 (0x0)
0x17cb9e unsubscribe sensor_accel r2=100 (0x64) r3=0 (0x0)
0x17cbaa unsubscribe sensor_gyro  r2=100 (0x64) r3=0 (0x0)
```

### Resume path

Resume uses the same 100 Hz descriptor pair but a larger report-latency literal:

```text
0x17cb58 subscribe   sensor_accel r2=100 (0x64) r3=200000 (0x30d40)
0x17cb66 subscribe   sensor_gyro  r2=100 (0x64) r3=200000 (0x30d40)
```

This makes the initial SportXms start literal (`0x17cc00 = 0x186a0`) the more important low-latency target.

## Secondary algo evidence

The same helper found non-SportXms algorithm subscriptions, useful as a sanity check but not the primary IMU stream target:

```text
0x1953ec subscribe         sensor_accel r2=sl       r3=200000 (0x30d40)
0x1953fa subscribe         sensor_ppgd  r2=sl       r3=400000 (0x61a80)
0x1954d2 subscribe         sensor_accel r2=25       r3=200000 (0x30d40)
0x1954e0 subscribe         sensor_ppgd  r2=25       r3=400000 (0x61a80)
0x19551a subscribe_flagged sensor_accel r2=25       r3=0      (0x0)
0x195526 subscribe_flagged sensor_ppgd  r2=25       r3=0      (0x0)
```

These appear in an `AlgoXMHR` area and show the wrapper convention: accel/PPG algorithms use 25-ish selectors and 200–400 ms latency values, while SportXms uses 100 and 100 ms for accel+gyro.

## Descriptor xref summary

Descriptor-table references confirm the ActSport function is a real accel/gyro uORB subscriber and not a string false positive:

- `sensor_accel` descriptor entry: raw `0x506c64`
- `sensor_gyro` descriptor entry: raw `0x506cb4`
- ActSport references:
  - `0x17ca22`, `0x17cb06`, `0x17cb52`, `0x17cb9c` -> `sensor_accel`
  - `0x17ca30`, `0x17cb12`, `0x17cb60`, `0x17cba8` -> `sensor_gyro`

Full helper output:

- `/tmp/miband9_sportxms_latency_xref_20260602_021445/miband9_sportxms_latency_subscribers.txt`
- `/tmp/miband9_sportxms_latency_xref_20260602_021445/miband9_sportxms_latency_subscribers.json`

## Host-dispatch verdict

The免-patch host path is still **not** proven.

Evidence remains split:

- Host-reachable App side:
  - Mi Fitness sends `hns.e = 13` debug/factory commands through `DeviceContact`.
  - Known subtypes include `f=0` factory mode, `f=2` device log dump, `f=4` media log dump, `f=9/12/13` CTA/app debug, `f=5` brightness.
- Live-tested safe-ish bridge:
  - `hns.e=13 f=2` was queued successfully over the proven Mac RFCOMM encrypted path.
  - It produced no decoded `13/*` response and no `sensor/uORB/factory/lsm6dso/bmi270/batch/wtm/latency/gyro/accel` keyword hits.
- Firmware-internal side:
  - `uorb_listener -b <latency>` exists as a NuttX/NSH diagnostic app.
  - `lsm6dso_factory_old_test_*`, `OPR_READ_DATA`, and raw factory IMU functions exist.
  - No static bridge from encrypted host command dispatch to those internal routines is proven.

So: do not keep guessing type-13 subcommands; especially do not live-run `hns.e=13 f=0` factory mode without a separate risk decision.

## Patch feasibility update

### Current best patch target

If firmware patching is ever authorized, the current best target is the SportXms callsite literal:

- raw `0x17cc00`: `0x000186a0` = `100000 us`
- referenced by:
  - `0x17ca20` for accel start subscription
  - `0x17ca2e` for gyro start subscription

Candidate behavior-preserving low-latency patch would change only this literal in a copy of `vela_ap.bin`, for example:

- `100000 us` -> `10000 us` (`0x2710`) for roughly 1-sample batches at 100 Hz, if the lower stack honors it; or
- `100000 us` -> `20000 us` for roughly 2-sample batches, more conservative.

Do not apply this to the device yet.

### Secondary patch target

- raw `0x17cc30`: `0x00030d40` = `200000 us`
- referenced by resume path:
  - `0x17cb50` / `0x17cb5e`

This matters only if pause/resume is part of the target flow. The initial live SportXms start path uses `0x17cc00`.

### Fallback driver target

The earlier LSM6DSO target remains useful but is now lower priority:

- raw function area `0x53418`
- key arithmetic `0x53466: udiv r8, r3, r6`
- likely computes `batch_num = latency_us / interval`

Patch the subscription caller first if patching is allowed; it is cleaner, sensor-model independent, and closer to the desired SportXms behavior.

## Remaining risks before any patch/flash

1. OTA/boot verification is still not fully understood. The OTA zip exposes md5 metadata, but that is not proof the bootloader/application accepts arbitrary modified `vela_ap.bin`.
2. Rollback/recovery is not prepared. Need a same-version reinstall path, rejection behavior, and safe failure-mode plan before writing firmware.
3. Runtime stability risk: lowering latency from 100 ms to 10–20 ms may increase wakeups, RF traffic, power draw, and queue pressure.
4. App/protocol assumptions may expect 10-sample batches. Decoder can handle different batch sizes, but watch firmware / SportXms packet builder behavior still needs live validation if patched.
5. We have not confirmed whether firmware silently clamps low `latency_us` to a minimum; only a patched live run can prove packet cadence changes.

## Next recommended step

Stay read-only for one more slice:

1. Produce a patch-on-copy experiment only:
   - duplicate `vela_ap.bin`, patch raw `0x17cc00` in the copy only, recompute local hashes, and inspect OTA package metadata impact;
   - do **not** flash or OTA-write.
2. Investigate OTA acceptance / signature / rollback path.
3. In parallel, keep the existing unpatched Mac gesture CLI path as MVP; current 100 Hz / 10-pack data is already usable for non-twitch gestures.

## Verification

```text
python3 tools/firmware/find_sportxms_latency_subscribers.py /tmp/miband9_windows_firmware_20260601_2140/extracted/vela_ap.bin --start 0x160000 --end 0x1a0000
# rows: 118
# key rows include ActSport accel/gyro subscribe/unsubscribe listed above
```
