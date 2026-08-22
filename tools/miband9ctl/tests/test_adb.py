import unittest

from miband9ctl.adb import (
    build_hfimu_broadcast_cmd,
    hfimu_action_for_package,
    hfimu_component_for_package,
)


class AdbCommandTest(unittest.TestCase):
    def test_package_scoped_action(self):
        self.assertEqual(
            "nodomain.freeyourgadget.gadgetbridge.hfimucli.CLI",
            hfimu_action_for_package("nodomain.freeyourgadget.gadgetbridge.hfimucli"),
        )
        self.assertEqual(
            "nodomain.freeyourgadget.gadgetbridge.hfimucli/"
            "nodomain.freeyourgadget.gadgetbridge.externalevents.hfimu.HfImuCliReceiver",
            hfimu_component_for_package("nodomain.freeyourgadget.gadgetbridge.hfimucli"),
        )

    def test_build_broadcast_command_with_serial(self):
        cmd = build_hfimu_broadcast_cmd(
            serial="c8f9a1da",
            package="nodomain.freeyourgadget.gadgetbridge.hfimucli",
            command="ping",
            request_id="req-1",
            nonce="abc123",
        )
        self.assertEqual(
            [
                "adb", "-s", "c8f9a1da", "shell", "am", "broadcast",
                "--include-stopped-packages",
                "-n", "nodomain.freeyourgadget.gadgetbridge.hfimucli/"
                "nodomain.freeyourgadget.gadgetbridge.externalevents.hfimu.HfImuCliReceiver",
                "-a", "nodomain.freeyourgadget.gadgetbridge.hfimucli.CLI",
                "--es", "command", "ping",
                "--es", "request_id", "req-1",
                "--es", "nonce", "abc123",
            ],
            cmd,
        )

    def test_build_broadcast_command_with_extra_strings(self):
        cmd = build_hfimu_broadcast_cmd(
            serial="c8f9a1da",
            package="nodomain.freeyourgadget.gadgetbridge.hfimucli",
            command="pair",
            request_id="req-1",
            nonce="abc123",
            extras={"address": "AA:BB:CC:DD:EE:02", "reset_bond": "true"},
        )
        self.assertEqual("--es", cmd[-6])
        self.assertEqual("address", cmd[-5])
        self.assertEqual("AA:BB:CC:DD:EE:02", cmd[-4])
        self.assertEqual("--es", cmd[-3])
        self.assertEqual("reset_bond", cmd[-2])
        self.assertEqual("true", cmd[-1])

    def test_build_broadcast_command_skips_empty_extras(self):
        cmd = build_hfimu_broadcast_cmd(
            serial="c8f9a1da",
            package="nodomain.freeyourgadget.gadgetbridge.hfimucli",
            command="gamesir-probe",
            request_id="req-1",
            nonce="abc123",
            extras={"name": "GameSir,Nova,Wireless", "address": "", "hex": None},
        )
        self.assertIn("name", cmd)
        self.assertIn("GameSir,Nova,Wireless", cmd)
        self.assertNotIn("address", cmd)
        self.assertNotIn("hex", cmd)


if __name__ == "__main__":
    unittest.main()
