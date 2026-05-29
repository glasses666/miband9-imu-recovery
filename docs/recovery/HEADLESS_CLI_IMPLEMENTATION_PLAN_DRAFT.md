# Mi Band 9 HF IMU Headless CLI Implementation Plan — Draft v0

> **For Hermes:** This is the first detailed implementation plan before the brainstorming revision pass. Use it as a baseline, then apply the revised plan in `HEADLESS_CLI_IMPLEMENTATION_PLAN.md`.

**Goal:** Build a CLI-Anything-style local harness named `miband9ctl` so Mac can control the rooted Android `Gadgetbridge HF IMU` side-by-side APK without repeated screen swiping, while preserving Gadgetbridge as the real Bluetooth backend.

**Architecture:** Mac-side Python CLI wraps `adb`, Gradle, logcat, APK install, root/run-as preference edits, and IMU packet construction. Android-side Gadgetbridge receives guarded package-scoped debug broadcasts and gradually exposes headless state/scan/connect/init actions. Real Bluetooth, pairing, Xiaomi support, SPP channel 5, and app lifecycle remain inside Android/Gadgetbridge.

**Tech Stack:** Python 3 stdlib + optional Click, adb/platform-tools, Gradle/JDK17, Android Java broadcast receivers/services, logcat artifact parser, git checkpoints.

---

## Acceptance Target

The first usable version is successful when these work from repo root:

```bash
python3 tools/miband9ctl/miband9ctl.py doctor --json
python3 tools/miband9ctl/miband9ctl.py build --json
python3 tools/miband9ctl/miband9ctl.py install --json
python3 tools/miband9ctl/miband9ctl.py setup --json
python3 tools/miband9ctl/miband9ctl.py app launch --json
python3 tools/miband9ctl/miband9ctl.py imu init --json
python3 tools/miband9ctl/miband9ctl.py imu collect --seconds 10 --json
```

Expected proof:

- JSON output is valid for every command.
- Original Gadgetbridge package remains untouched.
- Side-by-side package `nodomain.freeyourgadget.gadgetbridge.hfimu` remains the default target.
- `setup` grants Android permissions where possible and enables `intent_api_allow_debug_commands=true` without printing private app data.
- `imu init` produces Android broadcast success.
- `imu collect` writes a log artifact and a summary JSON artifact under `/tmp/miband9-hfimu/`.
- Unit tests cover packet construction, adb command construction, log parsing, JSON schema, and redaction.
- Build verification still passes: `:app:assembleMainlineDebug`.

Non-goals for MVP:

- Do not claim >100Hz IMU success.
- Do not rewrite Gadgetbridge Bluetooth logic in Python.
- Do not use Mac Bluetooth as the main control path.
- Do not store or print Mi Band auth keys, app private data, OAuth tokens, passwords, or rclone config.
- Do not replace the original Gadgetbridge package.

---

## Phase 0 — Repo state and rollback guard

**Objective:** Confirm the plan starts from a clean, rollback-safe branch.

**Files:**

- Read: `docs/recovery/CLI_ANYTHING_INSPIRATION.md`
- Read: `tools/imu/send_imu_cmd.py`
- Read: `tools/imu/mobile_smoke_test.sh`
- Read: `app/src/main/java/nodomain/freeyourgadget/gadgetbridge/externalevents/IntentApiReceiver.java`

**Steps:**

1. Verify branch and clean tree:
   ```bash
   cd <repo>
   git status --short --branch
   git log --oneline -6
   ```
   Expected: branch `hf-imu-recovery`, clean or only plan files.

2. Verify no current background logcat confusion before device smoke testing:
   ```bash
   ps aux | grep '[a]db logcat' || true
   ```
   If old capture is running, record its path and stop only if it belongs to this project.

3. Commit the final revised plan before implementation:
   ```bash
   git add docs/recovery/HEADLESS_CLI_IMPLEMENTATION_PLAN.md
   git commit -m "docs: plan headless Mi Band 9 CLI harness"
   ```

---

## Phase 1 — Mac CLI skeleton and JSON contract

**Objective:** Create a small but structured `miband9ctl` CLI that can run with no third-party dependencies.

**Files:**

- Create: `tools/miband9ctl/miband9ctl.py`
- Create: `tools/miband9ctl/miband9ctl/__init__.py`
- Create: `tools/miband9ctl/miband9ctl/output.py`
- Create: `tools/miband9ctl/miband9ctl/config.py`
- Create: `tools/miband9ctl/README.md`
- Test: `tools/miband9ctl/tests/test_cli_json.py`

