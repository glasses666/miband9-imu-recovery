# N66NFC GPT Pro static integration — 2026-06-05

## Bottom line

GPT Pro's analysis agrees with the current safety boundary: there is **no safe live route to device-side package acceptance** in the supplied evidence. Notify/NFX can prove an app-owned connected session and host-side `FIRMWARE5_ZIP` parser admission, but its next meaningful firmware path crosses into `buttonStartUpdate -> install broadcast -> fwUpload -> type=2/subtype=5 preflight -> body`.

The best current static artifact is the `20128us` **NOT_FOR_INSTALL** candidate. It is structurally cleaner than the older `10000us` / `20000us` variants, but it is still not an install candidate.

No phone, app, Bluetooth, firmware picker, ZIP selection, prepare, body, validate, or upgrade action was performed for this integration pass.

## GPT Pro verdict distilled

- Notify/NFX has no supplied-code evidence for a safe pre-DFU/status-only transition before `buttonStartUpdate`.
- `FIRMWARE5_ZIP` only proves host-side parser admission (`PK` ZIP + `ota.sh` or `ota.json`, with `sw_version` extraction). It does not prove band/recovery/package acceptance.
- Mi Fitness `getOtaStatus` (`hns.e=2`, `f=90`) is a real no-body status lane, but the connected result for the current state decoded to code `1` / `not support`; repeating the same path is exhausted unless state/app/firmware changes.
- `prepareOta` is the first package-admission-looking official boundary, but it sends firmware metadata and is coupled to `startOta` on reason `0`; it remains forbidden.
- DFU V5 `D1` remains allowed only if `1530/1531` are already visible. Prior live service discovery did not see `1530`, so no D1 write should happen in that state.
- The `20128us` artifact passes known reproduced local/static checks, but retail device acceptance and compensation-byte runtime safety remain unproven.

## Local static validation performed after GPT Pro response

Artifacts:

- `docs/recovery/artifacts/gpt_pro_20128_static_validation_20260605/20128_static_validation.json`
- `docs/recovery/artifacts/gpt_pro_20128_static_validation_20260605/20128_static_validation.md`
- `docs/recovery/artifacts/gpt_pro_20128_static_validation_20260605/20128_compensation_semantic_probe.json`
- `docs/recovery/artifacts/gpt_pro_20128_static_validation_20260605/20128_compensation_semantic_probe.md`

Validation checks all passed:

- `ap_same_size`: true
- `ap_crc_preserved`: true
- `ap_target_expected`: true
- `ap_diff_count_expected`: true
- `ota_size_preserved`: true
- `ota_crc_preserved`: true
- `ota_contains_patched_ap_md5`: true

Guard regression:

```text
python3 -m pytest tools/firmware/test_ota_preflight_guard.py -q
..... [100%]
5 passed in 0.04s
```

## 20128us artifact facts

Original AP:

- target word at raw `0x1779bc`: `a0860100` (`100000us`)
- md5: `25fd1c5aa57b42f4c74f0e4e2dcadf4a`
- crc32: `fc8d7d66`

Patched `20128us` AP:

- target word at raw `0x1779bc`: `a04e0000` (`20128us`)
- md5: `2891fad713c2bdc2659f1330bcfb7130`
- crc32: `fc8d7d66`
- AP size preserved

Patched `ota.json`:

- size: `3458`
- crc32: `e249a3ef`
- contains patched AP md5: yes

AP diff count is exactly 8 bytes:

- primary target bytes at `0x1779bd` and `0x1779be`
- CRC compensation bytes at `0x5008be`, `0x5008c0`, `0x5008c3`, `0x5008c6`, `0x5008d4`, `0x5008d5`

## Compensation-byte semantic probe

Preliminary result:

The compensation bytes sit inside a long printable ASCII run/table. A raw little-endian absolute-address scan found no direct exact pointer to the compensation window, but there are literal pointers into the surrounding window and absence of direct pointers does **not** prove semantic inertness. Code can reference a table base or compute offsets.

Therefore the compensation region remains **behavior-uncertain**. The `20128us` candidate is still a proof-of-gate/static candidate, not an install candidate.

## Safe next actions

1. Do broader disassembly/xref of the compensation region.
   - Static only.
   - Goal: determine whether the modified printable run/table is reachable or semantically inert.
   - Stop if table usage cannot be proven safe.

2. If full ZIP verification is needed, reproduce the full splice from the official ZIP.
   - Static only.
   - Output must remain `NOT_FOR_INSTALL`.
   - Require unchanged central directory, EOCD, post-EOCD trailer, AP stride ECDSA pass, `zipfile.testzip() == None`.

3. Future live work is limited to owner-session / DFU visibility observation.
   - Notify/NFX: stop before firmware picker, ZIP selection, `buttonStartUpdate`.
   - Mi Fitness: stop before `prepareOta` / `startOta`.
   - DFU: send `D1` only if `1530/1531` are already visible.

## Explicit no-go routes under current constraints

- Notify firmware picker / ZIP selection / `buttonStartUpdate`
- Notify install broadcast `302ff3b3-953f-4a3c-8c3e-b8451f20fe53`
- `fwUpload`
- Notify `p2(type=2, subtype=5)`
- Mi Fitness `prepareOta hns.e=2/f=5`
- Mi Fitness `startOta`
- DFU `D2/D3/D5/D6`
- firmware body/chunks
- validate / upgrade / recovery / factory

## Source from GPT Pro response

The GPT Pro response was supplied by Queen Glasser as:

`/path/to/local-user/Desktop/未命名2.rtf`

It was converted locally to plain text for integration. The original RTF was not committed.
