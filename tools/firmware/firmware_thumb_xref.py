#!/usr/bin/env python3
"""Heuristic Thumb xref scanner for raw Vela firmware images.

Read-only helper: disassembles a raw binary in Thumb mode, extracts PC-relative
literal loads and branch/call targets, then reports references near target string
offsets. It does not patch or write firmware images.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import struct
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable

try:
    from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN, CS_OP_MEM, CS_OP_IMM
    from capstone.arm import ARM_REG_PC
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"capstone unavailable: {exc.__class__.__name__}: {exc}")


@dataclass
class InstrLite:
    addr: int
    size: int
    mnemonic: str
    op_str: str


def printable_context(data: bytes, offset: int, limit: int = 120) -> str:
    if offset < 0 or offset >= len(data):
        return ""
    end = data.find(b"\0", offset, min(len(data), offset + limit))
    if end < 0:
        end = min(len(data), offset + limit)
    raw = data[offset:end]
    return raw.decode("utf-8", errors="replace")


def read_u32(data: bytes, offset: int) -> int | None:
    if offset < 0 or offset + 4 > len(data):
        return None
    return struct.unpack_from("<I", data, offset)[0]


def literal_addr_for(insn_addr: int, disp: int) -> int:
    # ARM Thumb literal loads use PC aligned to 4 from current instruction + 4.
    pc = (insn_addr + 4) & ~3
    return pc + disp


def disassemble(data: bytes, start: int, end: int) -> list:
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)
    md.detail = True
    md.skipdata = True
    return list(md.disasm(data[start:end], start))


def scan_literals(data: bytes, start: int, end: int) -> list[dict]:
    rows: list[dict] = []
    for insn in disassemble(data, start, end):
        if insn.mnemonic == ".byte":
            continue
        try:
            operands = insn.operands
        except Exception:
            continue
        # Capstone sometimes marks Thumb literal loads as ldr/ldrb/ldrh with mem.base pc.
        for op in operands:
            if op.type == CS_OP_MEM and op.mem.base == ARM_REG_PC:
                lit = literal_addr_for(insn.address, op.mem.disp)
                val = read_u32(data, lit)
                row = {
                    "insn_addr": insn.address,
                    "insn": f"{insn.mnemonic} {insn.op_str}".strip(),
                    "literal_addr": lit,
                    "literal_value": val,
                }
                if val is not None:
                    row["literal_value_hex"] = hex(val)
                    if 0 <= val < len(data):
                        row["literal_points_into_file"] = True
                        row["literal_string_prefix"] = printable_context(data, val, 96)
                rows.append(row)
        # Also collect direct immediates that point into file; useful for ADR-ish cases.
        for op in operands:
            if op.type == CS_OP_IMM and 0 <= op.imm < len(data):
                rows.append({
                    "insn_addr": insn.address,
                    "insn": f"{insn.mnemonic} {insn.op_str}".strip(),
                    "immediate_value": op.imm,
                    "immediate_value_hex": hex(op.imm),
                    "immediate_points_into_file": True,
                    "immediate_string_prefix": printable_context(data, int(op.imm), 96),
                })
    return rows


def scan_branches(data: bytes, start: int, end: int) -> list[dict]:
    rows: list[dict] = []
    for insn in disassemble(data, start, end):
        if insn.mnemonic == ".byte":
            continue
        try:
            operands = insn.operands
        except Exception:
            continue
        if not insn.mnemonic.startswith("b") and insn.mnemonic not in {"bl", "blx"}:
            continue
        for op in operands:
            if op.type == CS_OP_IMM and 0 <= op.imm < len(data):
                rows.append({
                    "insn_addr": insn.address,
                    "insn": f"{insn.mnemonic} {insn.op_str}".strip(),
                    "target": int(op.imm),
                    "target_hex": hex(int(op.imm)),
                })
    return rows


def nearest_literal_refs(literals: list[dict], targets: dict[str, int], tolerance: int, address_base: int = 0) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for name, off in targets.items():
        wanted = address_base + off
        rows = []
        for row in literals:
            val = row.get("literal_value")
            if isinstance(val, int) and abs(val - wanted) <= tolerance:
                rows.append({**row, "target_delta": val - wanted, "target_virtual": wanted})
            imm = row.get("immediate_value")
            if isinstance(imm, int) and abs(imm - wanted) <= tolerance:
                rows.append({**row, "target_delta": imm - wanted, "target_virtual": wanted})
        out[name] = sorted(rows, key=lambda r: (abs(int(r.get("target_delta", 0))), int(r.get("insn_addr", 0))))[:50]
    return out


def find_ascii(data: bytes, needle: bytes) -> list[int]:
    hits = []
    pos = 0
    while True:
        idx = data.find(needle, pos)
        if idx < 0:
            return hits
        hits.append(idx)
        pos = idx + 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("firmware", type=pathlib.Path)
    p.add_argument("--start", type=lambda x: int(x, 0), default=0)
    p.add_argument("--end", type=lambda x: int(x, 0), default=None)
    p.add_argument("--target", action="append", default=[], help="name=0xoffset or name=ascii-string to locate")
    p.add_argument("--address-base", type=lambda x: int(x, 0), default=0, help="virtual-address base added to raw target offsets when matching literal values")
    p.add_argument("--tolerance", type=lambda x: int(x, 0), default=0x100)
    p.add_argument("--out", type=pathlib.Path, required=True)
    args = p.parse_args(argv)

    data = args.firmware.read_bytes()
    end = min(len(data), args.end or len(data))
    targets: dict[str, int] = {}
    for item in args.target:
        if "=" in item:
            name, raw = item.split("=", 1)
            try:
                targets[name] = int(raw, 0)
                continue
            except ValueError:
                hits = find_ascii(data, raw.encode())
                for i, off in enumerate(hits):
                    targets[name if len(hits) == 1 else f"{name}#{i}"] = off
                continue
        hits = find_ascii(data, item.encode())
        for i, off in enumerate(hits):
            targets[item if len(hits) == 1 else f"{item}#{i}"] = off

    literals = scan_literals(data, args.start, end)
    branches = scan_branches(data, args.start, end)
    literal_values_in_file = [r["literal_value"] for r in literals if isinstance(r.get("literal_value"), int) and 0 <= int(r["literal_value"]) < len(data)]
    branch_targets = [r["target"] for r in branches]

    report = {
        "firmware": str(args.firmware),
        "file_size": len(data),
        "scan_range": [args.start, end],
        "address_base": args.address_base,
        "address_base_hex": hex(args.address_base),
        "targets": {k: {"offset": v, "offset_hex": hex(v), "virtual": args.address_base + v, "virtual_hex": hex(args.address_base + v), "string_prefix": printable_context(data, v, 96)} for k, v in targets.items()},
        "literal_row_count": len(literals),
        "literal_values_pointing_into_file_count": len(literal_values_in_file),
        "branch_row_count": len(branches),
        "branch_targets_count": len(branch_targets),
        "literal_ref_hits": nearest_literal_refs(literals, targets, args.tolerance, args.address_base),
        "literal_value_top_pages": Counter((int(v) >> 12) << 12 for v in literal_values_in_file).most_common(20),
        "branch_target_top_pages": Counter((int(v) >> 12) << 12 for v in branch_targets).most_common(20),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    print(json.dumps({
        "out": str(args.out),
        "file_size": len(data),
        "literal_ref_target_counts": {k: len(v) for k, v in report["literal_ref_hits"].items()},
        "literal_values_pointing_into_file_count": len(literal_values_in_file),
        "branch_targets_count": len(branch_targets),
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
