# CLI-Anything Inspiration for Mi Band 9 HF IMU Tooling

**Context:** Queen Glasser remembered the HKUDS project that turns software into CLI tools. This note records what is useful for the Mi Band 9 recovery project.

**Audited repo:** `HKUDS/CLI-Anything`

- URL: `https://github.com/HKUDS/CLI-Anything`
- Homepage: `https://clianything.cc/`
- Positioning: "Making ALL Software Agent-Native"
- Current observed metadata: Python, Apache-2.0, default branch `main`, ~41k stars, updated 2026-05-29 UTC
- Current observed structure: 57 `*/agent-harness/setup.py`, 60 top-level `skills/*/SKILL.md`, 56 unit-test modules, 54 E2E-test modules

## Bottom Line

CLI-Anything is the right mental model, but not something to drop in wholesale.

For this project, Gadgetbridge should remain the real Android backend engine. The new tool should be a thin, structured harness:

```text
Mac CLI: miband9ctl
  -> adb backend
  -> Android side-by-side Gadgetbridge HF IMU debug agent
  -> real Android Bluetooth / Gadgetbridge connection state
  -> Mi Band 9 Classic/SPP/raw IMU experiment path
```

Do not rewrite Gadgetbridge in Python. Do not make Mac Bluetooth the main path. The CLI is a control plane, not the Bluetooth implementation.

## Useful CLI-Anything Ideas to Copy

### 1. Use the real software as the backend

CLI-Anything's strongest rule is: wrap the real software; do not reimplement it.

Applied here:

- Real backend: `Gadgetbridge HF IMU` Android APK.
- Transport: `adb shell am broadcast`, `adb logcat`, `adb shell pm`, `adb shell run-as` / root fallback.
- CLI responsibility: build packets, install APK, configure debug prefs, call receiver actions, parse logs, save artifacts.
- Android responsibility: Bluetooth permissions, foreground/service lifecycle, device support, Xiaomi auth/session, SPP channel 5, raw send/receive.

### 2. Make commands probe-first

Agents need cheap state before mutation.

First-class commands should include:

```bash
miband9ctl doctor --json
miband9ctl phone info --json
miband9ctl app state --json
miband9ctl band list --json
miband9ctl logs status --json
miband9ctl imu stats --json
```

Only after those should we expose mutating commands:

```bash
miband9ctl build
miband9ctl install
miband9ctl setup
miband9ctl app launch
miband9ctl band scan
miband9ctl band connect --address XX:XX:XX:XX:XX:XX
miband9ctl imu init
miband9ctl imu raw <hex>
miband9ctl imu collect --seconds 30
```

### 3. JSON output is non-negotiable

Every command should support `--json` with a stable schema:

```json
{
  "ok": true,
  "command": "imu.collect",
  "device_serial": "c8f9a1da",
  "package": "nodomain.freeyourgadget.gadgetbridge.hfimu",
  "artifacts": {
    "logcat": "/tmp/miband9-hfimu/collect_YYYYMMDD_HHMMSS.log",
    "summary": "/tmp/miband9-hfimu/collect_YYYYMMDD_HHMMSS.json"
  },
  "metrics": {
    "raw_packets": 0,
    "stats_lines": 0,
    "window_packet_rate": null
  }
}
```

Human text is allowed, but it must be a view over the same structured result.

### 4. Split CLI into core + backend modules

Recommended file layout:

```text
tools/miband9ctl/
  pyproject.toml
  miband9ctl/
    __init__.py
    cli.py
    backends/
      adb.py
      gradle.py
      logcat.py
    core/
      packets.py
      install.py
      setup.py
      state.py
      imu.py
      band.py
    tests/
      test_packets.py
      test_adb_backend.py
      test_cli_json.py
  SKILL.md
```

This mirrors CLI-Anything's agent-harness pattern without importing the whole platform.

### 5. Keep state in a session file, not in chat memory

Suggested file:

```text
~/.miband9ctl/session.json
```

Allowed contents:

- selected Android serial
- target package
- APK path
- last known APK sha256
- repo commit
- current log path
- last chosen band address/name
- last collect artifact path

