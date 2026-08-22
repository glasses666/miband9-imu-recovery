# n66nfc 1.3.206 official OTA package validation (2026-06-02)

## Scope

Queen Glasser provided a candidate local OTA package:

```text
/path/to/local-user/Downloads/Telegram Desktop/MIBand9_1.3.206.zip
```

This pass is read-only. It does not call Mi Fitness/Notify OTA install paths, does not connect to the band, and does not send firmware body/chunks, prepare, validate, upgrade, or recovery commands.

## Bottom line

The package is a valid-looking official full OTA for Mi Band 9 NFC / n66 line, and it matches the target current firmware version:

```text
ota.json magic_string = n66
ota.json sw_version   = 1.3.206
zip testzip           = None
section md5 entries   = all matched
post-EOCD trailer     = present, 80 bytes
```

The SportXms start-path latency literal was also re-located on this exact `1.3.206` `vela_ap.bin`; it is **not** the old `1.3.210` raw offset `0x17cc00`.

```text
1.3.206 start latency literal raw offset: 0x1779bc
original value: 0x000186a0 = 100000 us
```

## Package hashes

```text
file size : 43,934,203 bytes
zip md5   : 16194c1758240ab236d43534f0537b2d
zip sha256: b42cc913af5941d5a48222767dd13180db88b16651efc7141122c6d3a42802e4
```

## ZIP / trailer audit

EOCD parsing:

```text
EOCD offset        : 0x29e8d95 (43934101)
ZIP comment length : 0
post-EOCD trailer  : 80 bytes
```

Trailer bytes:

```text
00 00 00 01 10 00 00 00 00 00 00 00 00 00 00 00
55 48 4D EA 19 03 51 AD C8 87 4D 75 53 AC EA 02
17 25 E8 FB FD C5 DC 38 13 CF 4C 42 75 E6 F7 90
3C F2 C9 5C D7 F3 72 21 30 FE FC AD CC 43 1A BE
D6 65 A3 D3 B5 27 1F 46 73 43 C9 37 08 FE 25 3D
```

Interpretation:

- The package has the same important risk shape as the previously audited official `1.3.210` OTA: an 80-byte blob after EOCD despite ZIP comment length `0`.
- The visible ZIP layer is internally consistent, but the trailer is still not decoded/recomputed.
- Therefore a patched package that only updates `ota.json` MD5 remains a local proof artifact, not a device-accepted OTA.

## Visible entry list

```text
recovery.bin   1,208,320 bytes
i18n.bin       4,605,952 bytes
font.bin      35,252,224 bytes
vendor.bin       673,792 bytes
quickapp.bin      62,464 bytes
ota.json          3,458 bytes
version              18 bytes
watchface.bin 16,645,120 bytes
vela_ap.bin    6,741,584 bytes
app.bin       28,860,416 bytes
misc.bin         540,672 bytes
system.bin     3,320,832 bytes
vela_ota.bin     663,408 bytes
```

## ota.json section MD5 verification

Every visible `ota.json` section MD5 matched the extracted file contents.

Important target section:

```text
vela_ap.bin md5    : 25fd1c5aa57b42f4c74f0e4e2dcadf4a
vela_ap.bin sha256 : extracted in temp artifact only for this pass
vela_ap.bin size   : 6,741,584 bytes
```

## Dynamic SportXms xref on 1.3.206

A dynamic descriptor scan was used instead of the old fixed `1.3.210` descriptor/wrapper offsets.

Discovered descriptor table entries in `1.3.206`:

```text
0x4f7e14 -> sensor_accel
0x4f7e1c -> sensor_accel_uncal
0x4f7e64 -> sensor_gyro
0x4f7e6c -> sensor_gyro_uncal
```

Primary start path:

```text
0x1777ce: ldrh r3, [r5, #8]
0x1777d0: cmp r3, r2
0x1777d2: beq #0x1777da
0x1777d4: cmp.w r3, #0x32c
0x1777d8: bne #0x17780a
0x1777da: movs r2, #0x64
0x1777dc: ldr r3, [pc, #0x1dc]
0x1777de: ldr r1, [pc, #0x1e0]
0x1777e0: mov r0, r4
0x1777e2: str r6, [sp]
0x1777e4: bl #0x16a12c
```

Resolved callsites:

```text
0x1777e4 subscribe sensor_accel r2=100 r3=100000 literal=0x1779bc target=0x16a12c
0x1777f2 subscribe sensor_gyro  r2=100 r3=100000 literal=0x1779bc target=0x16a12c
```

Stop/unsubscribe path:

```text
0x1778c4 unsubscribe sensor_accel r2=100 r3=0 target=0x16a158
0x1778d0 unsubscribe sensor_gyro  r2=100 r3=0 target=0x16a158
```

Resume/alternate path uses a larger literal:

```text
0x177914 subscribe sensor_accel r2=100 r3=200000 literal=0x1779ec target=0x16a12c
0x177922 subscribe sensor_gyro  r2=100 r3=200000 literal=0x1779ec target=0x16a12c
```

Literal bytes:

```text
raw 0x1779bc: A0 86 01 00 = 0x000186a0 = 100000 us
raw 0x1779ec: 40 0D 03 00 = 0x00030d40 = 200000 us
```

## Patch implication

If a local-only patch-on-copy is later authorized for `1.3.206`, the conservative start-path target is:

```text
vela_ap.bin raw offset: 0x1779bc
old value             : 100000 us
candidate value       : 20000 us first, 10000 us only after the conservative path is justified
```

But the patched candidate remains blocked for live OTA use until the post-EOCD 80-byte trailer / `verify_upgrade_package_func` package-verification path is understood or bypass risk is explicitly accepted under a live-OTA runbook.

## Status update

- Current-version official package acquisition: resolved.
- Same-version trailer/signature-shape audit: resolved enough to confirm the risk structure exists on `1.3.206` too.
- SportXms xref: resolved on the exact `1.3.206` package.
- Patch-on-copy candidate: not produced in this pass; blocked pending explicit decision on local-only artifact vs trailer/signature work.
