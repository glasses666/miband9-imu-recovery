#!/usr/bin/env python3
"""Splice a same-size raw DEFLATE stream into one ZIP entry in place.

Local/static helper for signed OTA research: it preserves all ZIP metadata,
central directory, EOCD, and any post-EOCD trailer bytes. It refuses to write if
raw DEFLATE length, inflated size, or CRC32 do not match the existing ZIP entry
metadata.
"""

from __future__ import annotations

import argparse
import json
import struct
import zlib
import zipfile
from pathlib import Path


def crc32_u32(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


def local_data_offset(raw_zip: bytes, info: zipfile.ZipInfo) -> int:
    off = info.header_offset
    if raw_zip[off:off + 4] != b"PK\x03\x04":
        raise ValueError("bad local file header signature")
    fn_len, extra_len = struct.unpack_from("<HH", raw_zip, off + 26)
    return off + 30 + fn_len + extra_len


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source_zip", type=Path)
    ap.add_argument("entry")
    ap.add_argument("raw_deflate", type=Path)
    ap.add_argument("output_zip", type=Path)
    ap.add_argument("--allow-data-descriptor", action="store_true", help="Allow entries with general-purpose bit 3 set. The descriptor bytes are still preserved unchanged.")
    args = ap.parse_args()

    raw_zip = bytearray(args.source_zip.read_bytes())
    raw_deflate = args.raw_deflate.read_bytes()
    inflated = zlib.decompress(raw_deflate, -15)
    with zipfile.ZipFile(args.source_zip) as zf:
        info = zf.getinfo(args.entry)
        gp_flags = info.flag_bits
        if (gp_flags & 0x08) and not args.allow_data_descriptor:
            raise SystemExit(f"entry {args.entry!r} uses data descriptor flag bit 3; pass --allow-data-descriptor only after auditing layout")
        if len(raw_deflate) != info.compress_size:
            raise SystemExit(f"raw deflate size {len(raw_deflate)} != ZIP entry compress_size {info.compress_size}")
        if len(inflated) != info.file_size:
            raise SystemExit(f"inflated size {len(inflated)} != ZIP entry file_size {info.file_size}")
        if crc32_u32(inflated) != info.CRC:
            raise SystemExit(f"inflated CRC32 0x{crc32_u32(inflated):08x} != ZIP entry CRC32 0x{info.CRC:08x}")
        data_off = local_data_offset(bytes(raw_zip), info)

    old = bytes(raw_zip[data_off:data_off + len(raw_deflate)])
    raw_zip[data_off:data_off + len(raw_deflate)] = raw_deflate
    args.output_zip.parent.mkdir(parents=True, exist_ok=True)
    args.output_zip.write_bytes(raw_zip)

    with zipfile.ZipFile(args.output_zip) as zf:
        bad = zf.testzip()
    print(json.dumps({
        "source_zip": str(args.source_zip),
        "output_zip": str(args.output_zip),
        "entry": args.entry,
        "local_data_offset": hex(data_off),
        "raw_deflate_size": len(raw_deflate),
        "inflated_size": len(inflated),
        "crc32": f"0x{crc32_u32(inflated):08x}",
        "changed_compressed_bytes": sum(a != b for a, b in zip(old, raw_deflate)),
        "zip_testzip": bad,
    }, ensure_ascii=False))
    return 0 if bad is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
