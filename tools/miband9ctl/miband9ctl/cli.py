import argparse
import base64
import hashlib
import json
import os
import re
import shlex
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from . import adb
from .result import Result

DEFAULT_APK = "app/build/outputs/apk/mainline/hfimucli/app-mainline-hfimucli.apk"
ORIGINAL_PACKAGE = "nodomain.freeyourgadget.gadgetbridge"
GLOBAL_FLAGS_WITH_VALUES = {"--serial", "--package", "--repo-root", "--apk", "--timeout"}
GLOBAL_FLAGS_BOOL = {"--json", "--pretty"}


def normalize_global_args(argv):
    """Allow global flags before or after subcommands.

    argparse subparsers normally require global options before the subcommand;
    CLI-Anything-style tools are easier to use when `doctor --json` also works.
    """
    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    globals_out = []
    rest = []
    i = 0
    while i < len(argv):
        token = argv[i]
        if token in GLOBAL_FLAGS_BOOL:
            globals_out.append(token)
            i += 1
        elif token in GLOBAL_FLAGS_WITH_VALUES:
            globals_out.append(token)
            if i + 1 < len(argv):
                globals_out.append(argv[i + 1])
                i += 2
            else:
                rest.append(token)
                i += 1
        else:
            rest.append(token)
            i += 1
    return globals_out + rest


def repo_root_from_args(value: Optional[str]) -> Path:
    if value:
        return Path(value).expanduser().resolve()
    return Path.cwd().resolve()


def remote_pkg_dir(package: str) -> str:
    return f"/data/data/{package}"


def remote_db_path(package: str) -> str:
    return f"{remote_pkg_dir(package)}/databases/Gadgetbridge"


def remote_device_prefs_path(package: str, address: str) -> str:
    return f"{remote_pkg_dir(package)}/shared_prefs/devicesettings_{address}.xml"


def run_bytes(cmd, *, timeout=30):
    return subprocess.run(cmd, capture_output=True, timeout=timeout)


def adb_exec_out_su(serial: Optional[str], command: str, *, timeout: int = 30):
    return run_bytes(adb.adb_prefix(serial) + ["exec-out", "su", "-c", command], timeout=timeout)


def adb_shell_su(serial: Optional[str], command: str, *, timeout: int = 30):
    return adb.run(adb.adb_prefix(serial) + ["shell", "su", "-c", command], timeout=timeout)


def adb_shell_run_as(serial: Optional[str], package: str, command: str, *, timeout: int = 30):
    remote = f"run-as {shlex.quote(package)} sh -c {shlex.quote(command)}"
    return adb.run(adb.adb_prefix(serial) + ["shell", remote], timeout=timeout)


def read_remote_root_file(serial: Optional[str], path: str, *, timeout: int = 30) -> bytes:
    completed = adb_exec_out_su(serial, f"cat {shlex.quote(path)}", timeout=timeout)
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace") if isinstance(completed.stderr, bytes) else str(completed.stderr)
        raise RuntimeError(f"remote_read_failed:{path}:{stderr.strip()}")
    return completed.stdout


def remote_path_exists(serial: Optional[str], path: str, *, timeout: int = 15) -> bool:
    completed = adb_shell_su(serial, f"test -e {shlex.quote(path)}", timeout=timeout)
    return completed.returncode == 0


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def pull_root_file(serial: Optional[str], remote_path: str, local_path: Path, *, timeout: int = 60) -> None:
    local_path.parent.mkdir(parents=True, exist_ok=True)
    completed = adb_exec_out_su(serial, f"base64 {shlex.quote(remote_path)}", timeout=timeout)
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace") if isinstance(completed.stderr, bytes) else str(completed.stderr)
        raise RuntimeError(f"remote_base64_failed:{remote_path}:{stderr.strip()}")
    try:
        data = base64.b64decode(re.sub(rb"\s+", b"", completed.stdout), validate=True)
    except Exception as exc:
        raise RuntimeError(f"remote_base64_decode_failed:{remote_path}:{exc.__class__.__name__}") from exc
    write_bytes(local_path, data)


def pull_sqlite_triplet(serial: Optional[str], package: str, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    base = remote_db_path(package)
    local_db = dest_dir / "Gadgetbridge"
    pull_root_file(serial, base, local_db, timeout=60)
    for suffix in ("-wal", "-shm"):
        remote = base + suffix
        if remote_path_exists(serial, remote):
            pull_root_file(serial, remote, dest_dir / ("Gadgetbridge" + suffix), timeout=60)
    return local_db


def remote_owner(serial: Optional[str], path: str) -> str:
    completed = adb_shell_su(serial, f"stat -c '%u:%g' {shlex.quote(path)}", timeout=15)
    if completed.returncode != 0 or not completed.stdout.strip():
        raise RuntimeError(f"remote_owner_failed:{path}:{completed.stderr.strip()}")
    return completed.stdout.strip().splitlines()[-1]


def push_root_file(serial: Optional[str], local_path: Path, remote_path: str, *, owner: str, mode: str = "660", timeout: int = 60) -> dict:
    temp_remote = f"/data/local/tmp/miband9ctl-{uuid.uuid4().hex}"
    pushed = adb.run(adb.adb_prefix(serial) + ["push", str(local_path), temp_remote], timeout=timeout)
    if pushed.returncode != 0:
        return {"ok": False, "stage": "push", "returncode": pushed.returncode, "stderr": pushed.stderr.strip()}
    parent = str(Path(remote_path).parent)
    command = " && ".join([
        f"mkdir -p {shlex.quote(parent)}",
        f"cp {shlex.quote(temp_remote)} {shlex.quote(remote_path)}",
        f"chown {shlex.quote(owner)} {shlex.quote(remote_path)}",
        f"chmod {shlex.quote(mode)} {shlex.quote(remote_path)}",
        f"rm -f {shlex.quote(temp_remote)}",
    ])
    installed = adb_shell_su(serial, command, timeout=timeout)
    return {
        "ok": installed.returncode == 0,
        "stage": "install",
        "returncode": installed.returncode,
        "stdout": installed.stdout.strip(),
        "stderr": installed.stderr.strip(),
    }


def push_app_file(serial: Optional[str], package: str, local_path: Path, relative_path: str, *, mode: str = "660", timeout: int = 60) -> dict:
    temp_remote = f"/data/local/tmp/miband9ctl-{uuid.uuid4().hex}"
    pushed = adb.run(adb.adb_prefix(serial) + ["push", str(local_path), temp_remote], timeout=timeout)
    if pushed.returncode != 0:
        return {"ok": False, "stage": "push", "returncode": pushed.returncode, "stderr": pushed.stderr.strip()}
    parent = str(Path(relative_path).parent)
    command = " && ".join([
        f"mkdir -p {shlex.quote(parent)}",
        f"cp {shlex.quote(temp_remote)} {shlex.quote(relative_path)}",
        f"chmod {shlex.quote(mode)} {shlex.quote(relative_path)}",
    ])
    installed = adb_shell_run_as(serial, package, command, timeout=timeout)
    cleanup = adb.run(adb.adb_prefix(serial) + ["shell", "rm", "-f", temp_remote], timeout=15)
    return {
        "ok": installed.returncode == 0 and cleanup.returncode == 0,
        "stage": "run_as_install",
        "returncode": installed.returncode,
        "stdout": installed.stdout.strip(),
        "stderr": installed.stderr.strip(),
        "cleanup_returncode": cleanup.returncode,
    }


def backup_target_state(serial: Optional[str], package: str, address: str) -> dict:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup_dir = f"files/miband9ctl-backups/{stamp}"
    target_prefs = f"shared_prefs/devicesettings_{address}.xml"
    command = " && ".join([
        f"mkdir -p {shlex.quote(backup_dir)}",
        f"for f in databases/Gadgetbridge databases/Gadgetbridge-wal databases/Gadgetbridge-shm {shlex.quote(target_prefs)}; do [ -e \"$f\" ] && cp -p \"$f\" {shlex.quote(backup_dir)}/; done; true",
    ])
    completed = adb_shell_run_as(serial, package, command, timeout=30)
    return {"path": f"/data/data/{package}/{backup_dir}", "returncode": completed.returncode, "stderr": completed.stderr.strip()}


def sqlite_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f'pragma table_info("{table}")')]


