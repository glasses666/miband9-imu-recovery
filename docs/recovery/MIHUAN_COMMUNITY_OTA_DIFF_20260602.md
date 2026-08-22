# Mi Band 9 third-party flash app audit: 米环社区 / Notify / Mi Fitness

Date: 2026-06-02

Scope: read-only APK/JADX audit only. No app launch, no band connection, no OTA write, no firmware body transfer, no factory mode.

## Bottom line

Two Android apps were found on the phone-side APK set and audited:

- `tech.pingx.watchface` — 米环/表盘社区 style app, version observed from package dump as `6.2.8`.
- `com.mc.xiaomi1` — Notify for Mi Band/Amazfit style app.

They are materially different:

1. `tech.pingx.watchface` is useful evidence for **Xiaomi auth + RPK/watchface/app-resource install over FE95/XiaomiProto**, but it does **not** look like the right path for flashing our full Mi Band 9 NFC OTA ZIP (`ota.json` + `vela_ap.bin` + `vela_ota.bin` etc.).
2. `com.mc.xiaomi1` does have a real **local firmware/custom firmware** path and recognizes full Xiaomi/Vela OTA ZIPs by `ota.sh` / `ota.json`. This probably bypasses Mi Fitness' cloud/download-cache MD5 gate, but it does not prove the device will accept the patched package.
3. Neither app bypasses the band-side validation problem. A patched ZIP can still be rejected at prepare/transfer/validate/upgrade or by recovery/boot checks.

## Evidence: `tech.pingx.watchface`

Artifact root:

```text
/tmp/mihuan_community_app_audit_20260602_030607/jadx-tech-pingx
```

### Accepted external file types are `.bin`, `.rpk`, `.face`

`FileOpenActivity` only accepts:

```text
FileOpenActivity.java:88-91
- .bin
- .rpk
- .face
```

It does not accept `.zip` as a direct external file for full firmware OTA.

### N66 / Mi Band 9 is present, but in watchface/RPK resource tooling

Evidence examples:

```text
com/givemefive/ble/device/DeviceType.java
- MI_BAND_N66

com/givemefive/ble/device/c.java
- N66 maps to miwear.watch.n66 / miwear.watch.n66cn

com/givemefive/mi8wf/util/BaseUtil.java
- DEVICE_TYPE_N66 = "N66"
```

This confirms Band 9/N66 support, but the surrounding package is `mi8wf` / watchface packing and device compatibility logic.

### Xiaomi BLE path is Gadgetbridge-like FE95/XiaomiProto, not Mi Fitness OTA UI

The app imports Gadgetbridge Xiaomi protobuf classes:

```text
com/givemefive/ble/xiaomi/t.java:10
import nodomain.freeyourgadget.gadgetbridge.proto.xiaomi.XiaomiProto;
```

The command router maps:

```text
com/givemefive/ble/xiaomi/t.java:82-85
- type 1  -> auth/session handler
- type 4  -> misc/device handler
- type 20 -> RPK/watchface handler
- type 22 -> data-upload handler
```

The FE95/SAR-ish chunker in `k.java` uses:

```text
com/givemefive/ble/xiaomi/k.java
- max payload chunk = 242 bytes
- chunk start / ack / chunk transfer framing
- optional encrypted payload through Xiaomi session handler
```

This is very useful as a protocol reference for our Mac direct transport, but it is not a full OTA boot/recovery flash path.

### RPK/watchface install flow

`o.java` is the RPK/watchface installer:

```text
com/givemefive/ble/xiaomi/o.java
- type 20, subtype 1: RpkInstallStart
- type 20, subtype 3: delete RPK
- upload uses type 22 DataUpload
```

`m.java` is the generic data-upload helper:

```text
com/givemefive/ble/xiaomi/m.java
- type 22 DataUploadRequest
- carries md5Sum + size
- uploads chunks after device acknowledges upload start
```

`n.java` validates three resource styles:

```text
com/givemefive/ble/xiaomi/n.java
- raw watchface header 0x5A 0xA5
- .rpk containing manifest.json with package/name/versionName/versionCode
- .mwz-like ZIP with resource.bin; then may copy into Mi Fitness WatchFace dir via Shizuku
```

This is app/watchface/resource install, not the official OTA ZIP containing `vela_ap.bin`.

### Auth/key behavior

`BLEActivityMi8BleNew.java` can read auth material from Mi Fitness logs / AuthKey tool, then uses Xiaomi session auth. This is why the app can connect to modern Xiaomi bands. Raw values are intentionally not reproduced here.

## Evidence: `com.mc.xiaomi1` / Notify

Artifact root:

```text
/tmp/mihuan_community_app_audit_20260602_030607/jadx-com-mc
```

### It has a real custom firmware UI

`UpdateFirmwareActivity.java` contains the custom firmware flow and passes file URI + firmware type to `BaseService`:

```text
com/mc/xiaomi1/ui/updateFirmware/UpdateFirmwareActivity.java
- firmwareFile
- firmwareType
- forceValidFirmware
- FIRMWARE5_ZIP
- THIRD_PARTY_APP
```

This is a stronger candidate than `tech.pingx.watchface` for local patched OTA testing.

