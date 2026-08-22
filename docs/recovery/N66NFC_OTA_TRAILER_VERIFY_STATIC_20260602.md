# n66nfc OTA post-EOCD trailer / verify-package static analysis (2026-06-02)

## Scope

This is step 1 of the current-version patched OTA safety work: static trailer / verify-path analysis only.

Safety boundary:

- no band connection;
- no Notify/NFX install click;
- no Mi Fitness/DFU `prepare`, body/chunk transfer, `validate`, `upgrade`, or recovery command;
- no patched package generated in this pass.

Inputs:

```text
1.3.206 official: /path/to/local-user/Downloads/Telegram Desktop/MIBand9_1.3.206.zip
1.3.210 official: /tmp/miband9_windows_firmware_20260601_2140/673e64214a0c42412771243b5f3a47bb_upd_miwear.watch.n66nfc.zip
old patched 1.3.210 20000us artifact, static comparison only: /tmp/miband9_patch_on_copy_20260602_022409/mi_band9_n66nfc_sportxms_latency_20000us_patch_on_copy.zip
```

A read-only helper was added:

```text
tools/firmware/audit_ota_trailer.py
```

It parses EOCD, post-EOCD trailer, visible ZIP entries, `ota.json` MD5 consistency, and suspicious signature-like ZIP entries. It does not patch, repack, connect to a device, or call any OTA install path.

## Bottom line

The post-EOCD 80-byte block is strongly tied to device-side package verification, not a harmless ZIP comment.

Best current static model:

```text
trailer[0:4]   = magic / marker = 00 00 00 01
trailer[4]     = offset_from_head = 0x10 = 16
trailer[5:16]  = reserved / padding = 11 zero bytes
trailer[16:80] = 64-byte signature / sign_info
```

`verify_package` in `vela_ap.bin` does the following under the corrected 2026-06-02 reproduction:

1. check `persist.verify.upgrade` against string `on`;
2. if enabled, open the OTA ZIP as a raw file;
3. compute `padding_info_offset = file_size - 0x50`;
4. compute a firmware-specific SHA-256 **stride digest**, not a linear full-file digest:
   - for each complete 1 MiB region before `padding_info_offset`, hash only the first `0x400` bytes at that MiB boundary;
   - then hash the final low-20-bit remainder contiguously in `0x400` chunks plus tail;
5. seek/read the trailer at `EOF - 0x50`;
6. read the 4-byte marker and 1-byte `offset_from_head`;
7. read `0x50 - offset_from_head = 64` bytes of sign info;
8. verify `trailer[16:80]` as raw secp256k1 ECDSA `(r,s)` against the stride digest using the embedded AP-side public key;
9. log either:
   - `Verification passed. Congratulations!!!`, or
   - `Verification fail. Bad package`.

Therefore:

- the hidden signature binds selected raw ZIP byte ranges plus the final low-20-bit remainder, not every byte of the ZIP;
- a normal Python `zipfile` repack drops the post-EOCD trailer entirely;
- ordinary patch-on-copy + updated visible `ota.json` MD5 + old trailer was tested locally and fails this AP-side verifier;
- visible `ota.json` MD5 self-consistency is not enough for device acceptance.

## Official package trailer comparison

`1.3.206` official:

```text
outer md5                  = 16194c1758240ab236d43534f0537b2d
outer sha256               = b42cc913af5941d5a48222767dd13180db88b16651efc7141122c6d3a42802e4
sw_version                 = 1.3.206
zip test                   = pass
visible section MD5s       = all matched
central directory offset   = 0x29e5d89
central directory size     = 1036
EOCD offset                = 0x29e6195
ZIP comment length         = 0
post-EOCD trailer length   = 80
linear sha256 without trailer = 44d2f1ca1a702530b1eda77af33a75532669b9fd76920ec99b39bd7f125cf73e
firmware stride sha256     = b43272bc3ecb57f20be42173c615bc6bf59ede71d9c340d690901dd4dbbc75d3
stride verifier result     = pass
```

