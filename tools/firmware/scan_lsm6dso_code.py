#!/usr/bin/env python3
"""Scan a local firmware binary for likely LSM6DSO WHO_AM_I checks.

Public-safe helper: pass the firmware path explicitly instead of hardcoding a
private local artifact path.

Example:
    python tools/firmware/scan_lsm6dso_code.py /path/to/vela_ap.bin
"""

from __future__ import annotations

import argparse
from pathlib import Path

from capstone import CS_ARCH_ARM, CS_MODE_THUMB, Cs
from capstone.arm import ARM_OP_IMM


BASE_ADDR = 0x1FBC0000


def scan_lsm6dso_check(file_path: str, base_addr: int = BASE_ADDR) -> int:
    code = Path(file_path).read_bytes()

    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    md.detail = True

    print("Scanning for LSM6DSO checks (CMP Rx, #0x6C)...")
    hits = 0
    for insn in md.disasm(code, base_addr):
        if insn.mnemonic != "cmp" or len(insn.operands) < 2:
            continue
        op2 = insn.operands[1]
        if op2.type == ARM_OP_IMM and op2.imm == 0x6C:
            print(
                f"[HIT] 0x{insn.address:X}: {insn.mnemonic} {insn.op_str} "
                "(possible WHO_AM_I check)"
            )
            hits += 1

    print(f"Total hits: {hits}")
    return hits


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("firmware", help="Path to firmware binary, e.g. vela_ap.bin")
    parser.add_argument("--base-addr", default=hex(BASE_ADDR), help="Thumb disassembly base address")
    args = parser.parse_args()
    scan_lsm6dso_check(args.firmware, int(str(args.base_addr), 0))


if __name__ == "__main__":
    main()
