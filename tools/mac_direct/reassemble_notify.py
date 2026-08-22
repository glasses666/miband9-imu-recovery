#!/usr/bin/env python3
"""Reassemble A5A5 Xiaomi SPP-v2 frames from macOS BLE notify JSON.

Input should be JSON produced by `ble_notify_probe.swift`.  The tool reads local raw
`events[].hex` chunks, reassembles complete frames, and prints a redacted summary: no
payload hex is emitted unless `--include-payload-prefix` is explicitly passed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running from repo root without installing the Python package.
REPO_TOOL = Path(__file__).resolve().parents[1] / "miband9ctl"
if str(REPO_TOOL) not in sys.path:
    sys.path.insert(0, str(REPO_TOOL))

from miband9ctl.mac_direct_protocol import FrameParseError, SppV2StreamParser  # noqa: E402


def load_events(path: Path) -> list[dict]:
    data = json.loads(path.read_text())
    events = data.get("events", [])
    if not isinstance(events, list):
        raise SystemExit("input JSON has no events list")
    return events


def summarize(path: Path, include_payload_prefix: bool = False) -> dict:
    parser = SppV2StreamParser()
    frames = []
    errors = []
    events = load_events(path)
    for idx, event in enumerate(events):
        hex_value = event.get("hex") or event.get("hexPrefix") or ""
        try:
            chunk = bytes.fromhex(hex_value)
        except ValueError as exc:
            errors.append({"event_index": idx, "error": f"invalid_hex:{exc.__class__.__name__}"})
            continue
        try:
            for frame in parser.feed(chunk):
                item = {
                    "packet_type": int(frame.packet_type),
                    "packet_type_name": frame.packet_type.name,
                    "sequence": frame.sequence,
                    "payload_len": len(frame.payload),
                    "crc": f"0x{frame.crc:04x}",
                }
                if include_payload_prefix:
                    item["payload_hex_prefix"] = frame.payload[:32].hex()
                frames.append(item)
        except FrameParseError as exc:
            errors.append({"event_index": idx, "error": str(exc)})
    return {
        "input": str(path),
        "event_count": len(events),
        "frame_count": len(frames),
        "buffered_len": parser.buffered_len,
        "frames": frames,
        "errors": errors,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_path", type=Path)
    parser.add_argument("--include-payload-prefix", action="store_true")
    args = parser.parse_args(argv)
    print(json.dumps(summarize(args.json_path, args.include_payload_prefix), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
