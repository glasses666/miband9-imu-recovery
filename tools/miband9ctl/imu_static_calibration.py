#!/usr/bin/env python3
"""Build a static-pose calibration JSON from SportXms probe output.

The SportXms CLI output is intentionally log/JSON oriented.  For quick field
calibration we only need a quiet flat/anchor capture: robust accel gravity
vector, gyro bias, pitch/roll zero offsets, and noise-derived gate thresholds.

Input format: stdout JSON from

    python3 -m miband9ctl --json band sport-xms-probe --start --sport-type 812 --capture-ms 15000

The parser accepts both per-sample packets (from live state dumps) and compact
packet summaries (min/max ranges).  Compact summaries use packet midpoints,
which is enough for static-pose bias and dashboard recentering.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import statistics
from pathlib import Path
from typing import Any, Iterable


def _mean(values: Iterable[float]) -> float:
    seq = list(values)
    if not seq:
        raise ValueError("empty sequence")
    return float(statistics.fmean(seq))


def _pstdev(values: Iterable[float]) -> float:
    seq = list(values)
    if len(seq) < 2:
        return 0.0
    return float(statistics.pstdev(seq))


def _quantile(values: Iterable[float], q: float) -> float:
    seq = sorted(float(v) for v in values)
    if not seq:
        raise ValueError("empty sequence")
    if len(seq) == 1:
        return seq[0]
    pos = (len(seq) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return seq[lo]
    frac = pos - lo
    return seq[lo] * (1.0 - frac) + seq[hi] * frac


def _packet_midpoint(packet: dict[str, Any], axis: str) -> float:
    return (float(packet[f"{axis}_min"]) + float(packet[f"{axis}_max"])) / 2.0


def _packet_range(packet: dict[str, Any], axis: str) -> float:
    return float(packet[f"{axis}_max"]) - float(packet[f"{axis}_min"])


def _valid_summary_packet(packet: dict[str, Any]) -> bool:
    if int(packet.get("accel_samples") or 0) <= 0 or int(packet.get("gyro_samples") or 0) <= 0:
        return False
    first = int(float(packet.get("first_accel_timestamp") or 0))
    last = int(float(packet.get("last_accel_timestamp") or 0))
    if not first or not last:
        return False
    # Normal 10-sample packet spans ~90 ms at 100 Hz.  Startup packets can carry
    # stale pre-session timestamps and poison the baseline, so drop them.
    return 70_000 <= (last - first) <= 130_000


def samples_from_probe_json(data: dict[str, Any]) -> tuple[list[dict[str, float]], list[dict[str, float]]]:
    """Return (sample_rows, packet_range_rows) from a miband9ctl probe JSON object."""
    probe = data.get("data", {}).get("probe", data.get("probe", data))
    packets = probe.get("packets") or []
    rows: list[dict[str, float]] = []
    ranges: list[dict[str, float]] = []
    for packet in packets:
        packet_samples = packet.get("samples") or []
        if packet_samples:
            for sample in packet_samples:
                rows.append(
                    {
                        "ax": float(sample.get("ax") or 0.0),
                        "ay": float(sample.get("ay") or 0.0),
                        "az": float(sample.get("az") or 0.0),
                        "gx": float(sample.get("gx") or 0.0),
                        "gy": float(sample.get("gy") or 0.0),
                        "gz": float(sample.get("gz") or 0.0),
                    }
                )
            continue
        if not _valid_summary_packet(packet):
            continue
        rows.append(
            {
                "ax": _packet_midpoint(packet, "accel_x"),
                "ay": _packet_midpoint(packet, "accel_y"),
                "az": _packet_midpoint(packet, "accel_z"),
                "gx": _packet_midpoint(packet, "gyro_x"),
                "gy": _packet_midpoint(packet, "gyro_y"),
                "gz": _packet_midpoint(packet, "gyro_z"),
            }
        )
        ranges.append(
            {
                "accel_range": math.sqrt(
                    sum(_packet_range(packet, axis) ** 2 for axis in ("accel_x", "accel_y", "accel_z"))
                ),
                "gyro_range": math.sqrt(
                    sum(_packet_range(packet, axis) ** 2 for axis in ("gyro_x", "gyro_y", "gyro_z"))
                ),
            }
        )
    return rows, ranges


def build_calibration(data: dict[str, Any], *, name: str, source: str = "") -> dict[str, Any]:
    rows, ranges = samples_from_probe_json(data)
    if len(rows) < 20:
        raise ValueError(f"need at least 20 quiet samples/packet midpoints, got {len(rows)}")

    ax = _mean(row["ax"] for row in rows)
    ay = _mean(row["ay"] for row in rows)
    az = _mean(row["az"] for row in rows)
    gx = _mean(row["gx"] for row in rows)
    gy = _mean(row["gy"] for row in rows)
    gz = _mean(row["gz"] for row in rows)
    accel_mag_values = [math.sqrt(row["ax"] ** 2 + row["ay"] ** 2 + row["az"] ** 2) for row in rows]
    accel_mag = _mean(accel_mag_values)
    pitch = math.atan2(-ax, math.sqrt(ay * ay + az * az))
    roll = math.atan2(ay, az)

    if ranges:
        accel_range_p95 = _quantile((row["accel_range"] for row in ranges), 0.95)
        gyro_range_p95 = _quantile((row["gyro_range"] for row in ranges), 0.95)
        accel_range_mean = _mean(row["accel_range"] for row in ranges)
        gyro_range_mean = _mean(row["gyro_range"] for row in ranges)
    else:
        # Per-sample inputs do not have intra-packet ranges.  Use conservative
        # gates around the observed inter-sample noise floor.
        accel_range_mean = _pstdev(accel_mag_values)
        gyro_mags = [math.sqrt(row["gx"] ** 2 + row["gy"] ** 2 + row["gz"] ** 2) for row in rows]
        gyro_range_mean = _pstdev(gyro_mags)
        accel_range_p95 = max(accel_range_mean * 3.0, 0.08)
        gyro_range_p95 = max(gyro_range_mean * 3.0, 0.006)

    # Thresholds are deliberately above the quiet floor: they should catch table
    # taps / vibration / real movement, not normal quantization jitter.
    accel_delta_threshold = max(0.18, accel_range_p95 * 1.8)
    gyro_abs_threshold = max(0.025, gyro_range_p95 * 3.0)

    return {
        "schema": "miband9-sportxms-static-calibration.v1",
        "name": name,
        "source": source,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "sample_count": len(rows),
        "packet_range_count": len(ranges),
        "accel_neutral": {"x": ax, "y": ay, "z": az, "mag": accel_mag},
        "gyro_bias": {"x": gx, "y": gy, "z": gz},
        "pitch_rad": pitch,
        "roll_rad": roll,
        "pitch_deg": math.degrees(pitch),
        "roll_deg": math.degrees(roll),
        "noise": {
            "accel_mag_stdev": _pstdev(accel_mag_values),
            "accel_range_mean": accel_range_mean,
            "accel_range_p95": accel_range_p95,
            "gyro_range_mean": gyro_range_mean,
            "gyro_range_p95": gyro_range_p95,
        },
        "vibration_gate": {
            "accel_delta_threshold": accel_delta_threshold,
            "gyro_abs_threshold": gyro_abs_threshold,
            "settle_ms": 350,
            "note": "Dashboard freezes/softens attitude correction while sample jerk exceeds these quiet-flat gates.",
        },
        "notes": [
            "Generated from a quiet flat/anchor capture; yaw remains relative and is not magnetically stabilized.",
            "Do not update gyro bias during vibration or non-stationary windows.",
        ],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="miband9ctl SportXms probe JSON file")
    parser.add_argument("-o", "--output", required=True, help="output calibration JSON path")
    parser.add_argument("--name", default="flat-static-calibration", help="human-readable calibration name")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    input_path = Path(args.input)
    with input_path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    calibration = build_calibration(data, name=args.name, source=str(input_path))
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(calibration, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(json.dumps({"output": str(output_path), "sample_count": calibration["sample_count"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
