#!/usr/bin/env python3
"""Run a controlled quiet -> find-band vibration -> quiet SportXms IMU probe.

This script intentionally uses the headless Gadgetbridge find-band path rather
than weak notification/call side effects. It is designed for gate tuning: the
marker log records the wall-clock find-band window while the SportXms probe
records per-packet accel/gyro ranges.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import statistics
import subprocess
import time
from pathlib import Path


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    seq = sorted(values)
    if len(seq) == 1:
        return seq[0]
    pos = (len(seq) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return seq[lo]
    frac = pos - lo
    return seq[lo] * (1.0 - frac) + seq[hi] * frac


def _mean(values: list[float]) -> float:
    return float(statistics.fmean(values)) if values else 0.0


def _range(packet: dict, prefix: str, axis: str) -> float:
    return float(packet.get(f"{prefix}_{axis}_max") or 0.0) - float(packet.get(f"{prefix}_{axis}_min") or 0.0)


def _mid(packet: dict, prefix: str, axis: str) -> float:
    return (float(packet.get(f"{prefix}_{axis}_max") or 0.0) + float(packet.get(f"{prefix}_{axis}_min") or 0.0)) / 2.0


def _packet_metric(packet: dict, calibration: dict | None) -> dict:
    accel_range = math.sqrt(sum(_range(packet, "accel", axis) ** 2 for axis in ("x", "y", "z")))
    gyro_range = math.sqrt(sum(_range(packet, "gyro", axis) ** 2 for axis in ("x", "y", "z")))
    gyro_mid = {axis: _mid(packet, "gyro", axis) for axis in ("x", "y", "z")}
    accel_mid = {axis: _mid(packet, "accel", axis) for axis in ("x", "y", "z")}
    accel_delta = 0.0
    gyro_abs = math.sqrt(sum(v * v for v in gyro_mid.values()))
    if calibration:
        neutral = calibration.get("accel_neutral") or {}
        bias = calibration.get("gyro_bias") or {}
        accel_delta = math.sqrt(sum((accel_mid[axis] - float(neutral.get(axis) or 0.0)) ** 2 for axis in ("x", "y", "z")))
        gyro_abs = math.sqrt(sum((gyro_mid[axis] - float(bias.get(axis) or 0.0)) ** 2 for axis in ("x", "y", "z")))
    return {
        "elapsed_ms": int(float(packet.get("elapsed_ms") or 0)),
        "accel_range": accel_range,
        "gyro_range": gyro_range,
        "accel_delta": accel_delta,
        "gyro_abs": gyro_abs,
    }


def summarize_gate_metrics(capture_path: Path, *, quiet_before_ms: int, vibration_ms: int, quiet_after_ms: int,
                           calibration_path: Path | None = None, settle_ms: int = 350) -> dict:
    with capture_path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    calibration = None
    if calibration_path and calibration_path.exists():
        with calibration_path.open(encoding="utf-8") as fh:
            calibration = json.load(fh)
    gate = (calibration or {}).get("vibration_gate") or {}
    accel_delta_threshold = float(gate.get("accel_delta_threshold") or 0.18)
    gyro_abs_threshold = float(gate.get("gyro_abs_threshold") or 0.025)
    packets = data.get("data", {}).get("probe", data.get("probe", data)).get("packets") or []
    rows = [_packet_metric(packet, calibration) for packet in packets if int(packet.get("accel_samples") or 0) > 0]
    windows = {
        "quiet_before": (0, quiet_before_ms),
        "vibration": (quiet_before_ms, quiet_before_ms + vibration_ms + settle_ms),
        "quiet_after": (quiet_before_ms + vibration_ms + settle_ms, quiet_before_ms + vibration_ms + settle_ms + quiet_after_ms),
    }
    result = {
        "schema": "miband9-vibration-gate-metrics.v1",
        "capture": str(capture_path),
        "calibration": str(calibration_path) if calibration_path else "",
        "thresholds": {
            "accel_delta_threshold": accel_delta_threshold,
            "gyro_abs_threshold": gyro_abs_threshold,
            "settle_ms": settle_ms,
        },
        "packet_count": len(rows),
        "windows": {},
    }
    for name, (start, end) in windows.items():
        bucket = [row for row in rows if start <= row["elapsed_ms"] < end]
        accel_delta = [row["accel_delta"] for row in bucket]
        gyro_abs = [row["gyro_abs"] for row in bucket]
        accel_range = [row["accel_range"] for row in bucket]
        gyro_range = [row["gyro_range"] for row in bucket]
        gate_hits = [row for row in bucket if row["accel_delta"] > accel_delta_threshold or row["gyro_abs"] > gyro_abs_threshold]
        result["windows"][name] = {
            "start_ms": start,
            "end_ms": end,
            "packet_count": len(bucket),
            "gate_hit_count": len(gate_hits),
            "gate_hit_ratio": (len(gate_hits) / len(bucket)) if bucket else 0.0,
            "accel_delta_mean": _mean(accel_delta),
            "accel_delta_p95": _quantile(accel_delta, 0.95),
            "accel_delta_max": max(accel_delta) if accel_delta else 0.0,
            "gyro_abs_mean": _mean(gyro_abs),
            "gyro_abs_p95": _quantile(gyro_abs, 0.95),
            "gyro_abs_max": max(gyro_abs) if gyro_abs else 0.0,
            "accel_range_mean": _mean(accel_range),
            "accel_range_p95": _quantile(accel_range, 0.95),
            "gyro_range_mean": _mean(gyro_range),
            "gyro_range_p95": _quantile(gyro_range, 0.95),
        }
    return result


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="milliseconds")


def run_find_band(args: argparse.Namespace, *, label: str, duration_ms: int) -> dict:
    cmd = [
        "python3",
        "-m",
        "miband9ctl",
        "--json",
        "--timeout",
        str(max(args.timeout, duration_ms // 1000 + 10)),
        "band",
        "mi-find-band" if (args.mi_health_route or args.mi_health_did) else "find-band",
    ]
    if args.mi_health_did:
        cmd.extend(["--did", args.mi_health_did])
    cmd.extend(["--duration-ms", str(duration_ms)])
    if not (args.mi_health_route or args.mi_health_did) and args.address:
        cmd.extend(["--address", args.address.upper()])
    started = now_iso()
    proc = subprocess.run(
        cmd,
        cwd=args.miband9ctl_dir,
        text=True,
        capture_output=True,
        timeout=max(args.timeout, duration_ms // 1000 + 15),
    )
    ended = now_iso()
    payload: dict = {}
    if proc.stdout.strip():
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"raw_stdout": proc.stdout.strip()}
    return {
        "label": label,
        "started_wall": started,
        "ended_wall": ended,
        "returncode": proc.returncode,
        "stdout": payload,
        "stderr": proc.stderr.strip(),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--miband9ctl-dir", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--out-dir", type=Path, default=Path(__file__).resolve().parent / "artifacts" / "imu_calibration" / "vibration_gate_probe")
    parser.add_argument("--address", default="", help="Optional band MAC address for Gadgetbridge find-band route.")
    parser.add_argument("--mi-health-route", action="store_true", default=False, help="Use Mi Fitness DeviceSettings find-device route and auto-resolve DID through SportXms device info.")
    parser.add_argument("--mi-health-did", default="", help="Optional Mi Fitness device id override for Mi Health route; redacted from summaries.")
    parser.add_argument("--sport-type", type=int, default=812)
    parser.add_argument("--quiet-before-ms", type=int, default=5000)
    parser.add_argument("--vibration-ms", type=int, default=3000)
    parser.add_argument("--quiet-after-ms", type=int, default=5000)
    parser.add_argument("--settle-ms", type=int, default=350)
    parser.add_argument("--calibration", type=Path, default=Path(__file__).resolve().parent / "artifacts" / "imu_calibration" / "20260530_flat_vibration" / "flat_table_calibration_20260530.json")
    parser.add_argument("--timeout", type=int, default=45)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.miband9ctl_dir = args.miband9ctl_dir.expanduser().resolve()
    stamp = dt.datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    out_dir = args.out_dir.expanduser().resolve() / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    capture_ms = max(500, args.quiet_before_ms + args.vibration_ms + args.quiet_after_ms)
    capture_path = out_dir / "sport_xms_probe.json"
    markers_path = out_dir / "markers.jsonl"
    metrics_path = out_dir / "gate_metrics.json"

    def marker(payload: dict) -> None:
        with markers_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    marker({"event": "probe_start", "wall": now_iso(), "capture_ms": capture_ms})
    with capture_path.open("wb") as fh:
        probe = subprocess.Popen(
            [
                "python3",
                "-m",
                "miband9ctl",
                "--json",
                "--timeout",
                str(max(args.timeout, capture_ms // 1000 + 20)),
                "band",
                "sport-xms-probe",
                "--start",
                "--sport-type",
                str(args.sport_type),
                "--capture-ms",
                str(capture_ms),
            ],
            cwd=args.miband9ctl_dir,
            stdout=fh,
            stderr=subprocess.PIPE,
        )
        time.sleep(args.quiet_before_ms / 1000.0)
        marker({"event": "find_band_requested", "wall": now_iso(), "duration_ms": args.vibration_ms})
        find_result = run_find_band(args, label="find-band", duration_ms=args.vibration_ms)
        marker({"event": "find_band_result", **find_result})
        try:
            _, stderr = probe.communicate(timeout=max(args.timeout, capture_ms // 1000 + 20))
        except subprocess.TimeoutExpired:
            probe.kill()
            _, stderr = probe.communicate(timeout=5)
    marker({
        "event": "probe_end",
        "wall": now_iso(),
        "returncode": probe.returncode,
        "stderr": stderr.decode("utf-8", "replace").strip() if stderr else "",
    })
    metrics = {}
    if capture_path.exists() and capture_path.stat().st_size > 0:
        try:
            metrics = summarize_gate_metrics(
                capture_path,
                quiet_before_ms=args.quiet_before_ms,
                vibration_ms=args.vibration_ms,
                quiet_after_ms=args.quiet_after_ms,
                calibration_path=args.calibration.expanduser().resolve() if args.calibration else None,
                settle_ms=args.settle_ms,
            )
            with metrics_path.open("w", encoding="utf-8") as fh:
                json.dump(metrics, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
        except Exception as exc:  # noqa: BLE001 - field probe should preserve raw capture even if analysis fails.
            metrics = {"error": f"{exc.__class__.__name__}: {exc}"}
    print(json.dumps({
        "out_dir": str(out_dir),
        "capture": str(capture_path),
        "markers": str(markers_path),
        "metrics": str(metrics_path) if metrics else "",
        "capture_ms": capture_ms,
        "probe_returncode": probe.returncode,
        "find_returncode": find_result.get("returncode"),
        "window_summary": metrics.get("windows", {}) if isinstance(metrics, dict) else {},
    }, ensure_ascii=False, indent=2))
    return int(probe.returncode or 0)


if __name__ == "__main__":
    raise SystemExit(main())
