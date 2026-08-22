#!/usr/bin/env python3
"""Analyze n66nfc OTA signed-gap patch feasibility.

Static-only helper. It does not connect to any device and does not create an
installable firmware artifact. Optional byte-flip output must stay under /tmp and
is only used to demonstrate that an unsigned compressed byte can leave the
AP-side trailer verifier passing while ZIP CRC/inflate integrity fails.
"""
from __future__ import annotations

import argparse
import json
import zlib
import zipfile
from pathlib import Path
from typing import Any

try:
    from ota_trailer_ecdsa_probe import audit as audit_trailer
except Exception:  # pragma: no cover
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from ota_trailer_ecdsa_probe import audit as audit_trailer


def find_eocd_end(data: bytes) -> int:
    eocd = data.rfind(b"PK\x05\x06")
    if eocd < 0:
        raise ValueError("EOCD not found")
    comment_len = int.from_bytes(data[eocd + 20 : eocd + 22], "little")
    return eocd + 22 + comment_len


def signed_ranges(eocd_end: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i in range(eocd_end >> 20):
        out.append({"name": f"mib{i}_first1k", "start": i * 0x100000, "end": i * 0x100000 + 0x400})
    out.append(
        {
            "name": "final_low20_remainder",
            "start": (eocd_end >> 20) * 0x100000,
            "end": eocd_end,
        }
    )
    return out


def overlaps(start: int, end: int, ranges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hits = []
    for r in ranges:
        a = max(start, r["start"])
        b = min(end, r["end"])
        if a < b:
            hits.append({"name": r["name"], "start": a, "end": b, "rel_start": a - start, "rel_end": b - start})
    return hits


def entry_data_span(data: bytes, info: zipfile.ZipInfo) -> tuple[int, int]:
    header = data[info.header_offset : info.header_offset + 30]
    if header[:4] != b"PK\x03\x04":
        raise ValueError(f"bad local header for {info.filename}")
    name_len = int.from_bytes(header[26:28], "little")
    extra_len = int.from_bytes(header[28:30], "little")
    start = info.header_offset + 30 + name_len + extra_len
    return start, start + info.compress_size


def approximate_deflate_input_at_output(stream: bytes, output_offset: int, step: int = 64) -> dict[str, Any]:
    obj = zlib.decompressobj(-15)
    out_len = 0
    for pos in range(0, len(stream), step):
        chunk = stream[pos : pos + step]
        out = obj.decompress(chunk)
        out_len += len(out)
        consumed = pos + len(chunk) - len(obj.unconsumed_tail)
        if out_len >= output_offset:
            return {"compressed_rel_approx": consumed, "output_len_at_probe": out_len, "step": step}
    raise ValueError(f"output offset 0x{output_offset:x} not reached")


def central_directory_entries(data: bytes) -> dict[str, Any]:
    eocd = data.rfind(b"PK\x05\x06")
    cd_size = int.from_bytes(data[eocd + 12 : eocd + 16], "little")
    cd_offset = int.from_bytes(data[eocd + 16 : eocd + 20], "little")
    entries: dict[str, Any] = {}
    pos = cd_offset
    while pos < cd_offset + cd_size:
        if data[pos : pos + 4] != b"PK\x01\x02":
            raise ValueError(f"bad central directory signature at 0x{pos:x}")
        crc = int.from_bytes(data[pos + 16 : pos + 20], "little")
        csize = int.from_bytes(data[pos + 20 : pos + 24], "little")
        usize = int.from_bytes(data[pos + 24 : pos + 28], "little")
        name_len = int.from_bytes(data[pos + 28 : pos + 30], "little")
        extra_len = int.from_bytes(data[pos + 30 : pos + 32], "little")
        comment_len = int.from_bytes(data[pos + 32 : pos + 34], "little")
        local_header = int.from_bytes(data[pos + 42 : pos + 46], "little")
        name = data[pos + 46 : pos + 46 + name_len].decode("utf-8", "replace")
        end = pos + 46 + name_len + extra_len + comment_len
        entries[name] = {
            "cd_start": pos,
            "cd_end": end,
            "crc32": f"{crc:08x}",
            "compressed_size": csize,
            "uncompressed_size": usize,
            "local_header": local_header,
        }
        pos = end
    return {"central_directory_start": cd_offset, "central_directory_end": cd_offset + cd_size, "entries": entries}


def zip_read_status(path: Path, member: str) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(path) as zf:
            zf.read(member)
        return {"member": member, "ok": True}
    except Exception as exc:
        return {"member": member, "ok": False, "error_type": type(exc).__name__, "error": str(exc)}


def enforce_tmp(path: Path) -> None:
    resolved = path.resolve()
    if not (str(resolved).startswith("/tmp/") or str(resolved).startswith("/private/tmp/")):
        raise SystemExit(f"refusing non-/tmp flip output: {resolved}")


def analyze(args: argparse.Namespace) -> dict[str, Any]:
    path = args.official_zip.expanduser().resolve()
    data = path.read_bytes()
    eocd_end = find_eocd_end(data)
    ranges = signed_ranges(eocd_end)
    cd = central_directory_entries(data)
    report: dict[str, Any] = {
        "path": str(path),
        "file_size": len(data),
        "eocd_end": eocd_end,
        "eocd_end_hex": hex(eocd_end),
        "signed_ranges": ranges,
        "central_directory": cd,
        "entries": {},
    }
    with zipfile.ZipFile(path) as zf:
        for name in args.entries:
            info = zf.getinfo(name)
            start, end = entry_data_span(data, info)
            entry_report: dict[str, Any] = {
                "compress_type": info.compress_type,
                "header_offset": info.header_offset,
                "data_start": start,
                "data_end": end,
                "compressed_size": info.compress_size,
                "uncompressed_size": info.file_size,
                "crc32": f"{info.CRC:08x}",
                "signed_overlaps": overlaps(start, end, ranges),
                "central_directory": cd["entries"].get(name),
            }
            if name == "vela_ap.bin":
                stream = data[start:end]
                approx = approximate_deflate_input_at_output(stream, args.patch_offset)
                approx_outer = start + approx["compressed_rel_approx"]
                approx.update(
                    {
                        "patch_uncompressed_offset": args.patch_offset,
                        "patch_uncompressed_offset_hex": hex(args.patch_offset),
                        "outer_offset_approx": approx_outer,
                        "outer_offset_approx_hex": hex(approx_outer),
                        "outer_signed_overlap": overlaps(approx_outer, approx_outer + 1, ranges),
                    }
                )
                entry_report["patch_compressed_position_approx"] = approx
            report["entries"][name] = entry_report
    if args.flip_out:
        flip_out = args.flip_out.expanduser().resolve()
        enforce_tmp(flip_out)
        vela = report["entries"]["vela_ap.bin"]
        flip_off = vela["patch_compressed_position_approx"]["outer_offset_approx"]
        mutated = bytearray(data)
        before = mutated[flip_off]
        mutated[flip_off] = before ^ 0x01
        flip_out.parent.mkdir(parents=True, exist_ok=True)
        flip_out.write_bytes(mutated)
        trailer = audit_trailer(flip_out, args.pubkey)
        report["unsigned_byte_flip_test"] = {
            "output": str(flip_out),
            "offset": flip_off,
            "offset_hex": hex(flip_off),
            "old_byte": before,
            "new_byte": mutated[flip_off],
            "ap_stride_pass": trailer.get("firmware_stride_secp256k1_ecdsa_with_embedded_pubkey"),
            "firmware_stride_sha256": trailer.get("firmware_stride_sha256"),
            "zip_read_vela_ap": zip_read_status(flip_out, "vela_ap.bin"),
        }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("official_zip", type=Path)
    parser.add_argument("--patch-offset", type=lambda s: int(s, 0), default=0x1779BC)
    parser.add_argument("--entries", nargs="+", default=["vela_ap.bin", "ota.json"])
    parser.add_argument("--flip-out", type=Path)
    parser.add_argument(
        "--pubkey",
        default=(
            "4c5ee3be1fc08452f8b7064cbec0bd13b65a9fced76acf9d87c7fba91add3dd5"
            "85356d12dbb8278e4b3c8b61c40b87c62ab613c1f0f69f8c21b90bde5856687e"
        ),
    )
    args = parser.parse_args()
    print(json.dumps(analyze(args), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
