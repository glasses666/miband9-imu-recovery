#!/usr/bin/env python3
"""Summarize Mi Band 9 macOS direct encrypted-traffic sanity results.

Inputs may reference local auth artifacts. Output is redacted: it reports frame sizes,
packet/channel/opcode metadata, and decrypted protobuf type/subtype only. It never emits
raw auth keys, nonces, session material, ciphertext, plaintext, or full payload hex.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import pathlib
import sys

REPO_TOOL = pathlib.Path(__file__).resolve().parents[1] / "miband9ctl"
if str(REPO_TOOL) not in sys.path:
    sys.path.insert(0, str(REPO_TOOL))

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from miband9ctl.mac_direct_protocol import (  # noqa: E402
    Channel,
    PacketType,
    SppV2StreamParser,
    decrypt_v2,
    derive_session_material,
)
from build_auth_step3_from_events import find_watch_nonce, load_authkey, load_phone_nonce  # noqa: E402


def first_two_varints(data: bytes) -> tuple[int | None, int | None]:
    values: dict[int, int] = {}
    i = 0
    while i < len(data) and (1 not in values or 2 not in values):
        key = data[i]
        i += 1
        field = key >> 3
        wire_type = key & 7
        if wire_type == 0:
            shift = 0
            value = 0
            while i < len(data):
                b = data[i]
                i += 1
                value |= (b & 0x7F) << shift
                if not (b & 0x80):
                    break
                shift += 7
            if field in (1, 2):
                values[field] = value
        elif wire_type == 2:
            shift = 0
            length = 0
            while i < len(data):
                b = data[i]
                i += 1
                length |= (b & 0x7F) << shift
                if not (b & 0x80):
                    break
                shift += 7
            i += length
        elif wire_type == 5:
            i += 4
        elif wire_type == 1:
            i += 8
        else:
            break
    return values.get(1), values.get(2)


def summarize(state_json: pathlib.Path, payloads: pathlib.Path, auth_tar: pathlib.Path) -> dict[str, object]:
    state = json.loads(state_json.read_text())
    phone_nonce = load_phone_nonce(payloads)
    _, _, watch, _ = find_watch_nonce(state_json)
    authkey, auth_member = load_authkey(auth_tar)
    raw_watch_nonce = watch["watch_nonce"]
    raw_watch_hmac = watch["watch_hmac"]
    if not isinstance(raw_watch_nonce, (bytes, bytearray)) or not isinstance(raw_watch_hmac, (bytes, bytearray)):
        raise ValueError("watch nonce parse did not return bytes")
    watch_nonce = bytes(raw_watch_nonce)
    watch_hmac = bytes(raw_watch_hmac)
    material = derive_session_material(
        secret_key=bytes.fromhex(authkey),
        phone_nonce=phone_nonce,
        watch_nonce=watch_nonce,
    )
    expected = hmac.new(material.decryption_key, watch_nonce + phone_nonce, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, watch_hmac):
        raise ValueError("watch hmac mismatch")

    parser = SppV2StreamParser()
    frames: list[dict[str, object]] = []
    encrypted_decoded = 0
    seen_hashes: set[str] = set()
    for event in state.get("events") or []:
        chunk_hex = event.get("hex", "")
        if not isinstance(chunk_hex, str):
            continue
        for frame in parser.feed(bytes.fromhex(chunk_hex)):
            raw_hash = hashlib.sha256(frame.raw).hexdigest()
            duplicate = raw_hash in seen_hashes
            seen_hashes.add(raw_hash)
            row: dict[str, object] = {
                "sequence": frame.sequence,
                "packet_type": int(frame.packet_type),
                "packet_type_name": frame.packet_type.name,
                "payload_len": len(frame.payload),
                "duplicate": duplicate,
            }
            if int(frame.packet_type) == int(PacketType.DATA) and len(frame.payload) >= 2:
                channel = frame.payload[0]
                opcode = frame.payload[1]
                row["channel"] = channel
                row["opcode"] = opcode
                if channel == int(Channel.PROTOBUF_COMMAND) and opcode == 2:
                    plaintext = decrypt_v2(material.decryption_key, frame.payload[2:])
                    cmd_type, cmd_subtype = first_two_varints(plaintext)
                    row["decrypted_len"] = len(plaintext)
                    row["command_type"] = cmd_type
                    row["command_subtype"] = cmd_subtype
                    encrypted_decoded += 1
            frames.append(row)

    writes = state.get("writes") or []
    notes = state.get("notes") or []
    return {
        "ok": True,
        "state_json": str(state_json),
        "connected": bool(state.get("connected")),
        "scan_found": bool(state.get("scanFound")),
        "auth_step3_queued": bool(state.get("authStep3Queued")),
        "encrypted_sanity_queued": "encrypted_sanity_queued=device_info_get" in "\n".join(notes),
        "write_labels": [w.get("label") for w in writes if isinstance(w, dict)],
        "notification_count": len(state.get("events") or []),
        "frame_count": len(frames),
        "unique_frame_count": len(seen_hashes),
        "encrypted_protobuf_decoded_count": encrypted_decoded,
        "watch_hmac_verified": True,
        "authkey_source_member_sha256_16": hashlib.sha256(auth_member.encode()).hexdigest()[:16],
        "frames": frames,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--state-json", required=True, type=pathlib.Path)
    p.add_argument("--payloads", required=True, type=pathlib.Path)
    p.add_argument("--auth-tar", required=True, type=pathlib.Path)
    args = p.parse_args(argv)
    print(json.dumps(summarize(args.state_json, args.payloads, args.auth_tar), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
