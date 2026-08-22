# N66NFC 1.3.206 Deflate/CRC Scout

Date: 2026-06-02
Scope: local/static research only. No device connection, no OTA install, no firmware body/validate/upgrade.

## Question

After reproducing the n66nfc OTA trailer verifier as stride-digest + raw secp256k1 ECDSA, can the SportXms latency patch be moved through the unsigned compressed-data gap without re-signing the OTA?

Known constraints:

- Official package: `/path/to/local-user/Downloads/Telegram Desktop/MIBand9_1.3.206.zip`.
- SportXms raw patch point: `vela_ap.bin` raw `0x1779bc`.
- Original little-endian value: `a0860100` = `100000 us`.
- Original exact target considered earlier: `204e0000` = `20000 us`.
- AP trailer verifier signs only stride windows and final remainder, not every byte.
- `vela_ap.bin` compressed data around the patch is outside the signed stride windows.
- The central directory and EOCD are inside the signed final remainder, so normal CRC/size/offset metadata updates would invalidate the trailer.

## Spark scouting result

Three low-cost Spark lanes were used as long-context scouts. Their final reports were written to `/tmp/miband9_spark_scout/` and are intentionally not committed.

### Deflate lane

Useful references/tools found:

- `madler/infgen`: DEFLATE stream disassembler. Useful for seeing literal/match structure.
- Puffin / `puffdiff` / `puffpatch`: mature deflate-aware patching framework, but designed for controlled patch pipelines, not fixed-central-directory signed ZIP surgery.
- `microsoft/preflate-rs`: lossless re-compression metadata extraction, relevant to understanding existing deflate streams, not an immediate in-place patch primitive.
- `bea4dev/cozip`: has documented bit-level deflate manipulation concepts, worth reading if this continues.
- Nullprogram `Modifying the Middle of a zlib Stream`: useful conceptual reference for zlib mutation boundaries, but it assumes different stream/checksum freedoms than this OTA case.
- `uhc`: Python token-level DEFLATE parser candidate; maturity uncertain.

Deflate lane verdict: exact 20000us patch is not a straightforward local edit if any target bytes are emitted by matches/backreferences.

### CRC lane

Useful references/tools found:

- Project Nayuki: “Forcing a file's CRC to any value”. Shows CRC32 can be forced by modifying four chosen bytes.
- `AdjustCRC.jl`: CRC32/CRC32C adjustment library.
- `crchack`: public-domain style CRC forcing tool family.
- `crcmod` / `crccheck` / GF(2) linear algebra: useful primitives, but not an OTA-aware solution.

CRC lane verdict: CRC32 compensation is mathematically possible if there are behavior-safe controllable bytes. However, this OTA needs more than CRC math: the compensation bytes must also be representable via signed-window-safe deflate edits, and OTA section MD5 checks must be satisfied.

### Security lane

Security framing verdict:

- Current state is an implementation quirk / high-friction exploitation candidate, not a proven trusted-artifact forgery.
- The signed-gap is security-relevant because AP stride verification can pass after unsigned compressed-byte mutation.
- It is not yet exploitable because ZIP CRC, `ota.json` MD5, central directory immutability, and live verifier path are unresolved.

## Local deflate token classification

A temporary raw-deflate tracer was built under `/tmp/miband9_tool_scout/` to map uncompressed offsets back to DEFLATE tokens.

Target bytes at `vela_ap.bin` raw `0x1779bc`:

```text
raw 0x1779bc..0x1779bf = a0 86 01 00
```

Token mapping:

```text
0x1779bc = 0xa0  match byte
  copied from 0x176d1c
  copied from 0x1748a0
  root token is a literal 0xa0

0x1779bd = 0x86  literal token
0x1779be = 0x01  literal token
0x1779bf = 0x00  literal token
```

The first byte is the dangerous part. Its root literal is not isolated padding; local inspection shows it is embedded in pointer-like data:

