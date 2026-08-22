import unittest
from typing import cast

from sportxms_812_packet_skeleton import build_packet


class SportXms812PacketSkeletonTests(unittest.TestCase):
    def test_select_version_can_be_omitted(self):
        with_select = build_packet(timestamp_sec=1, timezone_value=32, sport_type=812, sport_state=1, select_version=3)
        without_select = build_packet(timestamp_sec=1, timezone_value=32, sport_type=812, sport_state=1, select_version=None)

        self.assertEqual(22, cast(int, with_select["hns_len"]))
        self.assertEqual(20, cast(int, without_select["hns_len"]))
        self.assertNotIn("30 03", str(without_select["hfa_hex"]))

    def test_accessory_wear_mode_serializes_field_10(self):
        packet = build_packet(timestamp_sec=1, timezone_value=32, sport_type=812, sport_state=1, select_version=3, accessory_wear_mode=3)

        self.assertEqual(24, cast(int, packet["hns_len"]))
        self.assertIn("50 03", str(packet["hfa_hex"]))

    def test_sport_target_serializes_field_7_nfa(self):
        packet = build_packet(
            timestamp_sec=1,
            timezone_value=32,
            sport_type=812,
            sport_state=1,
            select_version=3,
            sport_target_type=7,
            sport_target_value=100,
        )

        self.assertEqual(28, cast(int, packet["hns_len"]))
        self.assertIn("3a 04 08 07 10 64", str(packet["hfa_hex"]))

    def test_sport_target_requires_type_and_value_together(self):
        with self.assertRaises(ValueError):
            build_packet(timestamp_sec=1, timezone_value=32, sport_type=812, sport_state=1, sport_target_type=7)

    def test_sport_launch_type_serializes_field_9(self):
        packet = build_packet(timestamp_sec=1, timezone_value=32, sport_type=812, sport_state=1, select_version=3, sport_launch_type=2)

        self.assertEqual(24, cast(int, packet["hns_len"]))
        self.assertIn("48 02", str(packet["hfa_hex"]))


if __name__ == "__main__":
    unittest.main()
