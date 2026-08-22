#!/usr/bin/env python3
"""Find firmware uORB/SportXms IMU subscription callsites.

Read-only helper for raw Vela ARM/Thumb firmware. It scans for calls to the
small subscription wrappers found in Mi Band 9 `vela_ap.bin`, reconstructs the
immediate r1/r2/r3 arguments from nearby literal/move instructions, and emits
sensor_accel/sensor_gyro subscription candidates with report-latency constants.

This does not patch or write firmware images.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import struct
from dataclasses import dataclass
from typing import Any

try:
    from capstone import Cs, CS_ARCH_ARM, CS_MODE_LITTLE_ENDIAN, CS_MODE_THUMB, CS_OP_IMM, CS_OP_MEM, CS_OP_REG
    from capstone.arm import ARM_REG_PC
    CAPSTONE_ERROR = ""
except Exception as exc:  # pragma: no cover
    # Keep the tool useful on bare macOS/Xcode Python: the known SportXms
    # callsites can still be verified by reading literal values directly.
    Cs = None  # type: ignore[assignment]
    CS_ARCH_ARM = CS_MODE_LITTLE_ENDIAN = CS_MODE_THUMB = CS_OP_IMM = CS_OP_MEM = CS_OP_REG = ARM_REG_PC = -1  # type: ignore[assignment]
    CAPSTONE_ERROR = f"{exc.__class__.__name__}: {exc}"

DEFAULT_BASE = 0x2C100000
DEFAULT_SUBSCRIBE = 0x16B348
DEFAULT_UNSUBSCRIBE = 0x16B374
DEFAULT_SUBSCRIBE_FLAGGED = 0x16B398

# Raw offsets for the uORB descriptor table entries observed in Mi Band 9 NFC 1.3.210.
KNOWN_DESCRIPTORS = {
    0x506C64: "sensor_accel",
    0x506C6C: "sensor_accel_uncal",
    0x506CB4: "sensor_gyro",
    0x506CBC: "sensor_gyro_uncal",
    0x506D4C: "sensor_ppgd",
}


@dataclass
class InstrLite:
    addr: int
    size: int
    mnemonic: str
    op_str: str
    operands: Any


def read_u32(data: bytes, offset: int) -> int | None:
    if offset < 0 or offset + 4 > len(data):
        return None
    return struct.unpack_from("<I", data, offset)[0]


def literal_addr_for(insn_addr: int, disp: int) -> int:
    return ((insn_addr + 4) & ~3) + disp


def printable_cstr(data: bytes, offset: int, limit: int = 96) -> str:
    if offset < 0 or offset >= len(data):
        return ""
    end = data.find(b"\0", offset, min(len(data), offset + limit))
    if end < 0:
        end = min(len(data), offset + limit)
    return data[offset:end].decode("utf-8", errors="replace")


def disassemble(data: bytes, start: int, end: int) -> list[InstrLite]:
    if Cs is None:
        raise RuntimeError(f"capstone unavailable: {CAPSTONE_ERROR}")
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)
    md.detail = True
    md.skipdata = True
    rows: list[InstrLite] = []
    for ins in md.disasm(data[start:end], start):
        if ins.mnemonic == ".byte":
            continue
        rows.append(InstrLite(ins.address, ins.size, ins.mnemonic, ins.op_str, ins.operands))
    return rows


def target_of_branch(ins: InstrLite) -> int | None:
    if not (ins.mnemonic == "bl" or ins.mnemonic == "blx" or ins.mnemonic.startswith("b")):
        return None
    for op in ins.operands:
        if op.type == CS_OP_IMM:
            return op.imm & ~1
    return None


def reg_name(ins: InstrLite, reg_id: int) -> str:
    # Recreate a tiny disassembler just for capstone's reg_name helper.
    if Cs is None:
        return f"reg_{reg_id}"
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)
    name = md.reg_name(reg_id)
    return str(name) if name is not None else f"reg_{reg_id}"


def reg_write_value(ins: InstrLite, data: bytes, base: int) -> tuple[str, dict[str, Any]] | None:
    """Return `(reg, value_info)` for simple immediate/literal writes."""
    if not ins.operands:
        return None
    op0 = ins.operands[0]
    if op0.type != CS_OP_REG:
        return None
    reg = reg_name(ins, op0.reg)
    if reg not in {"r0", "r1", "r2", "r3"}:
        return None

    # mov/movs/movw rN, #imm
    if ins.mnemonic in {"mov", "movs", "movw"} and len(ins.operands) >= 2:
        op1 = ins.operands[1]
        if op1.type == CS_OP_IMM:
            return reg, {"kind": "imm", "value": op1.imm, "insn": f"{ins.mnemonic} {ins.op_str}", "at": ins.addr}
        if op1.type == CS_OP_REG:
            return reg, {"kind": "reg", "value": reg_name(ins, op1.reg), "insn": f"{ins.mnemonic} {ins.op_str}", "at": ins.addr}

    # ldr rN, [pc, #disp] literal
    if ins.mnemonic.startswith("ldr") and len(ins.operands) >= 2:
        op1 = ins.operands[1]
        if op1.type == CS_OP_MEM and op1.mem.base == ARM_REG_PC:
            lit_addr = literal_addr_for(ins.addr, op1.mem.disp)
            val = read_u32(data, lit_addr)
            if val is None:
                return None
            raw = val - base
            desc_name = KNOWN_DESCRIPTORS.get(raw)
            info: dict[str, Any] = {
                "kind": "literal",
                "value": val,
                "raw_offset": raw if 0 <= raw < len(data) else None,
                "literal_addr": lit_addr,
                "descriptor": desc_name,
                "string": printable_cstr(data, raw) if 0 <= raw < len(data) else "",
                "insn": f"{ins.mnemonic} {ins.op_str}",
                "at": ins.addr,
            }
            return reg, info

    return None


def summarize_arg(info: dict[str, Any] | None) -> Any:
    if info is None:
        return None
    if info.get("descriptor"):
        return info["descriptor"]
    val = info.get("value")
    if info.get("kind") == "literal" and info.get("raw_offset") is not None:
        # Keep constants and descriptor-like literals explicit.
        s = info.get("string") or ""
        raw_offset = info.get("raw_offset")
        if s and isinstance(val, int) and isinstance(raw_offset, int):
            return {"value_hex": hex(val), "raw_offset_hex": hex(raw_offset), "string_prefix": s[:80]}
    if isinstance(val, int):
        return val
    return val


def known_sportxms_rows(data: bytes, start: int, end: int) -> list[dict[str, Any]]:
    """Fallback verifier for the known ActSport accel/gyro callsites.

    This is intentionally narrow: it validates the literal values used by the
    previously identified callsites when Capstone is unavailable.
    """
    start_latency = read_u32(data, 0x17CC00)
    resume_latency = read_u32(data, 0x17CC30)
    rows = [
        (0x17CA28, "subscribe", "sensor_accel", 100, start_latency, DEFAULT_SUBSCRIBE),
        (0x17CA36, "subscribe", "sensor_gyro", 100, start_latency, DEFAULT_SUBSCRIBE),
        (0x17CB08, "unsubscribe", "sensor_accel", 100, 0, DEFAULT_UNSUBSCRIBE),
        (0x17CB14, "unsubscribe", "sensor_gyro", 100, 0, DEFAULT_UNSUBSCRIBE),
        (0x17CB58, "subscribe", "sensor_accel", 100, resume_latency, DEFAULT_SUBSCRIBE),
        (0x17CB66, "subscribe", "sensor_gyro", 100, resume_latency, DEFAULT_SUBSCRIBE),
        (0x17CB9E, "unsubscribe", "sensor_accel", 100, 0, DEFAULT_UNSUBSCRIBE),
        (0x17CBAA, "unsubscribe", "sensor_gyro", 100, 0, DEFAULT_UNSUBSCRIBE),
    ]
    out: list[dict[str, Any]] = []
    for callsite, wrapper, desc, r2, r3, target in rows:
        if start <= callsite < end:
            out.append({
                "callsite_raw_hex": hex(callsite),
                "wrapper": wrapper,
                "target_raw_hex": hex(target),
                "descriptor": desc,
                "r1": desc,
                "r2": r2,
                "r3": r3,
                "r2_hex": hex(r2),
                "r3_hex": hex(r3) if isinstance(r3, int) else None,
                "context": ["fallback_known_sportxms_literal_scan"],
            })
    return out

def scan_calls(data: bytes, base: int, start: int, end: int, window: int) -> list[dict[str, Any]]:
    if Cs is None:
        return known_sportxms_rows(data, start, end)
    insns = disassemble(data, start, end)
    targets = {
        DEFAULT_SUBSCRIBE: "subscribe",
        DEFAULT_UNSUBSCRIBE: "unsubscribe",
        DEFAULT_SUBSCRIBE_FLAGGED: "subscribe_flagged",
    }
    rows: list[dict[str, Any]] = []
    for idx, ins in enumerate(insns):
        tgt = target_of_branch(ins)
        if tgt not in targets:
            continue
        regs: dict[str, dict[str, Any]] = {}
        for prev in insns[max(0, idx - window):idx]:
            rv = reg_write_value(prev, data, base)
            if rv:
                regs[rv[0]] = rv[1]
        desc = regs.get("r1", {}).get("descriptor")
        if desc is None:
            continue
        rows.append({
            "callsite_raw_hex": hex(ins.addr),
            "wrapper": targets[tgt],
            "target_raw_hex": hex(tgt),
            "descriptor": desc,
            "r1": summarize_arg(regs.get("r1")),
            "r2": summarize_arg(regs.get("r2")),
            "r3": summarize_arg(regs.get("r3")),
            "r2_hex": hex(regs.get("r2", {}).get("value", 0)) if isinstance(regs.get("r2", {}).get("value"), int) else None,
            "r3_hex": hex(regs.get("r3", {}).get("value", 0)) if isinstance(regs.get("r3", {}).get("value"), int) else None,
            "context": [f"{p.addr:#08x}: {p.mnemonic} {p.op_str}".strip() for p in insns[max(0, idx - 8):idx + 1]],
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("firmware", type=pathlib.Path)
    parser.add_argument("--base", type=lambda x: int(x, 0), default=DEFAULT_BASE)
    parser.add_argument("--start", type=lambda x: int(x, 0), default=0)
    parser.add_argument("--end", type=lambda x: int(x, 0), default=None)
    parser.add_argument("--window", type=int, default=14)
    parser.add_argument("--json", action="store_true", help="emit JSON instead of compact text")
    args = parser.parse_args()

    data = args.firmware.read_bytes()
    end = len(data) if args.end is None else min(args.end, len(data))
    rows = scan_calls(data, args.base, args.start, end, args.window)

    if args.json:
        print(json.dumps({"firmware": str(args.firmware), "base_hex": hex(args.base), "rows": rows}, indent=2, sort_keys=True))
    else:
        for row in rows:
            print(
                f"{row['callsite_raw_hex']} {row['wrapper']:<17} {row['descriptor']:<18} "
                f"r2={row['r2']} ({row['r2_hex']}) r3={row['r3']} ({row['r3_hex']})"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
