from __future__ import annotations

import math
from typing import Iterable


def axis_to_vgamepad_float(value: float, *, invert: bool = False) -> float:
    value = max(-1.0, min(1.0, float(value)))
    return -value if invert else value


def _quantile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = (len(sorted_values) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return sorted_values[lo]
    frac = pos - lo
    return sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac


def latency_summary(latencies_ms: Iterable[float]) -> dict[str, float | int]:
    values = sorted(float(v) for v in latencies_ms)
    if not values:
        return {"count": 0, "min_ms": 0.0, "p50_ms": 0.0, "avg_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0, "max_ms": 0.0}
    avg = sum(values) / len(values)
    return {
        "count": len(values),
        "min_ms": round(values[0], 3),
        "p50_ms": round(_quantile(values, 0.50), 3),
        "avg_ms": round(avg, 3),
        "p95_ms": round(_quantile(values, 0.95), 3),
        "p99_ms": round(_quantile(values, 0.99), 3),
        "max_ms": round(values[-1], 3),
    }


def interval_summary_ms(received_at_ms: Iterable[float]) -> dict[str, float | int]:
    times = [float(v) for v in received_at_ms]
    intervals = [b - a for a, b in zip(times, times[1:])]
    return latency_summary(intervals)


def frame_latency_ms(frame: dict, *, received_at_ms: int) -> float | None:
    sent = frame.get("sent_at_ms")
    if sent is None:
        return None
    try:
        return float(received_at_ms) - float(sent)
    except (TypeError, ValueError):
        return None


def collect_frame_latency(latencies_ms: list[float], frame: dict, *, received_at_ms: int) -> float | None:
    latency = frame_latency_ms(frame, received_at_ms=received_at_ms)
    if latency is not None:
        latencies_ms.append(latency)
    return latency
