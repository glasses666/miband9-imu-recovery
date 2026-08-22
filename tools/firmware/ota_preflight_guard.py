#!/usr/bin/env python3
"""Fail-closed Mi Band 9 OTA preflight helper.

This tool is intentionally local/static. It does not connect to a band, launch an
Android app, send firmware metadata, transfer chunks, validate, upgrade, or enter
recovery/factory mode.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

LOCAL_SAFE_ACTIONS = {
    "read_local_zip",
    "classify_file",
    "host_admission_check",
    "map_app_session_states",
    "map_mi_fitness_status_path",
    "map_notify_owner_session",
}

LIVE_NO_BODY_ACTIONS = {
    "live_dfu_status_query",
}

DANGEROUS_ACTIONS = {
    "prepare_transfer",
    "start_transfer",
    "firmware_body",
    "chunk_transfer",
    "validate",
    "upgrade",
    "recovery",
    "factory_mode",
    "app_launch",
    "band_connect_for_ota",
    "notify_firmware_selection",
    "notify_install_broadcast",
    "mi_fitness_prepare_ota",
    "mi_fitness_start_ota",
    "dfu_prepare_transfer",
    "dfu_start_transfer",
    "dfu_validate",
    "dfu_upgrade",
}

GATE_MAP = [
    {
        "gate": "host_file_admission",
        "status": "local_safe",
        "description": "Open ZIP locally; check ota.json / ota.sh and visible md5 fields.",
        "forbidden": [],
    },
    {
        "gate": "dfu_status_query",
        "status": "live_no_body_requires_explicit_authorization",
        "description": "Only query device DFU/update status; no firmware metadata/body.",
        "forbidden": ["prepare_transfer", "start_transfer", "firmware_body", "validate", "upgrade"],
    },
    {
        "gate": "prepare_transfer",
        "status": "blocked_by_default",
        "description": "prepareTransfer(type,totalSize,crc32,maxChunkSize,mode) can move the device into update negotiation.",
        "forbidden": ["prepare_transfer"],
    },
    {
        "gate": "body_transfer",
        "status": "blocked_by_default",
        "description": "startTransfer and chunks are firmware body transfer.",
        "forbidden": ["start_transfer", "firmware_body", "chunk_transfer"],
    },
    {
        "gate": "validate_upgrade_recovery",
        "status": "blocked_by_default",
        "description": "validate / upgrade / recovery are post-body or boot-risk operations.",
        "forbidden": ["validate", "upgrade", "recovery", "factory_mode"],
    },
]

SOURCE_GATE_MAP = [
    {
        "source": "mi_fitness",
        "gate": "app_owned_connected_status_only",
        "status": "no_body_status_query",
        "proof_point": "DeviceSender.getOtaStatus sends hns.e=2/f=90 with no firmware path, md5, size, ZIP body, or OTA executor.",
        "current_result": "Connected Mi Fitness Band 9 NFC session returned HNS field100 code=1, named not-support by SyncResult; disconnected runs returned -6.",
        "safe_next": "Only split passive/raw observation or guarded f90 retry after app-owned connected state is visible; keep prepare/start blockers armed.",
        "danger_boundary": "DeviceSender.prepareOta hns.e=2/f=5 or BluetoothOtaManager.startUpgrade/startOta.",
        "blocked_actions": ["mi_fitness_prepare_ota", "mi_fitness_start_ota", "firmware_body", "validate", "upgrade"],
    },
    {
        "source": "dfu_v5_gatt",
        "gate": "dfu_status_d1_only_if_1530_visible",
        "status": "live_no_body_requires_explicit_authorization",
        "proof_point": "Only write 0xD1 after DFU V5 service 1530 and CPT 1531 are discovered and CPT notify/indicate is enabled.",
        "current_result": "State-1 Android GATT saw normal FE95 but not DFU V5 1530; Notify owner-session secondary GATT was not observable.",
        "safe_next": "Do not scan harder as a substitute; first map the app-owned transition that plausibly exposes 1530, then rerun the D1-only probe.",
        "danger_boundary": "DFU D2 prepareTransfer, D3 startTransfer, D5 validate, D6 upgrade.",
        "blocked_actions": ["dfu_prepare_transfer", "dfu_start_transfer", "dfu_validate", "dfu_upgrade"],
    },
    {
        "source": "notify_nfx",
        "gate": "main_connected_owner_session",
        "status": "safe_next_gate_before_firmware_selection",
        "proof_point": "Notify/NFX MainActivity -> StartupActivity -> BaseService.P1 reaches MainAppActivity; connected broadcasts set MainAppActivity.P=true and hide repair UI.",
        "current_result": "Prior UI evidence reached the Notify/NFX device page for Band 9 NFC, but a second debug GATT client could not observe services while Notify owned the connection.",
        "safe_next": "Map or passively observe owner-session predicates: connected broadcast, BaseService device object, connectedFully/W0 state, visible main/device page. Do not open firmware picker.",
        "danger_boundary": "Opening firmware selection is still host-admission territory; tapping install crosses into the install broadcast/service path.",
        "blocked_actions": ["notify_firmware_selection", "notify_install_broadcast"],
    },
    {
        "source": "notify_nfx",
        "gate": "pairing_key_auth_acquisition",
        "status": "safe_to_map_static_only",
        "proof_point": "AuthKeyActivity/je.b offers Mi Fitness local procedure, asks for the migrated wearablelog folder, extracts a key for the selected MAC, then saves it into app preferences/profile state.",
        "current_result": "This explains why community NFX/Notify OTA guides require Mi Fitness log migration before NFX can own the session.",
        "safe_next": "Document predicates and keep raw auth material redacted; do not print keys, DID, sessions, or log contents.",
        "danger_boundary": "Using the acquired session to enter firmware install/preflight is separate and blocked here.",
        "blocked_actions": ["notify_install_broadcast", "firmware_body", "validate", "upgrade"],
    },
    {
        "source": "notify_nfx",
        "gate": "firmware5_zip_host_admission",
        "status": "host_parser_only",
        "proof_point": "UpdateFirmwareActivity copies the selected URI to cache/firmware; i6.l marks FIRMWARE5_ZIP when the ZIP has ota.sh or ota.json and can surface sw_version.",
        "current_result": "UI labels such as valid firmware/new version/install prove host parser success only.",
        "safe_next": "Use only local classifier/admission documentation; do not select or install a patched ZIP in a connected updater during this slice.",
        "danger_boundary": "buttonStartUpdate sends broadcast 302ff3b3-953f-4a3c-8c3e-b8451f20fe53 with firmwareFile/forceValidFirmware/firmwareType; BaseService then calls J.F(uri, force).",
        "blocked_actions": ["notify_install_broadcast", "prepare_transfer", "firmware_body", "chunk_transfer", "validate", "upgrade"],
    },
]


class PreflightBlocked(RuntimeError):
    """Raised when a requested OTA action crosses the current safety boundary."""


def _walk_json(obj: Any, path: str = "$") -> Iterable[tuple[str, Any]]:
    yield path, obj
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield from _walk_json(value, f"{path}.{key}")
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            yield from _walk_json(value, f"{path}[{index}]")


def _read_ota_json(zf: zipfile.ZipFile) -> dict[str, Any] | None:
    if "ota.json" not in zf.namelist():
        return None
    raw = zf.read("ota.json")
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {"_parse_error": True, "_raw_sha256": hashlib.sha256(raw).hexdigest()}


def _md5_file(path: Path) -> str:
    h = hashlib.md5()  # noqa: S324 - visible OTA metadata uses md5; not for security here.
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def classify_ota_zip(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(str(p))
    result: dict[str, Any] = {
        "path": str(p),
        "size": p.stat().st_size,
        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        "zip": False,
        "entries": [],
        "has_ota_json": False,
        "has_ota_sh": False,
        "firmware5_zip_like": False,
        "sw_version": None,
        "visible_md5_mentions": [],
        "local_only": True,
        "live_actions_performed": [],
    }
    with zipfile.ZipFile(p) as zf:
        entries = zf.namelist()
        result["zip"] = True
        result["entries"] = entries
        result["has_ota_json"] = "ota.json" in entries
        result["has_ota_sh"] = "ota.sh" in entries
        result["firmware5_zip_like"] = bool(result["has_ota_json"] or result["has_ota_sh"])
        ota_json = _read_ota_json(zf)
        if isinstance(ota_json, dict):
            result["sw_version"] = ota_json.get("sw_version")
            md5_mentions = []
            for jpath, value in _walk_json(ota_json):
                if "md5" in jpath.lower() or (isinstance(value, str) and len(value) == 32 and all(c in "0123456789abcdefABCDEF" for c in value)):
                    md5_mentions.append({"json_path": jpath, "value": value})
            result["visible_md5_mentions"] = md5_mentions
    return result


def enforce_actions(actions: Iterable[str], *, allow_live_status: bool = False) -> dict[str, Any]:
    requested = list(actions)
    unknown = sorted(set(requested) - LOCAL_SAFE_ACTIONS - LIVE_NO_BODY_ACTIONS - DANGEROUS_ACTIONS)
    if unknown:
        raise PreflightBlocked(f"Unknown OTA action(s): {', '.join(unknown)}")
    dangerous = sorted(set(requested) & DANGEROUS_ACTIONS)
    if dangerous:
        raise PreflightBlocked(
            "Blocked by OTA safety gate: "
            + ", ".join(dangerous)
            + ". Current authorization allows local/static checks only; live status query requires a separate explicit authorization and body/validate/upgrade remain forbidden."
        )
    live = sorted(set(requested) & LIVE_NO_BODY_ACTIONS)
    if live and not allow_live_status:
        raise PreflightBlocked(
            "Blocked live no-body DFU/status query: requires explicit Queen Glasser authorization before connecting near the OTA path."
        )
    return {
        "allowed": True,
        "actions": requested,
        "local_safe": sorted(set(requested) & LOCAL_SAFE_ACTIONS),
        "live_no_body": live,
        "dangerous": [],
    }


def build_summary(zip_path: str | None, actions: Iterable[str], allow_live_status: bool) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "tool": "ota_preflight_guard",
        "local_static_only": True,
        "never_performs": sorted(DANGEROUS_ACTIONS),
        "gate_map": GATE_MAP,
        "source_gate_map": SOURCE_GATE_MAP,
    }
    if zip_path:
        summary["zip_classification"] = classify_ota_zip(zip_path)
    summary["action_gate"] = enforce_actions(actions, allow_live_status=allow_live_status)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail-closed local/static OTA preflight guard for Mi Band 9.")
    parser.add_argument("--zip", dest="zip_path", help="Local OTA ZIP to classify. No file is sent anywhere.")
    parser.add_argument(
        "--action",
        action="append",
        default=["read_local_zip", "classify_file"],
        help="Requested gate action. Dangerous actions are blocked by default.",
    )
    parser.add_argument("--allow-live-status", action="store_true", help="Allow only the named live no-body status query gate in the policy output. This tool still does not connect.")
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    args = parser.parse_args(argv)
    try:
        summary = build_summary(args.zip_path, args.action, args.allow_live_status)
    except PreflightBlocked as exc:
        blocked = {
            "allowed": False,
            "error": str(exc),
            "requested_actions": args.action,
            "gate_map": GATE_MAP,
            "source_gate_map": SOURCE_GATE_MAP,
        }
        print(json.dumps(blocked, ensure_ascii=False, indent=2))
        return 2
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print("OTA preflight guard: allowed")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
