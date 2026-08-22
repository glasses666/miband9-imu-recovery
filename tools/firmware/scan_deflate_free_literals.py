#!/usr/bin/env python3
"""Scan a ZIP deflate member for literal-addressable free-variable regions.

This is a local/static helper for the Mi Band 9 n66nfc OTA research. It never
contacts a device and never produces an installable package. It parses the raw
DEFLATE stream of one ZIP entry, maps inflated offsets back to literal/match
tokens, and reports candidate zero-runs whose bytes are directly emitted as
literal tokens in unsigned outer-ZIP byte ranges.
"""

from __future__ import annotations

import argparse
import json
import struct
import zipfile
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

LENGTH_BASE = [
    3, 4, 5, 6, 7, 8, 9, 10,
    11, 13, 15, 17, 19, 23, 27, 31,
    35, 43, 51, 59, 67, 83, 99, 115,
    131, 163, 195, 227, 258,
]
LENGTH_EXTRA = [
    0, 0, 0, 0, 0, 0, 0, 0,
    1, 1, 1, 1, 2, 2, 2, 2,
    3, 3, 3, 3, 4, 4, 4, 4,
    5, 5, 5, 5, 0,
]
DIST_BASE = [
    1, 2, 3, 4, 5, 7, 9, 13,
    17, 25, 33, 49, 65, 97, 129, 193,
    257, 385, 513, 769, 1025, 1537, 2049, 3073,
    4097, 6145, 8193, 12289, 16385, 24577,
]
DIST_EXTRA = [
    0, 0, 0, 0, 1, 1, 2, 2,
    3, 3, 4, 4, 5, 5, 6, 6,
    7, 7, 8, 8, 9, 9, 10, 10,
    11, 11, 12, 12, 13, 13,
]
CL_ORDER = [16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15]


def reverse_bits(value: int, width: int) -> int:
    out = 0
    for _ in range(width):
        out = (out << 1) | (value & 1)
        value >>= 1
    return out


class BitReader:
    def __init__(self, data: bytes):
        self.data = data
        self.bitpos = 0

    def read(self, n: int) -> int:
        value = 0
        for i in range(n):
            byte_i = self.bitpos >> 3
            if byte_i >= len(self.data):
                raise EOFError("deflate bitstream ended early")
            bit_i = self.bitpos & 7
            value |= ((self.data[byte_i] >> bit_i) & 1) << i
            self.bitpos += 1
        return value

    def align_byte(self) -> None:
        if self.bitpos & 7:
            self.bitpos += 8 - (self.bitpos & 7)


class Huffman:
    def __init__(self, lengths: Sequence[int]):
        self.lengths = list(lengths)
        self.max_len = max(self.lengths) if self.lengths else 0
        bl_count: Dict[int, int] = {}
        for length in self.lengths:
            if length:
                bl_count[length] = bl_count.get(length, 0) + 1
        code = 0
        next_code: Dict[int, int] = {}
        for bits in range(1, self.max_len + 1):
            code = (code + bl_count.get(bits - 1, 0)) << 1
            next_code[bits] = code
        self.table: Dict[Tuple[int, int], int] = {}
        self.symbol_to_wire: Dict[int, Tuple[int, int]] = {}
        for sym, length in enumerate(self.lengths):
            if not length:
                continue
            canonical = next_code[length]
            next_code[length] += 1
            wire = reverse_bits(canonical, length)
            self.table[(wire, length)] = sym
            self.symbol_to_wire[sym] = (wire, length)

    def decode(self, br: BitReader) -> Tuple[int, int, int, int]:
        code = 0
        start = br.bitpos
        for length in range(1, self.max_len + 1):
            code |= br.read(1) << (length - 1)
            sym = self.table.get((code, length))
            if sym is not None:
                return sym, start, br.bitpos, length
        raise ValueError(f"invalid huffman code at bit {start}")


@dataclass
class Token:
    kind: str
    out_start: int
    out_end: int
    bit_start: int
    bit_end: int
    block: int
    symbol: Optional[int] = None
    length: Optional[int] = None
    distance: Optional[int] = None
    source_start: Optional[int] = None
    lit_code_len: Optional[int] = None


def fixed_tables() -> Tuple[List[int], List[int]]:
    lit = [0] * 288
    for i in range(0, 144):
        lit[i] = 8
    for i in range(144, 256):
        lit[i] = 9
    for i in range(256, 280):
        lit[i] = 7
    for i in range(280, 288):
        lit[i] = 8
    dist = [5] * 32
    return lit, dist


