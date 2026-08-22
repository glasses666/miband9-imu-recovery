# GPT Pro Prompt — N66NFC Coupled DEFLATE/CRC/MD5 OTA Constraint

I need expert help on a constrained firmware OTA patch feasibility problem. Please reason as a binary/DEFLATE/CRC/firmware-update specialist. Be conservative: if the construction is impractical, say so and identify the exact blocker.

## Context

Target: Xiaomi Mi Band 9 NFC / n66nfc official OTA ZIP `1.3.206`.

Goal: change one decoded byte sequence inside `vela_ap.bin` at raw offset `0x1779bc` from:

```text
a0 86 01 00 = 100000us
```

to preferably:

```text
a0 4e 00 00 = 20128us
```

Not `20000us = 20 4e 00 00`, because the first byte `0xa0` is match-derived from pointer-like table data; changing it corrupts unrelated firmware bytes.

## Already proven locally

The outer ZIP has an 80-byte post-EOCD trailer. The AP-side verifier is not whole-file SHA256. It computes a stride digest:

```text
padding_info_offset = file_size - 0x50
for every full 1MiB region before that point: hash only the first 0x400 bytes
then hash the final low20 remainder contiguously through EOCD
verify trailer[16:80] as raw secp256k1 ECDSA
```

Official OTA passes this AP stride verifier.

The compressed bit location for the SportXms value is outside the signed stride windows. A local bit-level DEFLATE patch changes only literal tokens:

```text
0x86 -> 0x4e  (same Huffman code length: 10 bits)
0x01 -> 0x00  (same Huffman code length: 6 bits)
```

This preserves compressed layout and changes the inflated bytes to:

```text
a0 4e 00 00 = 20128us
```

After that local bitpatch:

```text
AP stride ECDSA: PASS
ZIP read vela_ap.bin: FAIL, Bad CRC-32
original vela_ap.bin CRC32 in central directory: 0xfc8d7d66
new inflated vela_ap.bin CRC32: 0x7af0a46c
```

Central directory and EOCD are in the signed final remainder, so their CRC/size fields cannot be changed without breaking AP ECDSA.

## Additional likely hard gate

Static analysis found `/data/ota.json`, `check_upgraded_resource_md5`, `check_zip_file_md5`, `check_ota_files`, and `md5 not match` in `vela_ota.bin`; and `/data/ota.json`, `verify_package`, `check_zip_file_md5`, plus hidden trailer verifier strings in `vela_ap.bin`.

So `ota.json` MD5 is likely a hard gate. If `vela_ap.bin` content changes, `ota.json` should reflect the new MD5. But updating `ota.json` creates a second constrained ZIP member problem: `ota.json` is also deflated and has a central-directory CRC/size that cannot be changed.

## Candidate compensation-zone scouting so far

Long zero runs exist in inflated `vela_ap.bin`, e.g.:

```text
0x37601..0x378c4   len=707
0x633af8..0x633d14 len=540
0x65cc54..0x65ce6c len=536
0x4eae45..0x4eb048 len=515
0x635554..0x635710 len=444
```

But sampled DEFLATE provenance shows these are mostly match-chain derived, not obvious independent literal padding. No clearly behavior-safe literal-only compensation zone has been found.

## Question

Is there a practical construction for a NOT_FOR_INSTALL local artifact satisfying all of these at once?

Required invariants:

1. Outer central directory / EOCD / 80-byte trailer unchanged.
2. AP stride ECDSA still PASS.
3. ZIP `testzip()` / read of `vela_ap.bin` PASS, meaning inflated `vela_ap.bin` CRC32 remains the original `0xfc8d7d66` despite the 20128us semantic change.
4. `ota.json` section MD5 reflects the changed `vela_ap.bin`, or you can argue convincingly that this MD5 is not enforced.
5. If `ota.json` is changed, ZIP read of `ota.json` must also PASS with its unchanged central-directory CRC/size.
6. Any compensation bytes must be behavior-safe in firmware and their compressed bytes must be outside signed stride windows.
7. No private signing key, no re-signing, no live device install.

Please answer:

- Is this constraint system realistically solvable with DEFLATE bit surgery + CRC32 compensation?
- If yes, give a concrete algorithmic route, including how to choose compensation bytes, how many controllable bytes are needed, how to handle dynamic Huffman code length constraints, and how to handle `ota.json` MD5 text update without changing its ZIP CRC.
- If no, identify the minimal impossible/hard blocker and what extra capability would be required: private key, bypass of `ota.json` MD5, behavior-safe literal compensation area, a decompression-level CRC preimage solver, or live-path proof that ZIP CRC/MD5 are ignored.
- Keep the conclusion fail-closed. Do not assume installability from AP stride PASS alone.
