#!/usr/bin/env python3
"""Build Mi Fitness factory/debug hns packet skeletons.

These are plaintext protobuf-nano hns command bodies before Xiaomi DeviceContact
transport/session wrapping. They are reverse-engineering helpers, not a sender.

Source snippets:
- FactoryTestFragment.doFactoryMode: hns.e=13, hns.f=0, iq9.s(factoryMode)
- FactoryTestFragment.dumpDeviceLog / DeviceModelExtKt.doFactoryDump: hns.e=13, hns.f=2
- FactoryTestFragment.dumpMediaLog: hns.e=13, hns.f=4
- FactoryTestFragment.setBrightness: hns.e=13, hns.f=5, iq9.r(brightness)
- FactoryTestViewModel.nfcConfig: hns.e=13, hns.f=1, iq9.t(kq9 map payload) (not implemented here)
- DeviceInstallAPPInfoDebugViewModel CTA debug: hns.e=13, hns.f=9/12/13
"""
from __future__ import annotations

import argparse
import json


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


def iq9_field1_factory_mode(mode: int) -> bytes:
    # iq9.s(factoryMode): iq9 oneof field 1 varint.
    return field_varint(1, mode)


def iq9_field6_brightness(value: int) -> bytes:
    # iq9.r(brightness): iq9 oneof field 6 uint32/varint.
    return field_varint(6, value)


def build_hns(*, command_type: int = 13, subtype: int, iq9_payload: bytes | None = None) -> bytes:
    parts = [field_varint(1, command_type), field_varint(2, subtype)]
    if iq9_payload is not None:
        # hns.R(iq9) serializes hns field 15.
        parts.append(field_message(15, iq9_payload))
    return b"".join(parts)


def build_factory_mode(mode: int) -> bytes:
    if mode not in {0, 1, 2, 4}:
        raise ValueError("known FactoryTestFragment modes are 0, 1, 2, and 4")
    return build_hns(subtype=0, iq9_payload=iq9_field1_factory_mode(mode))


def build_factory_dump() -> bytes:
    return build_hns(subtype=2)


def build_factory_media_dump() -> bytes:
    return build_hns(subtype=4)


def build_factory_brightness(value: int) -> bytes:
    if not 0 <= value <= 255:
        raise ValueError("brightness should be in byte-ish range 0..255 unless source evidence says otherwise")
    return build_hns(subtype=5, iq9_payload=iq9_field6_brightness(value))


def build_cta_app_list() -> bytes:
    # DeviceInstallAPPInfoDebugViewModel.getCTAAppList: hns.e=13, hns.f=9.
    return build_hns(subtype=9)


def build_cta_subscribe_behavior() -> bytes:
    # DeviceInstallAPPInfoDebugViewModel.subscribeAppBehavior: hns.e=13, hns.f=12.
    return build_hns(subtype=12)


def build_cta_unsubscribe_behavior() -> bytes:
    # DeviceInstallAPPInfoDebugViewModel.unSubscribeAppBehavior: hns.e=13, hns.f=13.
    return build_hns(subtype=13)


def build_command(action: str, value: int | None = None) -> tuple[bytes, str]:
    if action == "factory_dump":
        return build_factory_dump(), "hns.e=13 f=2"
    if action == "factory_media_dump":
        return build_factory_media_dump(), "hns.e=13 f=4"
    if action == "factory_mode":
        if value is None:
            raise ValueError("factory_mode requires --value 0/1/2/4")
        return build_factory_mode(value), f"hns.e=13 f=0 iq9.field1={value}"
    if action == "factory_brightness":
        if value is None:
            raise ValueError("factory_brightness requires --value")
        return build_factory_brightness(value), f"hns.e=13 f=5 iq9.field6={value}"
    if action == "cta_app_list":
        return build_cta_app_list(), "hns.e=13 f=9"
    if action == "cta_subscribe_behavior":
        return build_cta_subscribe_behavior(), "hns.e=13 f=12"
    if action == "cta_unsubscribe_behavior":
        return build_cta_unsubscribe_behavior(), "hns.e=13 f=13"
    raise ValueError(f"unknown action: {action}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=[
            "factory_dump",
            "factory_media_dump",
            "factory_mode",
            "factory_brightness",
            "cta_app_list",
            "cta_subscribe_behavior",
            "cta_unsubscribe_behavior",
        ],
    )
    parser.add_argument("--value", type=int, help="mode or brightness value, depending on action")
    args = parser.parse_args()
    payload, source = build_command(args.action, args.value)
    print(json.dumps({
        "warning": "Plain hns command skeleton before Xiaomi encrypted DeviceContact transport/session wrapping; do not send raw over BLE/RFCOMM.",
        "action": args.action,
        "source": source,
        "hns_hex": payload.hex(" "),
        "hns_len": len(payload),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