def sqlite_row_by_identifier(conn: sqlite3.Connection, address: str) -> Optional[dict]:
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "select * from DEVICE where upper(IDENTIFIER) = upper(?) limit 1",
        (address,),
    ).fetchone()
    return None if row is None else dict(row)


def copy_device_row(source_db: Path, target_db: Path, address: str) -> dict:
    src = sqlite3.connect(source_db)
    dst = sqlite3.connect(target_db)
    try:
        src.row_factory = sqlite3.Row
        dst.row_factory = sqlite3.Row
        device = sqlite_row_by_identifier(src, address)
        if not device:
            raise RuntimeError("source_device_missing")
        target_existing = sqlite_row_by_identifier(dst, address)
        device_cols = sqlite_columns(dst, "DEVICE")
        attr_cols = sqlite_columns(dst, "DEVICE_ATTRIBUTES")
        used_id = target_existing["_id"] if target_existing else None
        if used_id is None:
            source_id = int(device["_id"])
            taken = dst.execute("select 1 from DEVICE where _id = ?", (source_id,)).fetchone()
            if taken:
                used_id = int(dst.execute("select coalesce(max(_id), 0) + 1 from DEVICE").fetchone()[0])
            else:
                used_id = source_id

        dst.execute("delete from DEVICE_ATTRIBUTES where DEVICE_ID = ?", (used_id,))
        dst.execute("delete from DEVICE where upper(IDENTIFIER) = upper(?)", (address,))
        values = {col: device.get(col) for col in device_cols}
        values["_id"] = used_id
        placeholders = ",".join("?" for _ in device_cols)
        dst.execute(
            f'insert into DEVICE ({",".join(device_cols)}) values ({placeholders})',
            [values[col] for col in device_cols],
        )

        attr_rows = [dict(row) for row in src.execute(
            "select * from DEVICE_ATTRIBUTES where DEVICE_ID = ? order by _id",
            (device["_id"],),
        )]
        next_attr_id = int(dst.execute("select coalesce(max(_id), 0) + 1 from DEVICE_ATTRIBUTES").fetchone()[0])
        inserted_attrs = 0
        for attr in attr_rows:
            attr_values = {col: attr.get(col) for col in attr_cols}
            attr_values["_id"] = next_attr_id
            attr_values["DEVICE_ID"] = used_id
            dst.execute(
                f'insert into DEVICE_ATTRIBUTES ({",".join(attr_cols)}) values ({",".join("?" for _ in attr_cols)})',
                [attr_values[col] for col in attr_cols],
            )
            next_attr_id += 1
            inserted_attrs += 1
        dst.commit()
        dst.execute("pragma wal_checkpoint(TRUNCATE)")
        return {
            "address": address,
            "device_id": used_id,
            "name": device.get("NAME"),
            "type_name": device.get("TYPE_NAME"),
            "model": device.get("MODEL"),
            "device_attributes": inserted_attrs,
        }
    finally:
        src.close()
        dst.close()


def prefs_auth_summary(prefs_bytes: bytes) -> dict:
    try:
        root = ET.fromstring(prefs_bytes.decode("utf-8", errors="replace"))
    except ET.ParseError:
        return {"authkey_present": False, "parse_error": True}
    authkey = None
    for elem in root:
        if elem.attrib.get("name") == "authkey":
            authkey = (elem.attrib.get("value") or elem.text or "").strip()
            break
    if not authkey:
        return {"authkey_present": False, "parse_error": False}
    return {
        "authkey_present": True,
        "format": "hex32" if re.fullmatch(r"[0-9a-fA-F]{32}", authkey) else "other",
        "length": len(authkey),
        "sha256_16": hashlib.sha256(authkey.encode()).hexdigest()[:16],
    }


def emit(result: Result, *, json_mode: bool, pretty: bool) -> int:
    if json_mode:
        print(result.to_json(pretty=pretty))
    else:
        if result.ok:
            print(f"ok: {result.command}")
            if result.data:
                print(result.to_json(pretty=True))
        else:
            print(f"error: {result.error or result.command}", file=sys.stderr)
            if result.data:
                print(result.to_json(pretty=True), file=sys.stderr)
    return 0 if result.ok else 1


def cmd_doctor(args) -> Result:
    devices = adb.adb_devices()
    return Result(
        ok=devices.returncode == 0,
        command="doctor",
        data={
            "adb_returncode": devices.returncode,
            "adb_stdout": devices.stdout.strip(),
            "adb_stderr": devices.stderr.strip(),
            "package": args.package,
        },
        error=None if devices.returncode == 0 else "adb_devices_failed",
    )


