# IMU static correction and vibration-gate pass — 2026-05-30

This note records the first quiet-table correction pass for the Mi Band 9 SportXms / 812 IMU dashboard.

## Setup

- Device pose: band left flat/still on the desk/table.
- Sport route: Mi Fitness SportXms `sportType=812` through the existing `hfimucli` harness.
- Capture: `miband9ctl --json band sport-xms-probe --start --sport-type 812`.
- Safety: no bond reset, no auth-key export, no raw private artifacts committed.

## Static baseline result

A 15 s quiet capture produced 144 sensor packets; 143 valid packets remained after dropping the startup/stale timestamp packet.

Baseline vector, in the band's SportXms sensor frame:

```json
{
  "accel_neutral": {"x": 8.5579, "y": -4.1832, "z": -2.5923, "mag": 9.8720},
  "gyro_bias": {"x": -0.00453, "y": -0.00313, "z": -0.00217},
  "pitch_deg": -60.10,
  "roll_deg": -121.79
}
```

The key observation is that "flat on table" is not `+Z ≈ +g` in the raw SportXms frame.  It is stable, but the sensor axes are rotated relative to the visual band model, so the dashboard must treat this pose as an anchor rather than assume a phone-like coordinate frame.

## New helper

`tools/miband9ctl/imu_static_calibration.py` turns a quiet SportXms JSON capture into a dashboard calibration file:

```bash
python3 imu_static_calibration.py \
  artifacts/imu_calibration/20260530_flat_vibration/baseline_flat_15s.json \
  -o artifacts/imu_calibration/20260530_flat_vibration/flat_table_calibration_20260530.json \
  --name flat-table-live-20260530
```

The generated JSON includes:

- `accel_neutral`: stable gravity vector in the SportXms frame.
- `gyro_bias`: stationary gyro zero bias.
- `pitch_rad` / `roll_rad`: pose zero offsets for the live dashboard.
- `noise`: quiet-pose range/stdev summary.
- `vibration_gate`: derived thresholds used to soften/freeze attitude correction during vibration or table taps.

## Dashboard correction changes

`live_sportxms_web.py` now applies:

1. Gyro bias subtraction from the calibration file.
2. Low-pass smoothing on the accel vector before attitude estimation.
3. Pose zeroing from `pitch_rad` / `roll_rad`.
4. A vibration/motion gate using accel jerk + gyro magnitude.
5. Slow attitude updates while the gate is active, so haptics do not become a false pose correction.
6. Live readout of raw accel, filtered accel, calibrated gyro, gate state, accel delta, and gyro magnitude.

Example run:

```bash
python3 live_sportxms_web.py \
  --duration-ms 18000 \
  --no-open \
  --port 8766 \
  --calibration artifacts/imu_calibration/20260530_flat_vibration/flat_table_calibration_20260530.json \
  --out artifacts/imu_calibration/20260530_flat_vibration/live_verify
```

## Vibration probe result

Two ADB-triggered debug notification/call probes were sent while capturing SportXms data.  The broadcasts were accepted, but the quiet-table IMU window did not show a strong distinct vibration spike above the normal stationary noise floor.

Observed ranges stayed roughly:

- Static accel packet range mean: ~0.11–0.12 m/s².
- Static gyro packet range mean: ~0.006–0.007 rad/s.
- Call-window values were very close to pre/post windows.

Interpretation: either the current debug notification/call route did not strongly vibrate the band during SportXms, or the desk/table coupling is weak enough that this probe is not a reliable haptic calibration signal.  The dashboard still has a motion/vibration gate, but validating it needs a stronger known haptic command, likely Gadgetbridge `find device` or a native Mi Fitness haptic path.

## Headless find-band command — implementation pass

The direct Android service route was tried first:

```text
adb shell am start-foreground-service \
  -n nodomain.freeyourgadget.gadgetbridge.hfimucli/nodomain.freeyourgadget.gadgetbridge.service.DeviceCommunicationService \
  -a nodomain.freeyourgadget.gadgetbridge.devices.action.find_device \
  --ez find_start true
```

It failed with `Requires permission not exported from uid ...`, which means ADB cannot safely call Gadgetbridge's internal `DeviceCommunicationService` directly from outside the package.  That is good evidence for adding the haptic trigger inside `hfimucli` instead of trying to poke private services from the shell.

Added headless route:

```bash
python3 -m miband9ctl --json band find-band --duration-ms 3000
# optional explicit target:
python3 -m miband9ctl --json band find-band --address AA:BB:CC:DD:EE:02 --duration-ms 3000
```

The Android side resolves the initialized `GBDevice`, calls `GBApplication.deviceService(device).onFindDevice(true)`, then stops it after the requested duration.  Logs include `find_started`, `find_stopped`, and `find_complete`, with device state and duration fields for marker alignment.

A repeatable probe wrapper now exists:

```bash
python3 tools/miband9ctl/vibration_gate_probe.py \
  --quiet-before-ms 5000 \
  --vibration-ms 3000 \
  --quiet-after-ms 5000
```

It writes a timestamped `sport_xms_probe.json`, `markers.jsonl`, and `gate_metrics.json` under `tools/miband9ctl/artifacts/imu_calibration/vibration_gate_probe/`.  The metrics split the capture into `quiet_before`, `vibration`, and `quiet_after` windows and record packet count, gate-hit ratio, accel delta mean/p95/max, gyro abs mean/p95/max, and packet accel/gyro range summaries against the flat-table calibration thresholds.

The local phone still has the old `hfimucli` APK, so a live CLI smoke currently reports `unknown_command` for `find-band`. That is expected until the updated APK is built and installed.

## Next step

Build/install the updated `hfimucli` APK when Android SDK is available on this machine or on a build host, then repeat:

```text
quiet 5 s → find-band vibration 2–4 s → quiet 5 s
```

That will give a controlled haptic window for tuning `vibration_gate` without relying on notification behavior.