def read_dynamic_tables(br: BitReader) -> Tuple[List[int], List[int]]:
    hlit = br.read(5) + 257
    hdist = br.read(5) + 1
    hclen = br.read(4) + 4
    cl_lengths = [0] * 19
    for i in range(hclen):
        cl_lengths[CL_ORDER[i]] = br.read(3)
    cl_huff = Huffman(cl_lengths)
    lengths: List[int] = []
    total = hlit + hdist
    while len(lengths) < total:
        sym, _, _, _ = cl_huff.decode(br)
        if sym <= 15:
            lengths.append(sym)
        elif sym == 16:
            if not lengths:
                raise ValueError("repeat previous length with no previous length")
            repeat = br.read(2) + 3
            lengths.extend([lengths[-1]] * repeat)
        elif sym == 17:
            repeat = br.read(3) + 3
            lengths.extend([0] * repeat)
        elif sym == 18:
            repeat = br.read(7) + 11
            lengths.extend([0] * repeat)
        else:
            raise ValueError(f"bad code length symbol {sym}")
    return lengths[:hlit], lengths[hlit:]


def parse_deflate(data: bytes) -> Tuple[bytes, List[Token], array, array, array, List[dict]]:
    br = BitReader(data)
    out = bytearray()
    token_idx = array("i")
    source_idx = array("i")
    root_idx = array("i")
    tokens: List[Token] = []
    blocks: List[dict] = []
    block_no = 0

    while True:
        final = br.read(1)
        btype = br.read(2)
        if btype == 0:
            br.align_byte()
            length = br.read(16)
            nlength = br.read(16)
            if (length ^ 0xFFFF) != nlength:
                raise ValueError("stored block LEN/NLEN mismatch")
            bit_start = br.bitpos
            byte_start = br.bitpos >> 3
            chunk = data[byte_start:byte_start + length]
            br.bitpos += length * 8
            block = {"block": block_no, "type": "stored", "lit_lengths": None}
            blocks.append(block)
            for b in chunk:
                idx = len(tokens)
                pos = len(out)
                tokens.append(Token("literal", pos, pos + 1, bit_start, br.bitpos, block_no, symbol=b, lit_code_len=8))
                out.append(b)
                token_idx.append(idx)
                source_idx.append(-1)
                root_idx.append(pos)
        elif btype in (1, 2):
            if btype == 1:
                lit_lengths, dist_lengths = fixed_tables()
                btype_name = "fixed"
            else:
                lit_lengths, dist_lengths = read_dynamic_tables(br)
                btype_name = "dynamic"
            lit_h = Huffman(lit_lengths)
            dist_h = Huffman(dist_lengths)
            same_len_counts: Dict[int, int] = {}
            lit_symbols_by_len: Dict[int, List[int]] = {}
            for sym, length in enumerate(lit_lengths[:256]):
                if length:
                    same_len_counts[length] = same_len_counts.get(length, 0) + 1
                    lit_symbols_by_len.setdefault(length, []).append(sym)
            blocks.append({
                "block": block_no,
                "type": btype_name,
                "bit_start": br.bitpos,
                "lit_same_len_counts": same_len_counts,
                "lit_symbols_by_len": lit_symbols_by_len,
                "lit_symbol_to_wire": lit_h.symbol_to_wire,
            })
            while True:
                sym, code_start, code_end, code_len = lit_h.decode(br)
                if sym < 256:
                    idx = len(tokens)
                    pos = len(out)
                    tokens.append(Token("literal", pos, pos + 1, code_start, code_end, block_no, symbol=sym, lit_code_len=code_len))
                    out.append(sym)
                    token_idx.append(idx)
                    source_idx.append(-1)
                    root_idx.append(pos)
                elif sym == 256:
                    tokens.append(Token("end", len(out), len(out), code_start, code_end, block_no, symbol=sym))
                    break
                else:
                    li = sym - 257
                    if not (0 <= li < len(LENGTH_BASE)):
                        raise ValueError(f"bad length symbol {sym}")
                    length = LENGTH_BASE[li] + (br.read(LENGTH_EXTRA[li]) if LENGTH_EXTRA[li] else 0)
                    dist_sym, _, _, _ = dist_h.decode(br)
                    if not (0 <= dist_sym < len(DIST_BASE)):
                        raise ValueError(f"bad distance symbol {dist_sym}")
                    distance = DIST_BASE[dist_sym] + (br.read(DIST_EXTRA[dist_sym]) if DIST_EXTRA[dist_sym] else 0)
                    token_bit_end = br.bitpos
                    idx = len(tokens)
                    pos = len(out)
                    src_start = pos - distance
                    if src_start < 0:
                        raise ValueError("match distance before output start")
                    tokens.append(Token("match", pos, pos + length, code_start, token_bit_end, block_no,
                                        symbol=sym, length=length, distance=distance, source_start=src_start))
                    for _ in range(length):
                        src = len(out) - distance
                        b = out[src]
                        out.append(b)
                        token_idx.append(idx)
                        source_idx.append(src)
                        root_idx.append(root_idx[src])
        else:
            raise ValueError("reserved deflate block type")
        block_no += 1
        if final:
            break
    return bytes(out), tokens, token_idx, source_idx, root_idx, blocks


