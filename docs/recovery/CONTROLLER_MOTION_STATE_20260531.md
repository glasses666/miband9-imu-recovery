# Mi Band 9 controller / motion state checkpoint — 2026-05-31

Purpose: preserve the current controller/HUD/XInput state before pivoting to direct-connection research.

## Git checkpoint

- Branch: `hfimucli-headless-mvp`
- Commit: `5663f9faa Add Mi Band motion channel HUD`
- Verification at checkpoint: `43 passed`

## Preserved product state

Working stack:

```text
Mi Band 9
→ Mi Fitness SportXms/812 + Android/hfimucli/logcat
→ Mac calibrated controller core
→ ControllerState + MotionState
→ HUD / Windows XInput receiver
```

Controller compatibility channel:

- `ControllerState`: `lx`, `ly`, `rx`, `ry`, triggers, gate.
- Windows1 vgamepad/XInput path had already been API-verified before this checkpoint.

Motion / claw channel:

- `MotionState` is emitted inside controller frames.
- Fields include:
  - `pitch_rad`, `roll_rad`, `yaw_rad`
  - `quat`
  - `angular_velocity`
  - `accel_norm`
  - `accel_delta`, `gyro_abs`
  - `intensity`
  - `palm`
  - `gesture`
  - `confidence`
- Current first-pass gesture labels:
  - `idle`
  - `twist_left` / `twist_right`
  - `slash_up` / `slash_down`
  - `roll_left` / `roll_right`
  - `jab`

HUD:

- URL when running: `http://127.0.0.1:18770/`
- Script: `tools/miband9ctl/controller_visualizer.py`
- Latest live calibration name: `flat-recalibration-20260531_115337`
- HUD was intentionally stopped after this checkpoint because Queen Glasser was outside and could not view it.

Last API snapshot before stopping the invisible HUD:

```json
{
  "hud_status": "live",
  "frames": 59920,
  "last_packet_age_ms": 777902,
  "calibration": "flat-recalibration-20260531_115337",
  "controller": {
    "lx": 0.0,
    "ly": -1.0,
    "rx": 0.0,
    "ry": 0.0,
    "gate": false
  },
  "motion": {
    "gesture": "idle",
    "confidence": 0.0,
    "palm": "edge",
    "intensity": 0.006856,
    "yaw_rad": 0.57179
  }
}
```

Note: the `last_packet_age_ms` in that snapshot was stale (~13 minutes). Treat the code state as preserved, not that specific live pose as useful calibration evidence.

## Restart commands

From `tools/miband9ctl`:

```bash
python3 controller_visualizer.py \
  --host 127.0.0.1 \
  --port 18770 \
  --duration-ms 3600000 \
  --tilt-full-scale-deg 30 \
  --yaw-rate-full-scale 1 \
  --pitch-rate-full-scale 1 \
  --deadzone 0.05 \
  --smoothing-alpha 0.34 \
  --response-curve 1
```

Verification:

```bash
python3 - <<'PY'
import json
from urllib.request import urlopen
s=json.load(urlopen('http://127.0.0.1:18770/api/state',timeout=5))
latest=s.get('latest') or {}
print({k:s.get(k) for k in ['status','mode','frames','last_packet_age_ms','calibration_name']})
print('controller', {k:latest.get(k) for k in ['lx','ly','rx','ry','gate']})
print('motion', (latest.get('motion') or {}))
PY
```

## Direct-connection pivot boundary

Do not destroy or overwrite this known-good Android-assisted route while exploring direct connection.

Direct route target is now:

```text
Gadgetbridge/hfimucli initialized auth/session knowledge
+ extracted Mi Fitness SportXms/812 start sequence
→ Gadgetbridge-native opener first
→ macOS CoreBluetooth direct daemon later
```

Important: `sportType=812` and Binder transaction IDs are not sufficient by themselves. The missing artifact is the real protocol command sequence emitted after `startSport(812)` and before the first `WearSensorData` sensor packet.