`1.3.206` trailer:

```text
00 00 00 01 10 00 00 00 00 00 00 00 00 00 00 00
55 48 4D EA 19 03 51 AD C8 87 4D 75 53 AC EA 02
17 25 E8 FB FD C5 DC 38 13 CF 4C 42 75 E6 F7 90
3C F2 C9 5C D7 F3 72 21 30 FE FC AD CC 43 1A BE
D6 65 A3 D3 B5 27 1F 46 73 43 C9 37 08 FE 25 3D
```

`1.3.210` official:

```text
outer md5                  = 673e64214a0c42412771243b5f3a47bb
outer sha256               = 8f8a20a8c690de2cd4e1bc6ddd3969e00fe9d55970ba0ccf4445a908ace37c23
sw_version                 = 1.3.210
zip test                   = pass
visible section MD5s       = all matched
central directory offset   = 0x29e5e24
central directory size     = 1036
EOCD offset                = 0x29e6230
ZIP comment length         = 0
post-EOCD trailer length   = 80
linear sha256 without trailer = bd7f4a343c01645fbf29ecb9601270b1b7d2b058d7f6495aafe6905258c4fc75
firmware stride sha256     = 20420b6185566fc72df48c53b2f0b5cb437368ec4af73ddca0ea0ace8c54411e
stride verifier result     = pass
```

`1.3.210` trailer:

```text
00 00 00 01 10 00 00 00 00 00 00 00 00 00 00 00
AA 48 E7 0A 8D 6D 83 30 E0 9F 2E 8B BE B3 02 56
8B F2 4F B8 3D 2C 25 B6 30 43 8F 85 FC 02 55 0E
0F C4 4B 5E 46 F4 FB 8C F4 18 E5 B5 84 63 3F 64
F9 37 9D D4 9E A1 99 43 C8 B1 CA D9 A0 76 B1 FB
```

Invariant comparison:

```text
entry order 1.3.206 vs 1.3.210: same
trailer length                   : both 80
first 16 trailer bytes           : identical
64-byte sign_info tail           : different; 63/64 bytes differ
```

The 1.3.206 and 1.3.210 packages have identical entry order and many identical resources; only `ota.json` and `vela_ap.bin` materially changed among visible entries. The sign_info tail changing almost completely is consistent with a signature over package contents.

Old patched 1.3.210 20000us artifact, static comparison only:

```text
sw_version               = 1.3.210
zip test                 = pass
visible section MD5s     = all matched
post-EOCD trailer length = 0
```

This confirms the previous Python repack style loses the hidden trailer.

## Static verify-path evidence in `vela_ap.bin` 1.3.206

Important string xrefs were found around raw code region `0x139f80..0x13b120` in extracted `vela_ap.bin`.

Property gate:

```text
0x13a024: ldr r0, [pc, #0x2d0] ; "persist.verify.upgrade"
0x13a026: bl  #0x2e32c4        ; read property into stack buffer
0x13a038: ldr r0, [pc, #0x2b8] ; "on"
0x13a046: bl  #0x64ee8         ; compare with property buffer
0x13a04e: bne.w #0x13a632      ; if not "on", skip verify_package path
```

Raw package hashing:

```text
0x13a0dc..0x13a0e0 construct SHA-256 IV word 0x5be0cd19
0x13a0e4: "%s: padding_info_offset = %ld"
0x13a0ec: lsrs r3, r5, #0x14     ; high complete-MiB count
0x13a0ee: ubfx r8, r5, #0, #0x14 ; low 20-bit remainder
...
0x13a26c..0x13a2a2 seek/hash 0x400 bytes at each complete-MiB boundary
0x13a12c..0x13a142 read/hash final partial block
```

`r5` is derived from opened file size minus `0x50`, so the logged `padding_info_offset` is `file_size - 80`. The corrected digest model is:

```text
for i in range((file_size - 80) >> 20):
    sha256.update(pkg[i * 0x100000 : i * 0x100000 + 0x400])
sha256.update(pkg[((file_size - 80) >> 20) * 0x100000 : file_size - 80])
```