```text
0x1748a0: a0 b6 62 2c ...  => little-endian pointer-like 0x2c62b6a0
0x176d1c: a0 b6 62 2c ...  => pointer-like table data
0x1779bc: a0 86 01 00      => SportXms latency literal
```

Changing the root literal `0xa0` to `0x20` would also mutate those earlier pointer-like bytes. That makes the exact `20000us` value (`204e0000`) unsafe under a simple source-byte edit.

A match-distance rewrite was also checked conceptually: the match emitting bytes around `0x1779ba` copies the triple `62 2c a0`. No previous `62 2c 20` triple exists within the 32 KiB DEFLATE window, so changing only the match distance is not an easy route to exact `20000us`.

## Narrower latency value: 20128us

A better value exists for this compression stream:

```text
20128 us = 0x00004ea0 = a0 4e 00 00
```

This preserves the first byte `0xa0`, avoiding the match/source pointer corruption issue. Only the literal bytes need to change:

```text
0x86 -> 0x4e
0x01 -> 0x00
0x00 -> 0x00 unchanged
```

For the dynamic Huffman block containing the target:

```text
0x86 literal code length = 10 bits
0x4e literal code length = 10 bits
0x01 literal code length = 6 bits
0x00 literal code length = 6 bits
```

So `100000us -> 20128us` can be expressed as an in-place bit edit with unchanged compressed size and unchanged DEFLATE token structure.

A local NOT_FOR_INSTALL bitpatch artifact was created under `/tmp` only:

```text
/tmp/miband9_tool_scout/MIBand9_1.3.206_sportxms_20128us_bitpatch_NOT_FOR_INSTALL.zip
```

Validation result:

```text
inflated target bytes: a04e0000 = 20128
AP stride ECDSA verifier: PASS
ZIP read vela_ap.bin: FAIL, Bad CRC-32 for file 'vela_ap.bin'
new vela_ap.bin CRC32: 0x7af0a46c
original central-directory CRC32: 0xfc8d7d66
```

This proves a narrower fact than “patch works”:

- The target latency can be changed to ~20ms at the DEFLATE bit level without breaking the AP stride signature.
- It still fails the ZIP CRC gate.
- It is not installable.

## Remaining coupled blockers

Even if `vela_ap.bin` CRC32 is compensated, that is not enough.

A complete signed-gap candidate would need all of these at once:

1. `vela_ap.bin` DEFLATE stream still inflates successfully.
2. `vela_ap.bin` ZIP CRC32 matches the signed central-directory CRC field without editing the central directory.
3. `vela_ap.bin` behavior is not broken by CRC compensation bytes.
4. `ota.json` is updated to the new `vela_ap.bin` MD5, or the live verifier is proven not to check it.
5. If `ota.json` changes, its own compressed stream must also keep ZIP CRC32/size/central-directory fields valid or be compensated.
6. All changed compressed bytes must avoid signed stride windows and final signed remainder.
7. AP stride ECDSA must still pass.
8. Recovery/package checks such as `check_zip_file_md5` / `check_ota_files` must pass.

The problem is therefore not one CRC. It is a two-file, compressed, signed-window-constrained consistency problem.

## Go / No-Go

Current verdict: `THEORETICALLY_OPEN_BUT_PRACTICALLY_BLOCKED`.

Continue only if the next task is framed as a bounded local experiment:

1. Find behavior-safe uncompressed compensation regions in `vela_ap.bin`.
2. Prove those bytes are emitted by editable literal tokens or otherwise controllable deflate structures in unsigned compressed regions.
3. Solve CRC32 delta for the chosen offsets.
4. Repeat the same style of analysis for `ota.json` MD5/CRC if MD5 checking remains required.

Stop if no behavior-safe, deflate-editable compensation zone exists.

## Safety language

The `/tmp` 20128us artifact is `NOT_FOR_INSTALL`. It is useful only as proof that the exact first-byte blocker can be avoided by choosing `20128us` instead of `20000us`. It remains rejected by ZIP CRC and must not be flashed or passed to live OTA tooling.
