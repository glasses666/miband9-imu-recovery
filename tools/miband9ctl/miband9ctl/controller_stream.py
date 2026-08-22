from __future__ import annotations

import json
import time
from typing import Any, Iterable

from .controller import ControllerState, SensorSample


def _mid(packet: dict[str, Any], prefix: str, axis: str) -> float:
    return (float(packet.get(f"{prefix}_{axis}_min") or 0.0) + float(packet.get(f"{prefix}_{axis}_max") or 0.0)) / 2.0


def _valid_summary_packet(packet: dict[str, Any]) -> bool:
    if int(packet.get("accel_samples") or 0) <= 0 or int(packet.get("gyro_samples") or 0) <= 0:
        return False
    first = int(float(packet.get("first_accel_timestamp") or 0))
    last = int(float(packet.get("last_accel_timestamp") or 0))
    return bool(first and last and 70_000 <= (last - first) <= 130_000)


def samples_from_probe_json(data: dict[str, Any]) -> Iterable[SensorSample]:
    probe = data.get("data", {}).get("probe", data.get("probe", data))
    packets = probe.get("packets") or []
    for packet in packets:
        elapsed_ms = float(packet.get("elapsed_ms") or 0.0)
        packet_samples = packet.get("samples") or []
        if packet_samples:
            for idx, sample in enumerate(packet_samples):
                yield SensorSample(
                    t_ms=float(sample.get("t", elapsed_ms + idx * 10.0) or 0.0),
                    ax=float(sample.get("ax") or 0.0),
                    ay=float(sample.get("ay") or 0.0),
                    az=float(sample.get("az") or 0.0),
                    gx=float(sample.get("gx") or 0.0),
                    gy=float(sample.get("gy") or 0.0),
                    gz=float(sample.get("gz") or 0.0),
                )
            continue
        if not _valid_summary_packet(packet):
            continue
        yield SensorSample(
            t_ms=elapsed_ms,
            ax=_mid(packet, "accel", "x"),
            ay=_mid(packet, "accel", "y"),
            az=_mid(packet, "accel", "z"),
            gx=_mid(packet, "gyro", "x"),
            gy=_mid(packet, "gyro", "y"),
            gz=_mid(packet, "gyro", "z"),
        )


def frame_for_state(*, seq: int, state: ControllerState, sent_at_ms: int | None = None) -> dict[str, Any]:
    if sent_at_ms is None:
        sent_at_ms = int(time.time() * 1000)
    frame: dict[str, Any] = {
        "seq": int(seq),
        "sent_at_ms": int(sent_at_ms),
        "lx": round(state.lx, 4),
        "ly": round(state.ly, 4),
        "rx": round(state.rx, 4),
        "ry": round(state.ry, 4),
        "lt": round(state.lt, 4),
        "rt": round(state.rt, 4),
        "gate": bool(state.gate),
    }
    if state.motion is not None:
        frame["motion"] = state.motion.as_dict()
    return frame


def encode_frame(frame: dict[str, Any]) -> bytes:
    return (json.dumps(frame, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
