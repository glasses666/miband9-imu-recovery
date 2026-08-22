#!/usr/bin/env python3
"""Read-only OTA ZIP trailer/manifest auditor for Mi Band 9 Vela packages.

This tool parses standard ZIP metadata plus the vendor post-EOCD trailer used by
n66/n66nfc OTA packages. It never patches, repacks, connects to a device, or
calls any OTA install/DFU path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import struct
import zipfile
from dataclasses import dataclass, asdict
from typing import Any

EOCD_SIG = b"PK\x05\x06"
ZIP_DIGITAL_SIGNATURE_SIG = b"PK\x05\x05"
SUSPICIOUS_SUFFIXES = (
    ".rsa",
    ".sf",
    ".dsa",
    ".ec",
    ".sig",
    ".signature",
    ".pem",
    ".crt",
    ".cer",
)


def hexdigest_bytes(data: bytes, algo: str) -> str:
    h = hashlib.new(algo)
    h.update(data)
    return h.hexdigest()


def hexdigest_file(path: pathlib.Path, algo: str) -> str:
    h = hashlib.new(algo)
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_eocd(data: bytes) -> dict[str, Any]:
    off = data.rfind(EOCD_SIG)
    if off < 0:
        return {"present": False, "offset": None}
    if off + 22 > len(data):
        return {"present": True, "offset": off, "truncated": True}
    (
        _sig,
        disk_no,
        cd_start_disk,
        entries_this_disk,
        entries_total,
        cd_size,
        cd_offset,
        comment_len,
    ) = struct.unpack_from("<4s4H2LH", data, off)
    eocd_end = off + 22 + comment_len
    trailer = data[eocd_end:]
    return {
        "present": True,
        "offset": off,
        "offset_hex": hex(off),
        "disk_no": disk_no,
        "central_dir_start_disk": cd_start_disk,
        "entries_this_disk": entries_this_disk,
        "entries_total": entries_total,
        "central_dir_size": cd_size,
        "central_dir_size_hex": hex(cd_size),
        "central_dir_offset": cd_offset,
        "central_dir_offset_hex": hex(cd_offset),
        "comment_len": comment_len,
        "eocd_end": eocd_end,
        "eocd_end_hex": hex(eocd_end),
        "trailer_len": len(trailer),
        "trailer_offset": eocd_end,
        "trailer_offset_hex": hex(eocd_end),
    }


def firmware_stride_digest(data: bytes, end: int) -> tuple[str, int]:
    h = hashlib.sha256()
    high_mib = end >> 20
    low20 = end & 0xFFFFF
    hashed = 0
    for i in range(high_mib):
        off = i * 0x100000
        chunk = data[off : off + 0x400]
        h.update(chunk)
        hashed += len(chunk)
    off = high_mib * 0x100000
    remainder = data[off:end]
    h.update(remainder)
    hashed += len(remainder)
    return h.hexdigest(), hashed


def interpret_trailer(data: bytes, eocd: dict[str, Any]) -> dict[str, Any]:
    if not eocd.get("present"):
        return {"present": False}
    start = int(eocd.get("trailer_offset") or len(data))
    trailer = data[start:]
    info: dict[str, Any] = {
        "present": bool(trailer),
        "length": len(trailer),
        "hex": trailer.hex(" ").upper(),
    }
    if not trailer:
        return info
    info["first16_hex"] = trailer[:16].hex(" ").upper()
    if len(trailer) >= 16:
        info["first16_be_u32"] = [hex(x) for x in struct.unpack(">4I", trailer[:16])]
        info["first16_le_u32"] = [hex(x) for x in struct.unpack("<4I", trailer[:16])]
    # Static reverse-engineering of 1.3.206/1.3.210 verify_package suggests:
    # - the file size minus the post-EOCD 0x50-byte trailer is logged as
    #   padding_info_offset;
    # - the AP-side secp256k1 verifier uses a firmware stride digest, not a
    #   conventional full-file digest: first 0x400 bytes at each complete MiB
    #   boundary, plus the final low-20-bit remainder through EOCD;
    # - the first 4 bytes at -0x50 are read before "read magic err";
    # - one byte after that is logged as offset_from_head;
    # - the signature block is read from (trailer_start + offset_from_head)
    #   and has length trailer_len - offset_from_head.
    if len(trailer) >= 5:
        offset_from_head = trailer[4]
        info["candidate_magic4_hex"] = trailer[:4].hex(" ").upper()
        info["candidate_offset_from_head"] = offset_from_head
        if 0 <= offset_from_head <= len(trailer):
            sign_info = trailer[offset_from_head:]
            info["candidate_reserved_hex"] = trailer[5:offset_from_head].hex(" ").upper()
            info["candidate_sign_info_len"] = len(sign_info)
            info["candidate_sign_info_hex"] = sign_info.hex(" ").upper()
            info["candidate_sign_info_sha256"] = hexdigest_bytes(sign_info, "sha256")
    # Linear full-body digest is useful for comparison only. The AP-side hidden
    # verifier uses firmware_stride_sha256 below.
    bound_body = data[:start]
    info["linear_sha256_without_trailer"] = hexdigest_bytes(bound_body, "sha256")
    info["linear_md5_without_trailer"] = hexdigest_bytes(bound_body, "md5")
    stride_sha256, stride_len = firmware_stride_digest(data, start)
    info["firmware_stride_sha256"] = stride_sha256
    info["firmware_stride_hashed_len"] = stride_len
    return info


def audit_zip(path: pathlib.Path) -> dict[str, Any]:
    data = path.read_bytes()
    eocd = read_eocd(data)
    trailer = interpret_trailer(data, eocd)
    out: dict[str, Any] = {
        "path": str(path),
        "file_name": path.name,
        "file_size": len(data),
        "md5": hexdigest_bytes(data, "md5"),
        "sha256": hexdigest_bytes(data, "sha256"),
        "zip_digital_signature_record_present": ZIP_DIGITAL_SIGNATURE_SIG in data,
        "eocd": eocd,
        "trailer": trailer,
        "zip_testzip": None,
        "entries": [],
        "suspicious_signature_entries": [],
        "ota_json": None,
    }
    with zipfile.ZipFile(path) as zf:
        out["zip_testzip"] = zf.testzip()
        names = zf.namelist()
        suspicious = []
        for info in zf.infolist():
            lower = info.filename.lower()
            if lower.startswith("meta-inf/") or lower.endswith(SUSPICIOUS_SUFFIXES) or "signature" in lower:
                suspicious.append(info.filename)
            out["entries"].append(
                {
                    "name": info.filename,
                    "file_size": info.file_size,
                    "compress_size": info.compress_size,
                    "crc32": f"{info.CRC:08x}",
                    "header_offset": info.header_offset,
                    "compress_type": info.compress_type,
                }
            )
        out["suspicious_signature_entries"] = suspicious
        if "ota.json" in names:
            ota = json.loads(zf.read("ota.json"))
            sections = []
            all_ok = True
            for sec in ota.get("sections", []):
                location = sec.get("location_path")
                expected = (sec.get("md5sum") or "").lower()
                row: dict[str, Any] = {
                    "location_path": location,
                    "section_type": sec.get("section_type"),
                    "file_type": sec.get("file_type"),
                    "expected_md5": expected,
                }
                if location in names:
                    blob = zf.read(location)
                    actual = hexdigest_bytes(blob, "md5")
                    row.update(
                        {
                            "file_size": len(blob),
                            "actual_md5": actual,
                            "sha256": hexdigest_bytes(blob, "sha256"),
                            "md5_ok": actual == expected,
                        }
                    )
                    all_ok = all_ok and actual == expected
                else:
                    row["missing"] = True
                    row["md5_ok"] = False
                    all_ok = False
                sections.append(row)
            out["ota_json"] = {
                "magic_string": ota.get("magic_string"),
                "ota_version": ota.get("ota_version"),
                "sw_version": ota.get("sw_version"),
                "firmware_type": ota.get("firmware_type"),
                "section_md5_all_ok": all_ok,
                "sections": sections,
            }
    return out


def compare_reports(reports: list[dict[str, Any]]) -> dict[str, Any]:
    if len(reports) < 2:
        return {}
    names_by_report = [[e["name"] for e in r["entries"]] for r in reports]
    first_names = names_by_report[0]
    pairwise = []
    for idx in range(1, len(reports)):
        a, b = reports[0], reports[idx]
        trailer_a = bytes.fromhex(a["trailer"].get("hex", "")) if a.get("trailer") else b""
        trailer_b = bytes.fromhex(b["trailer"].get("hex", "")) if b.get("trailer") else b""
        row: dict[str, Any] = {
            "left": a["file_name"],
            "right": b["file_name"],
            "entry_order_equal_to_left": first_names == names_by_report[idx],
            "trailer_length_left": len(trailer_a),
            "trailer_length_right": len(trailer_b),
            "trailer_first16_equal": trailer_a[:16] == trailer_b[:16] if trailer_a and trailer_b else False,
            "trailer_equal": trailer_a == trailer_b if trailer_a and trailer_b else False,
        }
        if trailer_a and trailer_b:
            row["trailer_tail_differing_bytes"] = sum(x != y for x, y in zip(trailer_a[16:], trailer_b[16:]))
        pairwise.append(row)
    return {"pairwise_vs_first": pairwise}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip", nargs="+", type=pathlib.Path, help="OTA ZIP/package paths to audit")
    parser.add_argument("--out", type=pathlib.Path, help="Optional JSON output path")
    args = parser.parse_args()

    reports = [audit_zip(p) for p in args.zip]
    result = {"reports": reports, "compare": compare_reports(reports)}
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