**Implementation notes:**

Use `argparse` for MVP to avoid installing dependencies on Draco. Keep a later path to Click if the CLI grows.

Global options:

```text
--json
--serial <adb-serial>
--package <android-package>
--apk <apk-path>
--artifact-dir <dir>
--repo-root <path>
```

Defaults:

```text
package = nodomain.freeyourgadget.gadgetbridge.hfimu
apk = app/build/outputs/apk/mainline/debug/app-mainline-debug.apk
artifact_dir = /tmp/miband9-hfimu
session_file = ~/.miband9ctl/session.json
```

JSON result shape:

```json
{
  "ok": true,
  "command": "doctor",
  "message": "ready",
  "data": {},
  "artifacts": {},
  "warnings": [],
  "errors": []
}
```

**Verification:**

```bash
python3 tools/miband9ctl/miband9ctl.py --help
python3 tools/miband9ctl/miband9ctl.py doctor --json | python3 -m json.tool >/dev/null
python3 -m pytest tools/miband9ctl/tests/test_cli_json.py -q
```

**Commit:**

```bash
git add tools/miband9ctl
git commit -m "feat: scaffold miband9ctl CLI harness"
```

---

## Phase 2 — Backend wrappers: adb, Gradle, package state

**Objective:** Centralize all shell calls and return structured results instead of ad-hoc scripts.

**Files:**

- Create: `tools/miband9ctl/miband9ctl/backends/adb.py`
- Create: `tools/miband9ctl/miband9ctl/backends/gradle.py`
- Create: `tools/miband9ctl/miband9ctl/core/doctor.py`
- Create: `tools/miband9ctl/miband9ctl/core/install.py`
- Test: `tools/miband9ctl/tests/test_adb_backend.py`

**Commands to implement:**

```bash
miband9ctl doctor
miband9ctl phone info
miband9ctl build
miband9ctl install
miband9ctl app state
miband9ctl app launch
```

**Key behavior:**

- `doctor` checks `adb`, authorized device count, package install state, APK path, APK sha256, repo commit, Android release/API/model, root availability.
- `build` runs:
  ```bash
  JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home ./gradlew --no-daemon :app:assembleMainlineDebug
  ```
- `install` first tries normal `adb install -r`, then rooted fallback:
  ```bash
  adb push <apk> /data/local/tmp/miband9-hfimu.apk
  adb shell su -c 'pm install -r /data/local/tmp/miband9-hfimu.apk'
  ```
- `app state` uses `pm path`, `dumpsys package`, and `pidof`.
- `app launch` uses:
  ```bash
  adb shell monkey -p nodomain.freeyourgadget.gadgetbridge.hfimu 1
  ```

**Safety rules:**

- Never uninstall or overwrite `nodomain.freeyourgadget.gadgetbridge`.
- Always target `.hfimu` by default.
- Include the actual package in JSON output so mistakes are visible.

**Verification:**

```bash
python3 tools/miband9ctl/miband9ctl.py doctor --json | python3 -m json.tool
python3 tools/miband9ctl/miband9ctl.py app state --json | python3 -m json.tool
python3 -m pytest tools/miband9ctl/tests/test_adb_backend.py -q
```

**Commit:**

```bash
git add tools/miband9ctl
git commit -m "feat: add adb and install backends to miband9ctl"
```

---

## Phase 3 — Packet engine and IMU command commands

**Objective:** Move packet construction out of `send_imu_cmd.py` into testable CLI modules while keeping the old script as a compatibility wrapper.

**Files:**

- Create: `tools/miband9ctl/miband9ctl/core/packets.py`
- Create: `tools/miband9ctl/miband9ctl/core/imu.py`
- Modify: `tools/imu/send_imu_cmd.py`
- Test: `tools/miband9ctl/tests/test_packets.py`
- Test: `tools/miband9ctl/tests/test_imu_commands.py`

**Commands to implement:**

```bash
miband9ctl imu init
miband9ctl imu fuzz-fast
miband9ctl imu raw <hex>
miband9ctl imu data <payload-hex> --type 3
```

**Packet facts to preserve:**

- A5/A5 header.
- CRC-16/ARC payload-only calculation from recovered Xiaomi packet logic.
- Default init payload already used by `tools/imu/send_imu_cmd.py`.
- Target broadcast action:
  ```text
  nodomain.freeyourgadget.gadgetbridge.SEND_IMU_CMD
  ```

**Compatibility:**

`tools/imu/send_imu_cmd.py` should import the new packet functions or delegate to `miband9ctl imu ...`. This prevents packet logic drift.

