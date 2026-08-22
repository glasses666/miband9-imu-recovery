#!/usr/bin/env python3
"""Create a local patch-on-copy Mi Band 9 OTA package.

This helper duplicates an OTA ZIP into an output directory, modifies only the
SportXms report-latency literal in `vela_ap.bin`, updates the local `ota.json`
MD5 for `vela_ap.bin`, and writes a repacked ZIP. It never talks to the device,
never flashes, and never writes the source firmware.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import struct
import zipfile
from dataclasses import dataclass, asdict
from typing import Any

DEFAULT_PATCH_OFFSET = 0x17CC00
DEFAULT_ORIGINAL_VALUE = 100_000


@dataclass
class PatchResult:
    source_zip: str
    source_zip_sha256: str
    output_dir: str
    target_latency_us: int
    patch_offset_hex: str
    original_value: int
    patched_value: int
    bytes_before_hex: str
    bytes_after_hex: str
    original_vela_ap_md5: str
    patched_vela_ap_md5: str
    original_vela_ap_sha256: str
    patched_vela_ap_sha256: str
    repacked_zip: str
    repacked_zip_sha256: str
    ota_json_updated: bool
    files_repacked: list[str]


def digest(path: pathlib.Path, algo: str) -> str:
    h = hashlib.new(algo)
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def patch_package(source_zip: pathlib.Path, out_dir: pathlib.Path, target_latency_us: int, patch_offset: int) -> PatchResult:
    if target_latency_us <= 0:
        raise ValueError("target latency must be positive")
    out_dir.mkdir(parents=True, exist_ok=True)
    extract_dir = out_dir / f"patched_{target_latency_us}us"
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True)

    with zipfile.ZipFile(source_zip) as zf:
        names = zf.namelist()
        zf.extractall(extract_dir)

    vela = extract_dir / "vela_ap.bin"
    ota_json = extract_dir / "ota.json"
    if not vela.exists():
        raise FileNotFoundError("vela_ap.bin not found in OTA zip")
    if not ota_json.exists():
        raise FileNotFoundError("ota.json not found in OTA zip")

    original_md5 = digest(vela, "md5")
    original_sha256 = digest(vela, "sha256")
    blob = bytearray(vela.read_bytes())
    before = bytes(blob[patch_offset:patch_offset + 4])
    original_value = struct.unpack_from("<I", blob, patch_offset)[0]
    if original_value != DEFAULT_ORIGINAL_VALUE:
        raise ValueError(f"unexpected original value at {patch_offset:#x}: {original_value}, expected {DEFAULT_ORIGINAL_VALUE}")
    struct.pack_into("<I", blob, patch_offset, target_latency_us)
    after = bytes(blob[patch_offset:patch_offset + 4])
    vela.write_bytes(blob)
    patched_md5 = digest(vela, "md5")
    patched_sha256 = digest(vela, "sha256")

    ota = json.loads(ota_json.read_text(encoding="utf-8"))
    updated = False
    for section in ota.get("sections", []):
        if section.get("location_path") == "vela_ap.bin":
            section["md5sum"] = patched_md5
            updated = True
            break
    if not updated:
        raise ValueError("vela_ap.bin section not found in ota.json")
    ota_json.write_text(json.dumps(ota, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")

    repacked = out_dir / f"mi_band9_n66nfc_sportxms_latency_{target_latency_us}us_patch_on_copy.zip"
    if repacked.exists():
        repacked.unlink()
    with zipfile.ZipFile(repacked, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in names:
            zf.write(extract_dir / name, arcname=name)

    result = PatchResult(
        source_zip=str(source_zip),
        source_zip_sha256=digest(source_zip, "sha256"),
        output_dir=str(extract_dir),
        target_latency_us=target_latency_us,
        patch_offset_hex=hex(patch_offset),
        original_value=original_value,
        patched_value=target_latency_us,
        bytes_before_hex=before.hex(),
        bytes_after_hex=after.hex(),
        original_vela_ap_md5=original_md5,
        patched_vela_ap_md5=patched_md5,
        original_vela_ap_sha256=original_sha256,
        patched_vela_ap_sha256=patched_sha256,
        repacked_zip=str(repacked),
        repacked_zip_sha256=digest(repacked, "sha256"),
        ota_json_updated=updated,
        files_repacked=names,
    )
    (out_dir / f"patch_{target_latency_us}us_summary.json").write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_zip", type=pathlib.Path)
    parser.add_argument("--out-dir", type=pathlib.Path, required=True)
    parser.add_argument("--latency-us", type=int, action="append", required=True, help="target latency literal; may be repeated")
    parser.add_argument("--patch-offset", type=lambda x: int(x, 0), default=DEFAULT_PATCH_OFFSET)
    args = parser.parse_args()

    results: list[dict[str, Any]] = []
    for latency in args.latency_us:
        result = patch_package(args.source_zip, args.out_dir, latency, args.patch_offset)
        results.append(asdict(result))
    print(json.dumps({"results": results}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