def cmd_build(args) -> Result:
    repo_root = repo_root_from_args(args.repo_root)
    cmd = ["./gradlew", "--no-daemon", ":app:assembleMainlineHfimucli"]
    env = os.environ.copy()
    env.setdefault("JAVA_HOME", "/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home")
    proc = subprocess.run(cmd, cwd=repo_root, env=env, capture_output=True, text=True, timeout=args.timeout)
    apk = repo_root / DEFAULT_APK
    return Result(
        ok=proc.returncode == 0 and apk.exists(),
        command="build",
        data={
            "returncode": proc.returncode,
            "apk": str(apk),
            "apk_exists": apk.exists(),
            "stdout_tail": proc.stdout[-2000:],
            "stderr_tail": proc.stderr[-2000:],
        },
        error=None if proc.returncode == 0 and apk.exists() else "build_failed",
    )


def cmd_install(args) -> Result:
    repo_root = repo_root_from_args(args.repo_root)
    apk = Path(args.apk).expanduser()
    if not apk.is_absolute():
        apk = repo_root / apk
    if not apk.exists():
        return Result(False, "install", {"apk": str(apk)}, "apk_not_found")
    cmd = adb.adb_prefix(args.serial) + ["install", "-r", str(apk)]
    completed = adb.run(cmd, timeout=args.timeout)
    method = "adb_install"
    root_push = None
    root_install = None
    ok = completed.returncode == 0 and "Success" in completed.stdout
    if not ok and "INSTALL_FAILED_USER_RESTRICTED" in (completed.stdout + completed.stderr):
        remote_apk = "/data/local/tmp/miband9ctl-hfimucli.apk"
        root_push = adb.run(adb.adb_prefix(args.serial) + ["push", str(apk), remote_apk], timeout=args.timeout)
        root_install = adb.adb_shell(args.serial, "su", "-c", f"pm install -r {remote_apk}", timeout=args.timeout)
        method = "root_pm_install"
        ok = root_push.returncode == 0 and root_install.returncode == 0 and "Success" in root_install.stdout
    return Result(
        ok=ok,
        command="install",
        data={
            "package": args.package,
            "apk": str(apk),
            "method": method,
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
            "root_push": None if root_push is None else {
                "returncode": root_push.returncode,
                "stdout": root_push.stdout.strip(),
                "stderr": root_push.stderr.strip(),
            },
            "root_install": None if root_install is None else {
                "returncode": root_install.returncode,
                "stdout": root_install.stdout.strip(),
                "stderr": root_install.stderr.strip(),
            },
        },
        error=None if ok else "install_failed",
    )


def cmd_setup(args) -> Result:
    sdk_completed = adb.adb_shell(args.serial, "getprop", "ro.build.version.sdk", timeout=15)
    try:
        sdk = int(sdk_completed.stdout.strip())
    except ValueError:
        sdk = 0
    requested_permissions = [
        ("android.permission.ACCESS_FINE_LOCATION", 1),
        ("android.permission.ACCESS_COARSE_LOCATION", 1),
        ("android.permission.BLUETOOTH_SCAN", 31),
        ("android.permission.BLUETOOTH_CONNECT", 31),
        ("android.permission.POST_NOTIFICATIONS", 33),
    ]
    grants = []
    for permission, min_sdk in requested_permissions:
        if sdk and sdk < min_sdk:
            grants.append({
                "permission": permission,
                "skipped": True,
                "reason": f"requires_api_{min_sdk}",
                "device_sdk": sdk,
            })
            continue
        completed = adb.adb_shell(args.serial, "pm", "grant", args.package, permission, timeout=15)
        grants.append({
            "permission": permission,
            "skipped": False,
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        })

    enable = cmd_app_command(args, "enable-debug")
    start = cmd_app_command(args, "start-service")
    ok = enable.ok and start.ok
    return Result(
        ok=ok,
        command="setup",
        data={
            "package": args.package,
            "grants": grants,
            "enable_debug": enable.to_dict(),
            "start_service": start.to_dict(),
        },
        error=None if ok else "setup_incomplete",
    )


def cmd_state_import(args) -> Result:
    address = args.address.upper()
    if not re.fullmatch(r"[0-9A-F]{2}(?::[0-9A-F]{2}){5}", address):
        return Result(False, "state import", {"address": args.address}, "invalid_address")
    if args.source != "original-gadgetbridge":
        return Result(False, "state import", {"source": args.source}, "unsupported_source")
    if args.package == ORIGINAL_PACKAGE:
        return Result(False, "state import", {"package": args.package}, "refuse_original_package")

    try:
        backup = backup_target_state(args.serial, args.package, address)
        adb_shell_su(args.serial, f"am force-stop {shlex.quote(args.package)}", timeout=15)
        source_prefs_remote = remote_device_prefs_path(ORIGINAL_PACKAGE, address)
        source_prefs = read_remote_root_file(args.serial, source_prefs_remote, timeout=30)
        auth_summary = prefs_auth_summary(source_prefs)
        if not auth_summary.get("authkey_present"):
            return Result(False, "state import", {"address": address, "auth": auth_summary}, "source_authkey_missing")

        with tempfile.TemporaryDirectory(prefix="miband9ctl-import-") as temp:
            temp_path = Path(temp)
            source_db = pull_sqlite_triplet(args.serial, ORIGINAL_PACKAGE, temp_path / "source")
            target_db = pull_sqlite_triplet(args.serial, args.package, temp_path / "target")
            device_summary = copy_device_row(source_db, target_db, address)
            target_prefs = temp_path / "devicesettings.xml"
            target_prefs.write_bytes(source_prefs)
            db_push = push_app_file(args.serial, args.package, target_db, "databases/Gadgetbridge", mode="660", timeout=args.timeout)
            prefs_push = push_app_file(args.serial, args.package, target_prefs, f"shared_prefs/devicesettings_{address}.xml", mode="660", timeout=args.timeout)
            cleanup = adb_shell_run_as(
                args.serial,
                args.package,
                "rm -f databases/Gadgetbridge-wal databases/Gadgetbridge-shm",
                timeout=15,
            )
        ok = db_push.get("ok") and prefs_push.get("ok") and cleanup.returncode == 0 and backup.get("returncode") == 0
        return Result(
            ok=bool(ok),
            command="state import",
            data={
                "source_package": ORIGINAL_PACKAGE,
                "target_package": args.package,
                "address": address,
                "backup": backup,
                "write_method": "run-as",
                "device": device_summary,
                "auth": auth_summary,
                "db_push": db_push,
                "prefs_push": prefs_push,
                "wal_cleanup_returncode": cleanup.returncode,
            },
            error=None if ok else "state_import_incomplete",
        )
    except Exception as exc:
        return Result(False, "state import", {"address": address, "package": args.package, "error_class": exc.__class__.__name__, "error_message": str(exc)}, "state_import_failed")


