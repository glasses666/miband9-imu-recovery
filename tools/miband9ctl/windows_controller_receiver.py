#!/usr/bin/env python3
"""Receive Mi Band ControllerState frames on Windows and optionally drive vgamepad.

The default dry-run backend is intentionally safe: it prints latency and axis
stats without installing or touching a virtual controller driver. Use
`--backend vgamepad` only after ViGEmBus/vgamepad are ready on Windows.
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import time
from pathlib import Path
from typing import Any

from miband9ctl.controller_net import axis_to_vgamepad_float, collect_frame_latency, interval_summary_ms, latency_summary


class DryRunBackend:
    def update(self, frame: dict[str, Any]) -> None:
        return

    def close(self) -> None:
        return


class VGamepadBackend:
    def __init__(self, *, invert_left_y: bool = True, invert_right_y: bool = True) -> None:
        try:
            import vgamepad as vg  # type: ignore
        except Exception as exc:  # noqa: BLE001 - report import/driver readiness cleanly.
            raise RuntimeError(f"vgamepad_unavailable:{exc.__class__.__name__}:{exc}") from exc
        self.vg = vg
        self.gamepad = vg.VX360Gamepad()
        self.invert_left_y = invert_left_y
        self.invert_right_y = invert_right_y

    def update(self, frame: dict[str, Any]) -> None:
        self.gamepad.left_joystick_float(
            x_value_float=axis_to_vgamepad_float(frame.get("lx", 0.0)),
            y_value_float=axis_to_vgamepad_float(frame.get("ly", 0.0), invert=self.invert_left_y),
        )
        self.gamepad.right_joystick_float(
            x_value_float=axis_to_vgamepad_float(frame.get("rx", 0.0)),
            y_value_float=axis_to_vgamepad_float(frame.get("ry", 0.0), invert=self.invert_right_y),
        )
        self.gamepad.update()

    def close(self) -> None:
        self.gamepad.reset()
        self.gamepad.update()


def backend_from_args(args: argparse.Namespace):
    if args.backend == "dry-run":
        return DryRunBackend()
    if args.backend == "vgamepad":
        return VGamepadBackend(invert_left_y=args.invert_left_y, invert_right_y=args.invert_right_y)
    raise ValueError(f"unknown backend {args.backend}")


def recv_frames(args: argparse.Namespace) -> int:
    backend = backend_from_args(args)
    latencies: list[float] = []
    received_mono_ms: list[float] = []
    frames = 0
    last_frame: dict[str, Any] = {}
    started = time.time()
    try:
        with socket.create_connection((args.host, args.port), timeout=args.connect_timeout) as sock:
            sock.settimeout(args.read_timeout)
            file = sock.makefile("r", encoding="utf-8", newline="\n")
            for line in file:
                line = line.strip()
                if not line:
                    continue
                try:
                    frame = json.loads(line)
                except json.JSONDecodeError:
                    continue
                epoch_ms = int(time.time() * 1000)
                received_mono_ms.append(time.perf_counter() * 1000.0)
                latency = collect_frame_latency(latencies, frame, received_at_ms=epoch_ms)
                backend.update(frame)
                last_frame = frame
                frames += 1
                if args.print_every and frames % args.print_every == 0:
                    print(json.dumps({"frames": frames, "latency": latency_summary(latencies[-args.print_every:]), "arrival_interval": interval_summary_ms(received_mono_ms[-args.print_every:]), "last": frame}, ensure_ascii=False, separators=(",", ":")), flush=True)
                if args.max_frames and frames >= args.max_frames:
                    break
    finally:
        backend.close()
    result = {
        "backend": args.backend,
        "frames": frames,
        "elapsed_s": round(time.time() - started, 3),
        "latency": latency_summary(latencies),
        "arrival_interval": interval_summary_ms(received_mono_ms),
        "last": last_frame,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if frames else 2


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="Mac stream server host/IP, e.g. 192.168.100.190")
    parser.add_argument("--port", type=int, default=18766)
    parser.add_argument("--backend", choices=["dry-run", "vgamepad"], default="dry-run")
    parser.add_argument("--max-frames", type=int, default=0)
    parser.add_argument("--print-every", type=int, default=120)
    parser.add_argument("--connect-timeout", type=float, default=8.0)
    parser.add_argument("--read-timeout", type=float, default=15.0)
    parser.add_argument("--invert-left-y", action="store_true", default=True)
    parser.add_argument("--no-invert-left-y", action="store_false", dest="invert_left_y")
    parser.add_argument("--invert-right-y", action="store_true", default=True)
    parser.add_argument("--no-invert-right-y", action="store_false", dest="invert_right_y")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(recv_frames(parse_args()))
