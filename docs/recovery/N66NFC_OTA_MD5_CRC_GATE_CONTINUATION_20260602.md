# N66NFC OTA MD5/CRC Gate Continuation

Date: 2026-06-02
Scope: local/static only. No phone, no watch, no ADB/live OTA, no install, no firmware body/validate/upgrade.

## Current question

After the `20128us` bit-level DEFLATE patch proved that `vela_ap.bin` can be locally changed while the AP stride ECDSA still passes, the next question was whether the remaining OTA container gates are one-file or two-file:

- Can a candidate ignore `ota.json` section MD5 and only solve `vela_ap.bin` ZIP CRC?
- Or is `ota.json` MD5 a hard gate, requiring a coupled `vela_ap.bin` + `ota.json` consistency solution?

## Inputs

- Official `1.3.206` OTA: `/path/to/local-user/Downloads/Telegram Desktop/MIBand9_1.3.206.zip`
- Extracted local/static files: `/tmp/miband9_13206_extract_callgraph/{vela_ap.bin,vela_ota.bin,ota.json}`
- Existing reports:
  - `docs/recovery/N66NFC_OTA_SIGNATURE_MD5_STATIC_AUDIT_20260602.md`
  - `docs/recovery/N66NFC_SIGNED_GAP_PATCH_FEASIBILITY_20260602.md`
  - `docs/recovery/N66NFC_DEFLATE_CRC_SCOUT_20260602.md`

## Spark lanes

Two `gpt-5.3-codex-spark` read-only lanes were launched:

1. `md5_hardgate`: review static evidence around `check_zip_file_md5`, `check_ota_files`, `check_upgraded_resource_md5`, `/data/ota.json`, and `md5 not match`.
2. `crc_zone`: review candidate behavior-safe CRC32 compensation regions and stop conditions.

Their raw reports are in `/tmp/miband9_spark_scout/` and are not committed.

## Local static checks

The official OTA was extracted locally:

```text
vela_ap.bin   size=6741584 md5=25fd1c5aa57b42f4c74f0e4e2dcadf4a
vela_ota.bin  size=663408  md5=efb28e4a3de323d406c88378f51e358e
ota.json      size=3458    md5=d458dfa08b64592b778bee69da1f60ff
```

A temporary Capstone/string-xref helper was used to inspect AP-side literal-pool references under base `0x2c100000`:

```text
/tmp/miband9_13206_extract_callgraph/static_string_xrefs.py
/tmp/miband9_13206_extract_callgraph/ap_literal_loads.py
/tmp/miband9_13206_extract_callgraph/ap_upgrade_func_summary.py
```

These are scratch helpers, not production repo tools.

## MD5 gate conclusion

Conservative answer: **do not ignore `ota.json` MD5**.

Evidence:

### Recovery-side `vela_ota.bin`

The following strings are clustered together in the recovery image:

```text
0x00094e86: json > filepath:%s json>md5_sum:%s
0x00094ebe: md5 not match
0x0009503e: file:%s md5 is not ok
0x00095084: /data/ota.json
0x000950a0: check_upgraded_resource_md5
0x000950c8: check_zip_file_md5
0x0009518e: after upgrade md5 match check ok
0x00095616: check_ota_files
```

This is strong static evidence that recovery-side OTA completion checks read `/data/ota.json` and compare per-file MD5 values.

### AP-side `vela_ap.bin`

The AP image has both the hidden trailer verifier cluster and another `/data/ota.json` / MD5 cluster:

```text
0x00518a49: verify_upgrade_package_func
0x00518a89: padding_info_offset
0x00518d4d: /data/ota.json
0x00518e8f: json > filepath:%s json>md5_sum:%s
0x00518ec7: md5 not match
0x00518f55: after upgrade md5 match check ok
0x00519254: verify_package
0x00519682: check_zip_file_md5
```

Literal-pool xrefs confirm the AP-side upgrade function candidate loads `persist.verify.upgrade`, `verify_upgrade_package_func`, `verify_package`, `padding_info_offset`, and `check_zip_file_md5` strings from the same broad function region. This does not fully decompile the function, but it strengthens the earlier conclusion: AP-side hidden verification and visible `/data/ota.json` MD5 checks are part of the OTA acceptance surface.

### Practical implication

For a local candidate, solving only the `vela_ap.bin` ZIP CRC is probably insufficient. A candidate that changes `vela_ap.bin` content but leaves `ota.json` unchanged will likely fail the `/data/ota.json` per-section MD5 gate. Updating `ota.json` then creates a second constrained ZIP problem: `ota.json` itself is deflated, has a signed central-directory CRC/size record, and must still satisfy AP stride ECDSA.

Therefore the current problem is confirmed as a **coupled two-file problem**:

```text
vela_ap.bin: deflate bitpatch + CRC32 preservation + behavior safety
ota.json: md5 text update + its own deflate/CRC preservation
outer OTA: central directory and EOCD unchanged, AP stride ECDSA PASS
```

## CRC compensation zone scouting

Spark and local scratch checks looked for obvious behavior-safe compensation regions in `vela_ap.bin`.

Long zero runs exist, for example:

```text
0x37601..0x378c4   len=707
0x633af8..0x633d14 len=540
0x65cc54..0x65ce6c len=536
0x4eae45..0x4eb048 len=515
0x635554..0x635710 len=444
```

However, sampled provenance with `/tmp/miband9_tool_scout/trace_origin_chain.py` shows these are mostly match-chain derived, not clean independent literal padding. Examples:

```text
0x37601 -> long match chain rooted at 0x34e5b; transitive dependencies include many nearby bytes.
0x633af8 -> match chain rooted at 0x62c051; transitive dependent set includes multiple later offsets.
0x65cc54 -> match chain rooted at 0x65cbc5; transitive dependent set includes many later offsets.
```

This does not mathematically prove all compensation is impossible, but it rejects the easy route: no obvious long zero/padding run is yet both behavior-safe and trivially literal-editable.

## Bottleneck reached

The next obstacle is no longer ordinary static reversing. It is a constraint problem:

```text
simultaneous DEFLATE bit-level edit
+ CRC32 preimage/compensation
+ behavior-safe compensation bytes
+ signed-window-preserving compressed positions
+ unchanged central directory / EOCD
+ ota.json MD5 text update and its own ZIP CRC invariants
```

This is the point where a GPT Pro expert prompt is appropriate if we continue. The local/Spark team can still build helpers, but the strategic question is whether the coupled deflate+CRC+MD5 problem has a practical construction under these constraints.

## Current verdict

`MD5_HARD_GATE_LIKELY` and `CRC_COMPENSATION_ZONE_NOT_FOUND`.

Continue only with one of these bounded paths:

1. Ask GPT Pro for a constraint-solver strategy for the coupled `vela_ap.bin` + `ota.json` problem.
2. Alternatively, switch away from OTA patching and use static callgraph to search for a host-reachable command/debug path.

Do not produce another install candidate until:

- `vela_ap.bin` ZIP CRC passes without central-directory edits;
- `ota.json` section MD5 reflects the changed `vela_ap.bin` and its own ZIP CRC passes;
- AP stride ECDSA still passes;
- all artifacts remain marked **NOT_FOR_INSTALL** until a separate live preflight authorization exists.