def redacted_extras(extras: Optional[dict]) -> dict:
    if not extras:
        return {}
    return {key: ("[REDACTED]" if str(key) in {"xms_did", "did", "device_id", "app_device_id"} else value)
            for key, value in extras.items()}


def parse_bool_token(value: str) -> Optional[bool]:
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    return None


def parse_bluetooth_manager_dump(dump: str) -> dict:
    def first_match(pattern: str) -> Optional[str]:
        match = re.search(pattern, dump, re.MULTILINE)
        return match.group(1).strip() if match else None

    enabled_token = first_match(r"^\s*enabled:\s*(\S+)")
    discovering_token = first_match(r"^\s*Discovering:\s*(\S+)")
    bonded_devices = []
    for match in re.finditer(
        r"^\s+([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})\s+\[\s*([^\]]+?)\s*\]\s+(.+)$",
        dump,
        re.MULTILINE,
    ):
        bonded_devices.append({
            "address": match.group(1).upper(),
            "transport": " ".join(match.group(2).split()),
            "name": match.group(3).strip(),
        })

    return {
        "enabled": parse_bool_token(enabled_token or "") if enabled_token is not None else None,
        "state": first_match(r"^\s*state:\s*(\S+)") or first_match(r"^\s*State:\s*(\S+)"),
        "adapter_name": first_match(r"^\s*Name:\s*(.+)$") or first_match(r"^\s*name:\s*(.+)$"),
        "adapter_address": first_match(r"^\s*Address:\s*([0-9A-Fa-f:]{17})"),
        "discovering": parse_bool_token(discovering_token or "") if discovering_token is not None else None,
        "bonded_devices": bonded_devices,
    }


def parse_package_dump(dump: str) -> dict:
    if not dump.strip() or "Unable to find package" in dump:
        return {"installed": False}

    def first_match(pattern: str) -> Optional[str]:
        match = re.search(pattern, dump, re.MULTILINE)
        return match.group(1).strip() if match else None

    return {
        "installed": "Package [" in dump,
        "version_code": first_match(r"^\s*versionCode=(\S+)"),
        "version_name": first_match(r"^\s*versionName=(.+)$"),
        "first_install_time": first_match(r"^\s*firstInstallTime=(.+)$"),
        "last_update_time": first_match(r"^\s*lastUpdateTime=(.+)$"),
    }


def parse_structured_app_log(log_text: str) -> dict:
    payloads = parse_structured_app_logs(log_text)
    return payloads[0] if payloads else {}


def parse_structured_app_logs(log_text: str) -> list:
    payloads = []
    for line in log_text.splitlines():
        start = line.find("{")
        end = line.rfind("}")
        if start == -1 or end <= start:
            continue
        try:
            payload = json.loads(line[start:end + 1])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def parse_known_devices_log(log_text: str) -> list:
    payload = parse_structured_app_log(log_text)
    try:
        count = int(payload.get("device_count", "0"))
    except (TypeError, ValueError):
        count = 0
    devices = []
    for index in range(count):
        prefix = f"device_{index}_"
        devices.append({
            "address": payload.get(prefix + "address", ""),
            "name": payload.get(prefix + "name", ""),
            "type_name": payload.get(prefix + "type_name", ""),
            "model": payload.get(prefix + "model", ""),
            "credential_present": parse_bool_token(str(payload.get(prefix + "credential_present", ""))),
        })
    return devices


def parse_scan_log(log_text: str) -> list:
    payload = {}
    for candidate in parse_structured_app_logs(log_text):
        if candidate.get("command") == "scan" and candidate.get("message") == "scan_complete":
            payload = candidate
    try:
        count = int(payload.get("device_count", "0"))
    except (TypeError, ValueError):
        count = 0
    devices = []
    for index in range(count):
        prefix = f"device_{index}_"
        devices.append({
            "address": payload.get(prefix + "address", ""),
            "name": payload.get(prefix + "name", ""),
            "bond_state": payload.get(prefix + "bond_state", ""),
        })
    return devices


def parse_pair_log(log_text: str) -> dict:
    payload = {}
    for candidate in parse_structured_app_logs(log_text):
        if candidate.get("command") != "pair":
            continue
        if candidate.get("message") in {"pair_complete", "pair_failed", "pair_timeout", "needs_band_confirm"}:
            payload = candidate
        elif not payload and candidate.get("address"):
            payload = candidate
    return {
        "status": payload.get("status", ""),
        "message": payload.get("message", ""),
        "address": payload.get("address", ""),
        "name": payload.get("name", ""),
        "bond_state": payload.get("bond_state", ""),
        "reset_requested": parse_bool_token(str(payload.get("reset_requested", ""))),
    }


def parse_connect_log(log_text: str) -> dict:
    payload = {}
    for candidate in parse_structured_app_logs(log_text):
        if candidate.get("command") != "connect":
            continue
        if candidate.get("message") in {"initialized", "connect_failed", "connect_timeout"}:
            payload = candidate
        elif candidate.get("message") == "device_state":
            payload = candidate
        elif not payload and candidate.get("address"):
            payload = candidate
    return {
        "status": payload.get("status", ""),
        "message": payload.get("message", ""),
        "address": payload.get("address", ""),
        "name": payload.get("name", ""),
        "device_state": payload.get("device_state", ""),
        "state_ordinal": payload.get("state_ordinal", ""),
        "initialized": parse_bool_token(str(payload.get("initialized", ""))),
        "reason": payload.get("reason", ""),
    }


def parse_int_token(value, default: int = 0) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def parse_float_token(value, default: float = 0.0) -> float:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return default


def parse_csv_tokens(value) -> list[str]:
    return [part.strip() for part in str(value or "").split(",") if part.strip()]


