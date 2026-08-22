#!/usr/bin/env python3
"""Redacted summary for Mi Band 9 macOS-direct SportXms live runs.

Input points at local auth/live artifacts. Output contains command metadata and IMU
sample summaries only. It never prints auth keys, nonces, session material, full live
state, or encrypted/plaintext payload blobs. Full 8/53 payloads are written only to the
requested local JSONL path for decoder use.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import hmac
import json
import pathlib
import sys
from typing import Any

REPO_TOOL = pathlib.Path(__file__).resolve().parents[1] / "miband9ctl"
if str(REPO_TOOL) not in sys.path:
    sys.path.insert(0, str(REPO_TOOL))
SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_auth_step3_from_events import find_watch_nonce, load_authkey, load_phone_nonce  # noqa: E402
from miband9ctl.mac_direct_protocol import Channel, PacketType, SppV2StreamParser, decrypt_v2, derive_session_material  # noqa: E402
from decode_xms53_packets import records_from_packet_logs, summarize_records, write_csv, write_jsonl  # noqa: E402


def parse_two_varints(data: bytes) -> tuple[int | None, int | None]:
    values: dict[int, int] = {}
    i = 0
    while i < len(data) and (1 not in values or 2 not in values):
        key = data[i]
        i += 1
        field = key >> 3
        wt = key & 7
        if wt == 0:
            shift = 0
            val = 0
            while i < len(data):
                b = data[i]
                i += 1
                val |= (b & 0x7F) << shift
                if not b & 0x80:
                    break
                shift += 7
            if field in (1, 2):
                values[field] = val
        elif wt == 2:
            shift = 0
            length = 0
            while i < len(data):
                b = data[i]
                i += 1
                length |= (b & 0x7F) << shift
                if not b & 0x80:
                    break
                shift += 7
            i += length
        elif wt == 5:
            i += 4
        elif wt == 1:
            i += 8
        else:
            break
    return values.get(1), values.get(2)


def derive_material(state_json: pathlib.Path, payloads: pathlib.Path, auth_tar: pathlib.Path):
    phone_nonce = load_phone_nonce(payloads)
    _, _, watch, _ = find_watch_nonce(state_json)
    authkey, auth_member = load_authkey(auth_tar)
    watch_nonce = watch["watch_nonce"]
    watch_hmac = watch["watch_hmac"]
    if not isinstance(watch_nonce, (bytes, bytearray)) or not isinstance(watch_hmac, (bytes, bytearray)):
        raise ValueError("watch nonce parse did not return bytes")
    material = derive_session_material(secret_key=bytes.fromhex(authkey), phone_nonce=phone_nonce, watch_nonce=bytes(watch_nonce))
    expected = hmac.new(material.decryption_key, bytes(watch_nonce) + phone_nonce, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, bytes(watch_hmac)):
        raise ValueError("watch hmac mismatch")
    return material, auth_member


def summarize(*, state_json: pathlib.Path, payloads: pathlib.Path, auth_tar: pathlib.Path, xms53_jsonl: pathlib.Path, samples_jsonl: pathlib.Path | None, samples_csv: pathlib.Path | None) -> dict[str, Any]:
    state = json.loads(state_json.read_text())
    material, auth_member = derive_material(state_json, payloads, auth_tar)
    parser = SppV2StreamParser()
    counts: Counter[str] = Counter()
    xms_logs: list[dict[str, Any]] = []
    encrypted_frames = 0
    unique_raw_hashes: set[str] = set()
    frames_seen = 0

    for event in state.get("events") or []:
        chunk_hex = event.get("hex", "")
        if not isinstance(chunk_hex, str):
            continue
        for frame in parser.feed(bytes.fromhex(chunk_hex)):
            frames_seen += 1
            unique_raw_hashes.add(hashlib.sha256(frame.raw).hexdigest())
            if int(frame.packet_type) != int(PacketType.DATA) or len(frame.payload) < 3:
                continue
            channel, opcode = frame.payload[0], frame.payload[1]
            if channel != int(Channel.PROTOBUF_COMMAND) or opcode != 2:
                continue
            encrypted_frames += 1
            plaintext = decrypt_v2(material.decryption_key, frame.payload[2:])
            command_type, command_subtype = parse_two_varints(plaintext)
            counts[f"{command_type}/{command_subtype}"] += 1
            if command_type == 8 and command_subtype == 53:
                xms_logs.append({
                    "packet_index": len(xms_logs) + 1,
                    "channel": "mac_direct_encrypted_pb",
                    "command_type": 8,
                    "command_subtype": 53,
                    "payload_length": len(plaintext),
                    "payload_hex": plaintext.hex(),
                })

    xms53_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with xms53_jsonl.open("w", encoding="utf-8") as fh:
        for item in xms_logs:
            fh.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")

    records = records_from_packet_logs(xms_logs)
    decoder_summary, _decoded, rows = summarize_records(records)
    if samples_jsonl:
        write_jsonl(samples_jsonl, rows)
    if samples_csv:
        write_csv(samples_csv, rows)

    notes = state.get("notes") or []
    writes = state.get("writes") or []
    return {
        "ok": True,
        "state_json": str(state_json),
        "connected": bool(state.get("connected")),
        "auth_step3_queued": bool(state.get("authStep3Queued")),
        "sportxms_start_queued": "post_auth_queued=encrypted_sportxms_start" in "\n".join(notes),
        "sportxms_stop_queued": "post_auth_queued=encrypted_sportxms_stop" in "\n".join(notes),
        "write_labels": [w.get("label") for w in writes if isinstance(w, dict)],
        "notification_count": len(state.get("events") or []),
        "frame_count": frames_seen,
        "unique_frame_count": len(unique_raw_hashes),
        "encrypted_frame_count": encrypted_frames,
        "command_counts": dict(sorted(counts.items())),
        "xms53_packets": len(xms_logs),
        "decoder_summary": decoder_summary,
        "xms53_jsonl": str(xms53_jsonl),
        "samples_jsonl": str(samples_jsonl) if samples_jsonl else None,
        "samples_csv": str(samples_csv) if samples_csv else None,
        "watch_hmac_verified": True,
        "authkey_source_member_sha256_16": hashlib.sha256(auth_member.encode()).hexdigest()[:16],
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--state-json", required=True, type=pathlib.Path)
    p.add_argument("--payloads", required=True, type=pathlib.Path)
    p.add_argument("--auth-tar", required=True, type=pathlib.Path)
    p.add_argument("--xms53-jsonl", required=True, type=pathlib.Path)
    p.add_argument("--samples-jsonl", type=pathlib.Path)
    p.add_argument("--samples-csv", type=pathlib.Path)
    args = p.parse_args(argv)
    print(json.dumps(summarize(**vars(args)), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
