#!/usr/bin/env python3
"""Build Mi Band 9 macOS direct auth step 3 from local live WatchNonce events.

Input/output may contain live auth material. Keep artifacts local; stdout is intended for
`ble_sar_auth_probe.swift`, not chat. The `redacted` block is safe to summarize.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import pathlib
import re
import struct
import time
import sys
import tarfile
import xml.etree.ElementTree as ET

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESCCM
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"cryptography AESCCM unavailable: {exc.__class__.__name__}")

REPO_TOOL = pathlib.Path(__file__).resolve().parents[1] / "miband9ctl"
if str(REPO_TOOL) not in sys.path:
    sys.path.insert(0, str(REPO_TOOL))

from miband9ctl import mac_direct_protocol as mdp  # noqa: E402
from factory_command_skeleton import build_factory_dump  # noqa: E402
from sportxms_812_packet_skeleton import build_packet as build_sportxms_packet  # noqa: E402
from miband9ctl.mac_direct_protocol import (  # noqa: E402
    Channel,
    Opcode,
    PacketType,
    SppV2StreamParser,
    build_data_frame_from_encrypted_payload,
    build_l2_payload,
    derive_session_material,
    encode_frame,
    encrypt_v2,
    parse_frame,
    parse_watch_nonce_command,
)


def proto_fixed32(field_number: int, raw4: bytes) -> bytes:
    return mdp._proto_key(field_number, 5) + raw4


def proto_float(field_number: int, value: float) -> bytes:
    return proto_fixed32(field_number, struct.pack("<f", float(value)))


def proto_string(field_number: int, value: str) -> bytes:
    return mdp._proto_bytes(field_number, value.encode("utf-8"))


def auth_device_info(phone_api_level: float = 35.0, phone_name: str = "Mac", region: str = "ZH") -> bytes:
    # Mirrors XiaomiAuthService.AuthDeviceInfo: unknown1=0 is required and must be serialized.
    return b"".join(
        [
            mdp._proto_varint(1, 0),
            proto_float(2, phone_api_level),
            proto_string(3, phone_name),
            mdp._proto_varint(4, 224),
            proto_string(5, region[:2].upper()),
        ]
    )


def load_phone_nonce(payloads_path: pathlib.Path) -> bytes:
    auth_hex = None
    for line in payloads_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(maxsplit=1)
        if parts[0] == "auth_step1_phone_nonce" and len(parts) == 2:
            auth_hex = parts[1]
            break
    if not auth_hex:
        raise ValueError("auth_step1_phone_nonce payload missing")
    frame = parse_frame(bytes.fromhex(auth_hex))
    command = frame.payload[2:]
    fields = mdp._field_map(command)
    auth = mdp._field_map(mdp._expect_bytes(fields, 3))
    phone = mdp._field_map(mdp._expect_bytes(auth, 30))
    phone_nonce = mdp._expect_bytes(phone, 1)
    if len(phone_nonce) != 16:
        raise ValueError("phone nonce length mismatch")
    return phone_nonce


def load_authkey(tar_path: pathlib.Path) -> tuple[str, str]:
    with tarfile.open(tar_path, "r:gz") as tf:
        for member in tf.getmembers():
            name = member.name.lower()
            if "devicesettings" not in name or not name.endswith(".xml"):
                continue
            fh = tf.extractfile(member)
            if not fh:
                continue
            text = fh.read().decode("utf-8", errors="replace")
            if "authkey" not in text:
                continue
            try:
                root = ET.fromstring(text)
            except ET.ParseError:
                continue
            for elem in root.iter():
                if elem.attrib.get("name") == "authkey":
                    value = (elem.attrib.get("value") or elem.text or "").strip()
                    if value.startswith("0x"):
                        value = value[2:]
                    if re.fullmatch(r"[0-9a-fA-F]{32}", value):
                        return value, member.name
    raise ValueError("authkey not found")


def find_watch_nonce(state_json_path: pathlib.Path) -> tuple[int, int, dict[str, object], int]:
    data = json.loads(state_json_path.read_text())
    parser = SppV2StreamParser()
    parsed_frames = 0
    for event in data.get("events") or []:
        chunk = bytes.fromhex(event.get("hex", ""))
        for frame in parser.feed(chunk):
            parsed_frames += 1
            if int(frame.packet_type) != int(PacketType.DATA) or len(frame.payload) < 3:
                continue
            channel, opcode = frame.payload[0], frame.payload[1]
            if channel != int(Channel.PROTOBUF_COMMAND):
                continue
            try:
                watch = parse_watch_nonce_command(frame.payload[2:])
            except Exception:
                continue
            return frame.sequence, opcode, watch, parsed_frames
    raise ValueError("watch nonce not found yet")


def build_auth_step3_command(*, material: mdp.SessionMaterial, phone_nonce: bytes, watch_nonce: bytes) -> bytes:
    encrypted_nonces = hmac.new(material.encryption_key, phone_nonce + watch_nonce, hashlib.sha256).digest()
    device_info = auth_device_info()
    nonce = material.encryption_nonce + (0).to_bytes(4, "little") + (0).to_bytes(4, "little")
    encrypted_device_info = AESCCM(material.encryption_key, tag_length=4).encrypt(nonce, device_info, None)
    auth_step3 = mdp._proto_bytes(1, encrypted_nonces) + mdp._proto_bytes(2, encrypted_device_info)
    auth = mdp._proto_bytes(32, auth_step3)
    return mdp._proto_varint(1, 1) + mdp._proto_varint(2, 27) + mdp._proto_bytes(3, auth)


def build_device_info_get_command() -> bytes:
    """Build low-risk Xiaomi System/device-info get command: type=2, subtype=2."""

    return mdp._proto_varint(1, 2) + mdp._proto_varint(2, 2)


def build_encrypted_device_info_get_frame(*, material: mdp.SessionMaterial, seq: int) -> bytes:
    plaintext = build_device_info_get_command()
    encrypted = encrypt_v2(material.encryption_key, plaintext)
    return build_data_frame_from_encrypted_payload(seq=seq, channel=Channel.PROTOBUF_COMMAND, encrypted_payload=encrypted)


def build_sportxms_hns_command(
    *,
    sport_state: int,
    timestamp_sec: int | None = None,
    timezone_value: int = 32,
    sport_type: int = 812,
    select_version: int | None = 3,
    accessory_wear_mode: int | None = None,
    sport_target_type: int | None = None,
    sport_target_value: int | None = None,
    sport_launch_type: int | None = None,
) -> bytes:
    packet = build_sportxms_packet(
        timestamp_sec=int(timestamp_sec if timestamp_sec is not None else time.time()),
        timezone_value=timezone_value,
        sport_type=sport_type,
        sport_state=sport_state,
        select_version=select_version,
        accessory_wear_mode=accessory_wear_mode,
        sport_target_type=sport_target_type,
        sport_target_value=sport_target_value,
        sport_launch_type=sport_launch_type,
    )
    hns_hex = str(packet["hns_hex"])
    return bytes.fromhex(hns_hex)


def build_encrypted_protobuf_frame(*, material: mdp.SessionMaterial, seq: int, plaintext: bytes) -> bytes:
    encrypted = encrypt_v2(material.encryption_key, plaintext)
    return build_data_frame_from_encrypted_payload(seq=seq, channel=Channel.PROTOBUF_COMMAND, encrypted_payload=encrypted)


def build_post_auth_frames(
    *,
    material: mdp.SessionMaterial,
    first_seq: int,
    actions: list[str],
    timestamp_sec: int | None = None,
    sport_type: int = 812,
    sportxms_select_version: int | None = 3,
    sportxms_accessory_wear_mode: int | None = None,
    timezone_value: int = 32,
    sportxms_target_type: int | None = None,
    sportxms_target_value: int | None = None,
    sportxms_launch_type: int | None = None,
) -> list[dict[str, object]]:
    frames: list[dict[str, object]] = []
    seq = first_seq
    variant = {
        "sport_type": sport_type,
        "select_version": sportxms_select_version,
        "accessory_wear_mode": sportxms_accessory_wear_mode,
        "timezone_value": timezone_value,
        "sport_target_type": sportxms_target_type,
        "sport_target_value": sportxms_target_value,
        "sport_launch_type": sportxms_launch_type,
    }
    for action in actions:
        if action == "device_info_get":
            plaintext = build_device_info_get_command()
            label = "encrypted_device_info_get"
        elif action == "factory_dump":
            plaintext = build_factory_dump()
            label = "encrypted_factory_dump"
        elif action == "sportxms_start":
            plaintext = build_sportxms_hns_command(
                sport_state=1,
                timestamp_sec=timestamp_sec,
                timezone_value=timezone_value,
                sport_type=sport_type,
                select_version=sportxms_select_version,
                accessory_wear_mode=sportxms_accessory_wear_mode,
                sport_target_type=sportxms_target_type,
                sport_target_value=sportxms_target_value,
                sport_launch_type=sportxms_launch_type,
            )
            label = "encrypted_sportxms_start"
        elif action == "sportxms_stop":
            plaintext = build_sportxms_hns_command(
                sport_state=4,
                timestamp_sec=timestamp_sec,
                timezone_value=timezone_value,
                sport_type=sport_type,
                select_version=sportxms_select_version,
                accessory_wear_mode=sportxms_accessory_wear_mode,
                sport_target_type=sportxms_target_type,
                sport_target_value=sportxms_target_value,
                sport_launch_type=sportxms_launch_type,
            )
            label = "encrypted_sportxms_stop"
        else:
            raise ValueError(f"unknown post-auth action: {action}")
        frame = build_encrypted_protobuf_frame(material=material, seq=seq, plaintext=plaintext)
        frames.append(
            {
                "label": label,
                "action": action,
                "seq": seq,
                "frame_hex": frame.hex(),
                "frame_len": len(frame),
                "frame_sha256_16": hashlib.sha256(frame).hexdigest()[:16],
                "plaintext_len": len(plaintext),
                "plaintext_sha256_16": hashlib.sha256(plaintext).hexdigest()[:16],
                "sportxms_variant": variant,
            }
        )
        seq += 1
    return frames


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--state-json", required=True, type=pathlib.Path)
    p.add_argument("--payloads", required=True, type=pathlib.Path)
    p.add_argument("--auth-tar", required=True, type=pathlib.Path)
    p.add_argument("--data-seq", type=int, default=1)
    p.add_argument(
        "--post-auth-action",
        action="append",
        choices=["device_info_get", "factory_dump", "sportxms_start", "sportxms_stop"],
        default=None,
        help="Build post-auth encrypted frames after auth step 3. May be repeated. Default: device_info_get.",
    )
    p.add_argument("--timestamp-sec", type=int, default=None, help="Timestamp for SportXms hns start/stop frames")
    p.add_argument("--sportxms-sport-type", type=int, default=812)
    p.add_argument("--sportxms-select-version", default="3", help="SportXms hfa field 6/selectVersion. Use 'omit' to leave it out.")
    p.add_argument("--sportxms-accessory-wear-mode", type=int, default=None, help="SportXms hfa field 10/accessoryWearMode, 0..3")
    p.add_argument("--sportxms-timezone-value", type=int, default=32)
    p.add_argument("--sportxms-target-type", type=int, default=None, help="Optional hfa field 7 nfa.type, from SportTargetType 1..7")
    p.add_argument("--sportxms-target-value", type=int, default=None, help="Optional hfa field 7 nfa.value")
    p.add_argument("--sportxms-launch-type", type=int, default=None, help="Optional hfa field 9 launch type; not normally populated by vga.v")
    args = p.parse_args(argv)

    try:
        phone_nonce = load_phone_nonce(args.payloads)
        watch_seq, watch_opcode, watch, parsed_frame_count = find_watch_nonce(args.state_json)
        authkey, member = load_authkey(args.auth_tar)
        secret = bytes.fromhex(authkey)
        watch_nonce = watch["watch_nonce"]
        watch_hmac = watch["watch_hmac"]
        material = derive_session_material(secret_key=secret, phone_nonce=phone_nonce, watch_nonce=watch_nonce)
        expected = hmac.new(material.decryption_key, watch_nonce + phone_nonce, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, watch_hmac):
            raise ValueError("watch hmac mismatch")
        ack_frame = encode_frame(PacketType.ACK, watch_seq, b"")
        command = build_auth_step3_command(material=material, phone_nonce=phone_nonce, watch_nonce=watch_nonce)
        auth_frame = encode_frame(
            PacketType.DATA,
            args.data_seq,
            build_l2_payload(Channel.PROTOBUF_COMMAND, Opcode.SEND_PLAINTEXT, command),
        )
        actions = args.post_auth_action or ["device_info_get"]
        select_version = None if str(args.sportxms_select_version).lower() in {"omit", "none", "null"} else int(args.sportxms_select_version)
        post_auth_frames = build_post_auth_frames(
            material=material,
            first_seq=args.data_seq + 1,
            actions=actions,
            timestamp_sec=args.timestamp_sec,
            sport_type=args.sportxms_sport_type,
            sportxms_select_version=select_version,
            sportxms_accessory_wear_mode=args.sportxms_accessory_wear_mode,
            timezone_value=args.sportxms_timezone_value,
            sportxms_target_type=args.sportxms_target_type,
            sportxms_target_value=args.sportxms_target_value,
            sportxms_launch_type=args.sportxms_launch_type,
        )
        response = {
            "ok": True,
            "ack_frame_hex": ack_frame.hex(),
            "auth_step3_frame_hex": auth_frame.hex(),
            "encrypted_device_info_get_frame_hex": next((str(f["frame_hex"]) for f in post_auth_frames if f["action"] == "device_info_get"), ""),
            "post_auth_frames": post_auth_frames,
            "redacted": {
                "watch_frame_sequence": watch_seq,
                "watch_frame_opcode": watch_opcode,
                "watch_command_type": int(watch["type"]),
                "watch_command_subtype": int(watch["subtype"]),
                "parsed_frame_count": parsed_frame_count,
                "phone_nonce_sha256_16": hashlib.sha256(phone_nonce).hexdigest()[:16],
                "watch_nonce_sha256_16": hashlib.sha256(watch_nonce).hexdigest()[:16],
                "watch_hmac_verified": True,
                "authkey_sha256_16": hashlib.sha256(authkey.encode()).hexdigest()[:16],
                "authkey_source_member": member,
                "session_material_sha256_16": hashlib.sha256(material.step2_hmac).hexdigest()[:16],
                "auth_step3_frame_len": len(auth_frame),
                "auth_step3_frame_sha256_16": hashlib.sha256(auth_frame).hexdigest()[:16],
                "post_auth_actions": actions,
                "sportxms_variant": {
                    "sport_type": args.sportxms_sport_type,
                    "select_version": select_version,
                    "accessory_wear_mode": args.sportxms_accessory_wear_mode,
                    "timezone_value": args.sportxms_timezone_value,
                    "sport_target_type": args.sportxms_target_type,
                    "sport_target_value": args.sportxms_target_value,
                    "sport_launch_type": args.sportxms_launch_type,
                },
                "post_auth_frame_count": len(post_auth_frames),
                "post_auth_frame_summaries": [
                    {
                        "label": item["label"],
                        "action": item["action"],
                        "seq": item["seq"],
                        "frame_len": item["frame_len"],
                        "frame_sha256_16": item["frame_sha256_16"],
                        "plaintext_len": item["plaintext_len"],
                        "plaintext_sha256_16": item["plaintext_sha256_16"],
                    }
                    for item in post_auth_frames
                ],
            },
        }
    except Exception as exc:
        response = {"ok": False, "error": str(exc), "error_type": exc.__class__.__name__}
    print(json.dumps(response, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
