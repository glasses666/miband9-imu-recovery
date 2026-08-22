"""Pure Xiaomi BLE/SAR/SPP-v2 framing helpers for macOS direct probes.

This module intentionally does not implement Xiaomi auth/session encryption.  Callers must
provide already-encrypted payload bytes for opcode=2 frames; otherwise a direct Mac probe
could silently send fake plaintext through an encrypted channel and corrupt the experiment.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
import hashlib
import hmac

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
except Exception:  # pragma: no cover - exercised only on hosts without cryptography
    Cipher = None
    algorithms = None
    modes = None


PREAMBLE = b"\xa5\xa5"
HEADER_LEN = 8


class PacketType(IntEnum):
    ACK = 1
    SESSION_CONFIG = 2
    DATA = 3


class Channel(IntEnum):
    PROTOBUF_COMMAND = 1
    DATA = 2
    ACTIVITY = 5


class Opcode(IntEnum):
    SEND_PLAINTEXT = 1
    SEND_ENCRYPTED = 2


@dataclass(frozen=True)
class SppV2Frame:
    packet_type: PacketType
    sequence: int
    payload: bytes
    crc: int
    raw: bytes


@dataclass(frozen=True)
class SessionMaterial:
    decryption_key: bytes
    encryption_key: bytes
    decryption_nonce: bytes
    encryption_nonce: bytes
    step2_hmac: bytes


class FrameParseError(ValueError):
    """Raised when an SPP-v2 frame is structurally invalid."""


class IncompleteFrameError(FrameParseError):
    """Raised when a buffer begins with a valid frame prefix but is incomplete."""


class ProtoParseError(ValueError):
    """Raised for the tiny Xiaomi auth protobuf subset used by macOS direct probes."""


def _encode_varint(value: int) -> bytes:
    if value < 0:
        raise ValueError("varint value must be non-negative")
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _decode_varint(data: bytes, offset: int = 0) -> tuple[int, int]:
    shift = 0
    value = 0
    while offset < len(data):
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            return value, offset
        shift += 7
        if shift > 63:
            raise ProtoParseError("varint too long")
    raise ProtoParseError("truncated varint")


def _proto_key(field_number: int, wire_type: int) -> bytes:
    return _encode_varint((field_number << 3) | wire_type)


def _proto_varint(field_number: int, value: int) -> bytes:
    return _proto_key(field_number, 0) + _encode_varint(value)


def _proto_bytes(field_number: int, value: bytes) -> bytes:
    value = bytes(value)
    return _proto_key(field_number, 2) + _encode_varint(len(value)) + value


def _iter_proto_fields(data: bytes):
    offset = 0
    while offset < len(data):
        key, offset = _decode_varint(data, offset)
        field_number = key >> 3
        wire_type = key & 0x07
        if wire_type == 0:
            value, offset = _decode_varint(data, offset)
            yield field_number, wire_type, value
        elif wire_type == 2:
            length, offset = _decode_varint(data, offset)
            end = offset + length
            if end > len(data):
                raise ProtoParseError("truncated length-delimited field")
            yield field_number, wire_type, data[offset:end]
            offset = end
        else:
            raise ProtoParseError(f"unsupported wire type {wire_type}")


def _field_map(data: bytes) -> dict[int, tuple[int, object]]:
    return {field_number: (wire_type, value) for field_number, wire_type, value in _iter_proto_fields(data)}


def _expect_bytes(fields: dict[int, tuple[int, object]], field_number: int) -> bytes:
    try:
        wire_type, value = fields[field_number]
    except KeyError as exc:
        raise ProtoParseError(f"missing field {field_number}") from exc
    if wire_type != 2 or not isinstance(value, bytes):
        raise ProtoParseError(f"field {field_number} is not bytes")
    return value


def _expect_varint(fields: dict[int, tuple[int, object]], field_number: int) -> int:
    try:
        wire_type, value = fields[field_number]
    except KeyError as exc:
        raise ProtoParseError(f"missing field {field_number}") from exc
    if wire_type != 0 or not isinstance(value, int):
        raise ProtoParseError(f"field {field_number} is not varint")
    return value


def build_phone_nonce_command(phone_nonce: bytes) -> bytes:
    """Build XiaomiProto.Command for auth step 1: type=1/subtype=26/PhoneNonce."""

    phone_nonce = bytes(phone_nonce)
    if len(phone_nonce) != 16:
        raise ValueError("phone_nonce must be 16 bytes")
    phone_nonce_msg = _proto_bytes(1, phone_nonce)
    auth_msg = _proto_bytes(30, phone_nonce_msg)
    return _proto_varint(1, 1) + _proto_varint(2, 26) + _proto_bytes(3, auth_msg)


def parse_watch_nonce_command(payload: bytes) -> dict[str, object]:
    """Parse XiaomiProto.Command auth watch nonce subset.

    Returns only non-secret runtime values needed for the next auth derivation step.
    """

    command = _field_map(bytes(payload))
    command_type = _expect_varint(command, 1)
    subtype = _expect_varint(command, 2)
    auth = _field_map(_expect_bytes(command, 3))
    watch = _field_map(_expect_bytes(auth, 31))
    watch_nonce = _expect_bytes(watch, 1)
    watch_hmac = _expect_bytes(watch, 2)
    if len(watch_nonce) != 16:
        raise ProtoParseError("watch_nonce must be 16 bytes")
    return {"type": command_type, "subtype": subtype, "watch_nonce": watch_nonce, "watch_hmac": watch_hmac}


def _reverse32(value: int) -> int:
    value &= 0xFFFFFFFF
    out = 0
    for _ in range(32):
        out = (out << 1) | (value & 1)
        value >>= 1
    return out & 0xFFFFFFFF


def crc16_arc_xiaomi(payload: bytes) -> int:
    """CRC-16/ARC as implemented by Gadgetbridge XiaomiSppPacketV2.

    Gadgetbridge shifts bits MSB-side while feeding reflected input bits, then returns
    Integer.reverse(crc) >>> 16.  This is equivalent to CRC-16/ARC for the wire payload.
    """

    crc = 0
    for byte in payload:
        for bit_index in range(8):
            crc <<= 1
            bit_crc = (crc >> 16) & 1
            bit_in = (byte >> bit_index) & 1
            if bit_crc ^ bit_in:
                crc ^= 0x8005
            crc &= 0x1FFFF  # keep overflow bit available for the next iteration
    return (_reverse32(crc) >> 16) & 0xFFFF


def encode_frame(packet_type: PacketType | int, sequence: int, payload: bytes) -> bytes:
    packet_type_int = int(packet_type) & 0x0F
    sequence_int = sequence & 0xFF
    payload = bytes(payload)
    crc = crc16_arc_xiaomi(payload)
    return b"".join(
        [
            PREAMBLE,
            bytes([packet_type_int, sequence_int]),
            len(payload).to_bytes(2, "little"),
            crc.to_bytes(2, "little"),
            payload,
        ]
    )


def parse_frame(data: bytes) -> SppV2Frame:
    data = bytes(data)
    if len(data) < HEADER_LEN:
        raise IncompleteFrameError(f"need at least {HEADER_LEN} bytes, got {len(data)}")
    if data[:2] != PREAMBLE:
        raise FrameParseError("missing A5A5 preamble")
    packet_type_raw = data[2] & 0x0F
    sequence = data[3]
    payload_len = int.from_bytes(data[4:6], "little")
    given_crc = int.from_bytes(data[6:8], "little")
    total_len = HEADER_LEN + payload_len
    if len(data) < total_len:
        raise IncompleteFrameError(f"need {total_len} bytes, got {len(data)}")
    payload = data[HEADER_LEN:total_len]
    calculated = crc16_arc_xiaomi(payload)
    if calculated != given_crc:
        raise FrameParseError(f"crc mismatch: given=0x{given_crc:04x} calculated=0x{calculated:04x}")
    try:
        packet_type = PacketType(packet_type_raw)
    except ValueError as exc:
        raise FrameParseError(f"unknown packet type {packet_type_raw}") from exc
    return SppV2Frame(packet_type=packet_type, sequence=sequence, payload=payload, crc=given_crc, raw=data[:total_len])


def build_session_config_payload(opcode: int = 1) -> bytes:
    """Build XiaomiSppPacketV2.SessionConfigPacket payload.

    Defaults to OPCODE_START_SESSION_REQUEST.
    """

    return bytes(
        [
            opcode & 0xFF,
            0x01,
            0x03,
            0x00,
            0x01,
            0x00,
            0x00,
            0x02,
            0x02,
            0x00,
            0x00,
            0xFC,
            0x03,
            0x02,
            0x00,
            0x20,
            0x00,
            0x04,
            0x02,
            0x10,
            0x27,
        ]
    )


def build_session_config_start_frame(seq: int = 0) -> bytes:
    return encode_frame(PacketType.SESSION_CONFIG, seq, build_session_config_payload(opcode=1))


def build_l2_payload(channel: Channel | int, opcode: Opcode | int, payload: bytes) -> bytes:
    return bytes([int(channel) & 0x0F, int(opcode) & 0xFF]) + bytes(payload)


def build_data_frame_from_encrypted_payload(
    *,
    seq: int,
    channel: Channel = Channel.PROTOBUF_COMMAND,
    encrypted_payload: bytes,
) -> bytes:
    """Build a DATA frame whose payload is already encrypted for opcode=2.

    This deliberately does not accept plaintext SportXms hns bytes.  A future live sender
    must run authService.encryptV2-equivalent code first, then call this function.
    """

    if channel not in (Channel.PROTOBUF_COMMAND, Channel.ACTIVITY):
        raise ValueError("encrypted DATA frames are only expected for protobuf/activity channels")
    if not encrypted_payload:
        raise ValueError("encrypted_payload must be non-empty")
    return encode_frame(PacketType.DATA, seq, build_l2_payload(channel, Opcode.SEND_ENCRYPTED, encrypted_payload))


def build_data_frame_plaintext(*, seq: int, channel: Channel = Channel.DATA, payload: bytes) -> bytes:
    if channel != Channel.DATA:
        raise ValueError("plaintext helper is restricted to Channel.DATA")
    return encode_frame(PacketType.DATA, seq, build_l2_payload(channel, Opcode.SEND_PLAINTEXT, payload))


def derive_session_material(*, secret_key: bytes, phone_nonce: bytes, watch_nonce: bytes) -> SessionMaterial:
    """Derive Gadgetbridge XiaomiAuthService session keys/nonces.

    Mirrors `computeAuthStep3Hmac(secretKey, phoneNonce, watchNonce)`: first derive an
    HMAC key using HMAC-SHA256(phoneNonce || watchNonce, secretKey), then expand 64
    bytes with info string `miwear-auth` and counter bytes 1..N.
    """

    secret_key = bytes(secret_key)
    phone_nonce = bytes(phone_nonce)
    watch_nonce = bytes(watch_nonce)
    if len(secret_key) != 16:
        raise ValueError("secret_key must be 16 bytes")
    if len(phone_nonce) != 16:
        raise ValueError("phone_nonce must be 16 bytes")
    if len(watch_nonce) != 16:
        raise ValueError("watch_nonce must be 16 bytes")
    hmac_key = hmac.new(phone_nonce + watch_nonce, secret_key, hashlib.sha256).digest()
    output = bytearray()
    tmp = b""
    counter = 1
    while len(output) < 64:
        tmp = hmac.new(hmac_key, tmp + b"miwear-auth" + bytes([counter]), hashlib.sha256).digest()
        output.extend(tmp)
        counter += 1
    step2 = bytes(output[:64])
    return SessionMaterial(
        decryption_key=step2[0:16],
        encryption_key=step2[16:32],
        decryption_nonce=step2[32:36],
        encryption_nonce=step2[36:40],
        step2_hmac=step2,
    )


def _aes_ctr_key_as_iv(key: bytes, payload: bytes) -> bytes:
    if Cipher is None or algorithms is None or modes is None:
        raise RuntimeError("cryptography package is required for AES/CTR Xiaomi encryptV2")
    key = bytes(key)
    if len(key) != 16:
        raise ValueError("AES key/IV must be 16 bytes")
    encryptor = Cipher(algorithms.AES(key), modes.CTR(key)).encryptor()
    return encryptor.update(bytes(payload)) + encryptor.finalize()


def encrypt_v2(encryption_key: bytes, plaintext: bytes) -> bytes:
    """Gadgetbridge XiaomiAuthService.encryptV2: AES/CTR/NoPadding with key as IV."""

    return _aes_ctr_key_as_iv(encryption_key, plaintext)


def decrypt_v2(decryption_key: bytes, ciphertext: bytes) -> bytes:
    """Gadgetbridge XiaomiAuthService.decryptV2 equivalent.

    AES-CTR is symmetric; callers should pass the session's decryption key for inbound
    device data or the encryption key when round-tripping a locally encrypted test vector.
    """

    return _aes_ctr_key_as_iv(decryption_key, ciphertext)


def chunk_for_sar_write(frame: bytes, chunk_size: int = 244) -> list[bytes]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    data = bytes(frame)
    return [data[offset : offset + chunk_size] for offset in range(0, len(data), chunk_size)] or [b""]


class SppV2StreamParser:
    """Reassemble A5A5-framed L1 data from BLE SAR notification chunks."""

    def __init__(self) -> None:
        self._buffer = bytearray()

    @property
    def buffered_len(self) -> int:
        return len(self._buffer)

    def feed(self, chunk: bytes) -> list[SppV2Frame]:
        self._buffer.extend(chunk)
        frames: list[SppV2Frame] = []
        while True:
            start = self._buffer.find(PREAMBLE)
            if start < 0:
                # Keep at most one trailing 0xA5 so a split preamble can still be found.
                keep = 1 if self._buffer.endswith(PREAMBLE[:1]) else 0
                if keep:
                    self._buffer[:] = self._buffer[-1:]
                else:
                    self._buffer.clear()
                return frames
            if start > 0:
                del self._buffer[:start]
            if len(self._buffer) < HEADER_LEN:
                return frames
            payload_len = int.from_bytes(self._buffer[4:6], "little")
            total_len = HEADER_LEN + payload_len
            if len(self._buffer) < total_len:
                return frames
            raw = bytes(self._buffer[:total_len])
            del self._buffer[:total_len]
            frames.append(parse_frame(raw))