def parse_gamesir_probe_log(log_text: str) -> dict:
    terminal = {}
    candidates = []
    services = []
    writes = []
    notifications = []
    for candidate in parse_structured_app_logs(log_text):
        if candidate.get("command") != "gamesir-probe":
            continue
        message = candidate.get("message")
        if message == "scan_candidate":
            candidates.append({
                "address": candidate.get("address", ""),
                "name": candidate.get("name", ""),
                "rssi": parse_int_token(candidate.get("rssi"), 0),
                "bond_state": candidate.get("bond_state", ""),
                "service_uuids": parse_csv_tokens(candidate.get("service_uuids", "")),
            })
        elif message == "gatt_service":
            services.append({
                "service_uuid": candidate.get("service_uuid", ""),
                "char_uuids": parse_csv_tokens(candidate.get("char_uuids", "")),
            })
        elif message == "write_result":
            writes.append({
                "char_uuid": candidate.get("char_uuid", ""),
                "label": candidate.get("label", ""),
                "hex": candidate.get("hex", ""),
                "gatt_status": parse_int_token(candidate.get("gatt_status"), -1),
            })
        elif message == "notification":
            notifications.append({
                "char_uuid": candidate.get("char_uuid", ""),
                "elapsed_ms": parse_int_token(candidate.get("elapsed_ms"), 0),
                "bytes_read": parse_int_token(candidate.get("bytes_read"), 0),
                "hex": candidate.get("hex", ""),
            })
        elif message in {"probe_complete", "probe_failed"}:
            terminal = candidate
    return {
        "status": terminal.get("status", ""),
        "message": terminal.get("message", ""),
        "target_name": terminal.get("target_name", ""),
        "target_address": terminal.get("target_address", ""),
        "candidate_count": parse_int_token(terminal.get("candidate_count"), len(candidates)),
        "service_count": parse_int_token(terminal.get("service_count"), len(services)),
        "write_count": parse_int_token(terminal.get("write_count"), len(writes)),
        "notification_count": parse_int_token(terminal.get("notification_count"), len(notifications)),
        "duration_ms": parse_int_token(terminal.get("duration_ms"), 0),
        "reason": terminal.get("reason", ""),
        "candidates": candidates,
        "services": services,
        "writes": writes,
        "notifications": notifications,
    }


def parse_sport_xms_probe_log(log_text: str) -> dict:
    terminal = {}
    service_package = ""
    interface_name = ""
    device_info = {}
    packets = []
    for candidate in parse_structured_app_logs(log_text):
        if candidate.get("command") != "sport-xms-probe":
            continue
        message = candidate.get("message")
        if message == "binder_connected":
            service_package = candidate.get("service_package", service_package)
            interface_name = candidate.get("interface", interface_name)
        elif message == "device_info":
            device_info = candidate
        elif message == "sensor_packet":
            packet: dict = {
                "packet_index": parse_int_token(candidate.get("packet_index"), 0),
                "elapsed_ms": parse_int_token(candidate.get("elapsed_ms"), 0),
                "accel_samples": parse_int_token(candidate.get("accel_samples"), 0),
                "gyro_samples": parse_int_token(candidate.get("gyro_samples"), 0),
                "first_accel_timestamp": parse_int_token(candidate.get("first_accel_timestamp"), 0),
                "last_accel_timestamp": parse_int_token(candidate.get("last_accel_timestamp"), 0),
            }
            for field in (
                "accel_x_min", "accel_x_max", "accel_y_min", "accel_y_max", "accel_z_min", "accel_z_max",
                "gyro_x_min", "gyro_x_max", "gyro_y_min", "gyro_y_max", "gyro_z_min", "gyro_z_max",
            ):
                if field in candidate:
                    packet[field] = parse_float_token(candidate.get(field), 0.0)
            packets.append(packet)
        elif message in {"probe_complete", "probe_failed"}:
            terminal = candidate
    return {
        "status": terminal.get("status", ""),
        "message": terminal.get("message", ""),
        "service_package": service_package or terminal.get("service_package", ""),
        "interface": interface_name or terminal.get("interface", ""),
        "device_connected": parse_bool_token(str(device_info.get("device_connected", terminal.get("device_connected", "")))),
        "support_somatosensory": parse_bool_token(str(device_info.get("support_somatosensory", terminal.get("support_somatosensory", "")))),
        "device_name": device_info.get("device_name", terminal.get("device_name", "")),
        "device_model": device_info.get("device_model", terminal.get("device_model", "")),
        "did_present": parse_bool_token(str(device_info.get("did_present", terminal.get("did_present", "")))),
        "did_override_present": parse_bool_token(str(device_info.get("did_override_present", terminal.get("did_override_present", "false")))),
        "started": parse_bool_token(str(terminal.get("started", ""))),
        "capture_ms": parse_int_token(terminal.get("capture_ms"), 0),
        "sport_type": parse_int_token(terminal.get("sport_type"), 0),
        "sensor_packets": parse_int_token(terminal.get("sensor_packets"), len(packets)),
        "accel_samples": parse_int_token(terminal.get("accel_samples"), 0),
        "gyro_samples": parse_int_token(terminal.get("gyro_samples"), 0),
        "reason": terminal.get("reason", ""),
        "packets": packets,
    }


def parse_port_probe_log(log_text: str) -> dict:
    terminal = {}
    results = []
    for candidate in parse_structured_app_logs(log_text):
        if candidate.get("command") != "port-probe":
            continue
        if candidate.get("message") == "port_result":
            results.append({
                "port": parse_int_token(candidate.get("port"), -1),
                "connected": parse_bool_token(str(candidate.get("connected", ""))),
                "reason": candidate.get("reason", ""),
                "connect_ms": parse_int_token(candidate.get("connect_ms"), -1),
                "bytes_written": parse_int_token(candidate.get("bytes_written"), 0),
                "bytes_read": parse_int_token(candidate.get("bytes_read"), 0),
                "response_hex": candidate.get("response_hex", ""),
            })
        if candidate.get("message") in {"probe_complete", "probe_failed"}:
            terminal = candidate
    open_ports_text = str(terminal.get("open_ports", ""))
    open_ports = [parse_int_token(part, -1) for part in open_ports_text.split(",") if part]
    open_ports = [port for port in open_ports if port > 0]
    return {
        "status": terminal.get("status", ""),
        "message": terminal.get("message", ""),
        "address": terminal.get("address", ""),
        "tested_ports": parse_int_token(terminal.get("tested_ports"), 0),
        "open_ports": open_ports,
        "open_port_count": parse_int_token(terminal.get("open_port_count"), len(open_ports)),
        "reason": terminal.get("reason", ""),
        "results": results,
    }


def parse_find_band_log(log_text: str) -> dict:
    terminal = {}
    started = {}
    stopped = {}
    for candidate in parse_structured_app_logs(log_text):
        if candidate.get("command") != "find-band":
            continue
        message = candidate.get("message")
        if message == "find_started":
            started = candidate
        elif message == "find_stopped":
            stopped = candidate
        elif message in {"find_complete", "find_failed", "unknown_command"}:
            terminal = candidate
    source = terminal or stopped or started
    return {
        "status": source.get("status", ""),
        "message": source.get("message", ""),
        "requested_address": source.get("requested_address", ""),
        "address": source.get("address", ""),
        "name": source.get("name", ""),
        "duration_ms": parse_int_token(source.get("duration_ms"), 0),
        "device_state": source.get("device_state", ""),
        "state_ordinal": source.get("state_ordinal", ""),
        "initialized": parse_bool_token(str(source.get("initialized", ""))),
        "reason": source.get("reason", ""),
        "started": bool(started),
        "stopped": bool(stopped),
    }


