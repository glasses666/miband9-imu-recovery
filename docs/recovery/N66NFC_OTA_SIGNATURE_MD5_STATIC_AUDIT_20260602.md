# n66nfc OTA ZIP / firmware static validation audit

Scope: local static inspection only. No phone access, no live OTA, no flashing.

## Inputs

- Original OTA ZIP: `/tmp/miband9_windows_firmware_20260601_2140/673e64214a0c42412771243b5f3a47bb_upd_miwear.watch.n66nfc.zip`
  - size: `43934358`
  - md5: `673e64214a0c42412771243b5f3a47bb`
  - sha256: `8f8a20a8c690de2cd4e1bc6ddd3969e00fe9d55970ba0ccf4445a908ace37c23`
- Patched 20000us ZIP: `/tmp/miband9_patch_on_copy_20260602_022409/mi_band9_n66nfc_sportxms_latency_20000us_patch_on_copy.zip`
  - size: `43905667`
  - md5: `2e83f441715bcd67e291cd5fe60aea0d`
  - sha256: `36f5ed2a8af93b7d22a71aa1ce13c4003eba2321ce437e5f30a00dce0cb13262`
- Temporary extracted static artifacts: `/tmp/miband9_static_inspect_20260602/{orig,patched}/`

Commands used included:

```sh
stat -f 'path=%N size=%z mtime=%Sm' <zip>
shasum -a 256 <zip>
md5 -r <zip>
unzip -tqq <zip>
python3 - <<'PY'  # zipfile entry/hash compare, EOCD/trailer parse, string-offset scan
...
PY
```

## ZIP visible entries and manifest layer

`unzip -tqq` passed for both ZIPs.

Python `zipfile` inspection:

```text
original: testzip_bad=None, zip_comment_len=0
patched:  testzip_bad=None, zip_comment_len=0
entries: recovery.bin, i18n.bin, font.bin, vendor.bin, quickapp.bin, ota.json, version,
         watchface.bin, vela_ap.bin, app.bin, misc.bin, system.bin, vela_ota.bin
suspicious entry names matching META-INF/signature/.sig/cert/.RSA/.SF/.DSA/.EC: []
ZIP digital-signature record PK\x05\x05 count: 0
```

Visible content diff original -> patched:

```text
unchanged by uncompressed content: recovery.bin, i18n.bin, font.bin, vendor.bin,
quickapp.bin, version, watchface.bin, app.bin, misc.bin, system.bin, vela_ota.bin
changed: ota.json, vela_ap.bin
```

`vela_ap.bin` binary diff is a single 3-byte effective little-endian literal change at raw offset `0x17cc00`:

```text
range 0x17cc00..0x17cc02: orig a0 86 01 -> patched 20 4e 00
full dword: orig a0 86 01 00 = 100000 us; patched 20 4e 00 00 = 20000 us
```

`ota.json` diff updates only the visible md5 for `vela_ap.bin`:

```diff
- "md5sum": "430296be4a57b66be936ce8ffe2783b0"
+ "md5sum": "949df76a6241ce08ad628146501e8680"
```

Therefore the patched ZIP is visibly self-consistent at the `ota.json` per-file MD5 layer.

## Hidden trailer after EOCD: important new evidence

The original ZIP has bytes after the ZIP End Of Central Directory even though the ZIP comment length is zero. These bytes are not listed as a ZIP entry and are not a normal ZIP comment.

EOCD parse command logic: locate `PK\x05\x06`, parse EOCD fields, compute `eocd_end = eocd + 22 + comment_len`, then compare file size.

```text
original:
  size=43934358
  eocd=0x29e6230
  eocd_end=0x29e6246
  comment_len=0
  trailing_after_eocd=80
  central_directory_offset=0x29e5e24
  gap_before_central_directory=0

patched:
  size=43905667
  eocd=0x29df26d
  eocd_end=0x29df283
  comment_len=0
  trailing_after_eocd=0
  central_directory_offset=0x29def99
  gap_before_central_directory=0
```

Original 80-byte trailer:

```text
hex:
00 00 00 01 10 00 00 00 00 00 00 00 00 00 00 00
AA 48 E7 0A 8D 6D 83 30 E0 9F 2E 8B BE B3 02 56
8B F2 4F B8 3D 2C 25 B6 30 43 8F 85 FC 02 55 0E
0F C4 4B 5E 46 F4 FB 8C F4 18 E5 B5 84 63 3F 64
F9 37 9D D4 9E A1 99 43 C8 B1 CA D9 A0 76 B1 FB

ascii:
.................H...m.0.......V..O.=,%.0C....U...K^F........c?d.7.....C.....v..
```

Interpretation:

- It is not a `META-INF`/JAR signing file, not a ZIP comment, and not an APK-v2-style pre-central-directory block (`gap_before_central_directory=0`).
- It is exactly `16 + 64` bytes. The final 64 bytes look high-entropy and could plausibly be a vendor signature/digest record.
- The patched ZIP was rebuilt without this trailer. Even if the trailer were copied, it would no longer verify patched content unless the signing scheme is not content-bound.

This is the strongest static clue that the official OTA carries hidden non-manifest validation data outside normal ZIP entries.

## `vela_ota.bin` recovery-side strings

Focused ASCII string scan on original `vela_ota.bin` shows recovery/OTA MD5 behavior, with offsets in the uncompressed `vela_ota.bin`:

