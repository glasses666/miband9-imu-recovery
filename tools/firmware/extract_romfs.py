#!/usr/bin/env python3
"""Read-only ROMFS lister/extractor for Vela/NuttX firmware resource images."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path


def _pad16(value: int) -> int:
    return (value + 15) & ~15


def _cstr(data: bytes, offset: int) -> str:
    end = data.find(b"\x00", offset)
    if end < 0:
        end = len(data)
    return data[offset:end].decode("utf-8", "replace")


def _entry_at(data: bytes, offset: int, base_path: str) -> dict | None:
    if offset + 16 > len(data):
        return None
    next_raw, spec, size, checksum = struct.unpack(">IIII", data[offset : offset + 16])
    entry_type = next_raw & 0x7
    next_offset = next_raw & ~0xF
    name = _cstr(data, offset + 16)
    name_end = data.find(b"\x00", offset + 16)
    if name_end < 0:
        name_end = len(data)
    name_len = name_end - (offset + 16) + 1
    data_offset = _pad16(offset + 16 + name_len)
    path = f"{base_path}/{name}".strip("/") if base_path else name
    return {
        "offset": offset,
        "offset_hex": hex(offset),
        "next": next_offset,
        "type": entry_type,
        "spec": spec,
        "size": size,
        "checksum": checksum,
        "name": name,
        "path": path,
        "data_offset": data_offset,
        "data_offset_hex": hex(data_offset),
    }


def _walk(data: bytes, offset: int, base_path: str, entries: list[dict], seen: set[int]) -> None:
    while offset and offset < len(data) and offset not in seen:
        seen.add(offset)
        entry = _entry_at(data, offset, base_path)
        if entry is None:
            return
        entries.append(entry)
        if entry["type"] == 1 and entry["name"] not in (".", ".."):
            child = entry["spec"] & ~0xF
            if child and child < len(data) and child not in seen:
                _walk(data, child, entry["path"], entries, seen)
        offset = entry["next"]


def parse_romfs(path: Path) -> tuple[bytes, dict] | None:
    data = path.read_bytes()
    if not data.startswith(b"-rom1fs-"):
        return None
    full_size = struct.unpack(">I", data[8:12])[0]
    volume = _cstr(data, 16)
    root_offset = _pad16(16 + len(volume.encode()) + 1)
    entries: list[dict] = []
    _walk(data, root_offset, "", entries, set())
    return data, {
        "file": path.name,
        "path": str(path),
        "size": len(data),
        "full_size": full_size,
        "volume": volume,
        "root_offset": root_offset,
        "entries": entries,
    }


def extract_regular_files(data: bytes, parsed: dict, output_root: Path) -> int:
    count = 0
    base = output_root / parsed["file"]
    for entry in parsed["entries"]:
        if entry["type"] != 2 or not entry["size"]:
            continue
        start = entry["data_offset"]
        end = start + entry["size"]
        if end > len(data):
            continue
        destination = base / entry["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data[start:end])
        count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--extract", action="store_true", help="Extract regular files into --out-dir/<image>/")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    parsed_all = []
    for path in args.inputs:
        parsed_tuple = parse_romfs(path)
        if parsed_tuple is None:
            print(f"{path.name}: not romfs")
            continue
        data, parsed = parsed_tuple
        extracted = extract_regular_files(data, parsed, args.out_dir) if args.extract else 0
        parsed_all.append(parsed)
        (args.out_dir / f"{path.name}.entries.json").write_text(
            json.dumps(parsed, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(
            f"{path.name}: entries={len(parsed['entries'])} "
            f"regular_files={sum(1 for e in parsed['entries'] if e['type'] == 2)} extracted={extracted}"
        )
    (args.out_dir / "all_romfs_entries.json").write_text(
        json.dumps(parsed_all, indent=2, ensure_ascii=False), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
