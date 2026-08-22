#!/usr/bin/env python3
"""Search a local firmware binary for likely LSM6DSO ODR register patterns.

Public-safe helper: pass the firmware path explicitly instead of hardcoding a
private local artifact path.

Example:
    python tools/firmware/search_odr.py /path/to/vela_ap.bin
"""

from __future__ import annotations

import argparse
from pathlib import Path


PATTERNS = {
    "Set ODR 52Hz (CTRL1_XL 10 30)": bytes.fromhex("10 30"),
    "Set ODR 104Hz (CTRL1_XL 10 40)": bytes.fromhex("10 40"),
    "Set ODR 208Hz (CTRL1_XL 10 50)": bytes.fromhex("10 50"),
    "Set ODR 416Hz (CTRL1_XL 10 60)": bytes.fromhex("10 60"),
    "LSM6DSO CTRL1_XL register byte (10)": bytes.fromhex("10"),
}


def search_odr_patterns(file_path: str, *, limit_per_pattern: int = 20) -> None:
    content = Path(file_path).read_bytes()
    print(f"File loaded: {file_path} ({len(content)} bytes)")

    for name, pattern in PATTERNS.items():
        offset = 0
        count = 0
        while True:
            offset = content.find(pattern, offset)
            if offset == -1:
                break

            start = max(0, offset - 4)
            end = min(len(content), offset + 8)
            context = content[start:end]
            print(f"[FOUND] {name} at 0x{offset:X} | Context: {context.hex(' ')}")
            count += 1
            offset += 1
            if count >= limit_per_pattern:
                print("... (too many matches, stopping for this pattern)")
                break


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("firmware", help="Path to firmware binary, e.g. vela_ap.bin")
    parser.add_argument("--limit-per-pattern", type=int, default=20)
    args = parser.parse_args()
    search_odr_patterns(args.firmware, limit_per_pattern=args.limit_per_pattern)


if __name__ == "__main__":
    main()
