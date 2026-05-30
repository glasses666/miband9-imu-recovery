import json
import math
import tempfile
import unittest
from pathlib import Path

from imu_static_calibration import build_calibration, main, samples_from_probe_json


class ImuStaticCalibrationTest(unittest.TestCase):
    def _probe_json(self):
        packets = []
        for i in range(30):
            packets.append(
                {
                    "accel_samples": 10,
                    "gyro_samples": 10,
                    "first_accel_timestamp": 1_000_000 + i * 100_000,
                    "last_accel_timestamp": 1_090_000 + i * 100_000,
                    "accel_x_min": 8.5,
                    "accel_x_max": 8.6,
                    "accel_y_min": -4.2,
                    "accel_y_max": -4.1,
                    "accel_z_min": -2.6,
                    "accel_z_max": -2.5,
                    "gyro_x_min": -0.006,
                    "gyro_x_max": -0.004,
                    "gyro_y_min": -0.004,
                    "gyro_y_max": -0.002,
                    "gyro_z_min": -0.003,
                    "gyro_z_max": -0.001,
                }
            )
        # Startup/stale timestamp packet should be ignored.
        packets.insert(
            0,
            {
                **packets[0],
                "first_accel_timestamp": 10,
                "last_accel_timestamp": 9_000_000_000,
                "accel_x_max": 99.0,
            },
        )
        return {"ok": True, "data": {"probe": {"packets": packets}}}

    def test_samples_from_probe_json_drops_startup_packet(self):
        rows, ranges = samples_from_probe_json(self._probe_json())
        self.assertEqual(30, len(rows))
        self.assertEqual(30, len(ranges))
        self.assertAlmostEqual(8.55, rows[0]["ax"])

    def test_build_calibration_computes_zero_offsets_and_gates(self):
        cal = build_calibration(self._probe_json(), name="unit-flat", source="fixture.json")
        self.assertEqual("unit-flat", cal["name"])
        self.assertEqual(30, cal["sample_count"])
        self.assertAlmostEqual(-0.005, cal["gyro_bias"]["x"])
        expected_pitch = math.atan2(-8.55, math.sqrt((-4.15) ** 2 + (-2.55) ** 2))
        self.assertAlmostEqual(expected_pitch, cal["pitch_rad"])
        self.assertGreaterEqual(cal["vibration_gate"]["accel_delta_threshold"], 0.18)
        self.assertGreaterEqual(cal["vibration_gate"]["gyro_abs_threshold"], 0.025)

    def test_main_writes_json_file(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "probe.json"
            dst = Path(td) / "cal.json"
            src.write_text(json.dumps(self._probe_json()), encoding="utf-8")
            self.assertEqual(0, main([str(src), "-o", str(dst), "--name", "cli-flat"]))
            cal = json.loads(dst.read_text(encoding="utf-8"))
            self.assertEqual("cli-flat", cal["name"])


if __name__ == "__main__":
    unittest.main()
