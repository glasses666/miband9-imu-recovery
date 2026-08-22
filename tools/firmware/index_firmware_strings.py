#!/usr/bin/env python3
"""Read-only firmware string indexer for Mi Band / Vela firmware packages.

The script extracts printable strings with offsets, filters sensor/batch/FIFO/ODR
keywords, and writes local artifacts under an output directory. It never patches
or rewrites firmware input files.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

PRINTABLES = set(range(32, 127)) | {9}
KEYWORDS = {
    "imu_chip": r"(?i)(bmi270|bmi2|bmi08|lsm6dso|lsm6dsl|bosch|stmicro|gyro|gsensor|g-sensor|acceler|accel|imu)",
    "sensor_core": r"(?i)(sensor|sensors/|sensorhub|sensor_hub|input_event|device_register|sensor data)",
    "fifo_batch": r"(?i)(fifo|batch|watermark|wtm|latency|interval|poll|sampling|sample|odr|output data rate|report[_ -]?interval|period)",
    "xms_sport": r"(?i)(sportxms|sport xms|WearSensor|wear sensor|justdance|dance|activity|workout)",
    "hmpro_fee0": r"(?i)(hmpro|fee0|3512|af100700|gsensor|rawdata|factory)",
    "rtos_paths": r"(?i)(nuttx|vela|drivers/|frameworks/|apps/|system/|source/|src/|\.c$|\.h$)",
}
SIGNAL_RE = re.compile(
    r"(?i)(bmi270|lsm6dso|fifo|watermark|wtm|batch|odr|latency|interval|"
    r"sensors/|sensor\.c|sensor_|GSENSOR|GYRO|sportxms|wearsensor|fee0|rawdata|polling)"
)


def ascii_strings(data: bytes, minlen: int) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    start: int | None = None
    buf: list[str] = []
    for idx, byte in enumerate(data):
        if byte in PRINTABLES:
            if start is None:
                start = idx
                buf = []
            buf.append(chr(byte))
        else:
            if start is not None and len(buf) >= minlen:
                out.append((start, "".join(buf)))
            start = None
            buf = []
    if start is not None and len(buf) >= minlen:
        out.append((start, "".join(buf)))
    return out


def utf16le_strings(data: bytes, minchars: int) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    idx = 0
    while idx < len(data) - 1:
        start = idx
        chars: list[str] = []
        while idx < len(data) - 1 and data[idx] in PRINTABLES and data[idx + 1] == 0:
            chars.append(chr(data[idx]))
            idx += 2
        if len(chars) >= minchars:
            out.append((start, "".join(chars)))
        if idx == start:
            idx += 1
    return out


def file_type(path: Path) -> str:
    try:
        return subprocess.run(
            ["file", "-b", str(path)], capture_output=True, text=True, timeout=10, check=False
        ).stdout.strip()
    except Exception as exc:  # pragma: no cover - diagnostic only
        return f"file_error:{type(exc).__name__}:{exc}"


def index_files(inputs: list[Path], out_dir: Path, minlen: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    compiled = {name: re.compile(pattern) for name, pattern in KEYWORDS.items()}
    manifest = []
    hits = []

    for path in inputs:
        data = path.read_bytes()
        strings = ascii_strings(data, minlen)
        u16 = utf16le_strings(data, minlen)
        manifest.append(
            {
                "file": path.name,
                "path": str(path),
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "file_type": file_type(path),
            }
        )
        with (out_dir / f"{path.name}.ascii_strings.tsv").open("w", encoding="utf-8") as fp:
            for offset, value in strings:
                fp.write(f"{offset:#x}\t{value}\n")
        if u16:
            with (out_dir / f"{path.name}.utf16le_strings.tsv").open("w", encoding="utf-8") as fp:
                for offset, value in u16:
                    fp.write(f"{offset:#x}\t{value}\n")

        for sidx, (offset, value) in enumerate(strings):
            cats = [name for name, regex in compiled.items() if regex.search(value)]
            if not cats:
                continue
            neighbors = strings[max(0, sidx - 3) : min(len(strings), sidx + 4)]
            hits.append(
                {
                    "file": path.name,
                    "offset": offset,
                    "offset_hex": hex(offset),
                    "string": value[:240],
                    "categories": cats,
                    "neighbors": [
                        {"offset_hex": hex(neighbor_offset), "string": neighbor_value[:200]}
                        for neighbor_offset, neighbor_value in neighbors
                    ],
                }
            )

    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "keyword_hits.json").write_text(json.dumps(hits, indent=2, ensure_ascii=False), encoding="utf-8")
    with (out_dir / "keyword_hits.tsv").open("w", encoding="utf-8") as fp:
        fp.write("file\toffset\tcategories\tstring\n")
        for hit in hits:
            fp.write(
                f"{hit['file']}\t{hit['offset_hex']}\t{','.join(hit['categories'])}\t"
                f"{hit['string'].replace(chr(9), ' ')}\n"
            )

    cat_counts = Counter()
    file_counts = Counter()
    for hit in hits:
        file_counts[hit["file"]] += 1
        for category in hit["categories"]:
            cat_counts[category] += 1

    seen = set()
    signals = []
    for hit in hits:
        if not SIGNAL_RE.search(hit["string"]):
            continue
        key = (hit["file"], hit["string"])
        if key in seen:
            continue
        seen.add(key)
        signals.append(hit)

    lines = [
        "# Firmware string index",
        "",
        f"Generated: {_dt.datetime.now().isoformat(timespec='seconds')}",
        f"Output: `{out_dir}`",
        "",
        "## Manifest",
    ]
    for item in manifest:
        lines.append(
            f"- `{item['file']}`: {item['size']} bytes, sha256 `{item['sha256'][:16]}...`, file `{item['file_type']}`"
        )
    lines += [
        "",
        "## Keyword hit counts",
        "- By category: " + ", ".join(f"{k}={v}" for k, v in cat_counts.most_common()),
        "- By file: " + ", ".join(f"{k}={v}" for k, v in file_counts.most_common()),
        "",
        "## High-signal strings",
    ]
    for hit in signals[:220]:
        lines.append(f"- `{hit['file']}:{hit['offset_hex']}` [{','.join(hit['categories'])}] {hit['string']}")
    lines += ["", "## Context snippets"]
    for hit in signals[:60]:
        lines.append(f"### `{hit['file']}:{hit['offset_hex']}` {hit['string']}")
        for neighbor in hit["neighbors"]:
            lines.append(f"  - `{neighbor['offset_hex']}` {neighbor['string']}")
        lines.append("")
    (out_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path, help="Firmware files to index")
    parser.add_argument("--out-dir", type=Path, required=True, help="Output artifact directory")
    parser.add_argument("--minlen", type=int, default=4, help="Minimum printable string length")
    args = parser.parse_args()
    index_files(args.inputs, args.out_dir, args.minlen)


if __name__ == "__main__":
    main()