def parse_imu_capture_log(log_text: str) -> dict:
    terminal = {}
    packets = []
    for candidate in parse_structured_app_logs(log_text):
        if candidate.get("command") != "imu-capture":
            continue
        if candidate.get("message") == "capture_packet":
            packets.append({
                "packet_index": parse_int_token(candidate.get("packet_index"), 0),
                "elapsed_ms": parse_int_token(candidate.get("elapsed_ms"), 0),
                "bytes_read": parse_int_token(candidate.get("bytes_read"), 0),
                "hex": candidate.get("hex", ""),
            })
        if candidate.get("message") in {"capture_complete", "capture_failed"}:
            terminal = candidate
    return {
        "status": terminal.get("status", ""),
        "message": terminal.get("message", ""),
        "address": terminal.get("address", ""),
        "port": parse_int_token(terminal.get("port"), -1),
        "connected": parse_bool_token(str(terminal.get("connected", ""))),
        "reason": terminal.get("reason", ""),
        "connect_ms": parse_int_token(terminal.get("connect_ms"), -1),
        "bytes_written": parse_int_token(terminal.get("bytes_written"), 0),
        "bytes_read": parse_int_token(terminal.get("bytes_read"), 0),
        "packets": parse_int_token(terminal.get("packets"), len(packets)),
        "duration_ms": parse_int_token(terminal.get("duration_ms"), 0),
        "first_hex": terminal.get("first_hex", ""),
        "last_hex": terminal.get("last_hex", ""),
        "packet_logs": packets,
    }


def cmd_phone_info(args) -> Result:
    props = {
        "manufacturer": "ro.product.manufacturer",
        "brand": "ro.product.brand",
        "model": "ro.product.model",
        "product": "ro.product.name",
        "device": "ro.product.device",
        "android_release": "ro.build.version.release",
        "sdk": "ro.build.version.sdk",
    }
    values = {}
    prop_results = {}
    for field, prop in props.items():
        completed = adb.adb_shell(args.serial, "getprop", prop, timeout=10)
        values[field] = completed.stdout.strip()
        prop_results[field] = completed.returncode

    state = adb.run(adb.adb_prefix(args.serial) + ["get-state"], timeout=10)
    root = adb.adb_shell(args.serial, "su", "-c", "id", timeout=10)
    ok = state.returncode == 0 and state.stdout.strip() == "device"
    return Result(
        ok=ok,
        command="phone info",
        data={
            "serial": args.serial,
            "adb_state": state.stdout.strip(),
            "adb_returncode": state.returncode,
            "props": values,
            "prop_returncodes": prop_results,
            "root_available": root.returncode == 0 and "uid=0" in root.stdout,
            "root_id": root.stdout.strip() if root.returncode == 0 else "",
            "root_stderr": root.stderr.strip(),
        },
        error=None if ok else "adb_device_unavailable",
    )


def cmd_bluetooth_state(args) -> Result:
    setting = adb.adb_shell(args.serial, "settings", "get", "global", "bluetooth_on", timeout=10)
    dump = adb.adb_shell(args.serial, "dumpsys", "bluetooth_manager", timeout=15)
    parsed = parse_bluetooth_manager_dump(dump.stdout)
    setting_value = setting.stdout.strip()
    parsed["enabled_from_settings"] = parse_bool_token(setting_value)
    ok = setting.returncode == 0 and dump.returncode == 0
    return Result(
        ok=ok,
        command="bluetooth state",
        data={
            "setting_bluetooth_on": setting_value,
            "setting_returncode": setting.returncode,
            "dumpsys_returncode": dump.returncode,
            "state": parsed,
            "dumpsys_stderr": dump.stderr.strip(),
        },
        error=None if ok else "bluetooth_state_failed",
    )


def cmd_app_state(args) -> Result:
    pm_path = adb.adb_shell(args.serial, "pm", "path", args.package, timeout=10)
    package_dump = adb.adb_shell(args.serial, "dumpsys", "package", args.package, timeout=15)
    parsed = parse_package_dump(package_dump.stdout)
    app_dump_state = cmd_app_command(args, "dump-state") if parsed.get("installed") else None
    ok = pm_path.returncode == 0 and parsed.get("installed") and (app_dump_state is None or app_dump_state.ok)
    return Result(
        ok=bool(ok),
        command="app state",
        data={
            "package": args.package,
            "pm_path_returncode": pm_path.returncode,
            "pm_path_stdout": pm_path.stdout.strip(),
            "pm_path_stderr": pm_path.stderr.strip(),
            "package_dump_returncode": package_dump.returncode,
            "package_state": parsed,
            "headless_dump_state": None if app_dump_state is None else app_dump_state.to_dict(),
        },
        error=None if ok else "app_state_failed",
    )


def cmd_app_known_devices(args) -> Result:
    result = cmd_app_command(args, "known-devices")
    matching_log = result.data.get("matching_app_log", "")
    devices = parse_known_devices_log(matching_log)
    result.data["device_count"] = len(devices)
    result.data["devices"] = devices
    return result


def cmd_band_scan(args) -> Result:
    seconds = max(1, min(int(args.seconds), 30))
    result = cmd_app_command(
        args,
        "scan",
        extras={"seconds": str(seconds), "name": args.name or ""},
        wait_timeout=seconds + 5,
        terminal_messages={"scan_complete", "scan_failed"},
    )
    matching_log = result.data.get("matching_app_log", "")
    devices = parse_scan_log(matching_log)
    result.command = "band scan"
    result.data["seconds"] = seconds
    result.data["name"] = args.name
    result.data["device_count"] = len(devices)
    result.data["devices"] = devices
    return result


def cmd_band_pair(args) -> Result:
    reset_bond = bool(args.reset_bond)
    result = cmd_app_command(
        args,
        "pair",
        extras={"address": args.address.upper(), "reset_bond": "true" if reset_bond else "false"},
        wait_timeout=max(args.timeout, 45),
        terminal_messages={"pair_complete", "pair_failed", "pair_timeout", "needs_band_confirm"},
    )
    pair = parse_pair_log(result.data.get("matching_app_log", ""))
    result.command = "band pair"
    result.data["pair"] = pair
    if result.ok and pair.get("bond_state") != "BONDED":
        result.ok = False
        result.error = pair.get("message") or "pair_not_bonded"
    return result