### It recognizes full Vela/Xiaomi OTA ZIPs

`i6/l.java` classifies firmware formats:

```text
i6/l.java:86-89
- FIRMWARE      if magic 0x78563412
- FIRMWARE2     if contains "midr.watch"
- FIRMWARE3     if starts 0x605A5A7E / 0x805A5A7E
- FIRMWARE5_ZIP if ZIP contains ota.sh or ota.json
```

It extracts `sw_version` from `ota.json`:

```text
i6/l.java:157-172
- if entry name == "ota.json", parse JSON and read sw_version
```

Our Mi Band 9 NFC OTA ZIP has `ota.json`, so Notify's parser should classify it as `FIRMWARE5_ZIP`.

### It likely bypasses Mi Fitness cloud/download-cache MD5, but not device-side checks

For local firmware file import, the app copies the user-selected file to its own cache and starts its own BLE/update path:

```text
e6/c.java:2442-2473
- openInputStream(uri)
- copy to cache/fwUpload
- p2(... n8.o1.b(n8.o1.a(file)) ...)
```

This is different from Mi Fitness' server-driven `HuamiOtaManager` path, where the app first checks the downloaded file against cloud-provided MD5 before populating `firmwareUpdateMap`.

So: Notify can likely skip the **Mi Fitness app/cache MD5** layer.

But after local file admission, it still sends an update request and a file body into the device protocol:

```text
e6/c.java:4219-4231
- p2(...): type=2 subtype=5 update preflight/request

e6/c.java:4149-4160
- n2(...): type=20 subtype=1, package/file metadata

e6/c.java:2355-2357
- C2(...): B2(4, 0, file path, ...)

e6/c.java:2274-2277
- A2(...): new n8.v1(...).d(... file path ...)
```

This still leaves the same critical question: whether the band accepts `prepareTransfer`, chunks, `validate`, and `upgrade` for a patched ZIP.

### It also supports third-party apps, separately from full firmware

`i6/k.java` detects third-party apps as ZIPs with `manifest.json`:

```text
i6/k.java:79-94
- unzip ZIP
- require manifest.json
- read package/versionCode/versionName
- type = THIRD_PARTY_APP
```

That is separate from full firmware OTA.

## Comparison against Mi Fitness official path

### Mi Fitness

Already documented in:

```text
docs/recovery/MAC_DIRECT_FIRMWARE_OTA_AUDIT_NPACK_PROOF_20260602.md
```

Key gates:

```text
App/cache layer:
- cloud/download metadata MD5 gate before firmwareUpdateMap

DFU V5 layer:
- query UpgradeStatus.IDLE
- prepareTransfer(type, totalSize, crc32, maxChunkSize, mode)
- startTransfer
- chunks
- validate
- upgrade

Device/recovery layer:
- /data/ota.json
- check_zip_file_md5
- md5 not match
- ota fail, will reboot to old system
```

### 米环社区 / `tech.pingx.watchface`

Bypasses Mi Fitness official UI because it does not use Mi Fitness OTA flow, but it is mostly the wrong artifact class for our patch:

```text
watchface/RPK/resource app install over XiaomiProto type 20 + type 22
```

It is good protocol reference material; not a clean full firmware OTA test harness.

### Notify / `com.mc.xiaomi1`

Likely bypasses Mi Fitness cloud/download-cache MD5 because it accepts a local file and has its own firmware import/update UI.

But it still cannot bypass device-side validation. It only moves us past the earliest host-side gate.

## Practical verdict for our patch plan

### Is 米环社区 different?

Yes, but not in the way we need:

- It is different from Mi Fitness because it uses its own BLE/XiaomiProto flow and can install `.rpk`/watchface/app resources.
- It is not obviously a full Mi Band 9 NFC OTA ZIP flasher.
- It will not answer the brick-risk question for patching `vela_ap.bin` inside a full OTA ZIP.

### Is Notify different?

Yes, and more relevant:

- It has local custom firmware support.
- It recognizes Vela-style OTA ZIPs with `ota.json` / `ota.sh` as `FIRMWARE5_ZIP`.
- It likely bypasses Mi Fitness' server/cache MD5 gate.
- It still cannot bypass device `prepare/validate/upgrade/recovery` checks.

### Is either app safer for live flashing?

Not enough evidence. Notify may be a better host to test local package admission, but it is not automatically safer than our own controlled tool.

For safety, the next test should still be no-body/preflight or deliberately early-rejected metadata, not firmware body transfer.

## Recommended next gate

1. Use `tech.pingx.watchface` source as a reference for XiaomiProto/RPK/data-upload framing only.
2. Use `com.mc.xiaomi1` as a reference for local `FIRMWARE5_ZIP` admission and host-side checks.
3. Do not use either app to flash yet.
4. If testing app-side behavior, first test a local file classifier/admission path only, not connected to the band.
5. If testing live behavior later, perform a no-body preflight using our own Mac tool or a controlled harness:
   - query DFU/update status only;
   - do not send `vela_ap.bin` body;
   - do not validate;
   - do not upgrade.
6. If any real OTA is eventually authorized, start with the conservative `20000us` patched ZIP and have the original official ZIP staged as rollback evidence, while understanding rollback is not yet proven.