**Verification:**

```bash
python3 tools/miband9ctl/miband9ctl.py imu init --dry-run --json | python3 -m json.tool
python3 tools/imu/send_imu_cmd.py --init --dry-run
python3 -m pytest tools/miband9ctl/tests/test_packets.py tools/miband9ctl/tests/test_imu_commands.py -q
```

Expected init hex:

```text
a5a5020016001d4d0101030001000002020000fc03020020000402001027
```

**Commit:**

```bash
git add tools/miband9ctl tools/imu/send_imu_cmd.py
git commit -m "feat: add miband9ctl IMU packet commands"
```

---

## Phase 4 — Setup automation for rooted Android

**Objective:** Replace manual setup notes with a repeatable CLI command that prepares the side-by-side package.

**Files:**

- Create: `tools/miband9ctl/miband9ctl/core/setup.py`
- Test: `tools/miband9ctl/tests/test_setup_commands.py`
- Modify: `tools/imu/mobile_smoke_test.sh` or mark it deprecated in favor of `miband9ctl`.

**Command to implement:**

```bash
miband9ctl setup
```

**Behavior:**

1. Grant permissions where valid for the phone SDK:
   ```bash
   adb shell pm grant <pkg> android.permission.ACCESS_FINE_LOCATION
   adb shell pm grant <pkg> android.permission.ACCESS_COARSE_LOCATION
   ```
   On API 31+, also try Bluetooth permissions.

2. Enable debug command preference using the safest available route:
   - prefer `run-as <pkg>` when allowed;
   - fallback to `su` and app data path when rooted;
   - create backup of preference file before editing.

3. Verify preference without printing unrelated app data:
   ```text
   intent_api_allow_debug_commands=true
   ```

4. Start app once if needed to create shared preferences.

**Verification:**

```bash
python3 tools/miband9ctl/miband9ctl.py setup --json | python3 -m json.tool
python3 tools/miband9ctl/miband9ctl.py doctor --json | python3 -m json.tool
```

**Commit:**

```bash
git add tools/miband9ctl tools/imu/mobile_smoke_test.sh
git commit -m "feat: automate rooted Android setup for HF IMU package"
```

---

## Phase 5 — Log capture, parser, and experiment artifacts

**Objective:** Turn logcat capture into reproducible artifacts with a summary JSON.

**Files:**

- Create: `tools/miband9ctl/miband9ctl/backends/logcat.py`
- Create: `tools/miband9ctl/miband9ctl/core/logs.py`
- Create: `tools/miband9ctl/miband9ctl/core/collect.py`
- Test: `tools/miband9ctl/tests/test_log_parser.py`

**Commands to implement:**

```bash
miband9ctl logs tail
miband9ctl logs clear
miband9ctl imu collect --seconds 30
miband9ctl imu stats --from /tmp/miband9-hfimu/collect_*.log
```

**Artifact outputs:**

```text
/tmp/miband9-hfimu/collect_YYYYMMDD_HHMMSS.log
/tmp/miband9-hfimu/collect_YYYYMMDD_HHMMSS.json
```

**Summary metrics:**

- raw `MI_IMU_RAW_RX` lines
- `MI_IMU_STATS` lines
- first and last timestamps
- observed packet-rate window if log line exposes it
- broadcast success/failure lines
- package name
- phone model/API
- repo commit
- APK sha256
- warning if zero IMU packets were observed

**Verification:**

```bash
python3 tools/miband9ctl/miband9ctl.py imu collect --seconds 5 --json | python3 -m json.tool
python3 tools/miband9ctl/miband9ctl.py imu stats --from /tmp/miband9-hfimu/<file>.log --json | python3 -m json.tool
python3 -m pytest tools/miband9ctl/tests/test_log_parser.py -q
```

**Commit:**

```bash
git add tools/miband9ctl
git commit -m "feat: collect HF IMU log artifacts from miband9ctl"
```

---

## Phase 6 — Android headless state receiver before scan/connect

**Objective:** Add the smallest Android-side receiver action that lets the CLI ask Gadgetbridge what it knows, before trying harder scan/connect automation.

**Files:**

- Modify: `app/src/main/java/nodomain/freeyourgadget/gadgetbridge/externalevents/IntentApiReceiver.java`
- Create: `app/src/main/java/nodomain/freeyourgadget/gadgetbridge/externalevents/HfImuDebugState.java`
- Modify if needed: `app/src/main/java/nodomain/freeyourgadget/gadgetbridge/model/DeviceService.java`
- Modify if needed: `tools/miband9ctl/miband9ctl/core/state.py`
- Test: Java build + Python tests

