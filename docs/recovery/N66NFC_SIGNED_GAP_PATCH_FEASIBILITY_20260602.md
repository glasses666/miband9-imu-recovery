# n66nfc signed-gap patch feasibility (2026-06-02)

## Scope

Static-only analysis of whether the `1.3.206` SportXms patch could exploit the AP-side OTA trailer verifier's stride coverage gap.

Safety boundary:

- no band connection;
- no Notify/NFX install click;
- no Mi Fitness/DFU `prepare`, firmware body/chunk, `validate`, `upgrade`, or recovery command;
- `/tmp` mutated files are **NOT_FOR_INSTALL** and only prove local verifier/ZIP behavior.

Helpers:

```text
tools/firmware/analyze_n66nfc_signed_gap.py
tools/firmware/ota_trailer_ecdsa_probe.py
tools/firmware/make_n66nfc_sportxms_not_for_install.py
```

Spark workers were used for long-context static reading. Their useful conclusions were:

- ordinary ZIP-layer rewrite is not a practical signed-gap path;
- `vela_ota.bin` / `vela_ap.bin` expose MD5/ZIP/inflate/CRC style checks such as `check_zip_file_md5`, `check_ota_files`, `md5 not match`, `header crc mismatch`, and `inflate stream corrupt`;
- no live installability claim follows from local AP signature checks.

The final evidence below is from local bounded scripts, not from Spark self-report alone.

## Signed ranges in official `1.3.206`

For `/path/to/local-user/Downloads/Telegram Desktop/MIBand9_1.3.206.zip`:

```text
eocd_end / padding_info_offset = 0x29e61ab
signed stride ranges:
  0x00000000..0x00000400
  0x00100000..0x00100400
  ...
  0x02800000..0x02800400
  0x02900000..0x029e61ab   final low20 remainder, includes central directory + EOCD
```

Important entry layout:

```text
vela_ap.bin compressed data = 0x1d64616..0x215ee99
ota.json    compressed data = 0x186000d..0x1860243
central directory           = 0x29e5d89..0x29e6195
EOCD                         = 0x29e6195..0x29e61ab
```

`vela_ap.bin` signed overlaps are only the first 1 KiB at four MiB boundaries inside its compressed stream:

```text
mib30_first1k: 0x1e00000..0x1e00400
mib31_first1k: 0x1f00000..0x1f00400
mib32_first1k: 0x2000000..0x2000400
mib33_first1k: 0x2100000..0x2100400
```

The SportXms raw patch point is in the uncompressed `vela_ap.bin`:

```text
raw offset: 0x1779bc
old value : a0 86 01 00 = 100000us
new value : 20 4e 00 00 = 20000us
```

Approximate compressed-stream position corresponding to that uncompressed offset:

```text
outer ZIP offset approx: 0x1e758d6
signed overlap at that byte: none
nearest signed windows:
  previous mib30_first1k ends around 0x1e00400
  next     mib31_first1k starts at 0x1f00000
```

`ota.json` compressed data also has no direct signed-window overlap, but its central-directory entry is in the final signed remainder.

## Central-directory blocker

The central directory is fully inside the final signed low20 remainder. For the two directly relevant entries:

```text
ota.json central-dir entry:
  span      = 0x29e5f19..0x29e5f67
  crc field = 0x29e5f29
  crc       = e249a3ef
  csize     = 566
  usize     = 3458

vela_ap.bin central-dir entry:
  span      = 0x29e6007..0x29e6058
  crc field = 0x29e6017
  crc       = fc8d7d66
  csize     = 4171907
  usize     = 6741584
```

Because those bytes are signed by the AP stride digest, a candidate that wants to keep the old official trailer must keep central-directory CRC/size/offset fields byte-identical.

Implication:

- changing uncompressed `vela_ap.bin` normally changes ZIP CRC32 and possibly compressed bytes;
- updating central-directory CRC/size would invalidate AP trailer signature;
- leaving central-directory CRC unchanged risks ZIP extraction / firmware checks failing;
- updating `ota.json` MD5 also changes `ota.json` content, which normally changes its ZIP CRC and central-directory field.

## Minimal unsigned-byte flip test

A local-only mutated copy flipped one compressed byte near the patch-relevant region, outside all signed ranges:

```text
output: /tmp/miband9_sigrepro_20260602/NOT_FOR_INSTALL_one_unsigned_comp_byte_flip_from_gap_tool.zip
flip offset: 0x1e758d6
AP stride verifier: pass
ZIP read vela_ap.bin: fail, Bad CRC-32 for file 'vela_ap.bin'
```

This proves both sides of the current situation:

1. the AP trailer signature really does not cover every compressed byte;
2. ZIP CRC/inflate integrity can still reject a changed compressed stream.

## Feasibility verdict

A signed-gap artifact is **not impossible in pure theory**, but it is not a practical ordinary patch-on-copy path.

To produce a local candidate that even passes local static gates, it would need all of these at once:

1. AP stride verifier passes, so all signed stride ranges, final central directory, EOCD, and trailer remain byte-identical.
2. `vela_ap.bin` decompresses to patched bytes at raw `0x1779bc`.
3. `vela_ap.bin` central-directory CRC/size remain byte-identical, or the actual target unzip path must be proven not to enforce them.
4. `ota.json` contains the patched `vela_ap.bin` MD5, but its central-directory CRC/size also remain byte-identical, or the actual unzip path must be proven not to enforce them.
5. Firmware-side `check_zip_file_md5` / `check_ota_files` style checks pass after decompression.

That implies either:

- precise in-place deflate bitstream surgery that changes decompressed bytes without changing signed windows, compressed size, and effective ZIP CRC expectations; plus JSON/CRC compensation; or
- proof that the live updater ignores central-directory CRC and AP verifier despite the static strings; or
- vendor re-signing.

None of those has been proven.

## Current decision

- Do not call the patched package installable.
- Do not use ordinary repack + old trailer as a candidate.
- Continue only with local static experiments unless Queen Glasser separately authorizes a no-body preflight boundary.

The next local-only research question would be deflate-level feasibility:

- Is the target `vela_ap.bin` value emitted as literals or backreferences?
- Can it be changed in-place without changing bytes inside signed windows?
- Can `vela_ap.bin` CRC32 be preserved via a behavior-safe compensation region?
- Can `ota.json` be updated while preserving its ZIP CRC32 and compressed-size/central-directory invariants?

Until those are answered, `current-fw-13206-patch-candidate` remains pending/fail-closed.
