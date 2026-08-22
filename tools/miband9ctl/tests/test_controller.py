import json
import math
import unittest

from miband9ctl.controller import Calibration, ControllerMapper, SensorSample, apply_deadzone, clamp
from miband9ctl.controller_stream import frame_for_state, samples_from_probe_json


class ControllerCoreTest(unittest.TestCase):
    def test_neutral_anchor_maps_to_zero_axes(self):
        cal = Calibration(
            accel_neutral={"x": 0.0, "y": 0.0, "z": 9.81},
            gyro_bias={"x": 0.0, "y": 0.0, "z": 0.0},
            pitch_rad=0.0,
            roll_rad=0.0,
            accel_delta_threshold=0.25,
            gyro_abs_threshold=0.03,
            settle_ms=350,
        )
        mapper = ControllerMapper(cal, smoothing_alpha=1.0, tilt_full_scale_deg=30.0, yaw_rate_full_scale=1.0)

        state = mapper.update(SensorSample(t_ms=0, ax=0.0, ay=0.0, az=9.81, gx=0.0, gy=0.0, gz=0.0), now_ms=0)

        self.assertEqual(0.0, state.lx)
        self.assertEqual(0.0, state.ly)
        self.assertEqual(0.0, state.rx)
        self.assertEqual(0.0, state.ry)
        self.assertFalse(state.gate)
        self.assertIsNotNone(state.motion)
        assert state.motion is not None
        self.assertEqual("idle", state.motion.gesture)
        self.assertEqual("face_up", state.motion.palm)
        self.assertAlmostEqual(1.0, state.motion.quat["w"], places=6)

    def test_motion_state_integrates_relative_yaw_and_labels_twist(self):
        cal = Calibration(
            accel_neutral={"x": 0.0, "y": 0.0, "z": 9.81},
            gyro_bias={"x": 0.0, "y": 0.0, "z": 0.0},
            pitch_rad=0.0,
            roll_rad=0.0,
            accel_delta_threshold=99.0,
            gyro_abs_threshold=99.0,
            settle_ms=350,
        )
        mapper = ControllerMapper(cal, smoothing_alpha=1.0, deadzone=0.0)
        first = mapper.update(SensorSample(t_ms=0, ax=0.0, ay=0.0, az=9.81, gx=0.0, gy=0.0, gz=1.2), now_ms=0)
        second = mapper.update(SensorSample(t_ms=100, ax=0.0, ay=0.0, az=9.81, gx=0.0, gy=0.0, gz=1.2), now_ms=100)

        assert first.motion is not None
        assert second.motion is not None
        self.assertAlmostEqual(0.0, first.motion.yaw_rad, places=6)
        self.assertAlmostEqual(0.12, second.motion.yaw_rad, places=3)
        self.assertEqual("twist_right", second.motion.gesture)
        self.assertGreater(second.motion.confidence, 0.4)

    def test_roll_and_pitch_map_to_left_stick_with_deadzone_and_clamp(self):
        cal = Calibration(
            accel_neutral={"x": 0.0, "y": 0.0, "z": 9.81},
            gyro_bias={"x": 0.0, "y": 0.0, "z": 0.0},
            pitch_rad=0.0,
            roll_rad=0.0,
            accel_delta_threshold=99.0,
            gyro_abs_threshold=99.0,
            settle_ms=350,
        )
        mapper = ControllerMapper(cal, smoothing_alpha=1.0, tilt_full_scale_deg=30.0, deadzone=0.05)
        g = 9.81
        roll15 = math.radians(15.0)
        pitch_minus15 = math.radians(-15.0)
        # Inverse of pitch=atan2(-ax, sqrt(...)), roll=atan2(ay, az).
        sample = SensorSample(
            t_ms=0,
            ax=-math.sin(pitch_minus15) * g,
            ay=math.sin(roll15) * math.cos(pitch_minus15) * g,
            az=math.cos(roll15) * math.cos(pitch_minus15) * g,
            gx=0.0,
            gy=0.0,
            gz=0.0,
        )

        state = mapper.update(sample, now_ms=0)

        self.assertAlmostEqual(0.5, state.lx, places=3)
        self.assertAlmostEqual(math.sin(abs(pitch_minus15)) / math.sin(math.radians(30.0)), state.ly, places=3)
        self.assertEqual(0.0, apply_deadzone(0.02, 0.05))
        self.assertEqual(1.0, clamp(2.0, -1.0, 1.0))

    def test_gyro_yaw_maps_to_right_stick_after_bias(self):
        cal = Calibration(
            accel_neutral={"x": 0.0, "y": 0.0, "z": 9.81},
            gyro_bias={"x": 0.0, "y": 0.0, "z": 0.1},
            pitch_rad=0.0,
            roll_rad=0.0,
            accel_delta_threshold=99.0,
            gyro_abs_threshold=99.0,
            settle_ms=350,
        )
        mapper = ControllerMapper(cal, smoothing_alpha=1.0, yaw_rate_full_scale=1.0, deadzone=0.05)

        state = mapper.update(SensorSample(t_ms=0, ax=0.0, ay=0.0, az=9.81, gx=0.0, gy=0.0, gz=0.6), now_ms=0)

        self.assertAlmostEqual(0.5, state.rx, places=3)
        self.assertEqual(0.0, state.ry)

    def test_motion_gate_holds_until_settle_window_expires(self):
        cal = Calibration(
            accel_neutral={"x": 0.0, "y": 0.0, "z": 9.81},
            gyro_bias={"x": 0.0, "y": 0.0, "z": 0.0},
            pitch_rad=0.0,
            roll_rad=0.0,
            accel_delta_threshold=0.25,
            gyro_abs_threshold=0.03,
            settle_ms=350,
        )
        mapper = ControllerMapper(cal, smoothing_alpha=1.0)
        quiet = SensorSample(t_ms=0, ax=0.0, ay=0.0, az=9.81, gx=0.0, gy=0.0, gz=0.0)
        spike = SensorSample(t_ms=10, ax=2.0, ay=0.0, az=9.81, gx=0.0, gy=0.0, gz=0.0)

        self.assertFalse(mapper.update(quiet, now_ms=0).gate)
        self.assertTrue(mapper.update(spike, now_ms=10).gate)
        self.assertTrue(mapper.update(quiet, now_ms=200).gate)
        self.assertFalse(mapper.update(quiet, now_ms=500).gate)

    def test_recenter_current_pose_becomes_zero(self):
        cal = Calibration(
            accel_neutral={"x": 0.0, "y": 0.0, "z": 9.81},
            gyro_bias={"x": 0.0, "y": 0.0, "z": 0.0},
            pitch_rad=0.0,
            roll_rad=0.0,
            accel_delta_threshold=99.0,
            gyro_abs_threshold=99.0,
            settle_ms=350,
        )
        mapper = ControllerMapper(cal, smoothing_alpha=1.0, tilt_full_scale_deg=30.0)
        g = 9.81
        roll10 = math.radians(10.0)
        tilted = SensorSample(t_ms=0, ax=0.0, ay=math.sin(roll10) * g, az=math.cos(roll10) * g, gx=0.0, gy=0.0, gz=0.0)
        before = mapper.update(tilted, now_ms=0)
        self.assertGreater(before.lx, 0.2)

        mapper.recenter_current()
        after = mapper.update(tilted, now_ms=10)

        self.assertAlmostEqual(0.0, after.lx, places=3)
        self.assertAlmostEqual(0.0, after.ly, places=3)


