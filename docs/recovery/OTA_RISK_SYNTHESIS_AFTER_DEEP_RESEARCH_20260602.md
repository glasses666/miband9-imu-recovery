# Mi Band 9 n66nfc patched OTA risk synthesis after deep research

Date: 2026-06-02

Scope: local/static synthesis only. No phone UI action, no Notify `安装`, no OTA body/chunks, no `prepareTransfer`, no `validate`, no `upgrade`.

Inputs:

- User-provided public deep research report: `/path/to/local-user/.hermes/cache/documents/doc_c9e721e7225a_deep-research-report.md`
- Notify/NFX valid-file preflight: `docs/recovery/OTA_NOTIFY_FILE_PARSE_PREFLIGHT_20260602.md`
- Local OTA signature/static audit: `docs/recovery/N66NFC_OTA_SIGNATURE_MD5_STATIC_AUDIT_20260602.md`
- Existing patch/OTA audit: `docs/recovery/MAC_DIRECT_FIRMWARE_OTA_AUDIT_NPACK_PROOF_20260602.md`

## Bottom line

The patched `20000us` ZIP should **not** be treated as safe to install yet.

What improved:

- Public research supports that stock n66/n66nfc OTA ZIPs are commonly pushed locally via Notify/NFX / Mi Fitness hidden/manual paths.
- Public research supports that stock rollback/downgrade/flat-reflash exists in the community for Mi Band 9 NFC.
- Notify/NFX locally recognizes the patched ZIP as `有效固件` and exposes `新版本: 1.3.210`.

What got worse:

- Local static inspection found the original official ZIP has an invisible 80-byte post-EOCD trailer, while the rebuilt patched ZIP has no such trailer.
- `vela_ap.bin` contains a relevant OTA-adjacent verification cluster: `persist.verify.upgrade`, `verify_upgrade_package_func`, `padding_info_offset`, `Verification fail. Bad package`, `verify_package`, and `check_zip_file_md5`.
- This makes “visible `ota.json` MD5 updated” insufficient as an acceptance argument.

Risk verdict: **App-side file admission is green; device-side package acceptance is still yellow/red.** Do not tap Notify `安装` without a stronger plan.

## Public research synthesis

The deep research report found public evidence for stock firmware paths:

- BandBBS n66nfc official firmware posts expose Mi Fitness `checkUpdate` logs and stock ZIP md5 / filename.
- BandBBS Notify/NFX tutorials show local stock ZIP selection and install workflow.
- Wearable-Debug shows Mi Fitness hidden/manual local firmware entry via `manualUpgrade(context, path, false)`.
- BandBBS Vela wearable knowledge-base uses Mi Band 9 NFC as a downgrade example.
- A Mi Band 9 temporary-file cleanup thread explicitly mentions stock flat-reflash and `/data/mass/tmp/ota` temporary OTA residues.

But the report did **not** find public n66/n66nfc evidence for:

- modified/patched Vela OTA ZIP acceptance;
- “edited `ota.json` MD5 is enough”;
- `validate failed`, `md5 not match`, `hidden signature`, `RSA verify`, or `FIRMWARE5_ZIP` logs for a modified Band 9 package;
- prepare failure being provably non-destructive.

Therefore public evidence lowers the risk for **stock local OTA**, but does not validate **patched OTA**.

## Notify/NFX install path after `安装`

Static trace from decompiled Notify/NFX sources confirms the valid-file parser and install path are separate.

### File admission before install

`UpdateFirmwareActivity` path:

```text
buttonChooseFirmwareFile
  -> ACTION_GET_CONTENT requestCode=10037
  -> x1(uri, true)
  -> copy selected URI to getCacheDir()/firmware
  -> w1(false)
  -> new i6.l(...)
  -> require lVar.h()
  -> UI: 有效固件 / 新版本 / enable buttonStartUpdate
```

`i6.l` classifies `FIRMWARE5_ZIP` shallowly:

```text
ZIP first bytes PK
+ ota.sh or ota.json present
+ optional ota.json sw_version extraction
```

### Install button boundary

`UpdateFirmwareActivity.k0.b()` sends broadcast action:

```text
302ff3b3-953f-4a3c-8c3e-b8451f20fe53
extras:
  firmwareFile
  forceValidFirmware
  firmwareType
```

`BaseService` receives and dispatches normal firmware to:

```text
BaseService$a$i.run()
  -> f20632b.J.F(uri, forceValidFirmware)
```

`e6.c.F()` then:

```text
open firmware URI
copy to cache/fwUpload
p2(true, 0, "0", fileHash, successCallback, errorCallback)
```

`p2()` sends an upgrade-like preflight request:

```text
f8.a.type = 2
f8.a.subtype = 5
```

On success, it enters file upload:

