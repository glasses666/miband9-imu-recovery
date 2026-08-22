# Mi Band 9 firmware OTA safety audit + SportXms npack proof

Date: 2026-06-02

Scope: read-only / local-only analysis. No connection to the band, no OTA write, no factory mode, no firmware body transfer.

## Bottom line

The patch target at `vela_ap.bin` raw offset `0x17cc00` is strong evidence for changing SportXms report latency, which should change the number of IMU samples per `8/53` packet:

```text
100 Hz sample interval = 10000 us
original 100000 us / 10000 us = 10 samples per packet
patched   20000 us / 10000 us = 2 samples per packet, if honored
patched   10000 us / 10000 us = 1 sample per packet, if honored
```

But it is not a direct `npack` field. It is a `report_latency_us` argument passed to the firmware sensor subscription path. The final proof still requires a live post-patch capture that counts decoded `8/53` accel/gyro samples per packet and packet cadence.

## Why `0x17cc00` is likely the npack / one-send-data lever

### 1. SportXms start callsite loads this literal for both accel and gyro

Original firmware helper output:

```text
0x17ca28 subscribe sensor_accel r2=100 (0x64) r3=100000 (0x186a0)
0x17ca36 subscribe sensor_gyro  r2=100 (0x64) r3=100000 (0x186a0)
```

`r2=100` matches the observed 100 Hz sample rate. `r3=100000` matches the observed ~100 ms callback/packet cadence.

The corresponding disassembly context from the previous xref pass:

```text
0x17ca1e: movs r2, #0x64
0x17ca20: ldr  r3, [pc, #0x1dc]  ; literal 0x17cc00 = 0x186a0
0x17ca22: ldr  r1, [pc, #0x1e0]  ; sensor_accel descriptor
0x17ca28: bl   #0x16b348         ; subscribe sensor_accel

0x17ca2c: movs r2, #0x64
0x17ca2e: ldr  r3, [pc, #0x1d0]  ; literal 0x17cc00 = 0x186a0
0x17ca30: ldr  r1, [pc, #0x1d4]  ; sensor_gyro descriptor
0x17ca36: bl   #0x16b348         ; subscribe sensor_gyro
```

### 2. The lower-level driver path has the matching batch formula

The earlier callgraph pass found the LSM6DSO batch calculation around raw `0x53418`, especially:

```text
0x53466: udiv r8, r3, r6
```

Interpreted with the surrounding log strings:

```text
lsm6dso_batch_calcu, latency:%ld,interval:%ld, batch_num:%lu
batch_num = latency_us / interval_us
```

So if SportXms subscribes at 100 Hz, the interval is about `10000 us`, and `100000 us` naturally gives `10` samples per batch/packet.

### 3. Patch-on-copy changes the exact live subscription argument

Local duplicate patch verification:

```text
20000 us copy:
0x17ca28 subscribe sensor_accel r2=100 r3=20000
0x17ca36 subscribe sensor_gyro  r2=100 r3=20000

10000 us copy:
0x17ca28 subscribe sensor_accel r2=100 r3=10000
0x17ca36 subscribe sensor_gyro  r2=100 r3=10000
```

The patch leaves the sample rate argument (`r2=100`) alone and changes only the report latency argument (`r3`). That is exactly the change we want if the goal is to reduce “一发里面攒多少个样本” while keeping 100 Hz sampling.

## What would confirm it dynamically

After a real patch is safely installed, run the already-proven Mac RFCOMM SportXms capture:

```text
auth -> encrypted SportXms start -> capture 20-30s -> encrypted SportXms stop -> quiet-after
```

Pass criteria:

- Original firmware baseline:
  - `8/53` payloads contain `10 accel + 10 gyro` samples per packet.
  - packet cadence p50 ≈ `100 ms`.
  - derived sample rate ≈ `100 Hz`.
- `20000us` patch expected:
  - most `8/53` payloads contain `2 accel + 2 gyro` samples per packet.
  - packet cadence p50 ≈ `20 ms`, allowing transport jitter.
  - derived sample rate still ≈ `100 Hz`.
- `10000us` patch expected:
  - most `8/53` payloads contain `1 accel + 1 gyro` sample per packet.
  - packet cadence p50 ≈ `10 ms`, if transport/firmware does not clamp.
  - derived sample rate still ≈ `100 Hz`.
- Stop gate:
  - post-stop quiet window has `8/53 packets = 0`.

Failure interpretation:

- If `r3` patch is present but live packets still show `10 samples / ~100 ms`, then a later layer likely clamps or coalesces packets after the sensor subscription.
- If sample rate drops below 100 Hz, the patch may be causing driver/transport pressure instead of simply reducing batch size.
- If `20000us` works but `10000us` does not, prefer `20000us` for controller use.

## OTA / upgrade chain audit

### App/cache layer

Mi Fitness checks downloaded firmware files against server-provided MD5 before putting paths into the upgrade map:

