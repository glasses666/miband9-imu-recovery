import unittest

from miband9ctl.mac_direct_protocol import (
    Channel,
    Opcode,
    PacketType,
    SppV2Frame,
    SppV2StreamParser,
    build_data_frame_from_encrypted_payload,
    build_l2_payload,
    build_phone_nonce_command,
    build_session_config_start_frame,
    chunk_for_sar_write,
    crc16_arc_xiaomi,
    decrypt_v2,
    derive_session_material,
    encrypt_v2,
    parse_frame,
    parse_watch_nonce_command,
)


class XiaomiMacDirectProtocolTest(unittest.TestCase):
    def test_crc16_arc_matches_gadgetbridge_vector(self):
        # Payload from XiaomiSppPacketV2.SessionConfigPacket start-session request.
        payload = bytes.fromhex("0101030001000002020000fc030200200004021027")
        self.assertEqual(crc16_arc_xiaomi(payload), 0xCB86)

    def test_session_config_start_frame_matches_spp_v2_layout(self):
        frame = build_session_config_start_frame(seq=0)
        self.assertEqual(
            frame.hex(),
            "a5a50200150086cb0101030001000002020000fc030200200004021027",
        )
        parsed = parse_frame(frame)
        self.assertEqual(parsed.packet_type, PacketType.SESSION_CONFIG)
        self.assertEqual(parsed.sequence, 0)
        self.assertEqual(parsed.payload.hex(), "0101030001000002020000fc030200200004021027")

    def test_data_l2_payload_maps_protobuf_to_channel_1_opcode_2(self):
        encrypted_payload = bytes.fromhex("aabbcc")
        self.assertEqual(
            build_l2_payload(Channel.PROTOBUF_COMMAND, Opcode.SEND_ENCRYPTED, encrypted_payload).hex(),
            "0102aabbcc",
        )

    def test_data_frame_uses_encrypted_payload_without_fake_encrypting(self):
        frame = build_data_frame_from_encrypted_payload(
            seq=7,
            channel=Channel.PROTOBUF_COMMAND,
            encrypted_payload=bytes.fromhex("aabbcc"),
        )
        parsed = parse_frame(frame)
        self.assertEqual(parsed.packet_type, PacketType.DATA)
        self.assertEqual(parsed.sequence, 7)
        self.assertEqual(parsed.payload, bytes.fromhex("0102aabbcc"))

    def test_sar_chunking_and_stream_parser_reassemble_l1_frame(self):
        frame = build_session_config_start_frame(seq=0)
        chunks = chunk_for_sar_write(frame, chunk_size=7)
        self.assertGreater(len(chunks), 1)
        self.assertEqual(b"".join(chunks), frame)
        parser = SppV2StreamParser()
        complete = []
        for chunk in chunks:
            complete.extend(parser.feed(chunk))
        self.assertEqual(len(complete), 1)
        self.assertEqual(complete[0].payload.hex(), "0101030001000002020000fc030200200004021027")

    def test_parser_keeps_incomplete_tail_until_next_fragment(self):
        frame = build_session_config_start_frame(seq=0)
        parser = SppV2StreamParser()
        self.assertEqual(parser.feed(frame[:5]), [])
        self.assertEqual(parser.buffered_len, 5)
        frames = parser.feed(frame[5:])
        self.assertEqual(len(frames), 1)
        self.assertEqual(parser.buffered_len, 0)

    def test_auth_session_material_matches_gadgetbridge_hkdf_shape(self):
        material = derive_session_material(
            secret_key=bytes(range(0x20, 0x30)),
            phone_nonce=bytes(range(0x00, 0x10)),
            watch_nonce=bytes(range(0x10, 0x20)),
        )
        self.assertEqual(material.decryption_key.hex(), "0dcadbbc6ea170a202cdf470e58d928f")
        self.assertEqual(material.encryption_key.hex(), "473013825aad69238e69eca3cc2e4bf7")
        self.assertEqual(material.decryption_nonce.hex(), "4262b2d8")
        self.assertEqual(material.encryption_nonce.hex(), "fb261e7b")

    def test_encrypt_v2_uses_aes_ctr_with_key_as_iv(self):
        material = derive_session_material(
            secret_key=bytes(range(0x20, 0x30)),
            phone_nonce=bytes(range(0x00, 0x10)),
            watch_nonce=bytes(range(0x10, 0x20)),
        )
        plaintext = bytes.fromhex("0808101a")
        ciphertext = encrypt_v2(material.encryption_key, plaintext)
        self.assertEqual(ciphertext.hex(), "2864a832")
        self.assertEqual(decrypt_v2(material.encryption_key, ciphertext), plaintext)

    def test_build_phone_nonce_command_matches_xiaomi_proto_layout(self):
        nonce = bytes(range(16))
        self.assertEqual(
            build_phone_nonce_command(nonce).hex(),
            "0801101a1a15f201120a10000102030405060708090a0b0c0d0e0f",
        )

    def test_parse_watch_nonce_command_extracts_nonce_and_hmac(self):
        watch_nonce = bytes(range(0x10, 0x20))
        watch_hmac = bytes(range(0x20, 0x40))
        payload = bytes.fromhex("0801101a1a37fa01340a10") + watch_nonce + bytes.fromhex("1220") + watch_hmac
        parsed = parse_watch_nonce_command(payload)
        self.assertEqual(parsed["type"], 1)
        self.assertEqual(parsed["subtype"], 26)
        self.assertEqual(parsed["watch_nonce"], watch_nonce)
        self.assertEqual(parsed["watch_hmac"], watch_hmac)


if __name__ == "__main__":
    unittest.main()