def local_data_offset(raw: bytes, info: zipfile.ZipInfo) -> int:
    off = info.header_offset
    if raw[off:off + 4] != b"PK\x03\x04":
        raise ValueError("bad local file header")
    fnlen, extralen = struct.unpack_from("<HH", raw, off + 26)
    return off + 30 + fnlen + extralen


def signed_windows(zip_size: int) -> List[Tuple[int, int]]:
    padding_info_offset = zip_size - 0x50
    full = padding_info_offset >> 20
    windows = [(i << 20, (i << 20) + 0x400) for i in range(full)]
    windows.append((full << 20, padding_info_offset))
    return windows


def overlaps_any(start: int, end: int, windows: Sequence[Tuple[int, int]]) -> bool:
    return any(not (end <= a or start >= b) for a, b in windows)


def token_outer_byte_range(local_off: int, tok: Token) -> Tuple[int, int]:
    return local_off + (tok.bit_start >> 3), local_off + ((tok.bit_end + 7) >> 3)


def token_unsigned(local_off: int, tok: Token, windows: Sequence[Tuple[int, int]]) -> bool:
    a, b = token_outer_byte_range(local_off, tok)
    return not overlaps_any(a, b, windows)


def find_runs(data: bytes, byte: int = 0, min_len: int = 128) -> List[Tuple[int, int]]:
    runs = []
    i = 0
    n = len(data)
    while i < n:
        if data[i] != byte:
            i += 1
            continue
        j = i + 1
        while j < n and data[j] == byte:
            j += 1
        if j - i >= min_len:
            runs.append((i, j))
        i = j
    return runs


def chain_for_offset(off: int, token_idx: array, source_idx: array, root_idx: array, tokens: Sequence[Token], max_depth: int = 12) -> List[dict]:
    chain = []
    cur = off
    seen = set()
    for _ in range(max_depth):
        if cur in seen or cur < 0 or cur >= len(token_idx):
            break
        seen.add(cur)
        tok = tokens[token_idx[cur]]
        chain.append({
            "out_off": hex(cur),
            "byte_token": tok.kind,
            "token_out": [hex(tok.out_start), hex(tok.out_end)],
            "token_bits": [tok.bit_start, tok.bit_end],
            "symbol": tok.symbol,
            "literal_code_len": tok.lit_code_len,
            "source": None if source_idx[cur] < 0 else hex(source_idx[cur]),
        })
        if source_idx[cur] < 0:
            break
        cur = source_idx[cur]
    return chain


def summarize_literal_zero_windows(
    data: bytes,
    tokens: Sequence[Token],
    token_idx: array,
    source_idx: array,
    local_off: int,
    windows: Sequence[Tuple[int, int]],
    blocks: Sequence[dict],
    min_len: int,
    limit: int,
) -> List[dict]:
    out = []
    n = len(data)
    i = 0
    while i < n:
        tok = tokens[token_idx[i]]
        if data[i] != 0 or tok.kind != "literal" or not token_unsigned(local_off, tok, windows):
            i += 1
            continue
        j = i + 1
        while j < n:
            tj = tokens[token_idx[j]]
            if data[j] != 0 or tj.kind != "literal" or not token_unsigned(local_off, tj, windows):
                break
            j += 1
        if j - i >= min_len:
            sample_toks = [tokens[token_idx[k]] for k in range(i, min(j, i + 8))]
            same_len_counts = []
            for st in sample_toks:
                block = blocks[st.block]
                count = block.get("lit_same_len_counts", {}).get(st.lit_code_len, 0)
                same_len_counts.append(count)
            out.append({
                "start": hex(i),
                "end": hex(j),
                "len": j - i,
                "token_bit_ranges_sample": [[t.bit_start, t.bit_end] for t in sample_toks],
                "outer_byte_ranges_sample": [[hex(a), hex(b)] for a, b in (token_outer_byte_range(local_off, t) for t in sample_toks)],
                "literal_code_lengths_sample": [t.lit_code_len for t in sample_toks],
                "same_code_length_symbol_counts_sample": same_len_counts,
            })
            if len(out) >= limit:
                break
        i = max(j, i + 1)
    return out


