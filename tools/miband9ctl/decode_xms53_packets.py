#!/usr/bin/env python3
"""Decode Mi Band 9 SportXms type=8/subtype=53 packets from hfimucli logs.

This decoder follows the Mi Fitness parser path found in the decompiled app:

    hns.field10 -> uca.field15 -> fga
    qg6.l(fga): fga.field5 -> WearSensorData.accel
                fga.field6 -> WearSensorData.gyro
    ee4: field1 timestamp/tick, field2/3/4 float32 x/y/z

It accepts hfimucli JSON results, JSONL packet artifacts, or raw logcat text. Older
artifacts may contain only 64-byte `payload_hex` prefixes; those still decode the
visible prefix and mark the packet as incomplete. Newer hfimucli builds log the
complete payload hex so this script can emit full JSONL/CSV samples.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import struct
from pathlib import Path
from typing import Any, Iterable, Union


ACCEL_FIELD = 5
GYRO_FIELD = 6
SAMPLE_COLUMNS = [
    "packet_index",
    "sample_index",
    "tick",
    "timestamp",
    "accel_tick",
    "accel_x",
    "accel_y",
    "accel_z",
    "gyro_tick",
    "gyro_x",
    "gyro_y",
    "gyro_z",
]


class NeedMoreData(Exception):
    pass


class DecodeError(Exception):
    pass


def read_varint(buf: bytes, pos: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while True:
        if pos >= len(buf):
            raise NeedMoreData("truncated varint")
        b = buf[pos]
        pos += 1
        value |= (b & 0x7F) << shift
        if not b & 0x80:
            return value, pos
        shift += 7
        if shift > 70:
            raise DecodeError("varint too long")


def read_len(buf: bytes, pos: int) -> tuple[bytes, int]:
    size, pos = read_varint(buf, pos)
    end = pos + size
    if end > len(buf):
        raise NeedMoreData(f"need {size} bytes, have {len(buf) - pos}")
    return buf[pos:end], end


def iter_fields(buf: bytes) -> Iterable[tuple[int, int, Union[int, bytes]]]:
    pos = 0
    while pos < len(buf):
        key, pos = read_varint(buf, pos)
        field_no = key >> 3
        wire = key & 7
        if wire == 0:
            value, pos = read_varint(buf, pos)
            yield field_no, wire, value
        elif wire == 2:
            value, pos = read_len(buf, pos)
            yield field_no, wire, value
        elif wire == 5:
            if pos + 4 > len(buf):
                raise NeedMoreData("truncated fixed32")
            yield field_no, wire, buf[pos:pos + 4]
            pos += 4
        else:
            raise DecodeError(f"unsupported wire type {wire} at field {field_no}")


def iter_fields_prefix(buf: bytes) -> Iterable[tuple[int, int, Union[int, bytes], int, bool]]:
    """Yield protobuf fields from a possibly truncated prefix.

    For length-delimited fields, value may be shorter than the declared length and
    the returned truncated flag will be true.
    """
    pos = 0
    while pos < len(buf):
        try:
            key, pos = read_varint(buf, pos)
        except NeedMoreData:
            break
        field_no = key >> 3
        wire = key & 7
        if wire == 0:
            try:
                value, pos = read_varint(buf, pos)
            except NeedMoreData:
                break
            yield field_no, wire, value, 0, False
        elif wire == 2:
            try:
                declared, pos = read_varint(buf, pos)
            except NeedMoreData:
                break
            end = pos + declared
            actual_end = min(end, len(buf))
            yield field_no, wire, buf[pos:actual_end], declared, actual_end < end
            pos = actual_end
            if actual_end < end:
                break
        elif wire == 5:
            if pos + 4 > len(buf):
                break
            yield field_no, wire, buf[pos:pos + 4], 4, False
            pos += 4
        else:
            break


def fixed32_float(raw: bytes) -> float:
    return struct.unpack("<f", raw)[0]


def clean_hex_bytes(hex_text: str) -> bytes:
    clean = re.sub(r"[^0-9a-fA-F]", "", hex_text or "")
    if len(clean) % 2:
        clean = clean[:-1]
    return bytes.fromhex(clean) if clean else b""


def decode_ee4_sample(buf: bytes) -> dict[str, Any]:
    sample: dict[str, Any] = {"raw_len": len(buf)}
    for field_no, wire, value in iter_fields(buf):
        if field_no == 1 and wire == 0:
            tick = int(value)
            sample["tick"] = tick
            sample["timestamp"] = tick
            sample["t"] = tick  # backward-compatible alias used by earlier notes
        elif field_no == 2 and wire == 5 and isinstance(value, bytes):
            sample["x"] = fixed32_float(value)
        elif field_no == 3 and wire == 5 and isinstance(value, bytes):
            sample["y"] = fixed32_float(value)
        elif field_no == 4 and wire == 5 and isinstance(value, bytes):
            sample["z"] = fixed32_float(value)
        else:
            sample.setdefault("unknown", []).append({"field": field_no, "wire": wire})
    return sample


def parse_fga_prefix(buf: bytes, out: dict[str, Any]) -> None:
    # Official Mi Fitness mapping in qg6.l(fga): field5=WearSensorData.accel,
    # field6=WearSensorData.gyro. Each value is an ee4 sample.
    pos = 0
    while pos < len(buf):
        try:
            key, pos = read_varint(buf, pos)
            field_no = key >> 3
            wire = key & 7
            if wire != 2:
                out["uca"].setdefault("unexpected_fga_fields", []).append({"field": field_no, "wire": wire})
                break
            declared, pos = read_varint(buf, pos)
            end = pos + declared
            if end > len(buf):
                out["truncated"] = True
                out["truncated_reason"] = f"need sample {declared} bytes, have {len(buf) - pos}"
                break
            body = buf[pos:end]
            pos = end
            if field_no == ACCEL_FIELD:
                sample = decode_ee4_sample(body)
                sample["array_field"] = field_no
                sample["sensor"] = "accel"
                out["accel_samples"].append(sample)
                out["samples"].append(sample)
            elif field_no == GYRO_FIELD:
                sample = decode_ee4_sample(body)
                sample["array_field"] = field_no
                sample["sensor"] = "gyro"
                out["gyro_samples"].append(sample)
                out["samples"].append(sample)
            else:
                out["uca"].setdefault("unexpected_fga_fields", []).append({"field": field_no, "wire": wire})
        except NeedMoreData as exc:
            out["truncated"] = True
            out["truncated_reason"] = str(exc)
            break
        except DecodeError as exc:
            out["decode_error"] = str(exc)
            break


def decode_payload_prefix(hex_text: str) -> dict[str, Any]:
    buf = clean_hex_bytes(hex_text)
    out: dict[str, Any] = {
        "payload_hex_bytes": len(buf),
        "prefix_bytes": len(buf),  # backward-compatible alias
        "top": {},
        "uca": {},
        "accel_samples": [],
        "gyro_samples": [],
        "samples": [],
        "truncated": False,
    }
    for field_no, wire, value, declared, truncated in iter_fields_prefix(buf):
        if truncated:
            out["truncated"] = True
        if field_no in (1, 2) and wire == 0:
            out["top"][str(field_no)] = int(value)
        elif field_no == 10 and wire == 2 and isinstance(value, bytes):
            out["top"]["10_declared_len"] = declared
            out["top"]["10_prefix_len"] = len(value)
            for ufield, uwire, uvalue, udeclared, utruncated in iter_fields_prefix(value):
                if utruncated:
                    out["truncated"] = True
                if ufield == 15 and uwire == 2 and isinstance(uvalue, bytes):
                    out["uca"]["15_declared_len"] = udeclared
                    out["uca"]["15_prefix_len"] = len(uvalue)
                    parse_fga_prefix(uvalue, out)
                else:
                    out["uca"].setdefault("other_fields", []).append({"field": ufield, "wire": uwire})
        else:
            out["top"].setdefault("other_fields", []).append({"field": field_no, "wire": wire})
    return out


def parse_int_token(value: Any, default: int = 0) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def parse_structured_log_payloads(log_text: str) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for line in log_text.splitlines():
        start = line.find("{")
        end = line.rfind("}")
        if start < 0 or end < start:
            continue
        try:
            payload = json.loads(line[start:end + 1])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def record_from_payload(payload: dict[str, Any], fallback_index: int) -> dict[str, Any] | None:
    if not payload.get("payload_hex"):
        return None
    if str(payload.get("command_type")) != "8" or str(payload.get("command_subtype")) != "53":
        return None
    packet_index = parse_int_token(payload.get("packet_index"), fallback_index)
    payload_hex = str(payload.get("payload_hex", ""))
    payload_length = parse_int_token(payload.get("payload_length"), len(clean_hex_bytes(payload_hex)))
    observed_hex_bytes = len(clean_hex_bytes(payload_hex))
    return {
        "packet_index": packet_index,
        "channel": payload.get("channel", ""),
        "payload_length": payload_length,
        "payload_hex": payload_hex,
        "payload_hex_bytes": observed_hex_bytes,
        "payload_complete": payload_length == 0 or observed_hex_bytes >= payload_length,
    }


def records_from_packet_logs(packet_logs: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for payload in packet_logs:
        record = record_from_payload(payload, len(records) + 1)
        if record is not None:
            records.append(record)
    return records


def extract_payload_records(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(errors="replace")
    records: list[dict[str, Any]] = []

    # JSONL packet artifact, one packet per line.
    if path.suffix == ".jsonl":
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                record = record_from_payload(payload, len(records) + 1)
                if record is not None:
                    records.append(record)
        if records:
            return records

    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        obj = None

    if isinstance(obj, dict):
        data = obj.get("data", {}) if isinstance(obj.get("data"), dict) else {}
        for key in ("opener", "stopper"):
            section = data.get(key, {})
            if isinstance(section, dict):
                records.extend(records_from_packet_logs(section.get("packet_logs", [])))
        # Prefer parsed packet_logs when available; they avoid duplicate log parsing.
        if records:
            return records
        for log_key in ("matching_app_log", "app_log"):
            log_text = data.get(log_key, "")
            if not isinstance(log_text, str):
                continue
            log_records: list[dict[str, Any]] = []
            for payload in parse_structured_log_payloads(log_text):
                record = record_from_payload(payload, len(log_records) + 1)
                if record is not None:
                    log_records.append(record)
            if log_records:
                return log_records

    for payload in parse_structured_log_payloads(text):
        record = record_from_payload(payload, len(records) + 1)
        if record is not None:
            records.append(record)
    return records


def extract_payload_hexes(path: Path) -> list[str]:
    return [record["payload_hex"] for record in extract_payload_records(path)]


def sample_rows_for_packet(packet_index: int, decoded: dict[str, Any]) -> list[dict[str, Any]]:
    accel = decoded.get("accel_samples", [])
    gyro = decoded.get("gyro_samples", [])
    rows: list[dict[str, Any]] = []
    for sample_index in range(max(len(accel), len(gyro))):
        accel_sample = accel[sample_index] if sample_index < len(accel) else {}
        gyro_sample = gyro[sample_index] if sample_index < len(gyro) else {}
        tick = accel_sample.get("tick", gyro_sample.get("tick"))
        rows.append({
            "packet_index": packet_index,
            "sample_index": sample_index,
            "tick": tick,
            "timestamp": tick,
            "accel_tick": accel_sample.get("tick"),
            "accel_x": accel_sample.get("x"),
            "accel_y": accel_sample.get("y"),
            "accel_z": accel_sample.get("z"),
            "gyro_tick": gyro_sample.get("tick"),
            "gyro_x": gyro_sample.get("x"),
            "gyro_y": gyro_sample.get("y"),
            "gyro_z": gyro_sample.get("z"),
        })
    return rows


def decode_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    decoded: list[dict[str, Any]] = []
    for fallback_index, record in enumerate(records, start=1):
        packet_index = parse_int_token(record.get("packet_index"), fallback_index)
        packet = decode_payload_prefix(str(record.get("payload_hex", "")))
        packet["packet_index"] = packet_index
        packet["payload_length"] = parse_int_token(record.get("payload_length"), packet.get("payload_hex_bytes", 0))
        packet["payload_complete"] = bool(record.get("payload_complete"))
        decoded.append(packet)
    return decoded


def summarize_records(records: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    decoded = decode_records(records)
    rows: list[dict[str, Any]] = []
    for packet in decoded:
        rows.extend(sample_rows_for_packet(parse_int_token(packet.get("packet_index")), packet))

    first = decoded[0] if decoded else {}
    accel_counts = [len(item.get("accel_samples", [])) for item in decoded]
    gyro_counts = [len(item.get("gyro_samples", [])) for item in decoded]
    complete_packets = sum(1 for item in decoded if item.get("payload_complete"))
    truncated_packets = sum(1 for item in decoded if item.get("truncated") or not item.get("payload_complete"))
    inner_len = first.get("uca", {}).get("15_declared_len")
    inferred_total_ee4_per_full_packet = None
    if isinstance(inner_len, int):
        # Each repeated ee4 is normally tag(1) + len(1) + 22-byte ee4 body.
        inferred_total_ee4_per_full_packet = inner_len // 24

    summary = {
        "packets": len(records),
        "decoded_packets": len(decoded),
        "complete_payload_packets": complete_packets,
        "truncated_or_prefix_packets": truncated_packets,
        "accel_sample_counts": accel_counts[:10],
        "gyro_sample_counts": gyro_counts[:10],
        "total_accel_samples": sum(accel_counts),
        "total_gyro_samples": sum(gyro_counts),
        "sample_rows": len(rows),
        "first_top": first.get("top", {}),
        "first_uca": first.get("uca", {}),
        "inferred_total_ee4_per_full_packet": inferred_total_ee4_per_full_packet,
        "inferred_samples_per_full_packet": inferred_total_ee4_per_full_packet,  # legacy alias
        "first_samples": first.get("samples", [])[:3],
        "first_rows": rows[:3],
        "notes": [
            "top fields 1=8 and 2=53 confirm SportXms stream packet",
            "top field 10 contains uca; uca field 15 is fga",
            "official Mi Fitness qg6.l(fga) maps fga.field5 to WearSensorData.accel and fga.field6 to WearSensorData.gyro",
            "ee4 sample fields are field1 tick/timestamp plus float32 x/y/z",
            "older hfimucli artifacts may contain only 64-byte payload_hex prefixes; field6/gyro may sit beyond that prefix",
        ],
    }
    return summary, decoded, rows


def summarize(hexes: list[str]) -> dict[str, Any]:
    records = [
        {
            "packet_index": index,
            "payload_length": len(clean_hex_bytes(hex_text)),
            "payload_hex": hex_text,
            "payload_complete": True,
        }
        for index, hex_text in enumerate(hexes, start=1)
    ]
    summary, _decoded, _rows = summarize_records(records)
    return summary


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SAMPLE_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in SAMPLE_COLUMNS})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("log", type=Path, help="hfimucli JSON result, xms53_payloads.jsonl, or logcat text")
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument("--out-jsonl", type=Path, default=None, help="Write decoded sample rows as JSONL")
    parser.add_argument("--out-csv", type=Path, default=None, help="Write decoded sample rows as CSV")
    parser.add_argument("--summary", type=Path, default=None, help="Write summary JSON to this path")
    args = parser.parse_args()

    records = extract_payload_records(args.log)
    summary, _decoded, rows = summarize_records(records)
    if args.out_jsonl:
        write_jsonl(args.out_jsonl, rows)
        summary["out_jsonl"] = str(args.out_jsonl)
    if args.out_csv:
        write_csv(args.out_csv, rows)
        summary["out_csv"] = str(args.out_csv)
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