def cmd_band_connect(args) -> Result:
    result = cmd_app_command(
        args,
        "connect",
        extras={
            "address": args.address.upper(),
            "connect_timeout_seconds": str(max(10, min(args.timeout, 180))),
        },
        wait_timeout=max(args.timeout, 90),
        terminal_messages={"initialized", "connect_failed", "connect_timeout"},
    )
    connect = parse_connect_log(result.data.get("matching_app_log", ""))
    result.command = "band connect"
    result.data["connect"] = connect
    if result.ok and connect.get("message") != "initialized":
        result.ok = False
        result.error = connect.get("message") or "connect_not_initialized"
    return result


def cmd_band_port_probe(args) -> Result:
    result = cmd_app_command(
        args,
        "port-probe",
        extras={
            "address": args.address.upper(),
            "ports": args.ports,
            "hex": args.hex or "",
            "port_connect_timeout_ms": str(args.connect_timeout_ms),
            "port_read_ms": str(args.read_ms),
            "disconnect_first": "true" if args.disconnect_first else "false",
        },
        wait_timeout=max(args.timeout, 30),
        terminal_messages={"probe_complete", "probe_failed"},
    )
    probe = parse_port_probe_log(result.data.get("matching_app_log", ""))
    result.command = "band port-probe"
    result.data["probe"] = probe
    if result.ok and probe.get("message") != "probe_complete":
        result.ok = False
        result.error = probe.get("message") or "probe_not_completed"
    return result