```text
HuamiOtaManager.java:518-529
getFirmwareFile(updateInfo.getMd5())
MD5Util.getFileMD5(firmwareFile) == updateInfo.getMd5()
firmwareUpdateMap.put(updateInfo.getType(), updateInfo.getFilePath())
```

Implication: if using the official Mi Fitness update UI/cache, a patched outer ZIP will fail the cloud/app MD5 unless the app metadata/cache path is controlled. This is the earliest rejection layer.

### Upgrade start layer

Mi Fitness then calls the Huami API update path:

```text
HuamiOtaManager.java:653-677
startUpgrade(...)
huaMiApiCaller.updateFwUpgrade(false, 0, firmwareUpdateMap, changeLog, callback)
```

The SDK helper turns local firmware paths into `xd` firmware descriptors and enters the DFU pipeline:

```text
HuamiDevice.java:4009-4020 -> atu.y().j(...)
atu.java:310-322 -> collect files, then G(neVar)
```

### Preflight layer

Before data transfer, the helper checks device-side DFU state / upgrade status:

```text
eb.java:189-241
- rejects DfuState 32/33/48
- if DFU V5 is supported, rejects UpgradeStatus != IDLE
```

Likely rejection here: device already in upgrade/DFU state, not connected, unsupported mode, or incompatible status.

### DFU V5 prepare/transfer/validate layer

For devices using the newer DFU V5 path:

```text
ne.java:384-415
- picks DFU V5 when base feature 3 exists
- runs qm(k7, xd, callback)

qm.java:78-99
- init dfu api
- reads DfuProtocolInfo
- dispatches DfuV5Processor

p7.java:29-56
- query UpgradeStatus.IDLE
- prepareTransfer(type, totalSize, crc32, maxChunkSize, mode)
- startTransfer(fromBreakpoint=true)

r7.java:48-63
- sends chunks through api.d(byteArray)

p7.java:59-104
- validate command
- upgrade command
```

Likely rejection here: `PrepareResponse` error before body transfer, chunk write failure, validate failure after transfer, or final upgrade command failure.

### Device recovery / OTA package layer

The firmware package contains no obvious signature files:

```text
entries = recovery.bin, i18n.bin, font.bin, vendor.bin, quickapp.bin, ota.json, version, watchface.bin,
          vela_ap.bin, app.bin, misc.bin, system.bin, vela_ota.bin
suspicious_signature_entries = []
```

The visible `ota.json` has per-section MD5s, including `vela_ap.bin`; the patch-on-copy updated only the `vela_ap.bin` MD5 and both duplicate ZIPs pass `zip testzip`.

Device-side/recovery strings in `vela_ota.bin` show MD5 and fallback behavior:

```text
/data/ota.json
check_zip_file_md5
check_ota_files
check_upgraded_resource_md5
check file md5
json > filepath:%s json>md5_sum:%s
md5_tmp:%s
md5 not match
file:%s md5 is not ok
after upgrade md5 match check ok!
ota fail, will reboot to old system
ota success, will reboot to new system
```

Implication: the visible `ota.json` MD5 layer is probably satisfied by the patch-on-copy, but this does not rule out hidden app/bootloader validation.

### Hidden signature / boot verification uncertainty

The ZIP itself has no obvious `.sig`/cert entry, but `vela_ap.bin` contains generic crypto/RSA/verify strings:

```text
-----BEGIN RSA PUBLIC KEY-----
-----BEGIN PUBLIC KEY-----
rsaEncryption
[crypto:%d]Verify mdtype=%s, type=%d
[crypto:%d]rsa verify failed returned -0x%04x
```

This is not proof that OTA images are signed, and not proof that they are unsigned. It means the no-brick claim is still not proven.

## Current risk verdict

What is proven:

- The patch is a one-literal / 4-byte change on the SportXms start subscription path.
- The patched duplicate ZIPs are visible-manifest self-consistent.
- The expected `samples per packet` change is mathematically consistent with observed baseline and firmware batch formula.

What is not proven:

- Mi Fitness will accept a locally patched outer ZIP through the normal UI/cache path.
- The device will accept the patched ZIP in `prepareTransfer` / `validate`.
- Hidden signature/boot verification will pass.
- A failed validation always happens before destructive writes.
- A same-version original OTA can be re-sent as rollback on this exact band.

## Recommended next gate

Do not flash yet. The next low-risk gate should be one of:

1. **Deeper static DFU protocol audit**: recover `r7.b(...)` body from bytecode/smali or JADX bad-code output and map exact `prepare -> chunks -> validate -> upgrade` order.
2. **No-body live preflight only**, with explicit authorization: query DFU status / protocol info only; do not send firmware body, erase, validate, or upgrade.
3. **Rollback rehearsal with official package only**, after confirming same-version resend semantics and no write-before-validate risk.

If live patching is ever authorized, use the conservative `20000us` package first, not the `10000us` one.
