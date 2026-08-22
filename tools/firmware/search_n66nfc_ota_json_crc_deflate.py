#!/usr/bin/env python3
"""Search a fixed-size ota.json CRC/DEFLATE variant for n66nfc OTA research.

This is a local/static helper. It does not contact a device and does not produce
an installable OTA by itself. It searches JSON whitespace-only byte replacements
that:

- keep ota.json length unchanged,
- replace the old AP MD5 with a new AP MD5,
- keep the original ZIP central-directory CRC32,
- keep the JSON valid, and
- recompress as raw DEFLATE within the original ZIP entry size.

The intended use is the Mi Band 9 NFC n66nfc 1.3.206 signed-gap patch research,
where central directory / EOCD / post-EOCD trailer bytes are not movable.
"""

from __future__ import annotations

import argparse
import itertools
import json
import random
import sys
import time
import zlib
import zipfile
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple


def crc32_u32(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


def raw_zlib(data: bytes, level: int = 9) -> bytes:
    co = zlib.compressobj(level, zlib.DEFLATED, -15)
    return co.compress(data) + co.flush()


def raw_zopfli(data: bytes, iterations: int) -> bytes:
    try:
        import zopfli.zlib  # type: ignore
    except Exception as exc:  # pragma: no cover - environment guard
        raise SystemExit("Missing Python package 'zopfli'. Install in an isolated venv, e.g. `python -m pip install zopfli`.") from exc
    wrapped = zopfli.zlib.compress(data, numiterations=iterations)
    # zlib wrapper = 2 byte header + raw deflate + 4 byte Adler32 trailer.
    raw = wrapped[2:-4]
    if zlib.decompress(raw, -15) != data:
        raise ValueError("zopfli raw stream failed round-trip")
    return raw


def replace_unique(data: bytes, old: bytes, new: bytes) -> bytes:
    if len(old) != len(new):
        raise ValueError("old/new MD5 byte strings must have equal length")
    count = data.count(old)
    if count != 1:
        raise ValueError(f"old MD5 occurrence count must be 1, got {count}")
    return data.replace(old, new, 1)


def collect_json_whitespace_slots(data: bytes) -> List[Tuple[int, int, int]]:
    """Return conservative binary whitespace alternatives outside strings.

    Existing spaces toggle to tabs; existing newlines toggle to carriage returns.
    Existing tabs/CR toggle back to space/LF. Any byte inside a JSON string is
    excluded by a small string-state scanner.
    """
    slots: List[Tuple[int, int, int]] = []
    in_string = False
    escaped = False
    for i, ch in enumerate(data):
        if in_string:
            if escaped:
                escaped = False
            elif ch == 0x5C:  # backslash
                escaped = True
            elif ch == 0x22:  # quote
                in_string = False
            continue
        if ch == 0x22:
            in_string = True
        elif ch in (0x20, 0x09, 0x0A, 0x0D):
            if ch == 0x20:
                alt = 0x09
            elif ch == 0x09:
                alt = 0x20
            elif ch == 0x0A:
                alt = 0x0D
            else:
                alt = 0x0A
            slots.append((i, ch, alt))
    return slots


def slot_deltas(base: bytes, slots: Sequence[Tuple[int, int, int]]) -> List[Tuple[int, int, int, int]]:
    base_crc = crc32_u32(base)
    tmp = bytearray(base)
    rows: List[Tuple[int, int, int, int]] = []
    for pos, old, alt in slots:
        if tmp[pos] != old:
            raise ValueError("slot byte mismatch")
        tmp[pos] = alt
        delta = crc32_u32(bytes(tmp)) ^ base_crc
        tmp[pos] = old
        rows.append((pos, old, alt, delta))
    return rows


def combo_xors(items: Sequence[Tuple[int, int, int, int]], max_weight: int) -> Iterable[Tuple[int, Tuple[int, ...]]]:
    yield 0, ()
    for weight in range(1, max_weight + 1):
        for combo in itertools.combinations(range(len(items)), weight):
            x = 0
            for idx in combo:
                x ^= items[idx][3]
            yield x, combo


def find_mitm_solutions(
    items: Sequence[Tuple[int, int, int, int]],
    need: int,
    left_max_weight: int,
    right_max_weight: int,
    cap: int,
) -> List[Tuple[int, ...]]:
    mid = len(items) // 2
    left = items[:mid]
    right = items[mid:]
    # One shortest assignment per left xor is enough for broad candidate search.
    table = {}
    for x, combo in combo_xors(left, left_max_weight):
        table.setdefault(x, combo)
    out: List[Tuple[int, ...]] = []
    for xr, cr in combo_xors(right, right_max_weight):
        cl = table.get(need ^ xr)
        if cl is None:
            continue
        out.append(cl + tuple(mid + i for i in cr))
        if len(out) >= cap:
            break
    return out


def apply_solution(base: bytes, items: Sequence[Tuple[int, int, int, int]], solution: Sequence[int]) -> bytes:
    b = bytearray(base)
    for idx in solution:
        pos, old, alt, _ = items[idx]
        if b[pos] != old:
            raise ValueError("candidate slot byte mismatch")
        b[pos] = alt
    return bytes(b)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("zip", type=Path)
    ap.add_argument("--entry", default="ota.json")
    ap.add_argument("--old-md5", required=True)
    ap.add_argument("--new-md5", required=True)
    ap.add_argument("--target-size", type=int, default=None, help="Raw DEFLATE compressed-size budget. Defaults to ZIP entry compress_size.")
    ap.add_argument("--subset-size", type=int, default=300)
    ap.add_argument("--random-batches", type=int, default=80)
    ap.add_argument("--seed", type=int, default=13206)
    ap.add_argument("--left-max-weight", type=int, default=2)
    ap.add_argument("--right-max-weight", type=int, default=3)
    ap.add_argument("--zopfli-iterations", type=int, default=80)
    ap.add_argument("--output-json", type=Path)
    ap.add_argument("--output-raw-deflate", type=Path)
    args = ap.parse_args()

    old = args.old_md5.encode("ascii")
    new = args.new_md5.encode("ascii")
    with zipfile.ZipFile(args.zip) as zf:
        info = zf.getinfo(args.entry)
        orig = zf.read(args.entry)
    target_crc = info.CRC
    target_size = args.target_size or info.compress_size
    base = replace_unique(orig, old, new)
    json.loads(base.decode("utf-8"))

    slots = collect_json_whitespace_slots(base)
    items_all = slot_deltas(base, slots)
    need = crc32_u32(base) ^ target_crc
    rng = random.Random(args.seed)

    print(json.dumps({
        "entry": args.entry,
        "orig_len": len(orig),
        "orig_crc": hex(target_crc),
        "orig_compress_size": info.compress_size,
        "base_crc": hex(crc32_u32(base)),
        "crc_need_xor": hex(need),
        "whitespace_slots": len(slots),
        "base_zlib_raw_len": len(raw_zlib(base)),
        "base_zopfli_raw_len": len(raw_zopfli(base, args.zopfli_iterations)),
        "target_size": target_size,
    }, ensure_ascii=False), flush=True)

    batches: List[Tuple[str, int, Sequence[Tuple[int, int, int, int]]]] = []
    for start in range(0, min(len(items_all), args.subset_size * 3), max(1, args.subset_size // 2)):
        sub = items_all[start:start + args.subset_size]
        if len(sub) >= 16:
            batches.append(("contig", start, sub))
    for i in range(args.random_batches):
        size = min(args.subset_size, len(items_all))
        batches.append(("rand", i, rng.sample(items_all, size)))

    best: List[Tuple[int, int, Tuple[int, ...], bytes]] = []
    seen = set()
    t0 = time.time()
    for kind, batch_id, sub in batches:
        sols = find_mitm_solutions(sub, need, args.left_max_weight, args.right_max_weight, cap=50)
        if not sols:
            continue
        print(json.dumps({"batch_hit": kind, "id": batch_id, "solutions": len(sols), "elapsed_s": round(time.time() - t0, 3)}), flush=True)
        for sol in sols:
            key = tuple(sorted(sub[i][0] for i in sol))
            if key in seen:
                continue
            seen.add(key)
            cand = apply_solution(base, sub, sol)
            if crc32_u32(cand) != target_crc:
                continue
            try:
                json.loads(cand.decode("utf-8"))
            except Exception:
                continue
            zlen = len(raw_zlib(cand))
            best.append((zlen, len(sol), key, cand))
        best.sort(key=lambda row: (row[0], row[1], row[2]))
        best = best[:200]

    finals: List[Tuple[int, int, int, Tuple[int, ...], bytes, bytes]] = []
    for zlib_len, weight, key, cand in best[:80]:
        raw = raw_zopfli(cand, args.zopfli_iterations)
        finals.append((len(raw), zlib_len, weight, key, cand, raw))
        print(json.dumps({"zopfli_raw_len": len(raw), "zlib_raw_len": zlib_len, "weight": weight, "positions": list(key)}), flush=True)
    finals.sort(key=lambda row: (row[0], row[1], row[2], row[3]))
    if not finals:
        print(json.dumps({"result": "no_crc_hit_candidates"}))
        return 2

    zopfli_len, zlib_len, weight, key, cand, raw = finals[0]
    result = {
        "result": "found" if zopfli_len <= target_size else "found_crc_but_too_large",
        "zopfli_raw_len": zopfli_len,
        "zlib_raw_len": zlib_len,
        "weight": weight,
        "positions": list(key),
        "crc": hex(crc32_u32(cand)),
        "json_valid": True,
        "contains_new_md5": new.decode("ascii") in cand.decode("ascii"),
        "target_size": target_size,
    }
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_bytes(cand)
        result["output_json"] = str(args.output_json)
    if args.output_raw_deflate:
        args.output_raw_deflate.parent.mkdir(parents=True, exist_ok=True)
        args.output_raw_deflate.write_bytes(raw)
        result["output_raw_deflate"] = str(args.output_raw_deflate)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if zopfli_len <= target_size else 1


if __name__ == "__main__":
    raise SystemExit(main())
