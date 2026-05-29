import unittest

from live_sportxms_web import packet_from_payload


class LiveSportXmsWebTest(unittest.TestCase):
    def test_packet_from_payload_expands_ten_sample_series(self):
        payload = {
            "packet_index": "7",
            "elapsed_ms": "1234",
            "accel_samples": "3",
            "gyro_samples": "3",
            "first_accel_timestamp": "1000000",
            "last_accel_timestamp": "1020000",
            "accel_x_min": "1.0", "accel_x_max": "3.0",
            "accel_y_min": "4.0", "accel_y_max": "6.0",
            "accel_z_min": "7.0", "accel_z_max": "9.0",
            "gyro_x_min": "0.1", "gyro_x_max": "0.3",
            "gyro_y_min": "0.4", "gyro_y_max": "0.6",
            "gyro_z_min": "0.7", "gyro_z_max": "0.9",
            "accel_t_values": "1000000,1010000,1020000",
            "accel_x_values": "1.0,2.0,3.0",
            "accel_y_values": "4.0,5.0,6.0",
            "accel_z_values": "7.0,8.0,9.0",
            "gyro_t_values": "1000000,1010000,1020000",
            "gyro_x_values": "0.1,0.2,0.3",
            "gyro_y_values": "0.4,0.5,0.6",
            "gyro_z_values": "0.7,0.8,0.9",
        }
        packet = packet_from_payload(payload)
        self.assertAlmostEqual(100.0, packet.hz)
        self.assertEqual(3, len(packet.samples))
        self.assertEqual(1000000, packet.samples[0]["t"])
        self.assertEqual(1.0, packet.samples[0]["ax"])
        self.assertEqual(0.1, packet.samples[0]["gx"])
        self.assertEqual(3.0, packet.samples[-1]["ax"])
        self.assertEqual(0.9, packet.samples[-1]["gz"])


if __name__ == "__main__":
    unittest.main()