Never store:

- Mi Band auth key
- OAuth tokens
- Android private app-data contents
- rclone config
- any password/token/credential value

Use file locking for writes so parallel agent calls do not corrupt state.

### 6. Add Android-side headless receiver actions gradually

Existing action:

```text
nodomain.freeyourgadget.gadgetbridge.SEND_IMU_CMD
```

Useful new actions:

```text
nodomain.freeyourgadget.gadgetbridge.HFIMU_DUMP_STATE
nodomain.freeyourgadget.gadgetbridge.HFIMU_START_SCAN
nodomain.freeyourgadget.gadgetbridge.HFIMU_STOP_SCAN
nodomain.freeyourgadget.gadgetbridge.HFIMU_CONNECT
nodomain.freeyourgadget.gadgetbridge.HFIMU_RECONNECT
nodomain.freeyourgadget.gadgetbridge.HFIMU_SEND_INIT
nodomain.freeyourgadget.gadgetbridge.HFIMU_LOG_MARKER
```

They should be guarded by `intent_api_allow_debug_commands=true` and package-scoped with `adb shell am broadcast -p nodomain.freeyourgadget.gadgetbridge.hfimu ...`.

### 7. Logs are artifacts, not console spam

`collect` should always write files and then print paths:

```text
/tmp/miband9-hfimu/collect_YYYYMMDD_HHMMSS.log
/tmp/miband9-hfimu/collect_YYYYMMDD_HHMMSS.json
```

The summary JSON should include:

- raw log line count
- `MI_IMU_RAW_RX` count
- `MI_IMU_STATS` count
- first/last timestamps
- observed packet-rate window if present
- APK sha256
- git commit
- phone model / Android SDK
- whether the app reported connected device state

### 8. Tests should be layered

Unit tests, no phone needed:

- CRC / packet construction
- adb command construction
- log parser
- JSON output schema
- session file locking / redaction

Device smoke tests, phone required:

- `doctor` sees ADB device
- `install` installs side-by-side package
- `setup` grants permissions and flips debug preference
- `imu init` returns Android broadcast success
- `collect --seconds 5` creates non-empty log artifacts

True HF IMU success still requires real band state and cannot be faked.

## Rooted Android Impact

Root materially lowers tool-chain difficulty:

- can install side-by-side APK via `pm install`
- can grant runtime permissions
- can edit debug preferences with `run-as` or `su`
- can inspect package state, app data layout, and Bluetooth state
- can preserve/restore backups

Root does not eliminate:

- first USB authorization
- system Bluetooth pairing prompts
- Mi Band screen confirmations
- the hidden high-frequency IMU / ODR problem

So root turns the harness from annoying into clean, but it does not solve the sensor protocol itself.

## Kali Impact

Kali is useful as a passive or side-channel lab:

- BLE scan / advertisement capture
- `bluetoothctl` / `btmon` observation
- GameSir/FF12/865F route experiments with a separate adapter

But ordinary Bluetooth hardware in Kali should not become the main control path. The main path remains root Android + Gadgetbridge HF IMU + Mac CLI.

## Suggested MVP Order

1. Create `tools/miband9ctl` Python Click CLI with `doctor`, `build`, `install`, `setup`, `app launch`, `imu init`, `imu raw`, `logs tail`, `imu collect`.
2. Reuse existing `send_imu_cmd.py` packet code by moving it into `miband9ctl/core/packets.py`.
3. Replace `mobile_smoke_test.sh` with Python commands that return structured JSON.
4. Add unit tests for packet building and adb command generation.
5. Add one git checkpoint.
6. Add Android receiver actions for `dump-state` first, then scan/connect.
7. Only after state/scan/connect are CLI-visible, resume real hand-ring pairing and HF IMU capture.

## Design Verdict

This project should become a local CLI-Anything-style harness, not a packaged CLI-Anything marketplace entry yet.

The dragon version:

```text
miband9ctl is the scepter.
Gadgetbridge HF IMU is the hand.
The band is the stubborn little lizard.
```
