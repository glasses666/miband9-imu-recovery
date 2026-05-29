#!/usr/bin/env python3
"""Patch a local firmware binary by replacing one byte pattern with another.

Dangerous research helper. This script is intentionally path-explicit and does
not ship firmware blobs. Keep originals and rollback copies outside git.

Example:
    python tools/firmware/patch_firmware.py \
        --input /path/to/vela_ap.bin \
        --output /path/to/vela_ap_patched_208hz.bin \
        --target '10 30' \
        --replacement '10 50'
"""

from __future__ import annotations

import argparse
from pathlib import Path


def _hex_bytes(value: str) -> bytes:
    return bytes.fromhex(value.replace("0x", "").replace(",", " "))


def patch_file(input_path: str, output_path: str, target_bytes: bytes, replacement_bytes: bytes) -> bool:
    if len(target_bytes) != len(replacement_bytes):
        raise ValueError("target and replacement must have the same byte length")

    src = Path(input_path)
    if not src.exists():
        raise FileNotFoundError(f"Input file not found: {src}")

    content = src.read_bytes()
    count = content.count(target_bytes)
    print(f"Loaded {src} ({len(content)} bytes)")
    print(f"Found {count} occurrences of {target_bytes.hex(' ')}")

    if count == 0:
        print("No targets found. Skipping patch.")
        return False

    out = Path(output_path)
    out.write_bytes(content.replace(target_bytes, replacement_bytes))
    print(f"Patched content saved to {out}")
    print(f"Replaced {target_bytes.hex(' ')} with {replacement_bytes.hex(' ')}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Input firmware binary")
    parser.add_argument("--output", required=True, help="Output patched firmware binary")
    parser.add_argument("--target", default="10 30", help="Hex byte pattern to replace")
    parser.add_argument("--replacement", default="10 50", help="Replacement hex byte pattern")
    args = parser.parse_args()
    patch_file(args.input, args.output, _hex_bytes(args.target), _hex_bytes(args.replacement))


if __name__ == "__main__":
    main()
