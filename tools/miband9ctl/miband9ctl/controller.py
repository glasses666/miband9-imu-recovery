from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


def clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def apply_deadzone(value: float, deadzone: float) -> float:
    value = float(value)
    deadzone = abs(float(deadzone))
    if abs(value) < deadzone:
        return 0.0
    return clamp(value)


def apply_response_curve(value: float, curve: float) -> float:
    value = clamp(value)
    curve = max(0.25, float(curve))
    return math.copysign(abs(value) ** curve, value)


def unwrap_angle(previous: float, current: float) -> float:
    return previous + math.atan2(math.sin(current - previous), math.cos(current - previous))


def _normalized_xy(vector: dict[str, float]) -> tuple[float, float]:
    x = float(vector.get("x") or 0.0)
    y = float(vector.get("y") or 0.0)
    z = float(vector.get("z") or 0.0)
    mag = math.sqrt(x * x + y * y + z * z)
    if mag <= 1e-9:
        return 0.0, 0.0
    return x / mag, y / mag


def _normalized_xyz(vector: dict[str, float]) -> tuple[float, float, float]:
    x = float(vector.get("x") or 0.0)
    y = float(vector.get("y") or 0.0)
    z = float(vector.get("z") or 0.0)
    mag = math.sqrt(x * x + y * y + z * z)
    if mag <= 1e-9:
        return 0.0, 0.0, 1.0
    return x / mag, y / mag, z / mag


def _euler_to_quat(*, pitch: float, roll: float, yaw: float) -> dict[str, float]:
    """Return a display/debug quaternion from the controller's relative pose.

    This is intentionally a UI/protocol orientation, not a full magnetometer-grade
    attitude solution. Yaw is relative gyro integration and can drift; pitch/roll
    are gravity-anchored.
    """
    cy = math.cos(yaw * 0.5)
    sy = math.sin(yaw * 0.5)
    cp = math.cos(pitch * 0.5)
    sp = math.sin(pitch * 0.5)
    cr = math.cos(roll * 0.5)
    sr = math.sin(roll * 0.5)
    return {
        "w": round(cr * cp * cy + sr * sp * sy, 6),
        "x": round(sr * cp * cy - cr * sp * sy, 6),
        "y": round(cr * sp * cy + sr * cp * sy, 6),
        "z": round(cr * cp * sy - sr * sp * cy, 6),
    }


def _classify_motion(
    *,
    gx: float,
    gy: float,
    gz: float,
    accel_delta: float,
    accel_delta_threshold: float,
) -> tuple[str, float]:
    """First-pass intent label for the fun motion channel.

    Keep this conservative: the HUD should reveal likely gestures before they are
    wired to buttons. A later pass can turn stable labels into trigger events.
    """
    gyro_abs = math.sqrt(gx * gx + gy * gy + gz * gz)
    accel_hit = accel_delta / max(0.35, accel_delta_threshold * 3.0)
    if accel_hit >= 1.0 and gyro_abs < 0.65:
        return "jab", round(clamp(accel_hit, 0.0, 1.0), 3)
    if gyro_abs < 0.45 and accel_hit < 0.75:
        return "idle", 0.0
    axes = {"roll": gx, "pitch": gy, "twist": gz}
    axis, value = max(axes.items(), key=lambda item: abs(item[1]))
    confidence = clamp((max(abs(value), gyro_abs) - 0.35) / 1.65, 0.0, 1.0)
    if axis == "twist":
        return ("twist_right" if value > 0 else "twist_left"), round(confidence, 3)
    if axis == "pitch":
        return ("slash_down" if value > 0 else "slash_up"), round(confidence, 3)
    return ("roll_right" if value > 0 else "roll_left"), round(confidence, 3)


@dataclass(frozen=True)
class SensorSample:
    t_ms: float
    ax: float
    ay: float
    az: float
    gx: float
    gy: float
    gz: float


@dataclass(frozen=True)
class Calibration:
    accel_neutral: dict[str, float]
    gyro_bias: dict[str, float]
    pitch_rad: float
    roll_rad: float
    accel_delta_threshold: float
    gyro_abs_threshold: float
    settle_ms: int = 350
    name: str = ""

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Calibration":
        gate = data.get("vibration_gate") or {}
        return cls(
            accel_neutral={k: float((data.get("accel_neutral") or {}).get(k) or 0.0) for k in ("x", "y", "z")},
            gyro_bias={k: float((data.get("gyro_bias") or {}).get(k) or 0.0) for k in ("x", "y", "z")},
            pitch_rad=float(data.get("pitch_rad") or 0.0),
            roll_rad=float(data.get("roll_rad") or 0.0),
            accel_delta_threshold=float(gate.get("accel_delta_threshold") or 0.25),
            gyro_abs_threshold=float(gate.get("gyro_abs_threshold") or 0.03),
            settle_ms=int(gate.get("settle_ms") or 350),
            name=str(data.get("name") or ""),
        )


