import unittest

from controller_state_server import align_next_tick
from miband9ctl.controller_net import axis_to_vgamepad_float, collect_frame_latency, frame_latency_ms, interval_summary_ms, latency_summary


class ControllerNetTest(unittest.TestCase):
    def test_axis_to_vgamepad_float_clamps_and_optionally_inverts(self):
        self.assertEqual(1.0, axis_to_vgamepad_float(2.0))
        self.assertEqual(-1.0, axis_to_vgamepad_float(-2.0))
        self.assertEqual(-0.25, axis_to_vgamepad_float(0.25, invert=True))

    def test_latency_summary_reports_percentiles(self):
        summary = latency_summary([3.0, 1.0, 2.0, 10.0])

        self.assertEqual(4, summary["count"])
        self.assertEqual(1.0, summary["min_ms"])
        self.assertEqual(2.5, summary["p50_ms"])
        self.assertEqual(8.95, summary["p95_ms"])
        self.assertEqual(10.0, summary["max_ms"])

    def test_frame_latency_keeps_clock_skew_visible(self):
        self.assertEqual(-25.0, frame_latency_ms({"sent_at_ms": 1025}, received_at_ms=1000))
        self.assertIsNone(frame_latency_ms({}, received_at_ms=1000))

    def test_collect_frame_latency_preserves_negative_clock_skew(self):
        latencies: list[float] = []

        value = collect_frame_latency(latencies, {"sent_at_ms": 1025}, received_at_ms=1000)

        self.assertEqual(-25.0, value)
        self.assertEqual([-25.0], latencies)

    def test_interval_summary_uses_receive_timestamps(self):
        summary = interval_summary_ms([1000, 1010, 1020, 1031])

        self.assertEqual(3, summary["count"])
        self.assertEqual(10.0, summary["p50_ms"])
        self.assertEqual(11.0, summary["max_ms"])
        self.assertAlmostEqual(10.333, summary["avg_ms"], places=3)

    def test_align_next_tick_drops_scheduler_debt_after_acquisition_stalls(self):
        self.assertEqual(1.0, align_next_tick(1.0, 0.01, now=1.015))
        self.assertEqual(1.05, align_next_tick(1.0, 0.01, now=1.05))


if __name__ == "__main__":
    unittest.main()