```text
0x0009493b:  %s: ota fail, will reboot to old system, errno is %d
0x00094972:  %s: ota success, will reboot to new system
0x00094d88:  %s: check file md5: %s
0x00094e82: %s: json > filepath:%s json>md5_sum:%s
0x00094eaa: %s: md5_tmp:%s
0x00094eba: %s: md5 not match
0x00094ecd:  %s: check file md5: %s md5 match check ok!
0x0009503a: %s: file:%s md5 is not ok
0x00095084: /data/ota.json
0x000950a0: check_upgraded_resource_md5
0x000950c8: check_zip_file_md5
0x00095189:  %s: after upgrade md5 match check ok!
0x00095245:  %s: starting recovery ap....
0x0009528c: recovery_firmware
0x00095474:  %s: recovery ok!
0x00095486:  %s: recovery failed! times:%d,ret:%d
0x000955f6: %s: check ota.zip md5 failled!
0x00095616: check_ota_files
```

Focused scan did not find obvious OTA RSA/signature/public-key strings in `vela_ota.bin`. This suggests the recovery image itself visibly relies on `/data/ota.json` MD5 checks and success/fail fallback messaging.

## `vela_ap.bin` main-AP upgrade/signature strings

Focused ASCII string scan on original `vela_ap.bin` found a much stronger hidden-verification path near the OTA upgrade command strings:

```text
0x005133ac: persist.verify.upgrade
0x005133c3:  %s: verify_upgrade_package_func: %s
0x00513403:  %s: padding_info_offset = %ld
0x00513423: %s: update hash256 err
0x0051343b: %s: 256 err
0x00513448:  %s: digest_bytes[%d] = 0x%x
0x00513466: %s: read magic err
0x00513496: %s: malloc memory for sign info fail
0x005134bc:  %s: Verification passed.  Congratulations!!!
0x005134eb: %s: Verification fail.  Bad package
0x00513510: %s: verify %s fail
0x005136cc: /data/ota.json
0x005136ea: magic_string
0x00513729: ota_version
0x0051374b: sections
0x00513761: main_bootloader
0x0051377c: location_path
0x0051378a: md5sum
0x00513791: %s: upgrade bootloader firmware md5sum= %s
0x005137be: vela_ota.bin
0x005137cb:  %s: check file md5: %s
0x0051380a: %s: json > filepath:%s json>md5_sum:%s
0x00513842: %s: md5 not match
0x00513855:  %s: check file md5: %s md5 match check ok!
0x005138a0: main_app
0x005138b6: %s: upgrade firmware ok
0x005138cf:  %s: after upgrade md5 match check ok!
0x00513951:  %s: start reboot to enter ota
0x00513986: %s: USAGE: upgrade /system/xxx.zip
0x005139be: miwear.watch.n66nfc
0x005145f8: upgrade_main
0x0051466e: verify_package
0x00514740: upgrade_bootloader
0x005147d5: check_zip_file_md5
0x00514810: do_extract_currentfile_ota
```

Separate crypto/app verification strings exist in the same `vela_ap.bin`:

```text
0x004f458d: -----BEGIN RSA PUBLIC KEY-----
0x004f45c5: -----BEGIN PUBLIC KEY-----
0x004f4c96: SHA-256
0x004f4cc8: rsaEncryption
0x004fe8e1: [crypto:%d]Verify mdtype=%s, type=%d
0x004fe908: [crypto:%d]rsa verify failed returned -0x%04x
0x0050592b: ext/src/app_verify.c
0x00505a8e: read(fd, &app_block.signature_block.length, 4) > 0
0x00505c2b: (res = mbedtls_pk_verify(&pk, mbedtls_md_get_type(mdinfo), md, mbedtls_md_get_size(mdinfo), signature->data, signature->length)) == 0
0x00505cb1: (res = verify_block_signature(&signature_info.public_key, &signature_info.signed_data, &signature_info.signatures_content))== 0
0x00505db3: app_block_digest_verification(app_verify_info, &signature_info.one_digest) == 0
0x005aa5fa: app_verification(app_verify_info) == 0
```

The `app_verify.c` / AIOTJS strings may be for `.rpk`/quickapp packages and are not by themselves proof of OTA signing. The more relevant evidence is the nearby `persist.verify.upgrade` / `verify_upgrade_package_func` / `padding_info_offset` / `Verification fail. Bad package` cluster adjacent to `/data/ota.json`, `vela_ota.bin`, `upgrade_main`, and `check_zip_file_md5`.

## Bottom line

- Visible `ota.json` MD5 is likely sufficient only for the recovery-side per-file MD5 layer visible in `vela_ota.bin`.
- It is **not** likely sufficient for the full official OTA acceptance path.
- Static evidence points to an additional hidden package verification layer in `vela_ap.bin`, and the original ZIP contains an invisible 80-byte post-EOCD trailer that the patched ZIP lacks.
- Therefore a patched ZIP with only updated `ota.json` MD5 is at material risk of failing device-side `verify_package` / `verify_upgrade_package_func` before or during the AP-to-recovery transition.

## Uncertainty

- This was strings/structure inspection, not a full disassembly/callgraph proof. I did not prove the exact call order or whether `persist.verify.upgrade` is enabled on retail devices.
- The 80-byte trailer format is not decoded. It may be signature, digest, or vendor metadata. Its placement, size, and nearby firmware strings make a hidden signature/hash hypothesis likely, but not mathematically proven.
- No live OTA, no phone interaction, and no flashing were performed.
