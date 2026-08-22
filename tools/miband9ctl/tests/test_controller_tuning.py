import math

import pytest

from miband9ctl.controller import Calibration, ControllerMapper, SensorSample


def _calibration() -> Calibration:
    return Calibration(
        accel_neutral={"x": 0.0, "y": 0.0, "z": 9.81},
        gyro_bias={"x": 0.0, "y": 0.0, "z": 0.0},
        pitch_rad=0.0,
        roll_rad=0.0,
        accel_delta_threshold=99.0,
        gyro_abs_threshold=99.0,
    )


def test_runtime_tuning_can_invert_tilt_axis() -> None:
    mapper = ControllerMapper(_calibration(), smoothing_alpha=1.0, tilt_full_scale_deg=30.0)
    g = 9.81
    roll15 = math.radians(15.0)
    sample = SensorSample(t_ms=0, ax=0.0, ay=math.sin(roll15) * g, az=math.cos(roll15) * g, gx=0, gy=0, gz=0)

    normal = mapper.update(sample, now_ms=0)
    mapper.set_tuning(tilt_x_sign=-1.0)
    inverted = mapper.update(sample, now_ms=10)

    assert normal.lx > 0.45
    assert inverted.lx < -0.45


def test_runtime_tuning_response_curve_softens_center() -> None:
    mapper = ControllerMapper(_calibration(), smoothing_alpha=1.0, tilt_full_scale_deg=30.0)
    g = 9.81
    roll15 = math.radians(15.0)
    sample = SensorSample(t_ms=0, ax=0.0, ay=math.sin(roll15) * g, az=math.cos(roll15) * g, gx=0, gy=0, gz=0)

    linear = mapper.update(sample, now_ms=0)
    mapper.set_tuning(response_curve=2.0)
    curved = mapper.update(sample, now_ms=10)

    assert 0.45 < linear.lx < 0.55
    assert 0.20 < curved.lx < linear.lx


def test_recenter_uses_uncentered_pose_after_existing_offset() -> None:
    mapper = ControllerMapper(_calibration(), smoothing_alpha=1.0, tilt_full_scale_deg=30.0)
    g = 9.81
    roll20 = math.radians(20.0)
    roll25 = math.radians(25.0)
    sample20 = SensorSample(t_ms=0, ax=0.0, ay=math.sin(roll20) * g, az=math.cos(roll20) * g, gx=0, gy=0, gz=0)
    sample25 = SensorSample(t_ms=10, ax=0.0, ay=math.sin(roll25) * g, az=math.cos(roll25) * g, gx=0, gy=0, gz=0)

    assert mapper.update(sample20, now_ms=0).lx > 0.6
    mapper.recenter_current()
    assert mapper.update(sample20, now_ms=10).lx == 0.0
    assert 0.12 < mapper.update(sample25, now_ms=20).lx < 0.25
    mapper.recenter_current()
    recentered = mapper.update(sample25, now_ms=30)

    assert recentered.lx == 0.0


def test_tilt_stick_does_not_snap_at_roll_atan2_branch_cut() -> None:
    mapper = ControllerMapper(_calibration(), smoothing_alpha=1.0, tilt_full_scale_deg=30.0, deadzone=0.0)
    g = 9.81
    samples = []
    for deg in (170, 180, 190):
        th = math.radians(deg)
        samples.append(SensorSample(t_ms=deg, ax=0.0, ay=math.sin(th) * g, az=math.cos(th) * g, gx=0, gy=0, gz=0))

    states = [mapper.update(sample, now_ms=sample.t_ms) for sample in samples]

    assert states[0].lx > 0.3
    assert abs(states[1].lx) < 0.001
    assert states[2].lx < -0.3
    assert max(abs(states[i + 1].lx - states[i].lx) for i in range(len(states) - 1)) < 0.75
    assert math.degrees(states[2].roll_rad - states[1].roll_rad) == pytest.approx(10.0)


def test_tuning_snapshot_reflects_runtime_updates() -> None:
    mapper = ControllerMapper(_calibration())
    mapper.set_tuning(
        tilt_full_scale_deg=22.0,
        yaw_rate_full_scale=0.75,
        pitch_rate_full_scale=0.8,
        deadzone=0.04,
        smoothing_alpha=0.55,
        response_curve=1.2,
        gyro_y_sign=-1.0,
    )

    tuning = mapper.tuning_snapshot()
    assert tuning["tilt_full_scale_deg"] == 22.0
    assert tuning["yaw_rate_full_scale"] == 0.75
    assert tuning["pitch_rate_full_scale"] == 0.8
    assert tuning["deadzone"] == 0.04
    assert tuning["smoothing_alpha"] == 0.55
    assert tuning["response_curve"] == 1.2
    assert tuning["gyro_y_sign"] == -1.0
