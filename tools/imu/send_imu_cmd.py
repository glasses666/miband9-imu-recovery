#!/usr/bin/env python3
"""
send_imu_cmd.py - PC 端热更新 IMU 命令脚本 (含 CRC 自动计算)

功能：
1. 自动计算 Xiaomi A5 协议 CRC16
2. 构造 SessionConfig (Type 2) 或 Data (Type 3) 包
3. 通过 ADB 发送命令到手机 App

前提：恢复版 APK 已安装，Gadgetbridge 的 Intent API debug commands 已允许。
默认发送到旁路测试包 nodomain.freeyourgadget.gadgetbridge.hfimu，不覆盖原 Gadgetbridge。
App 侧接收 action：nodomain.freeyourgadget.gadgetbridge.SEND_IMU_CMD

用法：
  python send_imu_cmd.py --init             # 发送默认 Session Config (重连/心跳)
  python send_imu_cmd.py --fuzz-fast        # 发送修改过参数的 Session Config (更低延迟)
  python send_imu_cmd.py --data "010203"    # 发送 Data 包 (Type 3) payload hex
  python send_imu_cmd.py --raw "a5a5..."    # 发送原始完整 hex (不重算 CRC)
"""

import subprocess
import argparse
import struct
import sys

def reverse32(n):
    """Reverses the bits of a 32-bit integer."""
    n = ((n >> 1) & 0x55555555) | ((n & 0x55555555) << 1)
    n = ((n >> 2) & 0x33333333) | ((n & 0x33333333) << 2)
    n = ((n >> 4) & 0x0F0F0F0F) | ((n & 0x0F0F0F0F) << 4)
    n = ((n >> 8) & 0x00FF00FF) | ((n & 0x00FF00FF) << 8)
    n = (n >> 16) | (n << 16)
    return n & 0xFFFFFFFF

def calculate_checksum(payload):
    """
    Calculates CRC-16/ARC (Poly=0x8005) as per XiaomiSppPacketV2.java
    """
    crc = 0
    for b in payload:
        for j in range(8):
            crc <<= 1
            # (crc >> 16) & 1 checking overflow bit of "16-bit register" (simulated in int32)
            bit_crc = (crc >> 16) & 1
            bit_in = (b >> j) & 1
            if (bit_crc ^ bit_in):
                crc ^= 0x8005

    # Java: return (Integer.reverse(crc) >>> 16)
    # Python: reverse 32-bit, then right shift 16
    rev = reverse32(crc)
    return (rev >> 16) & 0xFFFF

def build_packet(packet_type, seq, payload_bytes):
    """
    Constructs A5 packet: [A5 A5] [Type] [Seq] [Len_L] [Len_H] [CRC_L] [CRC_H] [Payload...]
    """
    header = b'\xa5\xa5'

    # Type (lower 4 bits) - Flags (upper 4 bits, assumed 0)
    type_byte = packet_type & 0x0F

    length = len(payload_bytes)

    # Calculate CRC of PAYLOAD ONLY
    crc = calculate_checksum(payload_bytes)

    # Struct format: < (Little Endian) B B H H
    # B: Type, B: Seq, H: Length, H: CRC
    meta = struct.pack('<BBHH', type_byte, seq, length, crc)

    full_packet = header + meta + payload_bytes
    return full_packet

def send_adb_broadcast(hex_cmd, package_name):
    """通过 ADB 广播发送命令到 Gadgetbridge"""
    action = "nodomain.freeyourgadget.gadgetbridge.SEND_IMU_CMD"
    adb_cmd = [
        "adb", "shell", "am", "broadcast", "-p", package_name,
        "-a", action,
        "--es", "hex", hex_cmd
    ]

    print(f"Sending via ADB to {package_name}: {hex_cmd[:30]}... ({len(hex_cmd)//2} bytes)")
    result = subprocess.run(adb_cmd, capture_output=True, text=True)

    if "Broadcast completed" in result.stdout:
        print("✓ Broadcast Success")
    else:
        print(f"✗ Broadcast Failed: {result.stdout} {result.stderr}")

def main():
    parser = argparse.ArgumentParser(description="Xiaomi IMU Command Sender (CRC16)")
    parser.add_argument("--init", action="store_true", help="Send default Session Config")
    parser.add_argument("--fuzz-fast", action="store_true", help="Send fast Session Config (1ms timeout)")
    parser.add_argument("--opcode", type=int, help="Custom OpCode for Session Packet (Default: 1)")
    parser.add_argument("--data", type=str, help="Send Data packet (Hex Payload)")
    parser.add_argument("--raw", type=str, help="Send raw hex packet (no build/crc)")
    parser.add_argument("--type", type=int, default=3, help="Packet Type for --data (Default: 3, use 2 for Session)")
    parser.add_argument("--package", default="nodomain.freeyourgadget.gadgetbridge.hfimu", help="Target Android package")

    args = parser.parse_args()

    packet = None

    if args.raw:
        packet = bytes.fromhex(args.raw)

    elif args.init:
        # CMD_INIT_DEFAULT payload (without Type/Seq/Len/CRC headers)
        # Type 2 = Session Config
        # OpCode 1 = Start Session
        # Payload structure: [OpCode] [Key1] [Len1] [Val1] ...

        base_payload = bytes.fromhex("01030001000002020000fc03020020000402001027") # Keys without OpCode
        op = args.opcode if args.opcode is not None else 1
        payload = bytes([op]) + base_payload

        packet = build_packet(2, 0, payload)

    elif args.fuzz_fast:
        # Altered Payload:
        # Key 3 (Win): 20 00 -> 01 00 (Window size 1)
        # Key 4 (Timeout): 10 27 (10000) -> 0a 00 (10ms)

        base_payload = bytes.fromhex("01030001000002020000fc03020001000402000a00")
        op = args.opcode if args.opcode is not None else 1
        payload = bytes([op]) + base_payload

        packet = build_packet(2, 0, payload)

    elif args.data:
        # Send generic Data Packet (Type 3 by default, or custom)
        payload = bytes.fromhex(args.data)
        packet = build_packet(args.type, 0, payload)

    else:
        parser.print_help()
        return

    if packet:
        hex_str = packet.hex()
        print(f"Packet Constructed (CRC Calculated): {hex_str}")
        send_adb_broadcast(hex_str, args.package)

if __name__ == "__main__":
    main()
