#!/usr/bin/env python3
"""Create a local-only n66nfc SportXms patch artifact for static verifier tests.

This tool is intentionally NOT an install/flash tool. It never talks to a band,
Mi Fitness, Notify, NFX, BLE, DFU, or recovery. It only reads an official OTA ZIP,
patches the uncompressed `vela_ap.bin` bytes inside a rebuilt ZIP, updates visible
`ota.json` MD5, appends the original post-EOCD trailer, and records that the
result is NOT_FOR_INSTALL.

Default output is under /tmp. Refuse non-/tmp outputs unless --allow-non-tmp is
provided, so an accidentally generated artifact is not mistaken for a user-ready
firmware package.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

# Reuse the static AP verifier reproduction from the sibling tool.
try:
    from ota_trailer_ecdsa_probe import audit as audit_trailer
except Exception:  # pragma: no cover - fallback for direct module path issues
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from ota_trailer_ecdsa_probe import audit as audit_trailer

DEFAULT_OFF = 0x1779BC
DEFAULT_OLD_US = 100000
DEFAULT_NEW_US = 20000


def find_eocd_and_trailer(data: bytes) -> tuple[int, bytes]:
    eocd = data.rfind(b"PK\x05\x06")
    if eocd < 0:
        raise ValueError("EOCD not found")
    comment_len = int.from_bytes(data[eocd + 20 : eocd + 22], "little")
    eocd_end = eocd + 22 + comment_len
    trailer = data[eocd_end:]
    return eocd_end, trailer


def md5_hex(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def update_ota_json(ota_bytes: bytes, vela_ap: bytes) -> bytes:
    ota = json.loads(ota_bytes)
    new_md5 = md5_hex(vela_ap)
    updated = False
    for sec in ota.get("sections", []):
        if sec.get("location_path") == "vela_ap.bin" or sec.get("path") == "vela_ap.bin":
            sec["md5sum"] = new_md5
            updated = True
    if not updated:
        raise ValueError("ota.json section for vela_ap.bin not found")
    return json.dumps(ota, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def enforce_tmp_output(path: Path, allow_non_tmp: bool) -> None:
    resolved = path.resolve()
    if allow_non_tmp:
        return
    if not str(resolved).startswith("/tmp/") and not str(resolved).startswith("/private/tmp/"):
        raise SystemExit(
            f"Refusing non-/tmp output without --allow-non-tmp: {resolved}\n"
            "This artifact is NOT_FOR_INSTALL and should stay out of user firmware folders."
        )


def build(args: argparse.Namespace) -> dict[str, Any]:
    src = args.official_zip.expanduser().resolve()
    out = args.out.expanduser().resolve()
    enforce_tmp_output(out, args.allow_non_tmp)

    original_data = src.read_bytes()
    eocd_end, trailer = find_eocd_and_trailer(original_data)
    if len(trailer) != 80:
        raise ValueError(f"expected 80-byte post-EOCD trailer, got {len(trailer)}")

    with zipfile.ZipFile(src) as zin:
        infos = zin.infolist()
        blobs = {info.filename: zin.read(info.filename) for info in infos}

    if "vela_ap.bin" not in blobs:
        raise ValueError("vela_ap.bin not found")
    if "ota.json" not in blobs:
        raise ValueError("ota.json not found")

    off = args.offset
    old = args.old_us.to_bytes(4, "little")
    new = args.new_us.to_bytes(4, "little")
    vela = bytearray(blobs["vela_ap.bin"])
    actual_old = bytes(vela[off : off + 4])
    if actual_old != old:
        raise ValueError(
            f"unexpected bytes at vela_ap.bin+0x{off:x}: {actual_old.hex()} != expected {old.hex()}"
        )
    vela[off : off + 4] = new
    blobs["vela_ap.bin"] = bytes(vela)
    blobs["ota.json"] = update_ota_json(blobs["ota.json"], blobs["vela_ap.bin"])

    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w") as zout:
        for info in infos:
            zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            zi.compress_type = info.compress_type
            zi.external_attr = info.external_attr
            zi.comment = info.comment
            zi.extra = info.extra
            zout.writestr(zi, blobs[info.filename])
    with out.open("ab") as fh:
        fh.write(trailer)

    trailer_audit = audit_trailer(out, args.pubkey)
    manifest: dict[str, Any] = {
        "safety": "NOT_FOR_INSTALL: local static artifact only; do not flash/install/send to device",
        "source": str(src),
        "output": str(out),
        "source_eocd_end": eocd_end,
        "source_trailer_len": len(trailer),
        "patch": {
            "file": "vela_ap.bin",
            "offset_hex": hex(off),
            "old_us": args.old_us,
            "new_us": args.new_us,
            "old_bytes": old.hex(),
            "new_bytes": new.hex(),
            "patched_vela_ap_md5": md5_hex(blobs["vela_ap.bin"]),
        },
        "output_md5": md5_hex(out.read_bytes()),
        "output_sha256": sha256_hex(out.read_bytes()),
        "ap_trailer_verifier": {
            "linear_pass": trailer_audit.get("linear_secp256k1_ecdsa_with_embedded_pubkey"),
            "firmware_stride_pass": trailer_audit.get(
                "firmware_stride_secp256k1_ecdsa_with_embedded_pubkey"
            ),
            "firmware_stride_sha256": trailer_audit.get("firmware_stride_sha256"),
        },
    }
    if args.manifest:
        args.manifest.expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("official_zip", type=Path)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("/tmp/NOT_FOR_INSTALL_miband9_13206_sportxms_20000us_old_trailer.zip"),
    )
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--offset", type=lambda s: int(s, 0), default=DEFAULT_OFF)
    parser.add_argument("--old-us", type=int, default=DEFAULT_OLD_US)
    parser.add_argument("--new-us", type=int, default=DEFAULT_NEW_US)
    parser.add_argument("--allow-non-tmp", action="store_true")
    parser.add_argument(
        "--pubkey",
        default=(
            "4c5ee3be1fc08452f8b7064cbec0bd13b65a9fced76acf9d87c7fba91add3dd5"
            "85356d12dbb8278e4b3c8b61c40b87c62ab613c1f0f69f8c21b90bde5856687e"
        ),
    )
    args = parser.parse_args()
    manifest = build(args)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    if manifest["ap_trailer_verifier"].get("firmware_stride_pass"):
        print("Unexpected PASS for NOT_FOR_INSTALL artifact", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