Trailer read:

```text
0x13a238..0x13a246 seek to -0x50 from EOF
0x13a24a..0x13a252 read 4 bytes
0x13a25c: "%s: read magic err"
0x13a33c..0x13a344 read 1 byte
0x13a34c..0x13a350 "%s: offset_from_head = %d"
0x13a36a allocates 0x50 - offset_from_head bytes
0x13a37e..0x13a388 reads the sign_info block
```

With the observed official trailer, that yields:

```text
magic4           = 00 00 00 01
offset_from_head = 0x10
reserved         = 11 zero bytes
sign_info length = 64 bytes
```

Signature verification:

```text
0x13a3e4..0x13a610 performs multi-precision / secp256k1 ECDSA-style operations
0x13a616: "Verification passed.  Congratulations!!!"
0x13a79a: "Verification fail.  Bad package"
```

The function references a secp256k1 data table near raw `0x51991c`. The embedded AP-side public key used by this path is:

```text
Qx = 4c5ee3be1fc08452f8b7064cbec0bd13b65a9fced76acf9d87c7fba91add3dd5
Qy = 85356d12dbb8278e4b3c8b61c40b87c62ab613c1f0f69f8c21b90bde5856687e
```

`tools/firmware/ota_trailer_ecdsa_probe.py` reproduces the AP-side verifier for official `1.3.206` and `1.3.210` when using the firmware stride digest above.

## Answer to the safety questions

### 1. What is the 80-byte trailer?

Best static model: a 16-byte header plus a 64-byte signature/sign_info.

### 2. Does it bind to full ZIP contents?

Partially. The AP-side verifier does **not** hash every byte linearly. It hashes a firmware stride digest:

- first `0x400` bytes at each complete 1 MiB boundary before `file_size - 80`;
- then the final low-20-bit remainder contiguously through EOCD;
- excludes the final 80-byte post-EOCD trailer.

This still binds the ZIP layout, central directory/EOCD, and selected compressed-data regions. It does not prove every uncompressed firmware byte is directly covered by the hidden signature.

### 3. Is `persist.verify.upgrade` enabled on retail devices?

Not answered yet. Static code shows the gate exists and that non-`on` appears to skip verification. The live/default property state on the band is not known from this static pass.

### 4. Do adjacent official n66nfc packages share trailer structure?

Yes. `1.3.206` and `1.3.210` both have:

```text
00 00 00 01 10 00 00 00 00 00 00 00 00 00 00 00 + 64-byte tail
```

### 5. Can a patched candidate preserve/recompute the material?

Preserve: physically yes, by appending the old 80-byte trailer. But a `/tmp` local-only `1.3.206` SportXms `20000us` patch-on-copy with updated visible `ota.json` MD5 and the old trailer appended failed the reproduced AP-side stride verifier.

Recompute: not possible from current evidence without the private signing key or a bypass/disabled `persist.verify.upgrade` path. No recomputation path was found.

### 6. What happens on failure?

Static logs show failure before/inside `verify_package` produces:

```text
Verification fail. Bad package
verify %s fail
```

The exact live phase and whether rejection happens before body transfer depends on which app/device path invokes this function. This pass did not perform any live preflight.

## Current verdict

The AP-side trailer verifier is now reproduced for official packages, and ordinary patch-on-copy + old trailer fails it. Patch point quality is good, but OTA package acceptance is still blocked unless one of these becomes true:

- `persist.verify.upgrade` is proven off/bypassed in the actual live update path;
- the package is re-signed with valid vendor material;
- a different safe update path is proven to skip this AP-side verifier without triggering recovery-side failure.

A local-only `1.3.206` patch-on-copy can be generated for static evidence, but **do not call it installable** and do not tap `安装` or run no-body preflight without a separate authorization boundary.

The corrected result materially reduces uncertainty: the trailer is a secp256k1 ECDSA signature over a firmware stride digest, not a ZIP comment and not a linear full-file signature.