@dataclass(frozen=True)
class MotionState:
    pitch_rad: float
    roll_rad: float
    yaw_rad: float
    quat: dict[str, float]
    angular_velocity: dict[str, float]
    accel_norm: dict[str, float]
    accel_delta: float
    gyro_abs: float
    intensity: float
    palm: str
    gesture: str
    confidence: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "pitch_rad": self.pitch_rad,
            "roll_rad": self.roll_rad,
            "yaw_rad": self.yaw_rad,
            "quat": self.quat,
            "angular_velocity": self.angular_velocity,
            "accel_norm": self.accel_norm,
            "accel_delta": self.accel_delta,
            "gyro_abs": self.gyro_abs,
            "intensity": self.intensity,
            "palm": self.palm,
            "gesture": self.gesture,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class ControllerState:
    lx: float
    ly: float
    rx: float
    ry: float
    lt: float = 0.0
    rt: float = 0.0
    gate: bool = False
    pitch_rad: float = 0.0
    roll_rad: float = 0.0
    gyro_abs: float = 0.0
    accel_delta: float = 0.0
    motion: MotionState | None = None

    def as_dict(self) -> dict[str, Any]:
        data = {
            "lx": self.lx,
            "ly": self.ly,
            "rx": self.rx,
            "ry": self.ry,
            "lt": self.lt,
            "rt": self.rt,
            "gate": self.gate,
            "pitch_rad": self.pitch_rad,
            "roll_rad": self.roll_rad,
            "gyro_abs": self.gyro_abs,
            "accel_delta": self.accel_delta,
        }
        if self.motion is not None:
            data["motion"] = self.motion.as_dict()
        return data


