import subprocess
import threading
import queue
import re
import struct
import time
import sys
import signal

# Configuration
# Configuration
ADB_CMD = ["adb", "logcat"] # Capture EVERYTHING for debugging
# ADB_CMD = ["adb", "logcat", "-v", "raw", "MI_IMU_RAW_RX:I", "*:S"]
FILTER_TAG = "nodomain.freeyourgadget.gadgetbridge" # Simple string filter
CMD_INIT_HEX = "a5a5020016001d4d0101030001000002020000fc03020020000402001027"

# Tracking for sampling rate
packet_count = 0
last_time = time.time()
start_time = time.time()

def parse_imu_packet(payload):
    global packet_count, last_time
    if len(payload) < 14: return

    packet_count += 1
    now = time.time()

    # Calculate Hertz every 1 second
    if (now - last_time) > 1.0:
        elapsed = now - last_time
        hz = (packet_count - getattr(parse_imu_packet, 'last_count', 0)) / elapsed
        parse_imu_packet.last_count = packet_count
        total_avg_hz = packet_count / (now - start_time)
        print(f"\r[IMU STATS] Packets: {packet_count} | Current: {hz:.2f} Hz | Avg: {total_avg_hz:.2f} Hz", end="")
        last_time = now

    try:
        shorts = struct.unpack("<7h", payload[:14])
        seq = shorts[0]
        accel = shorts[1:4] # X, Y, Z
        gyro = shorts[4:7]  # X, Y, Z

        # Only print full data occasionally to show it's live
        if packet_count % 20 == 0:
            print(f"\n[IMU] Seq={seq:05d} | Accel={accel} | Gyro={gyro}")
    except Exception as e:
        pass
parse_imu_packet.last_count = 0

def process_stream_buffer(stream_buffer):
    """
    Scans buffer for A5 A5 packets.
    """
    ptr = 0
    buffer_len = len(stream_buffer)

    while ptr < buffer_len - 8:
        # Optimization: Scan for 0xA5 using fast string methods if possible,
        # but bytes find is good.
        idx = stream_buffer.find(b'\xa5\xa5', ptr)
        if idx == -1:
            # Discard all but last few bytes just in case split header
            return stream_buffer[-1:]

        ptr = idx

        # Check if we have header
        if ptr + 8 > buffer_len:
            break # Wait for more data

        # Parse Header
        # Header: A5 A5 [Type:2] [Len:2] [CRC:2?]
        try:
            ptype, plen, pcrc = struct.unpack("<HHH", stream_buffer[ptr+2:ptr+8])
        except:
             ptr += 2
             continue

        total_packet_len = 8 + plen

        if ptr + total_packet_len > buffer_len:
            break # Wait for rest of packet

        # Extract Packet
        payload = stream_buffer[ptr+8 : ptr+total_packet_len]

        # High-frequency IMU packets seem to be Type 0x1103, 0x1203, 0x1303, etc. (upper nibble = sequence)
        if ptype == 0x0003 or (ptype & 0x00FF) == 0x03:  # Any type ending in 03
            if plen >= 14:  # Has enough bytes for IMU data
                parse_imu_packet(payload)
        elif ptype == 0x0002:
            print(f"\n[CMD RESP] Type=0x0002 Len={plen} Hex={payload.hex()}")
        elif (ptype & 0x00FF) == 0x01:  # Control/KeepAlive packets
            pass  # Silent
        else:
            print(f"\n[PKT] Type=0x{ptype:04x} Len={plen}")  # Debug: show unknown types

        ptr += total_packet_len

    return stream_buffer[ptr:]

def main():
    print(f"Starting ADB Logcat Monitor...")
    print(f"Waiting for tag: MI_IMU_RAW_RX")
    print(f"Press Ctrl+C to stop.")

    process = subprocess.Popen(ADB_CMD, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    stream_buffer = b""

    try:
        while True:
            line = process.stdout.readline()
            if not line: break

            line_str = line.decode('utf-8', errors='replace').strip()

            # Filter for Gadgetbridge logs specifically related to Xiaomi Data
            if "nodomain.freeyourgadget" in line_str or "GB" in line_str:
                if "handleXiaomiData" in line_str or "MI_IMU_RAW_RX" in line_str:
                     print(f"[RAW LOG] {line_str}")

                # Look for Hex dumps
                # Typical format: "... (len=...): a5 a5 ..."
                # Or custom logs we added

                # Check for HEX pattern
                hex_match = re.search(r'([0-9a-fA-F]{2}\s){4,}', line_str)
                if hex_match:
                    clean_hex = re.sub(r'[^0-9a-fA-F]', '', hex_match.group(0))
                    try:
                        raw_bytes = bytes.fromhex(clean_hex)
                        if b'\xa5\xa5' in raw_bytes:
                            stream_buffer += raw_bytes
                            stream_buffer = process_stream_buffer(stream_buffer)
                    except:
                        pass

    except KeyboardInterrupt:
        print("\nStopping...")
        process.terminate()

if __name__ == "__main__":
    main()
