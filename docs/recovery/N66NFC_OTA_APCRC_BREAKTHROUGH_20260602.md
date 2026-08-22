# N66NFC OTA AP-CRC Breakthrough and Remaining ota.json Gate

Date: 2026-06-02
Scope: local/static research only. No device connection, no Notify/NFX install, no firmware body, no validate, no upgrade.

## Bottom line

The OTA patch route advanced one gate:

- `vela_ap.bin` SportXms target can be changed to `20128us` (`a04e0000`).
- `vela_ap.bin` ZIP CRC32 can be restored to the signed central-directory value without changing central directory / EOCD / trailer.
- The AP stride trailer verifier still passes.

But the package is still **NOT_FOR_INSTALL** because `ota.json` still contains the old `vela_ap.bin` MD5. Static evidence says that MD5 is likely a hard OTA gate.

## New helper

`tools/firmware/scan_deflate_free_literals.py`

Purpose:

- parse raw DEFLATE from a ZIP member;
- map inflated offsets back to literal/match tokens;
- identify whether token bytes are in AP stride-signed outer ZIP windows;
- inspect long zero runs and direct literal windows.

Local run result on official `MIBand9_1.3.206.zip`:

```text
tokens: 3,442,746
blocks: 129
SportXms target:
  0x1779bc = 0xa0 match, unsigned compressed bytes
  0x1779bd = 0x86 literal, unsigned, 10-bit code
  0x1779be = 0x01 literal, unsigned, 6-bit code
  0x1779bf = 0x00 literal, unsigned, 6-bit code
```

The largest inflated zero runs are not clean free variables. They are match-derived:

```text
0x37601..0x378c4   len=707  immediate literal bytes=0
0x633af8..0x633d14 len=540  immediate literal bytes=0
0x65cc54..0x65ce6c len=536  immediate literal bytes=0
0x4eae45..0x4eb048 len=515  immediate literal bytes=0
```

So the earlier suspicion was correct: "long zero run" is not enough. It must be token/root aware.

## AP CRC compensation proof

After applying the `20128us` target patch, `vela_ap.bin` CRC changed:

```text
patched target-only CRC32: 0x7af0a46c
original CD CRC32:        0xfc8d7d66
required delta:           0x867dd90a
```

A root-aware CRC32 compensation search found a local same-length literal-token solution using single-copy roots in an ASCII month/alphabet table region:

```text
0x5008be: 't' -> 'J'
0x5008c0: 'v' -> 'U'
0x5008c3: 'y' -> 'W'
0x5008c6: '1' -> 'n'
0x5008d4: '.' -> 'b'
0x5008d5: '/' -> 'o'
```

This is useful as a proof of gate mechanics, not as a behavior-safe final choice. The region may be a shared formatting/base64-style table, so it is not acceptable as a final firmware behavior patch without deeper impact analysis.

Generated local artifact:

```text
/tmp/miband9_tool_scout/MIBand9_1.3.206_sportxms_20128us_apcrc_pass_md5_fail_NOT_FOR_INSTALL.zip
```

Validation:

```text
inflated target bytes: a04e0000
vela_ap.bin CRC32:    0xfc8d7d66  (matches central directory)
zipfile.testzip:      None
new vela_ap.bin MD5:  2891fad713c2bdc2659f1330bcfb7130
ota.json contains new MD5: false
AP stride ECDSA:      PASS
post-EOCD trailer:    preserved, 80 bytes
```

This crosses the previous ZIP CRC blocker for `vela_ap.bin`, but it does not cross the section-MD5 gate.

## ota.json gate status

If `ota.json` is updated from old AP MD5:

```text
25fd1c5aa57b42f4c74f0e4e2dcadf4a
```

to AP-CRC-compensated MD5:

```text
2891fad713c2bdc2659f1330bcfb7130
```

then `ota.json` uncompressed CRC changes. Because its central-directory CRC is in the signed final remainder, we cannot update that metadata.

A whitespace-only JSON CRC compensation can restore the original uncompressed `ota.json` CRC while preserving valid JSON, but the resulting raw DEFLATE stream has not yet been made to fit the original compressed size:

```text
original ota.json compressed size: 566 bytes
md5-only update:
  zlib raw deflate:   568 bytes
  zopfli raw deflate: 556 bytes  (short enough, but CRC wrong)
md5 + whitespace CRC compensation:
  best tested zlib raw deflate:   ~592 bytes
  best tested zopfli raw deflate: ~575 bytes
```

So the current remaining blocker is narrow and concrete:

```text
Find a valid modified ota.json such that:
  - AP md5 string is updated correctly;
  - uncompressed CRC32 remains 0xe249a3ef;
  - uncompressed size remains 3458;
  - raw DEFLATE stream is <= 566 bytes, ideally exactly 566 or safely padded to 566;
  - compressed bytes remain within the existing ota.json compressed-data range.
```

## Spark worker notes

- Spark B independently called the CRC/MD5 route `FEASIBLE-ONLY-IF`: at least four controllable bytes per constrained ZIP entry, and the real blocker is deflate geometry + behavior-safe controllability.
- Spark C agreed on the local gates: AP stride, ZIP CRC, `ota.json` MD5, central directory immutability, and no live OTA.
- Spark A did not produce a usable final report: `/tmp/n66nfc_spark_out/deflate.md` was absent, and its process log only repeated the prompt plus local Codex memory/MCP auth errors (`no such table: jobs`, `invalid_grant`). The main agent implemented the DEFLATE token scanner directly.

## Current decision

The OTA route is no longer blocked at `vela_ap.bin` CRC. It is blocked at `ota.json` exact CRC + compression-size coupling.

Do not proceed to live preflight or install. The next useful external/GPT-Pro question is the `ota.json` constrained recompression/CRC problem, not generic CRC32 math.
