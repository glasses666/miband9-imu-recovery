#!/usr/bin/env python3
"""Probe Mi Band 9 n66nfc post-EOCD trailer as secp256k1/ECDSA.

This is a static/read-only probe. It does not patch, repack, connect to a band,
or call any OTA/DFU path.

The 2026-06-02 firmware static analysis found a micro-ecc/secp256k1-shaped
verification routine near `verify_package`, with the public key bytes loaded
from RAM globals. The first naive test used a linear SHA256 over all package
bytes excluding the final 80-byte trailer and failed. Re-reading the hash loop
showed that the firmware actually computes a stride digest:

    for every complete 1 MiB region before EOF-0x50: hash only its first 0x400 bytes
    then hash the final low-20-bit remainder contiguously

This script reports both the naive linear digest and the firmware-stride digest.
Under the firmware-stride digest, official n66nfc 1.3.206/1.3.210 trailers verify
as raw secp256k1 ECDSA(r,s) with the embedded verify_package public key.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

EOCD_SIG = b"PK\x05\x06"
TRAILER_LEN = 0x50
SECP256K1_P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
SECP256K1_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
SECP256K1_G = (
    0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
    0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8,
)

# Public key extracted from the verify_package-adjacent micro-ecc callsite in
# both official 1.3.206 and 1.3.210 vela_ap.bin images. It is public material,
# not a credential.
VERIFY_PACKAGE_PUBKEY_HEX = (
    "4c5ee3be1fc08452f8b7064cbec0bd13b65a9fced76acf9d87c7fba91add3dd5"
    "85356d12dbb8278e4b3c8b61c40b87c62ab613c1f0f69f8c21b90bde5856687e"
)

Point = Optional[tuple[int, int]]


def inv_mod(a: int, m: int) -> int:
    return pow(a % m, -1, m)


def point_add(p1: Point, p2: Point) -> Point:
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2 and (y1 + y2) % SECP256K1_P == 0:
        return None
    if p1 == p2:
        lam = (3 * x1 * x1) * inv_mod(2 * y1, SECP256K1_P) % SECP256K1_P
    else:
        lam = (y2 - y1) * inv_mod(x2 - x1, SECP256K1_P) % SECP256K1_P
    x3 = (lam * lam - x1 - x2) % SECP256K1_P
    y3 = (lam * (x1 - x3) - y1) % SECP256K1_P
    return x3, y3


def point_neg(p: Point) -> Point:
    if p is None:
        return None
    return p[0], (-p[1]) % SECP256K1_P


def scalar_mul(k: int, point: Point) -> Point:
    if point is None:
        return None
    k %= SECP256K1_N
    result: Point = None
    addend: Point = point
    while k:
        if k & 1:
            result = point_add(result, addend)
        addend = point_add(addend, addend)
        k >>= 1
    return result


def sqrt_mod_p(a: int) -> int:
    # secp256k1 p == 3 mod 4
    return pow(a % SECP256K1_P, (SECP256K1_P + 1) // 4, SECP256K1_P)


def is_on_curve(point: Point) -> bool:
    if point is None:
        return True
    x, y = point
    return (y * y - (x * x * x + 7)) % SECP256K1_P == 0


def parse_eocd(data: bytes) -> dict[str, Any]:
    eocd = data.rfind(EOCD_SIG)
    if eocd < 0 or eocd + 22 > len(data):
        raise ValueError("EOCD not found or truncated")
    comment_len = int.from_bytes(data[eocd + 20 : eocd + 22], "little")
    eocd_end = eocd + 22 + comment_len
    trailer = data[eocd_end:]
    return {
        "eocd_offset": eocd,
        "eocd_end": eocd_end,
        "comment_len": comment_len,
        "central_dir_size": int.from_bytes(data[eocd + 12 : eocd + 16], "little"),
        "central_dir_offset": int.from_bytes(data[eocd + 16 : eocd + 20], "little"),
        "trailer": trailer,
    }


def parse_signature(trailer: bytes) -> dict[str, Any]:
    if len(trailer) != TRAILER_LEN:
        return {
            "present": bool(trailer),
            "trailer_len": len(trailer),
            "valid_shape": False,
            "reason": "trailer length is not 80 bytes",
        }
    offset = trailer[4]
    sign_info = trailer[offset:]
    valid = trailer[:4] == b"\x00\x00\x00\x01" and offset == 0x10 and len(sign_info) == 64
    out: dict[str, Any] = {
        "present": True,
        "trailer_len": len(trailer),
        "magic4_hex": trailer[:4].hex(),
        "offset_from_head": offset,
        "reserved_hex": trailer[5:offset].hex(),
        "sign_info_len": len(sign_info),
        "valid_shape": valid,
    }
    if len(sign_info) == 64:
        out["r"] = f"{int.from_bytes(sign_info[:32], 'big'):064x}"
        out["s"] = f"{int.from_bytes(sign_info[32:], 'big'):064x}"
    return out


def firmware_stride_digest(data: bytes, end: int) -> bytes:
    """Reproduce the hash loop observed in `verify_package`.

    The firmware splits `padding_info_offset = file_size - 0x50` into
    high MiB count and low 20-bit remainder. For each complete MiB before the
    final remainder it reads/hashes only 0x400 bytes at that MiB boundary, then
    hashes the final low-20-bit remainder in ordinary 0x400-byte chunks plus a
    tail. This intentionally mirrors the observed code shape instead of a
    conventional full-file digest.
    """
    h = hashlib.sha256()
    high_mib = end >> 20
    low20 = end & 0xFFFFF
    for i in range(high_mib):
        off = i * 0x100000
        h.update(data[off : off + 0x400])
    off = high_mib * 0x100000
    whole_kib = low20 >> 10
    tail = low20 & 0x3FF
    for i in range(whole_kib):
        h.update(data[off + i * 0x400 : off + (i + 1) * 0x400])
    if tail:
        tail_start = off + whole_kib * 0x400
        h.update(data[tail_start : tail_start + tail])
    return h.digest()


def ecdsa_verify_raw_digest(pubkey: tuple[int, int], digest: bytes, r: int, s: int) -> bool:
    if not (1 <= r < SECP256K1_N and 1 <= s < SECP256K1_N):
        return False
    if not is_on_curve(pubkey):
        return False
    e = int.from_bytes(digest, "big")
    try:
        w = inv_mod(s, SECP256K1_N)
    except ValueError:
        return False
    u1 = (e * w) % SECP256K1_N
    u2 = (r * w) % SECP256K1_N
    point = point_add(scalar_mul(u1, SECP256K1_G), scalar_mul(u2, pubkey))
    return point is not None and (point[0] % SECP256K1_N) == r


def recover_ecdsa_pubkeys(digest: bytes, r: int, s: int) -> list[dict[str, Any]]:
    if not (1 <= r < SECP256K1_N and 1 <= s < SECP256K1_N):
        return []
    e = int.from_bytes(digest, "big")
    out: list[dict[str, Any]] = []
    r_inv = inv_mod(r, SECP256K1_N)
    for overflow in (0, 1):
        x = r + overflow * SECP256K1_N
        if x >= SECP256K1_P:
            continue
        y0 = sqrt_mod_p((x * x * x + 7) % SECP256K1_P)
        for parity, y in ((y0 & 1, y0), (((-y0) % SECP256K1_P) & 1, (-y0) % SECP256K1_P)):
            r_point = (x, y)
            if scalar_mul(SECP256K1_N, r_point) is not None:
                continue
            # Q = r^-1 * (sR - eG)
            q = scalar_mul(
                r_inv,
                point_add(scalar_mul(s, r_point), point_neg(scalar_mul(e, SECP256K1_G))),
            )
            if q is not None and ecdsa_verify_raw_digest(q, digest, r, s):
                out.append(
                    {
                        "overflow": overflow,
                        "parity": parity,
                        "pubkey_hex": f"{q[0]:064x}{q[1]:064x}",
                    }
                )
    return out


def audit(path: Path, pubkey_hex: str) -> dict[str, Any]:
    data = path.read_bytes()
    eocd = parse_eocd(data)
    trailer = eocd["trailer"]
    sig = parse_signature(trailer)
    bound = data[: eocd["eocd_end"]]
    linear_digest = hashlib.sha256(bound).digest()
    stride_digest = firmware_stride_digest(data, eocd["eocd_end"])
    pub_x = int(pubkey_hex[:64], 16)
    pub_y = int(pubkey_hex[64:], 16)
    result: dict[str, Any] = {
        "path": str(path),
        "file_size": len(data),
        "md5": hashlib.md5(data).hexdigest(),
        "sha256": hashlib.sha256(data).hexdigest(),
        "eocd_offset": eocd["eocd_offset"],
        "eocd_end": eocd["eocd_end"],
        "trailer_len": len(trailer),
        "linear_sha256_without_trailer": linear_digest.hex(),
        "firmware_stride_sha256": stride_digest.hex(),
        "firmware_stride_hashed_len": ((eocd["eocd_end"] >> 20) * 0x400) + (eocd["eocd_end"] & 0xFFFFF),
        "signature_shape": sig,
        "tested_pubkey_on_curve": is_on_curve((pub_x, pub_y)),
    }
    if sig.get("valid_shape"):
        r = int(sig["r"], 16)
        s = int(sig["s"], 16)
        result["linear_secp256k1_ecdsa_with_embedded_pubkey"] = ecdsa_verify_raw_digest(
            (pub_x, pub_y), linear_digest, r, s
        )
        result["firmware_stride_secp256k1_ecdsa_with_embedded_pubkey"] = ecdsa_verify_raw_digest(
            (pub_x, pub_y), stride_digest, r, s
        )
        result["linear_secp256k1_recovered_pubkeys"] = recover_ecdsa_pubkeys(linear_digest, r, s)
        result["firmware_stride_secp256k1_recovered_pubkeys"] = recover_ecdsa_pubkeys(stride_digest, r, s)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip", nargs="+", type=Path)
    parser.add_argument("--pubkey", default=VERIFY_PACKAGE_PUBKEY_HEX)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    result = {
        "model": "static verifier: trailer[16:80] as raw secp256k1 ECDSA(r,s); compare naive linear SHA256 vs firmware-stride SHA256",
        "embedded_verify_package_pubkey_hex": args.pubkey,
        "reports": [audit(p, args.pubkey) for p in args.zip],
    }
    if len(result["reports"]) >= 2:
        recovered_sets = [
            {x["pubkey_hex"] for x in r.get("firmware_stride_secp256k1_recovered_pubkeys", [])}
            for r in result["reports"]
        ]
        common = set.intersection(*recovered_sets) if recovered_sets else set()
        result["firmware_stride_recovered_pubkey_intersection"] = sorted(common)
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
