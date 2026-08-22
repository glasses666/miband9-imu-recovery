#!/usr/bin/env python3
"""Stream platform-neutral Mi Band controller frames over TCP NDJSON.

Phase-1 server: keep the phone attached to the Mac, map SportXms samples into a
small ControllerState frame, and let Windows1 connect outbound to this server.
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Iterable

from miband9ctl.controller import Calibration, ControllerMapper, SensorSample
from miband9ctl.controller_stream import encode_frame, frame_for_state, samples_from_probe_json

DEFAULT_CALIBRATION = Path(__file__).resolve().parent / "artifacts" / "imu_calibration" / "latest_flat_recalibration.json"
DEFAULT_PACKAGE = "nodomain.freeyourgadget.gadgetbridge.hfimucli"


class TcpFrameBroadcaster:
    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self._clients: list[socket.socket] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._server: socket.socket | None = None

    def start(self) -> None:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self.host, self.port))
        server.listen(8)
        server.settimeout(0.5)
        self._server = server
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()

    def _accept_loop(self) -> None:
        assert self._server is not None
        while not self._stop.is_set():
            try:
                client, addr = self._server.accept()
            except socket.timeout:
                continue
            client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            with self._lock:
                self._clients.append(client)
            print(f"client_connected {addr[0]}:{addr[1]}", flush=True)

    def client_count(self) -> int:
        with self._lock:
            return len(self._clients)

    def wait_for_client(self, timeout_s: float) -> bool:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if self.client_count() > 0:
                return True
            time.sleep(0.05)
        return self.client_count() > 0

    def send(self, payload: bytes) -> None:
        with self._lock:
            clients = list(self._clients)
        dead: list[socket.socket] = []
        for client in clients:
            try:
                client.sendall(payload)
            except OSError:
                dead.append(client)
        if dead:
            with self._lock:
                self._clients = [c for c in self._clients if c not in dead]
            for client in dead:
                try:
                    client.close()
                except OSError:
                    pass

    def close(self) -> None:
        self._stop.set()
        if self._server is not None:
            try:
                self._server.close()
            except OSError:
                pass
        with self._lock:
            clients = list(self._clients)
            self._clients = []
        for client in clients:
            try:
                client.close()
            except OSError:
                pass


def load_calibration(path: Path) -> Calibration:
    with path.expanduser().open(encoding="utf-8") as fh:
        return Calibration.from_json(json.load(fh))


def load_probe_samples(path: Path) -> list[SensorSample]:
    with path.expanduser().open(encoding="utf-8") as fh:
        return list(samples_from_probe_json(json.load(fh)))


def iter_live_samples(args: argparse.Namespace) -> Iterable[SensorSample]:
    # Reuse the existing live dashboard helpers so this script stays aligned with
    # the proven SportXms logcat path.
    from live_sportxms_web import broadcast_probe, clear_logcat, extract_payload, packet_from_payload, start_logcat

    request_id = f"controller-{uuid.uuid4().hex[:10]}"
    nonce = uuid.uuid4().hex
    helper_args = SimpleNamespace(
        serial=args.serial,
        package=args.package,
        duration_ms=args.duration_ms,
        start=True,
        sport_type=args.sport_type,
        did=args.did,
        adb_timeout=args.adb_timeout,
    )
    clear_logcat(args.serial)
    logcat = start_logcat(args.serial)
    try:
        launched = broadcast_probe(helper_args, request_id, nonce)
        print(f"sportxms_broadcast returncode={launched.returncode}", flush=True)
        deadline = time.time() + (args.duration_ms / 1000.0) + 5.0
        assert logcat.stdout is not None
        while time.time() < deadline:
            line = logcat.stdout.readline()
            if not line:
                if logcat.poll() is not None:
                    break
                time.sleep(0.01)
                continue
            payload = extract_payload(line, nonce)
            if payload is None or payload.get("message") != "sensor_packet":
                continue
            packet = packet_from_payload(payload)
            for sample in packet.samples:
                yield SensorSample(
                    t_ms=float(sample.get("t") or packet.elapsed_ms),
                    ax=float(sample.get("ax") or 0.0),
                    ay=float(sample.get("ay") or 0.0),
                    az=float(sample.get("az") or 0.0),
                    gx=float(sample.get("gx") or 0.0),
                    gy=float(sample.get("gy") or 0.0),
                    gz=float(sample.get("gz") or 0.0),
                )
    finally:
        logcat.terminate()
        try:
            logcat.wait(timeout=2)
        except Exception:
            logcat.kill()


def align_next_tick(next_tick: float, period: float, *, now: float | None = None, max_lag_periods: float = 2.0) -> float:
    """Drop scheduler debt after blocking acquisition waits.

    SportXms/logcat delivers batches: the generator can block for ~100 ms and
    then yield 10 samples immediately. If we keep the original stream-start
    deadline, the server tries to "catch up" by blasting samples at 0 ms
    intervals. Resetting only when the deadline is stale preserves 100 Hz
    spacing inside a newly-arrived batch without turning logcat stalls into
    fake gamepad bursts.
    """
    now = time.perf_counter() if now is None else now
    if now - next_tick > period * max_lag_periods:
        return now
    return next_tick


def pace_to(next_tick: float, *, mode: str) -> None:
    if mode == "sleep":
        remaining = next_tick - time.perf_counter()
        if remaining > 0:
            time.sleep(remaining)
        return
    while True:
        remaining = next_tick - time.perf_counter()
        if remaining <= 0:
            return
        # The current macOS/Hermes environment can oversleep 10 ms requests by
        # ~4x. Spin for sub-frame controller pacing; one core for a short stream
        # is a better trade than a 27 Hz fake gamepad.
        if remaining > 0.02:
            time.sleep(0.001)


def run_stream(args: argparse.Namespace) -> int:
    calibration = load_calibration(args.calibration)
    mapper = ControllerMapper(
        calibration,
        tilt_full_scale_deg=args.tilt_full_scale_deg,
        yaw_rate_full_scale=args.yaw_rate_full_scale,
        pitch_rate_full_scale=args.pitch_rate_full_scale,
        deadzone=args.deadzone,
        smoothing_alpha=args.smoothing_alpha,
    )
    if args.probe_json:
        samples: Iterable[SensorSample] = load_probe_samples(args.probe_json)
        mode = "probe"
    else:
        samples = iter_live_samples(args)
        mode = "live"

    server = TcpFrameBroadcaster(args.host, args.port)
    server.start()
    print(json.dumps({"status": "listening", "mode": mode, "host": args.host, "port": args.port, "calibration": str(args.calibration), "rate_hz": args.rate_hz}), flush=True)
    if args.wait_client_s and not server.wait_for_client(args.wait_client_s):
        print("warning=no_client_connected_before_stream", flush=True)
    period = 1.0 / max(1.0, args.rate_hz)
    seq = 0
    sent = 0
    started = time.time()
    next_tick = time.perf_counter()
    try:
        while True:
            for sample in samples:
                next_tick = align_next_tick(next_tick, period)
                state = mapper.update(sample, now_ms=int(time.time() * 1000))
                frame = frame_for_state(seq=seq, state=state)
                server.send(encode_frame(frame))
                sent += 1
                seq += 1
                if args.print_every and sent % args.print_every == 0:
                    print(json.dumps({"sent": sent, "clients": server.client_count(), "frame": frame}, separators=(",", ":")), flush=True)
                next_tick += period
                pace_to(next_tick, mode=args.pace)
            if not args.loop_probe or not args.probe_json:
                break
            samples = load_probe_samples(args.probe_json)
    finally:
        server.close()
    print(json.dumps({"status": "done", "sent": sent, "elapsed_s": round(time.time() - started, 3)}), flush=True)
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=18766)
    parser.add_argument("--calibration", type=Path, default=DEFAULT_CALIBRATION)
    parser.add_argument("--probe-json", type=Path, default=None, help="Replay a captured sport_xms_probe.json instead of live Android data")
    parser.add_argument("--loop-probe", action="store_true")
    parser.add_argument("--rate-hz", type=float, default=60.0)
    parser.add_argument("--pace", choices=["spin", "sleep"], default="spin", help="spin keeps controller pacing accurate on hosts with coarse sleep timers")
    parser.add_argument("--wait-client-s", type=float, default=10.0)
    parser.add_argument("--print-every", type=int, default=120)
    parser.add_argument("--tilt-full-scale-deg", type=float, default=30.0)
    parser.add_argument("--yaw-rate-full-scale", type=float, default=1.0)
    parser.add_argument("--pitch-rate-full-scale", type=float, default=1.0)
    parser.add_argument("--deadzone", type=float, default=0.05)
    parser.add_argument("--smoothing-alpha", type=float, default=0.34)
    parser.add_argument("--serial", default="")
    parser.add_argument("--package", default=DEFAULT_PACKAGE)
    parser.add_argument("--duration-ms", type=int, default=30000)
    parser.add_argument("--sport-type", type=int, default=812)
    parser.add_argument("--did", default="")
    parser.add_argument("--adb-timeout", type=int, default=20)
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(run_stream(parse_args()))