def summarize_zero_runs(
    data: bytes,
    tokens: Sequence[Token],
    token_idx: array,
    source_idx: array,
    root_idx: array,
    local_off: int,
    windows: Sequence[Tuple[int, int]],
    min_len: int,
    limit: int,
) -> List[dict]:
    rows = []
    for s, e in sorted(find_runs(data, 0, min_len), key=lambda p: -(p[1] - p[0]))[:limit]:
        total = e - s
        literal = 0
        match = 0
        unsigned_literal = 0
        roots = {}
        for pos in range(s, e):
            tok = tokens[token_idx[pos]]
            if tok.kind == "literal":
                literal += 1
                if token_unsigned(local_off, tok, windows):
                    unsigned_literal += 1
            else:
                match += 1
            roots[root_idx[pos]] = roots.get(root_idx[pos], 0) + 1
        top_roots = sorted(roots.items(), key=lambda kv: -kv[1])[:6]
        rows.append({
            "start": hex(s),
            "end": hex(e),
            "len": total,
            "immediate_literal_bytes": literal,
            "immediate_match_bytes": match,
            "unsigned_immediate_literal_bytes": unsigned_literal,
            "top_root_offsets": [[hex(k), v] for k, v in top_roots],
            "first_byte_chain": chain_for_offset(s, token_idx, source_idx, root_idx, tokens, 8),
        })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("zip", type=Path)
    ap.add_argument("--entry", default="vela_ap.bin")
    ap.add_argument("--targets", default="0x1779bc,0x1779bd,0x1779be,0x1779bf")
    ap.add_argument("--min-run", type=int, default=128)
    ap.add_argument("--literal-window-min", type=int, default=4)
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args()

    raw = args.zip.read_bytes()
    sw = signed_windows(len(raw))
    with zipfile.ZipFile(args.zip) as zf:
        info = zf.getinfo(args.entry)
        local_off = local_data_offset(raw, info)
        comp = raw[local_off:local_off + info.compress_size]
        inflated, tokens, token_idx, source_idx, root_idx, blocks = parse_deflate(comp)
        expected = zf.read(args.entry)
        if inflated != expected:
            raise SystemExit("parsed deflate output does not match zipfile output")

    targets = [int(x, 0) for x in args.targets.split(",") if x.strip()]
    target_rows = []
    for target in targets:
        tok = tokens[token_idx[target]]
        outer = token_outer_byte_range(local_off, tok)
        target_rows.append({
            "offset": hex(target),
            "value": hex(inflated[target]),
            "kind": tok.kind,
            "token_out": [hex(tok.out_start), hex(tok.out_end)],
            "token_bits": [tok.bit_start, tok.bit_end],
            "outer_byte_range": [hex(outer[0]), hex(outer[1])],
            "outer_bytes_unsigned": not overlaps_any(*outer, sw),
            "literal_code_len": tok.lit_code_len,
            "chain": chain_for_offset(target, token_idx, source_idx, root_idx, tokens),
        })

    result = {
        "zip": str(args.zip),
        "entry": args.entry,
        "entry_size": len(inflated),
        "compressed_size": len(comp),
        "local_data_offset": hex(local_off),
        "token_count": len(tokens),
        "block_count": len(blocks),
        "signed_window_count": len(sw),
        "targets": target_rows,
        "long_zero_runs": summarize_zero_runs(inflated, tokens, token_idx, source_idx, root_idx, local_off, sw, args.min_run, args.limit),
        "direct_literal_zero_windows": summarize_literal_zero_windows(
            inflated, tokens, token_idx, source_idx, local_off, sw, blocks, args.literal_window_min, args.limit
        ),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