def cmd_band_find_band(args) -> Result:
    duration_ms = max(250, min(int(args.duration_ms), 10000))
    result = cmd_app_command(
        args,
        "find-band",
        extras={
            "address": (args.address or "").upper(),
            "find_duration_ms": str(duration_ms),
        },
        wait_timeout=max(args.timeout, (duration_ms // 1000) + 10),
        terminal_messages={"find_complete", "find_failed", "unknown_command"},
    )
    probe = parse_find_band_log(result.data.get("matching_app_log", ""))
    result.command = "band find-band"
    result.data["probe"] = probe
    if result.ok and probe.get("message") != "find_complete":
        result.ok = False
        result.error = probe.get("message") or "find_band_not_completed"
    return result


def cmd_band_gamesir_probe(args) -> Result:
    seconds = max(1, min(int(args.seconds), 30))
    capture_ms = max(500, min(int(args.capture_ms), 30000))
    result = cmd_app_command(
        args,
        "gamesir-probe",
        extras={
            "seconds": str(seconds),
            "name": args.name or "GameSir,Nova,Wireless",
            "address": (args.address or "").upper(),
            "capture_ms": str(capture_ms),
            "gamesir_handshake": "true" if args.handshake else "false",
            "gamesir_bond": "true" if args.bond else "false",
            "gamesir_historical_010103": "true" if args.historical_010103 else "false",
        },
        wait_timeout=max(args.timeout, seconds + (capture_ms // 1000) + 15),
        terminal_messages={"probe_complete", "probe_failed"},
    )
    probe = parse_gamesir_probe_log(result.data.get("matching_app_log", ""))
    result.command = "band gamesir-probe"
    result.data["probe"] = probe
    if result.ok and probe.get("message") != "probe_complete":
        result.ok = False
        result.error = probe.get("message") or "gamesir_probe_not_completed"
    return result


def cmd_band_sport_xms_probe(args) -> Result:
    capture_ms = max(500, min(int(args.capture_ms), 600000))
    result = cmd_app_command(
        args,
        "sport-xms-probe",
        extras={
            "capture_ms": str(capture_ms),
            "xms_start": "true" if args.start else "false",
            "xms_sport_type": str(args.sport_type),
            "xms_did": args.did or "",
        },
        wait_timeout=max(args.timeout, (capture_ms // 1000) + 20),
        terminal_messages={"probe_complete", "probe_failed"},
    )
    probe = parse_sport_xms_probe_log(result.data.get("matching_app_log", ""))
    result.command = "band sport-xms-probe"
    result.data["probe"] = probe
    if result.ok and probe.get("message") != "probe_complete":
        result.ok = False
        result.error = probe.get("message") or "sport_xms_probe_not_completed"
    return result


def cmd_band_bind(args) -> Result:
    pair = cmd_band_pair(args)
    if not pair.ok:
        return Result(
            ok=False,
            command="band bind",
            data={"pair": pair.to_dict(), "connect": None},
            error=pair.error or "pair_failed",
        )
    connect = cmd_band_connect(args)
    ok = connect.ok and connect.data.get("connect", {}).get("message") == "initialized"
    return Result(
        ok=bool(ok),
        command="band bind",
        data={"pair": pair.to_dict(), "connect": connect.to_dict()},
        error=None if ok else connect.error or "bind_not_initialized",
    )


def app_log_lines_for_nonce(log_text: str, nonce: str) -> str:
    return "\n".join(line for line in log_text.splitlines() if nonce in line)


def app_log_reported_error(matching_log: str) -> bool:
    return "MI_HFIMU_ERROR" in matching_log or '\"status\":\"error\"' in matching_log


def cmd_app_command(args, command: str, *, extras: Optional[dict] = None,
                    wait_timeout: Optional[int] = None, terminal_messages: Optional[set] = None) -> Result:
    request_id = uuid.uuid4().hex[:12]
    nonce = uuid.uuid4().hex
    adb.clear_logcat(args.serial)
    sent = adb.broadcast_hfimu(
        serial=args.serial,
        package=args.package,
        command=command,
        request_id=request_id,
        nonce=nonce,
        extras=extras,
        timeout=args.timeout,
    )
    if terminal_messages:
        deadline = time.time() + float(wait_timeout or args.timeout)
        logs = adb.Completed([], 1, "", "timeout")
        while time.time() < deadline:
            logs = adb.dump_hfimu_logcat(args.serial)
            matching = app_log_lines_for_nonce(logs.stdout, nonce)
            payloads = parse_structured_app_logs(matching)
            if any(payload.get("message") in terminal_messages for payload in payloads):
                break
            time.sleep(0.25)
    else:
        logs = adb.wait_for_nonce(args.serial, nonce, timeout=min(args.timeout, 10))
    matching_log = app_log_lines_for_nonce(logs.stdout, nonce)
    found = bool(matching_log) or nonce in logs.stderr
    if terminal_messages:
        terminal_payload = {}
        for payload in parse_structured_app_logs(matching_log):
            if payload.get("message") in terminal_messages:
                terminal_payload = payload
        app_reported_error = terminal_payload.get("status") == "error"
    else:
        app_reported_error = app_log_reported_error(matching_log)
    ok = sent.returncode == 0 and found and not app_reported_error
    return Result(
        ok=ok,
        command=f"app {command}",
        data={
            "package": args.package,
            "request_id": request_id,
            "nonce": nonce,
            "broadcast_returncode": sent.returncode,
            "broadcast_stdout": sent.stdout.strip(),
            "broadcast_stderr": sent.stderr.strip(),
            "extras": redacted_extras(extras),
            "app_log_found": found,
            "app_reported_error": app_reported_error,
            "matching_app_log": matching_log,
            "app_log": logs.stdout.strip(),
        },
        error=None if ok else "app_result_error" if app_reported_error else "app_result_not_observed",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="miband9ctl")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument("--serial")
    parser.add_argument("--package", default=adb.DEFAULT_PACKAGE)
    parser.add_argument("--repo-root")
    parser.add_argument("--apk", default=DEFAULT_APK)
    parser.add_argument("--timeout", type=int, default=30)

    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor")
    sub.add_parser("build")
    sub.add_parser("install")
    sub.add_parser("setup")

    state = sub.add_parser("state")
    state_sub = state.add_subparsers(dest="state_cmd", required=True)
    state_import = state_sub.add_parser("import")
    state_import.add_argument("--source", default="original-gadgetbridge", choices=["original-gadgetbridge"])
    state_import.add_argument("--address", required=True)

    phone = sub.add_parser("phone")
    phone_sub = phone.add_subparsers(dest="phone_cmd", required=True)
    phone_sub.add_parser("info")

    bluetooth = sub.add_parser("bluetooth")
    bluetooth_sub = bluetooth.add_subparsers(dest="bluetooth_cmd", required=True)
    bluetooth_sub.add_parser("state")

    band = sub.add_parser("band")
    band_sub = band.add_subparsers(dest="band_cmd", required=True)
    band_scan = band_sub.add_parser("scan")
    band_scan.add_argument("--seconds", type=int, default=10)
    band_scan.add_argument("--name", default="Xiaomi")
    band_pair = band_sub.add_parser("pair")
    band_pair.add_argument("--address", required=True)
    band_pair.add_argument("--reset-bond", dest="reset_bond", action="store_true", default=False)
    band_connect = band_sub.add_parser("connect")
    band_connect.add_argument("--address", required=True)
    band_port_probe = band_sub.add_parser("port-probe")
    band_port_probe.add_argument("--address", required=True)
    band_port_probe.add_argument("--ports", default="1-30")
    band_port_probe.add_argument("--hex", default="")
    band_port_probe.add_argument("--connect-timeout-ms", type=int, default=3000)
    band_port_probe.add_argument("--read-ms", type=int, default=750)
    band_port_probe.add_argument("--disconnect-first", dest="disconnect_first", action="store_true", default=False)
    band_find_band = band_sub.add_parser("find-band")
    band_find_band.add_argument("--address", default="")
    band_find_band.add_argument("--duration-ms", type=int, default=3000)
    band_gamesir_probe = band_sub.add_parser("gamesir-probe")
    band_gamesir_probe.add_argument("--seconds", type=int, default=15)
    band_gamesir_probe.add_argument("--name", default="GameSir,Nova,Wireless")
    band_gamesir_probe.add_argument("--address", default="")
    band_gamesir_probe.add_argument("--capture-ms", type=int, default=5000)
    band_gamesir_probe.add_argument("--handshake", action="store_true", default=False)
    band_gamesir_probe.add_argument("--bond", action="store_true", default=False)
    band_gamesir_probe.add_argument("--historical-010103", dest="historical_010103", action="store_true", default=False)
    band_sport_xms_probe = band_sub.add_parser("sport-xms-probe")
    band_sport_xms_probe.add_argument("--capture-ms", type=int, default=5000)
    band_sport_xms_probe.add_argument("--start", action="store_true", default=False)
    band_sport_xms_probe.add_argument("--sport-type", type=int, default=812)
    band_sport_xms_probe.add_argument("--did", default="", help="Optional Mi Fitness device id override; never printed in summaries")
    band_bind = band_sub.add_parser("bind")
    band_bind.add_argument("--address", required=True)
    band_bind.add_argument("--reset-bond", dest="reset_bond", action="store_true", default=False)

    app = sub.add_parser("app")
    app_sub = app.add_subparsers(dest="app_cmd", required=True)
    app_sub.add_parser("ping")
    app_sub.add_parser("enable-debug")
    app_sub.add_parser("dump-state")
    app_sub.add_parser("state")
    app_sub.add_parser("known-devices")
    app_sub.add_parser("enable-bluetooth")
    app_sub.add_parser("start-service")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(normalize_global_args(argv))
    if args.cmd == "doctor":
        result = cmd_doctor(args)
    elif args.cmd == "build":
        result = cmd_build(args)
    elif args.cmd == "install":
        result = cmd_install(args)
    elif args.cmd == "setup":
        result = cmd_setup(args)
    elif args.cmd == "state" and args.state_cmd == "import":
        result = cmd_state_import(args)
    elif args.cmd == "phone" and args.phone_cmd == "info":
        result = cmd_phone_info(args)
    elif args.cmd == "bluetooth" and args.bluetooth_cmd == "state":
        result = cmd_bluetooth_state(args)
    elif args.cmd == "band" and args.band_cmd == "scan":
        result = cmd_band_scan(args)
    elif args.cmd == "band" and args.band_cmd == "pair":
        result = cmd_band_pair(args)
    elif args.cmd == "band" and args.band_cmd == "connect":
        result = cmd_band_connect(args)
    elif args.cmd == "band" and args.band_cmd == "port-probe":
        result = cmd_band_port_probe(args)
    elif args.cmd == "band" and args.band_cmd == "find-band":
        result = cmd_band_find_band(args)
    elif args.cmd == "band" and args.band_cmd == "gamesir-probe":
        result = cmd_band_gamesir_probe(args)
    elif args.cmd == "band" and args.band_cmd == "sport-xms-probe":
        result = cmd_band_sport_xms_probe(args)
    elif args.cmd == "band" and args.band_cmd == "bind":
        result = cmd_band_bind(args)
    elif args.cmd == "app" and args.app_cmd == "state":
        result = cmd_app_state(args)
    elif args.cmd == "app" and args.app_cmd == "known-devices":
        result = cmd_app_known_devices(args)
    elif args.cmd == "app":
        result = cmd_app_command(args, args.app_cmd)
    else:
        result = Result(False, args.cmd, {}, "unknown_command")
    return emit(result, json_mode=args.json, pretty=args.pretty)


if __name__ == "__main__":
    raise SystemExit(main())