**New action:**

```text
nodomain.freeyourgadget.gadgetbridge.HFIMU_DUMP_STATE
```

**State data to log under `MI_HFIMU_STATE`:**

- package/application id
- debug commands preference enabled/disabled
- Bluetooth enabled/disabled
- known Gadgetbridge devices: address, name, type, state
- selected/initialized devices
- whether target address extra matched a known device

**Why logcat instead of broadcast result extras:**

`adb shell am broadcast` output is too limited and Android receiver result extras are awkward across versions. Logging `MI_HFIMU_STATE` keeps the first implementation simple; CLI parses the next matching line.

**Verification:**

```bash
JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home ./gradlew --no-daemon :app:assembleMainlineDebug
python3 tools/miband9ctl/miband9ctl.py install --json
python3 tools/miband9ctl/miband9ctl.py app state --json
```

**Commit:**

```bash
git add app/src/main/java tools/miband9ctl
git commit -m "feat: expose HF IMU Android state dump action"
```

---

## Phase 7 — Headless scan/connect actions, guarded and reversible

**Objective:** Add minimal scan/connect controls only after `dump-state` is visible and tested.

**Files:**

- Create: `app/src/main/java/nodomain/freeyourgadget/gadgetbridge/externalevents/HfImuHeadlessController.java`
- Modify: `app/src/main/java/nodomain/freeyourgadget/gadgetbridge/externalevents/IntentApiReceiver.java`
- Modify: `tools/miband9ctl/miband9ctl/core/band.py`
- Test: Java build + device smoke

**New actions:**

```text
nodomain.freeyourgadget.gadgetbridge.HFIMU_START_SCAN
nodomain.freeyourgadget.gadgetbridge.HFIMU_STOP_SCAN
nodomain.freeyourgadget.gadgetbridge.HFIMU_CONNECT
nodomain.freeyourgadget.gadgetbridge.HFIMU_RECONNECT
```

**Staged approach:**

1. `band list`: list paired/known Gadgetbridge devices from state dump.
2. `band connect --address <MAC>`: only connect if the address is already known to Gadgetbridge.
3. `band scan --seconds N`: initially can open/trigger existing discovery only if reliable; otherwise use Android Bluetooth bonded/nearby state and report that full pairing still needs user confirmation.

**Acceptance:**

- It must not silently invent a device in the DB.
- It must not consume or print auth keys.
- If pairing requires hand/band confirmation, CLI reports `needs_user_confirmation`.
- Failure must be explicit: no known device, Bluetooth off, permission missing, receiver not installed, connect attempted but state not changed.

**Commit:**

```bash
git add app/src/main/java tools/miband9ctl
git commit -m "feat: add guarded headless band scan and connect actions"
```

---

## Phase 8 — First real device experiment using the CLI

**Objective:** Run the same SPP/init capture path with no screen swiping except unavoidable Android/band confirmations.

**Command sequence:**

```bash
miband9ctl doctor --json
miband9ctl setup --json
miband9ctl app state --json
miband9ctl band list --json
miband9ctl band connect --address <MAC> --json
miband9ctl imu init --json
miband9ctl imu collect --seconds 30 --json
```

**Experiment note file:**

```text
docs/recovery/experiments/YYYY-MM-DD-miband9ctl-spp-init.md
```

Record:

- repo commit
- APK sha256
- phone model/API
- band firmware if visible
- package name
- device state before and after connect
- init hex used
- raw packet count
- packet-rate estimate
- whether payload appears accel-only or accel+gyro
- whether result remains ~50Hz
- next path if SPP remains capped

**Commit:**

```bash
git add docs/recovery/experiments
git commit -m "test: record miband9ctl SPP init experiment"
```

---

## Brainstorming Prompt for Revision Pass

Before finalizing, critique this draft from three angles:

1. **CLI harness architecture:** Is this too much custom structure, or should it more closely mirror CLI-Anything packaging with `pyproject.toml`, console script, and `SKILL.md` immediately?
2. **Android headless integration:** Is `IntentApiReceiver` the right extension point, or should a dedicated debug service/receiver own `HFIMU_*` actions to avoid bloating the upstream intent API?
3. **Risk and verification:** What fails first on rooted MIUI/Android 9, and what should the plan do before touching scan/connect?

The revised plan should ruthlessly keep only what moves us toward a reliable headless experiment harness and avoid premature marketplace/polish work.