```text
N2(0, 0, fwUpload.path, responseValue, progressCallback)
  -> r8.c
  -> B2/A2
  -> n8.v1
  -> n8.l1.c(): type=22/subtype=0 with hash/length/offset
  -> n8.l1.u(): D1(104, chunkBytes, ...)
```

Static conclusion:

- `有效固件` is only local host-side parser success.
- Tapping `安装` moves into a service path that sends upgrade-like preflight and then body/chunks.
- In this Notify path, a visible preflight (`type=2/subtype=5`) occurs before chunks.
- The decompiled path did not show a separate explicit `validate` / `upgrade` command after chunks; chunk completion leads to done broadcast. That means validation/upgrade may be implicit inside device/firmware handling or hidden in lower layers, not absent as a risk.

## OTA ZIP validation / signature evidence

Static inspection of the original stock ZIP and patched ZIP:

```text
Original ZIP:
  md5:    673e64214a0c42412771243b5f3a47bb
  sha256: 8f8a20a8c690de2cd4e1bc6ddd3969e00fe9d55970ba0ccf4445a908ace37c23
  visible entries: 13
  META-INF/signature entries: none
  ZIP digital signature record: none
  post-EOCD trailer: 80 bytes

Patched 20000us ZIP:
  sha256: 36f5ed2a8af93b7d22a71aa1ce13c4003eba2321ce437e5f30a00dce0cb13262
  visible entries: 13
  changed entries: ota.json, vela_ap.bin
  post-EOCD trailer: 0 bytes
```

Original post-EOCD trailer:

```text
00 00 00 01 10 00 00 00 00 00 00 00 00 00 00 00
AA 48 E7 0A 8D 6D 83 30 E0 9F 2E 8B BE B3 02 56
8B F2 4F B8 3D 2C 25 B6 30 43 8F 85 FC 02 55 0E
0F C4 4B 5E 46 F4 FB 8C F4 18 E5 B5 84 63 3F 64
F9 37 9D D4 9E A1 99 43 C8 B1 CA D9 A0 76 B1 FB
```

The patched ZIP was rebuilt without this hidden trailer. Since the content changed, simply copying the old trailer back would not prove validity.

### `vela_ota.bin` recovery-side evidence

`vela_ota.bin` contains visible MD5/recovery strings:

```text
/data/ota.json
check_upgraded_resource_md5
check_zip_file_md5
check_ota_files
md5 not match
check ota.zip md5 failled!
ota fail, will reboot to old system
ota success, will reboot to new system
```

This supports visible `/data/ota.json` per-file MD5 checking and old/new-system fallback messaging.

### `vela_ap.bin` hidden verification evidence

`vela_ap.bin` contains a stronger upgrade verification cluster:

```text
persist.verify.upgrade
verify_upgrade_package_func
padding_info_offset = %ld
update hash256 err
read magic err
malloc memory for sign info fail
Verification passed. Congratulations!!!
Verification fail. Bad package
verify %s fail
/data/ota.json
vela_ota.bin
start reboot to enter ota
USAGE: upgrade /system/xxx.zip
upgrade_main
verify_package
check_zip_file_md5
```

It also contains generic crypto/app verification strings:

```text
-----BEGIN RSA PUBLIC KEY-----
SHA-256
rsaEncryption
rsa verify failed
mbedtls_pk_verify(...)
```

The generic crypto strings may belong partly to app/quickapp verification, but the `verify_upgrade_package_func` cluster is OTA-adjacent and directly relevant.

## Current install decision

Do not install the current patched ZIP yet.

Reasons:

1. It lacks the official hidden 80-byte post-EOCD trailer.
2. The main AP image has an upgrade package verification path that likely reads padding/sign/hash data.
3. Notify local parser is too shallow to prove device acceptance.
4. Public research found no n66/n66nfc modified-ZIP acceptance case.
5. Public stock rollback/flat-reflash evidence does not prove patched-package failure is harmless.

## Safer next gates

1. Decode or callgraph the 80-byte trailer / `verify_upgrade_package_func` path:
   - determine exact trailer format;
   - determine whether it signs the ZIP contents, central directory, full package, or only metadata;
   - determine whether `persist.verify.upgrade` can disable/enable the check on retail firmware.

2. Check whether official stock ZIPs for adjacent n66nfc versions all have the same post-EOCD trailer shape.

3. If patching continues, avoid rebuilding the ZIP casually. Preserve original ZIP structure as much as possible and understand the trailer before producing a new candidate.

4. Only after a stronger package-verification answer, consider a live OTA runbook. That runbook must still treat `安装` as real OTA and capture preflight/progress/reboot evidence.

## Final status

- `Notify/NFX 有效固件`: proven.
- Stock local OTA support: publicly supported.
- Stock rollback/downgrade/flat-reflash: publicly supported.
- Patched ZIP device acceptance: not proven; now more suspicious due to hidden trailer.
- Current recommendation: **stop before install; continue static verification work.**
