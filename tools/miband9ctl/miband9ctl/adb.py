import subprocess
import time
from dataclasses import dataclass
from typing import List, Mapping, Optional


DEFAULT_PACKAGE = "nodomain.freeyourgadget.gadgetbridge.hfimucli"
DEFAULT_ACTION_SUFFIX = ".CLI"
HFIMU_RECEIVER_CLASS = "nodomain.freeyourgadget.gadgetbridge.externalevents.hfimu.HfImuCliReceiver"


@dataclass
class Completed:
    args: List[str]
    returncode: int
    stdout: str
    stderr: str


def hfimu_action_for_package(package: str) -> str:
    return f"{package}{DEFAULT_ACTION_SUFFIX}"


def hfimu_component_for_package(package: str) -> str:
    return f"{package}/{HFIMU_RECEIVER_CLASS}"


def adb_prefix(serial: Optional[str] = None) -> List[str]:
    cmd = ["adb"]
    if serial:
        cmd += ["-s", serial]
    return cmd


def build_hfimu_broadcast_cmd(
    *,
    serial: Optional[str],
    package: str,
    command: str,
    request_id: str,
    nonce: str,
    extras: Optional[Mapping[str, object]] = None,
) -> List[str]:
    cmd = (
        adb_prefix(serial)
        + [
            "shell", "am", "broadcast",
            "--include-stopped-packages",
            "-n", hfimu_component_for_package(package),
            "-a", hfimu_action_for_package(package),
            "--es", "command", command,
            "--es", "request_id", request_id,
            "--es", "nonce", nonce,
        ]
    )
    for key, value in (extras or {}).items():
        if value is None:
            continue
        string_value = str(value)
        if string_value == "":
            continue
        cmd += ["--es", key, string_value]
    return cmd


def run(cmd: List[str], timeout: int = 30) -> Completed:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return Completed(cmd, proc.returncode, proc.stdout, proc.stderr)


def adb_devices() -> Completed:
    return run(["adb", "devices", "-l"], timeout=15)


def adb_shell(serial: Optional[str], *args: str, timeout: int = 30) -> Completed:
    return run(adb_prefix(serial) + ["shell", *args], timeout=timeout)


def clear_logcat(serial: Optional[str]) -> Completed:
    return run(adb_prefix(serial) + ["logcat", "-c"], timeout=15)


def dump_hfimu_logcat(serial: Optional[str]) -> Completed:
    return run(
        adb_prefix(serial)
        + [
            "logcat", "-d", "-v", "brief",
            "MI_HFIMU_RESULT:I", "MI_HFIMU_STATE:I", "MI_HFIMU_ERROR:I",
            "MI_IMU_RAW_RX:I", "MI_IMU_STATS:I", "XiaomiSppSupport:I", "XiaomiSupport:I", "*:S",
        ],
        timeout=15,
    )


def broadcast_hfimu(
    *,
    serial: Optional[str],
    package: str,
    command: str,
    request_id: str,
    nonce: str,
    extras: Optional[Mapping[str, object]] = None,
    timeout: int = 30,
) -> Completed:
    return run(
        build_hfimu_broadcast_cmd(
            serial=serial,
            package=package,
            command=command,
            request_id=request_id,
            nonce=nonce,
            extras=extras,
        ),
        timeout=timeout,
    )


def wait_for_nonce(serial: Optional[str], nonce: str, timeout: float = 5.0) -> Completed:
    deadline = time.time() + timeout
    last = Completed([], 1, "", "timeout")
    while time.time() < deadline:
        last = dump_hfimu_logcat(serial)
        if nonce in last.stdout or nonce in last.stderr:
            return last
        time.sleep(0.25)
    return last