class ControllerMapper:
    """Map calibrated SportXms accel/gyro samples into a platform-neutral controller state."""

    def __init__(
        self,
        calibration: Calibration,
        *,
        tilt_full_scale_deg: float = 30.0,
        yaw_rate_full_scale: float = 1.0,
        pitch_rate_full_scale: float = 1.0,
        deadzone: float = 0.05,
        smoothing_alpha: float = 0.34,
        response_curve: float = 1.0,
        tilt_x_sign: float = 1.0,
        tilt_y_sign: float = 1.0,
        gyro_x_sign: float = 1.0,
        gyro_y_sign: float = 1.0,
    ) -> None:
        self.calibration = calibration
        self.tilt_full_scale_rad = math.radians(float(tilt_full_scale_deg))
        self.yaw_rate_full_scale = float(yaw_rate_full_scale)
        self.pitch_rate_full_scale = float(pitch_rate_full_scale)
        self.deadzone = float(deadzone)
        self.smoothing_alpha = clamp(float(smoothing_alpha), 0.0, 1.0)
        self.response_curve = max(0.25, float(response_curve))
        self.tilt_x_sign = 1.0 if float(tilt_x_sign) >= 0 else -1.0
        self.tilt_y_sign = 1.0 if float(tilt_y_sign) >= 0 else -1.0
        self.gyro_x_sign = 1.0 if float(gyro_x_sign) >= 0 else -1.0
        self.gyro_y_sign = 1.0 if float(gyro_y_sign) >= 0 else -1.0
        self._filtered_accel: dict[str, float] | None = None
        self._previous_raw: dict[str, float] | None = None
        self._gate_until_ms = -1.0
        self._last_pitch_rad = 0.0
        self._last_roll_rad = 0.0
        self._last_uncentered_pitch_rad = 0.0
        self._last_uncentered_roll_rad = 0.0
        self._pose_initialized = False
        self._last_accel_norm_xy = _normalized_xy(calibration.accel_neutral)
        self._center_accel_norm_xy = self._last_accel_norm_xy
        self._center_pitch_rad = 0.0
        self._center_roll_rad = 0.0
        self._relative_yaw_rad = 0.0
        self._last_sample_ms: float | None = None

    def recenter_current(self) -> None:
        self._center_pitch_rad = self._last_uncentered_pitch_rad
        self._center_roll_rad = self._last_uncentered_roll_rad
        self._center_accel_norm_xy = self._last_accel_norm_xy
        self._relative_yaw_rad = 0.0

    def set_tuning(
        self,
        *,
        tilt_full_scale_deg: float | None = None,
        yaw_rate_full_scale: float | None = None,
        pitch_rate_full_scale: float | None = None,
        deadzone: float | None = None,
        smoothing_alpha: float | None = None,
        response_curve: float | None = None,
        tilt_x_sign: float | None = None,
        tilt_y_sign: float | None = None,
        gyro_x_sign: float | None = None,
        gyro_y_sign: float | None = None,
    ) -> None:
        if tilt_full_scale_deg is not None:
            self.tilt_full_scale_rad = math.radians(max(1.0, float(tilt_full_scale_deg)))
        if yaw_rate_full_scale is not None:
            self.yaw_rate_full_scale = max(0.05, float(yaw_rate_full_scale))
        if pitch_rate_full_scale is not None:
            self.pitch_rate_full_scale = max(0.05, float(pitch_rate_full_scale))
        if deadzone is not None:
            self.deadzone = min(0.9, max(0.0, float(deadzone)))
        if smoothing_alpha is not None:
            self.smoothing_alpha = clamp(float(smoothing_alpha), 0.0, 1.0)
        if response_curve is not None:
            self.response_curve = max(0.25, float(response_curve))
        if tilt_x_sign is not None:
            self.tilt_x_sign = 1.0 if float(tilt_x_sign) >= 0 else -1.0
        if tilt_y_sign is not None:
            self.tilt_y_sign = 1.0 if float(tilt_y_sign) >= 0 else -1.0
        if gyro_x_sign is not None:
            self.gyro_x_sign = 1.0 if float(gyro_x_sign) >= 0 else -1.0
        if gyro_y_sign is not None:
            self.gyro_y_sign = 1.0 if float(gyro_y_sign) >= 0 else -1.0

    def tuning_snapshot(self) -> dict[str, float]:
        return {
            "tilt_full_scale_deg": math.degrees(self.tilt_full_scale_rad),
            "yaw_rate_full_scale": self.yaw_rate_full_scale,
            "pitch_rate_full_scale": self.pitch_rate_full_scale,
            "deadzone": self.deadzone,
            "smoothing_alpha": self.smoothing_alpha,
            "response_curve": self.response_curve,
            "tilt_x_sign": self.tilt_x_sign,
            "tilt_y_sign": self.tilt_y_sign,
            "gyro_x_sign": self.gyro_x_sign,
            "gyro_y_sign": self.gyro_y_sign,
        }

    def update(self, sample: SensorSample, *, now_ms: float | None = None) -> ControllerState:
        now_ms = float(sample.t_ms if now_ms is None else now_ms)
        raw = {"x": float(sample.ax), "y": float(sample.ay), "z": float(sample.az)}
        bias = self.calibration.gyro_bias
        gx = float(sample.gx) - float(bias.get("x") or 0.0)
        gy = float(sample.gy) - float(bias.get("y") or 0.0)
        gz = float(sample.gz) - float(bias.get("z") or 0.0)
        gyro_abs = math.sqrt(gx * gx + gy * gy + gz * gz)
        if self._last_sample_ms is None:
            dt_s = 0.0
        else:
            dt_s = max(0.0, min(0.1, (now_ms - self._last_sample_ms) / 1000.0))
        self._last_sample_ms = now_ms
        next_yaw = self._relative_yaw_rad + gz * dt_s
        self._relative_yaw_rad = math.atan2(math.sin(next_yaw), math.cos(next_yaw))

        if self._previous_raw is None:
            accel_delta = 0.0
        else:
            accel_delta = math.sqrt(sum((raw[axis] - self._previous_raw[axis]) ** 2 for axis in ("x", "y", "z")))
        self._previous_raw = raw

        gate_active_before_sample = now_ms < self._gate_until_ms
        over_gate_threshold = accel_delta > self.calibration.accel_delta_threshold or gyro_abs > self.calibration.gyro_abs_threshold
        if over_gate_threshold and not gate_active_before_sample:
            self._gate_until_ms = max(self._gate_until_ms, now_ms + self.calibration.settle_ms)
        gate = now_ms < self._gate_until_ms

        if self._filtered_accel is None:
            self._filtered_accel = dict(raw)
        else:
            alpha = self.smoothing_alpha * (0.35 if gate else 1.0)
            for axis in ("x", "y", "z"):
                self._filtered_accel[axis] = self._filtered_accel[axis] * (1.0 - alpha) + raw[axis] * alpha

        ax = self._filtered_accel["x"]
        ay = self._filtered_accel["y"]
        az = self._filtered_accel["z"]
        accel_mag = math.sqrt(ax * ax + ay * ay + az * az)
        if accel_mag > 1e-9:
            accel_x_norm = ax / accel_mag
            accel_y_norm = ay / accel_mag
        else:
            accel_x_norm, accel_y_norm = self._last_accel_norm_xy
        self._last_accel_norm_xy = (accel_x_norm, accel_y_norm)
        accel_norm_x, accel_norm_y, accel_norm_z = _normalized_xyz({"x": ax, "y": ay, "z": az})

        raw_pitch = math.atan2(-ax, math.sqrt(ay * ay + az * az)) - self.calibration.pitch_rad
        raw_roll = math.atan2(ay, az) - self.calibration.roll_rad
        if self._pose_initialized:
            uncentered_pitch = unwrap_angle(self._last_uncentered_pitch_rad, raw_pitch)
            uncentered_roll = unwrap_angle(self._last_uncentered_roll_rad, raw_roll)
        else:
            uncentered_pitch = raw_pitch
            uncentered_roll = raw_roll
            self._pose_initialized = True
        self._last_uncentered_pitch_rad = uncentered_pitch
        self._last_uncentered_roll_rad = uncentered_roll
        pitch = uncentered_pitch - self._center_pitch_rad
        roll = uncentered_roll - self._center_roll_rad
        self._last_pitch_rad = pitch
        self._last_roll_rad = roll

        tilt_axis_scale = max(1e-6, math.sin(min(math.pi / 2, max(1e-6, self.tilt_full_scale_rad))))
        center_x_norm, center_y_norm = self._center_accel_norm_xy
        tilt_x = (accel_y_norm - center_y_norm) / tilt_axis_scale
        tilt_y = (accel_x_norm - center_x_norm) / tilt_axis_scale

        lx = apply_response_curve(
            apply_deadzone(self.tilt_x_sign * tilt_x, self.deadzone),
            self.response_curve,
        )
        ly = apply_response_curve(
            apply_deadzone(self.tilt_y_sign * tilt_y, self.deadzone),
            self.response_curve,
        )
        rx = apply_response_curve(
            apply_deadzone(self.gyro_x_sign * gz / self.yaw_rate_full_scale if self.yaw_rate_full_scale else 0.0, self.deadzone),
            self.response_curve,
        )
        ry = apply_response_curve(
            apply_deadzone(self.gyro_y_sign * -gy / self.pitch_rate_full_scale if self.pitch_rate_full_scale else 0.0, self.deadzone),
            self.response_curve,
        )

        palm = "face_up" if accel_norm_z > 0.55 else "face_down" if accel_norm_z < -0.55 else "edge"
        gesture, confidence = _classify_motion(
            gx=gx,
            gy=gy,
            gz=gz,
            accel_delta=accel_delta,
            accel_delta_threshold=self.calibration.accel_delta_threshold,
        )
        intensity = clamp((gyro_abs / 2.2) + (accel_delta / max(2.0, self.calibration.accel_delta_threshold * 8.0)) * 0.5, 0.0, 1.0)
        motion = MotionState(
            pitch_rad=pitch,
            roll_rad=roll,
            yaw_rad=round(self._relative_yaw_rad, 6),
            quat=_euler_to_quat(pitch=pitch, roll=roll, yaw=self._relative_yaw_rad),
            angular_velocity={"x": round(gx, 6), "y": round(gy, 6), "z": round(gz, 6)},
            accel_norm={"x": round(accel_norm_x, 6), "y": round(accel_norm_y, 6), "z": round(accel_norm_z, 6)},
            accel_delta=round(accel_delta, 6),
            gyro_abs=round(gyro_abs, 6),
            intensity=round(intensity, 6),
            palm=palm,
            gesture=gesture,
            confidence=confidence,
        )

        return ControllerState(
            lx=round(clamp(lx), 6),
            ly=round(clamp(ly), 6),
            rx=round(clamp(rx), 6),
            ry=round(clamp(ry), 6),
            gate=gate,
            pitch_rad=pitch,
            roll_rad=roll,
            gyro_abs=gyro_abs,
            accel_delta=accel_delta,
            motion=motion,
        )
