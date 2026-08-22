#!/usr/bin/env python3
"""Build the Mi Fitness SportXms/812 plaintext hns packet skeleton.

This intentionally stops before Xiaomi DeviceContact transport/session wrapping.
It is an offline reverse-engineering helper, not a BLE sender.
"""
from __future__ import annotations

import argparse
import json
import time


def varint(value: int) -> bytes:
    if value < 0:
        raise ValueError("negative varints are not supported by this helper")
    out: list[int] = []
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def key(field: int, wire_type: int) -> bytes:
    return varint((field << 3) | wire_type)


def field_varint(field: int, value: int) -> bytes:
    return key(field, 0) + varint(value)


def field_message(field: int, payload: bytes) -> bytes:
    return key(field, 2) + varint(len(payload)) + payload


def sport_state_to_proto(state: int) -> int:
    # Mirrors vga.x(...): 1->0, 2->1, 3->2, else->3.
    if state == 1:
        return 0
    if state == 2:
        return 1
    if state == 3:
        return 2
    return 3


def build_packet(
    *,
    timestamp_sec: int,
    timezone_value: int,
    sport_type: int = 812,
    sport_state: int = 1,
    select_version: int | None = 3,
    accessory_wear_mode: int | None = None,
    sport_target_type: int | None = None,
    sport_target_value: int | None = None,
    sport_launch_type: int | None = None,
) -> dict[str, object]:
    oe4 = field_varint(1, timezone_value)
    hfa_parts = [
        field_varint(1, timestamp_sec),
        field_message(2, oe4),
        field_varint(3, sport_type),
        field_varint(4, sport_state_to_proto(sport_state)),
    ]
    if select_version is not None:
        hfa_parts.append(field_varint(6, select_version))
    if (sport_target_type is None) ^ (sport_target_value is None):
        raise ValueError("sport_target_type and sport_target_value must be provided together")
    if sport_target_type is not None and sport_target_value is not None:
        # Mirrors vga.v(...): hfa.j = new nfa[]{type,value}; hfa serializes it as field 7.
        nfa = field_varint(1, sport_target_type) + field_varint(2, sport_target_value)
        hfa_parts.append(field_message(7, nfa))
    if sport_launch_type is not None:
        # hfa has a field 9 launch-type slot, although Mi Fitness' current vga.v(...)
        # converter does not populate it for the normal SportXms start path.
        hfa_parts.append(field_varint(9, sport_launch_type))
    if accessory_wear_mode is not None:
        hfa_parts.append(field_varint(10, accessory_wear_mode))
    hfa = b"".join(hfa_parts)
    uca = field_message(20, hfa)
    hns = b"".join([
        field_varint(1, 8),
        field_varint(2, 26),
        field_message(10, uca),
    ])
    return {
        "warning": "Plain hns/uca/hfa command skeleton before Xiaomi DeviceContact transport/session wrapping; do not send as raw BLE bytes.",
        "source": "Mi Fitness cgp.l + vga.v + hns/uca/hfa protobuf-nano writers",
        "timestamp_sec": timestamp_sec,
        "timezone_value": timezone_value,
        "sport_type": sport_type,
        "sport_state_app": sport_state,
        "sport_state_proto": sport_state_to_proto(sport_state),
        "select_version": select_version,
        "accessory_wear_mode": accessory_wear_mode,
        "sport_target_type": sport_target_type,
        "sport_target_value": sport_target_value,
        "sport_launch_type": sport_launch_type,
        "oe4_hex": oe4.hex(" "),
        "hfa_hex": hfa.hex(" "),
        "uca_hex": uca.hex(" "),
        "hns_hex": hns.hex(" "),
        "hns_len": len(hns),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timestamp-sec", type=int, default=int(time.time()))
    parser.add_argument("--timezone-value", type=int, default=32, help="Mi Fitness timezone value. Shanghai UTC+8 is usually 32 in 15-min units.")
    parser.add_argument("--sport-type", type=int, default=812)
    parser.add_argument("--sport-state", type=int, default=1)
    parser.add_argument("--select-version", type=int, default=3)
    parser.add_argument("--omit-select-version", action="store_true", help="Do not serialize hfa field 6/selectVersion")
    parser.add_argument("--accessory-wear-mode", type=int)
    parser.add_argument("--sport-target-type", type=int, help="Optional hfa field 7 nfa.type, from SportTargetType 1..7")
    parser.add_argument("--sport-target-value", type=int, help="Optional hfa field 7 nfa.value")
    parser.add_argument("--sport-launch-type", type=int, help="Optional hfa field 9 launch type. Not populated by the normal vga.v path.")
    args = parser.parse_args()
    print(json.dumps(build_packet(
        timestamp_sec=args.timestamp_sec,
        timezone_value=args.timezone_value,
        sport_type=args.sport_type,
        sport_state=args.sport_state,
        select_version=None if args.omit_select_version else args.select_version,
        accessory_wear_mode=args.accessory_wear_mode,
        sport_target_type=args.sport_target_type,
        sport_target_value=args.sport_target_value,
        sport_launch_type=args.sport_launch_type,
    ), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