class ControllerStreamTest(unittest.TestCase):
    def test_samples_from_probe_json_expands_samples_and_falls_back_to_midpoints(self):
        probe = {
            "data": {
                "probe": {
                    "packets": [
                        {
                            "elapsed_ms": 100,
                            "samples": [
                                {"t": 1000, "ax": 1, "ay": 2, "az": 3, "gx": 0.1, "gy": 0.2, "gz": 0.3},
                                {"t": 1010, "ax": 4, "ay": 5, "az": 6, "gx": 0.4, "gy": 0.5, "gz": 0.6},
                            ],
                        },
                        {
                            "elapsed_ms": 200,
                            "accel_samples": 10,
                            "gyro_samples": 10,
                            "first_accel_timestamp": 1000000,
                            "last_accel_timestamp": 1090000,
                            "accel_x_min": 0.0,
                            "accel_x_max": 2.0,
                            "accel_y_min": 2.0,
                            "accel_y_max": 4.0,
                            "accel_z_min": 8.0,
                            "accel_z_max": 10.0,
                            "gyro_x_min": 0.0,
                            "gyro_x_max": 0.2,
                            "gyro_y_min": 0.2,
                            "gyro_y_max": 0.4,
                            "gyro_z_min": 0.4,
                            "gyro_z_max": 0.6,
                        },
                    ]
                }
            }
        }

        samples = list(samples_from_probe_json(probe))

        self.assertEqual(3, len(samples))
        self.assertEqual(1000, samples[0].t_ms)
        self.assertEqual((4, 5, 6), (samples[1].ax, samples[1].ay, samples[1].az))
        self.assertEqual(200, samples[2].t_ms)
        self.assertEqual((1.0, 3.0, 9.0), (samples[2].ax, samples[2].ay, samples[2].az))

    def test_frame_for_state_is_compact_json_serializable_contract(self):
        cal = Calibration(
            accel_neutral={"x": 0.0, "y": 0.0, "z": 9.81},
            gyro_bias={"x": 0.0, "y": 0.0, "z": 0.0},
            pitch_rad=0.0,
            roll_rad=0.0,
            accel_delta_threshold=99.0,
            gyro_abs_threshold=99.0,
            settle_ms=350,
        )
        state = ControllerMapper(cal, smoothing_alpha=1.0).update(SensorSample(t_ms=0, ax=0.0, ay=0.0, az=9.81, gx=0.0, gy=0.0, gz=0.0), now_ms=10)

        frame = frame_for_state(seq=7, state=state, sent_at_ms=123456)
        encoded = json.dumps(frame, separators=(",", ":"))

        self.assertEqual(7, frame["seq"])
        self.assertEqual(123456, frame["sent_at_ms"])
        self.assertIn("lx", frame)
        self.assertIn("rx", frame)
        self.assertIn("gate", frame)
        self.assertIn("motion", frame)
        self.assertIn("quat", frame["motion"])
        self.assertLess(len(encoded), 900)


if __name__ == "__main__":
    unittest.main()
