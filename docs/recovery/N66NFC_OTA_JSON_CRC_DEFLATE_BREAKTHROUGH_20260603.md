# N66NFC OTA JSON CRC + DEFLATE Breakthrough — 2026-06-03

## Safety stance

This document records **local/static** OTA ZIP research only. The generated ZIP artifact is explicitly **NOT_FOR_INSTALL**:

- no live band connection;
- no Notify/NFX/Mi Fitness install tap;
- no OTA body/chunk transfer;
- no validate/upgrade/recovery command;
- no credential or signed URL material.

## Starting point

The prior local artifact already solved the AP side:

```text
/tmp/miband9_tool_scout/MIBand9_1.3.206_sportxms_20128us_apcrc_pass_md5_fail_NOT_FOR_INSTALL.zip
```

It satisfied:

```text
SportXms target bytes: a04e0000 = 20128us
vela_ap.bin CRC32:    0xfc8d7d66
zipfile.testzip:      None
AP stride ECDSA:      PASS
post-EOCD trailer:    preserved
```

But it still failed the visible section-MD5 gate because `ota.json` contained the old AP MD5:

```text
old AP MD5: 25fd1c5aa57b42f4c74f0e4e2dcadf4a
new AP MD5: 2891fad713c2bdc2659f1330bcfb7130
```

The remaining fixed constraints for `ota.json` were:

```text
uncompressed size:       3458 bytes
central-directory CRC32: 0xe249a3ef
raw DEFLATE size:        566 bytes
central directory/EOCD/trailer: unchanged
```

## Deep-research input

Queen Glasser supplied `deep-research-report.md`, which made two important corrections to the search strategy:

1. Do not rely on trailing garbage after a finished DEFLATE stream; strict ZIP/device inflate paths may reject or check unused input.
2. Treat the problem as CRC exact-hit + compression-aware search over valid JSON whitespace freedom; exact raw-DEFLATE size is not a format-level impossibility.

The report recommended a meet-in-the-middle CRC search over existing JSON whitespace slots, followed by Zopfli raw-DEFLATE scoring.

## Implemented helper

Added:

```text
tools/firmware/search_n66nfc_ota_json_crc_deflate.py
```

The helper:

- extracts `ota.json` from the official ZIP;
- replaces the old AP MD5 with the new AP MD5;
- collects existing JSON whitespace bytes outside strings;
- toggles a conservative binary whitespace alternate:
  - space `0x20` -> tab `0x09`;
  - newline `0x0a` -> carriage return `0x0d`;
- uses meet-in-the-middle CRC XOR search over sampled 300-slot subsets;
- filters candidates with `zlib` raw DEFLATE;
- final-scores with Zopfli raw DEFLATE;
- emits a JSON byte string and raw DEFLATE stream only when CRC/JSON/size conditions hold.

The successful run used:

```bash
/tmp/miband9_ota_json_search_venv/bin/python tools/firmware/search_n66nfc_ota_json_crc_deflate.py \
  '/path/to/local-user/Downloads/Telegram Desktop/MIBand9_1.3.206.zip' \
  --old-md5 25fd1c5aa57b42f4c74f0e4e2dcadf4a \
  --new-md5 2891fad713c2bdc2659f1330bcfb7130 \
  --output-json /tmp/miband9_ota_json_search/repro_tool_ota_json.json \
  --output-raw-deflate /tmp/miband9_ota_json_search/repro_tool_ota_json.raw.deflate
```

Key output:

```json
{
  "result": "found",
  "zopfli_raw_len": 566,
  "zlib_raw_len": 585,
  "weight": 5,
  "positions": [1802, 1804, 2397, 2403, 2435],
  "crc": "0xe249a3ef",
  "json_valid": true,
  "contains_new_md5": true,
  "target_size": 566
}
```

The five whitespace changes are all conservative same-length JSON whitespace substitutions:

```text
1802: 0x20 -> 0x09
1804: 0x20 -> 0x09
2397: 0x20 -> 0x09
2403: 0x20 -> 0x09
2435: 0x20 -> 0x09
```

So this route does **not** use comments, duplicate keys, object reordering, size changes, or trailing garbage.

## ZIP entry splice helper

Added:

```text
tools/firmware/splice_zip_entry_raw_deflate.py
```

It replaces one ZIP member's compressed data in place only if:

- raw DEFLATE length equals the existing member `compress_size`;
- inflated length equals the existing member `file_size`;
- inflated CRC32 equals the existing member central-directory CRC32;
- `zipfile.testzip()` passes after splicing.

It preserves local headers, central directory, EOCD, and the post-EOCD trailer bytes.

## Full local static artifact

Created local artifact:

```text
/tmp/miband9_tool_scout/MIBand9_1.3.206_sportxms_20128us_full_local_checks_PASS_NOT_FOR_INSTALL.zip
```

Splice command:

```bash
python3 tools/firmware/splice_zip_entry_raw_deflate.py \
  /tmp/miband9_tool_scout/MIBand9_1.3.206_sportxms_20128us_apcrc_pass_md5_fail_NOT_FOR_INSTALL.zip \
  ota.json \
  /tmp/miband9_ota_json_search/repro_tool_ota_json.raw.deflate \
  /tmp/miband9_tool_scout/MIBand9_1.3.206_sportxms_20128us_full_local_checks_PASS_NOT_FOR_INSTALL.zip
```

Splice output:

```json
{
  "entry": "ota.json",
  "local_data_offset": "0x186000d",
  "raw_deflate_size": 566,
  "inflated_size": 3458,
  "crc32": "0xe249a3ef",
  "changed_compressed_bytes": 564,
  "zip_testzip": null
}
```

## Verification result

Local ZIP checks:

```text
zipfile.testzip:          None
ota.json len:             3458
ota.json CRC32:           0xe249a3ef
ota.json contains new MD5: true
vela_ap.bin CRC32:        0xfc8d7d66
vela_ap.bin MD5:          2891fad713c2bdc2659f1330bcfb7130
SportXms bytes @0x1779bc: a04e0000
```

AP trailer verifier:

```text
AP stride ECDSA: true
linear SHA256 model: false (negative control)
post-EOCD trailer: present, 80 bytes
```

Artifact hashes:

```text
MD5:    955c2ebacb020ad91743bdf5b250d894
SHA256: 776c838e370ad15e8bf05a7fc2ed52e13defa7dbd3f7097586cd8ccbcf56afce
```

## Interpretation

The previous blocker:

```text
ota.json updated AP MD5 + original CRC32 + raw DEFLATE size 566
```

is now solved for the local/static artifact.

This means the current candidate satisfies every **known local static** constraint we have reproduced:

```text
SportXms semantic patch: PASS
vela_ap.bin ZIP CRC:    PASS
ota.json visible MD5:   PASS
ota.json ZIP CRC:      PASS
ZIP testzip:            PASS
AP stride ECDSA:        PASS
post-EOCD trailer:      preserved
central directory:      unchanged
EOCD:                   unchanged
```

However, it remains **NOT_FOR_INSTALL** because local static checks are not identical to a retail device install path. Before any live path is discussed, the next boundary is a separately authorized, no-body, fail-closed preflight runbook that refuses firmware body/validate/upgrade by default.

## Next decision

Recommended next step is **not** blind install.

The safe next research gate is:

1. write a no-body preflight guard/runbook;
2. prove it refuses body/chunk/validate/upgrade paths;
3. only with explicit authorization, test the earliest device-side package-admission/preflight boundary;
4. stop immediately before any transfer or validation command.
