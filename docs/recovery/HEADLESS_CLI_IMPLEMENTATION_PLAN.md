# Mi Band 9 HF IMU Headless CLI Implementation Plan

> **For Hermes:** This is the revised plan after the brainstorming pass. Implement task-by-task with small commits. Do not print, store, or commit auth keys/tokens/private app data. Use the original `HEADLESS_CLI_IMPLEMENTATION_PLAN_DRAFT.md` only as provenance.

**Goal:** Build a CLI-Anything-style local harness named `miband9ctl` so Mac can control the rooted Android `Gadgetbridge HF IMU` side-by-side APK without repeated screen swiping, while preserving Gadgetbridge as the real Bluetooth backend.

**Architecture:** Mac-side Python package `miband9ctl` wraps `adb`, Gradle, logcat, APK install, rooted/run-as setup, IMU packet construction, artifact capture, and experiment summaries. Android-side Gadgetbridge adds a dedicated guarded HF IMU debug receiver/controller for headless ping/state/connect/raw actions. Real Bluetooth, pairing, Xiaomi auth/session, SPP channel 5, raw RX, and lifecycle remain in Android/Gadgetbridge.

**Tech Stack:** Python 3 stdlib `argparse` packaged with `pyproject.toml`, no runtime third-party dependencies; adb/platform-tools; Gradle/JDK17; Android Java guarded debug receiver/controller; structured logcat parser; JSON result contract; session file with file locking and redaction; small git checkpoints. Click and CLI-Anything marketplace/SKILL packaging are deferred until after MVP.

---

## Brainstorming Revision Pass Applied

The draft was intentionally broad. The brainstorming pass changed the plan in these concrete ways:

1. Replace loose `tools/miband9ctl/miband9ctl.py` script with a real local Python package: `pyproject.toml`, `python -m miband9ctl`, and optional editable install.
2. Keep runtime dependency-free stdlib `argparse`; do not introduce Click yet.
3. Make stdout JSON-strict under `--json`: exactly one JSON object, no human progress text.
4. Add explicit exit-code mapping: `0` success, `1` command failure, `2` environment/precondition failure, `3` safety refusal.
5. Add `request_id`/`nonce` correlation for Android debug actions; never treat plain `am broadcast` completion as proof of app execution.
6. Do not keep bloating public `IntentApiReceiver`; new HFIMU actions use dedicated `HfImuDebugReceiver` and `HfImuHeadlessController`.
7. Use package-derived actions like `<pkg>.hfimu.debug.DUMP_STATE`, not global `nodomain.freeyourgadget.gadgetbridge.HFIMU_*` actions.
8. Make raw send target-specific by address or fail with `ambiguous_target`; avoid fan-out to all initialized devices.
9. Move scan/connect after ping, dump-state, preflight gates, artifact policy, fake-adb tests, and dry-run rehearsal.
10. Restrict MVP connect to known/bonded/Gadgetbridge-known devices; headless full pairing is not an MVP requirement.
11. Replace flat `/tmp/miband9-hfimu/collect_*.log` with per-run session directories and manifest files.
12. Add strict artifact and claim policy: packet rate, sample rate, payload class, and gyro presence are separate; `>100Hz` cannot be claimed without classifier-backed evidence.

---

## Acceptance Target

The first usable version is successful when these work from repo root:

```bash
PYTHONPATH=tools/miband9ctl python3 -m miband9ctl doctor --json
PYTHONPATH=tools/miband9ctl python3 -m miband9ctl phone info --json
PYTHONPATH=tools/miband9ctl python3 -m miband9ctl app state --json
PYTHONPATH=tools/miband9ctl python3 -m miband9ctl logs status --json
PYTHONPATH=tools/miband9ctl python3 -m miband9ctl build --json
PYTHONPATH=tools/miband9ctl python3 -m miband9ctl install --json
PYTHONPATH=tools/miband9ctl python3 -m miband9ctl setup --json
PYTHONPATH=tools/miband9ctl python3 -m miband9ctl app launch --json
PYTHONPATH=tools/miband9ctl python3 -m miband9ctl app debug-ping --json
PYTHONPATH=tools/miband9ctl python3 -m miband9ctl app dump-state --json
PYTHONPATH=tools/miband9ctl python3 -m miband9ctl imu init --dry-run --json
PYTHONPATH=tools/miband9ctl python3 -m miband9ctl imu collect --seconds 10 --json
```

Optional installed form:

```bash
python3 -m pip install -e tools/miband9ctl
miband9ctl doctor --json
```

Expected proof:

- With `--json`, stdout contains exactly one valid JSON object.
- Human progress, adb stderr, Gradle output, and logcat streams go to stderr or artifact files.
- Original Gadgetbridge package `nodomain.freeyourgadget.gadgetbridge` is not installed over, uninstalled, cleared, or mutated.
- Mutating commands refuse original Gadgetbridge unless the command is explicitly read-only and allowlisted.
- Side-by-side package `nodomain.freeyourgadget.gadgetbridge.hfimu` is the safe default target.
- If multiple ADB devices are authorized, commands fail with `needs_serial` unless `--serial` or session serial is set.
- `setup` grants Android permissions where possible and enables only `intent_api_allow_debug_commands=true`, without printing full preferences/private app data.
- `debug-ping` and `dump-state` prove app-side receiver execution via current-run `request_id`/`nonce` log lines.
- `imu init --dry-run` emits the known init packet and does not send anything.
- Real `imu init` is only used after target device state is known and initialized.
- `imu collect` writes per-run artifacts under `/tmp/miband9-hfimu/<timestamp>_<session_id>/`.
- Unit tests cover packet construction, adb command construction, root quoting, JSON schema, session locking, redaction, log parsing, and fake failure transcripts.
- Build verification still passes: `:app:assembleMainlineDebug`.

Non-goals for MVP:

- Do not claim >100Hz IMU success.
- Do not rewrite Gadgetbridge Bluetooth logic in Python.
- Do not use Mac Bluetooth as the main control path.
- Do not store or print Mi Band auth keys, app private data, OAuth tokens, passwords, rclone config, or complete shared preferences/database dumps.
- Do not automate firmware writes or destructive Bluetooth bond removal.
- Do not require full headless pairing as MVP; system/band confirmations may still be manual.

---

## Global CLI Contract

### Invocation

Development form:

```bash
PYTHONPATH=tools/miband9ctl python3 -m miband9ctl <command> [options]
```

Installed form:

```bash
miband9ctl <command> [options]
```

### Global options

```text
--json
--pretty
--serial <adb-serial>
--package <android-package>
--apk <apk-path>
--artifact-dir <dir>
--repo-root <path>
--session-file <path>
--no-session
--dry-run
--timeout <seconds>
```

### Config precedence

1. CLI flags
2. `MIBAND9CTL_*` environment variables
3. `~/.miband9ctl/session.json`
4. hardcoded safe defaults

Safe defaults:

```text
package = nodomain.freeyourgadget.gadgetbridge.hfimu
apk = app/build/outputs/apk/mainline/debug/app-mainline-debug.apk
artifact_dir = /tmp/miband9-hfimu
session_file = ~/.miband9ctl/session.json
```

### Session file

Path:

```text
~/.miband9ctl/session.json
```

Required properties:

- mode `0600`
- schema-versioned
- lock-protected writes
- resilient to corruption: preserve bad file as `session.json.corrupt.<timestamp>` and start clean

Allowed session keys:

```text
schema_version
selected_serial
target_package
apk_path
artifact_dir
repo_root
repo_commit
last_apk_sha256
last_logcat_path
last_summary_path
last_band_address
last_band_name
```

Forbidden session keys:

```text
auth_key
token
password
oauth
rclone
private_app_data
shared_preferences_dump
database_dump
```

### JSON result schema

Success shape:

```json
{
  "schema_version": 1,
  "ok": true,
  "command": "doctor",
  "timestamp_utc": "2026-05-29T00:00:00Z",
  "duration_ms": 123,
  "device_serial": null,
  "package": "nodomain.freeyourgadget.gadgetbridge.hfimu",
  "repo": {
    "root": "<repo>",
    "commit": null,
    "dirty": null
  },
  "data": {},
  "metrics": {},
  "artifacts": {},
  "warnings": [],
  "errors": []
}
```

Error item shape:

```json
{
  "code": "adb.no_device",
  "message": "No authorized Android device found",
  "hint": "Unlock the phone and accept the USB debugging prompt",
  "details": {}
}
```

Exit codes:

```text
0 success
1 command failure
2 environment/precondition failure
3 safety refusal
```

---

## Phase 0 — Baseline, rollback, and plan checkpoint

**Objective:** Start from a clean branch and record enough state to roll back without touching the original Gadgetbridge.

**Files:**

- Read: `docs/recovery/CLI_ANYTHING_INSPIRATION.md`
- Read: `docs/recovery/HEADLESS_CLI_IMPLEMENTATION_PLAN_DRAFT.md`
- Create: `docs/recovery/HEADLESS_CLI_IMPLEMENTATION_PLAN.md`

**Steps:**

1. Verify branch and tree:

   ```bash
   cd <repo>
   git status --short --branch
   git log --oneline -8
   ```

2. Record current package state before implementation:

   ```bash
   adb devices -l
   adb shell getprop ro.product.model
   adb shell getprop ro.build.version.release
   adb shell getprop ro.build.version.sdk
   adb shell pm path nodomain.freeyourgadget.gadgetbridge || true
   adb shell pm path nodomain.freeyourgadget.gadgetbridge.hfimu || true
   ```

3. Do not print or back up full app data here. Only record package presence, version, path, and APK sha if needed.

4. Commit the plan:

   ```bash
   git add docs/recovery/HEADLESS_CLI_IMPLEMENTATION_PLAN_DRAFT.md docs/recovery/HEADLESS_CLI_IMPLEMENTATION_PLAN.md
   git commit -m "docs: plan headless Mi Band 9 CLI harness"
   ```

**Acceptance:**

- Plan committed.
- No auth key/token/private app data in docs.
- Worktree clean after commit.

---

## Phase 1 — Python package skeleton, JSON, config, session, redaction

**Objective:** Create the CLI foundation with deterministic output and no side effects.

**Files:**

- Create: `tools/miband9ctl/pyproject.toml`
- Create: `tools/miband9ctl/README.md`
- Create: `tools/miband9ctl/miband9ctl/__init__.py`
- Create: `tools/miband9ctl/miband9ctl/__main__.py`
- Create: `tools/miband9ctl/miband9ctl/cli.py`
- Create: `tools/miband9ctl/miband9ctl/result.py`
- Create: `tools/miband9ctl/miband9ctl/config.py`
- Create: `tools/miband9ctl/miband9ctl/session.py`
- Create: `tools/miband9ctl/miband9ctl/redaction.py`
- Create: `tools/miband9ctl/miband9ctl/commands/__init__.py`
- Create: `tools/miband9ctl/miband9ctl/backends/__init__.py`
- Create: `tools/miband9ctl/miband9ctl/core/__init__.py`
- Test: `tools/miband9ctl/tests/test_cli_json.py`
- Test: `tools/miband9ctl/tests/test_config.py`
- Test: `tools/miband9ctl/tests/test_session.py`
- Test: `tools/miband9ctl/tests/test_redaction.py`

**Module boundary rules:**

```text
commands/: argparse command handlers and orchestration only
core/: pure functions, no subprocess, no adb
backends/: side effects only, subprocess/adb/gradle/logcat wrappers
result.py: one source for JSON schema, exit-code mapping, error shape
redaction.py: all adb/logcat/setup output passes through this before JSON/artifacts
session.py: lock-protected read/write of ~/.miband9ctl/session.json
```

**Commands implemented in this phase:**

```bash
miband9ctl --help
miband9ctl session show --json
miband9ctl session clear --json
```

**Verification:**

```bash
PYTHONPATH=tools/miband9ctl python3 -m miband9ctl --help
PYTHONPATH=tools/miband9ctl python3 -m miband9ctl session show --json | python3 -m json.tool >/dev/null
python3 -m unittest discover -s tools/miband9ctl/tests -p 'test_*.py'
```

**Commit:**

```bash
git add tools/miband9ctl
git commit -m "feat: scaffold packaged miband9ctl CLI harness"
```

---

## Phase 2 — Read-only probes and backend wrappers

**Objective:** Add safe probes before any mutating command.

**Files:**

- Create: `tools/miband9ctl/miband9ctl/backends/runner.py`
- Create: `tools/miband9ctl/miband9ctl/backends/adb.py`
- Create: `tools/miband9ctl/miband9ctl/backends/gradle.py`
- Create: `tools/miband9ctl/miband9ctl/backends/logcat.py`
- Create: `tools/miband9ctl/miband9ctl/commands/doctor.py`
- Create: `tools/miband9ctl/miband9ctl/commands/phone.py`
- Create: `tools/miband9ctl/miband9ctl/commands/app.py`
- Create: `tools/miband9ctl/miband9ctl/commands/logs.py`
- Test: `tools/miband9ctl/tests/test_runner.py`
- Test: `tools/miband9ctl/tests/test_adb_backend.py`
- Test: `tools/miband9ctl/tests/test_doctor.py`

**Backend rules:**

- Use `subprocess.run(argv_list, ...)`, never `shell=True`.
- Every command has a timeout.
- `runner` returns `returncode`, `stdout`, `stderr`, `duration_ms`.
- `adb shell su -c ...` quoting is centralized in one helper and unit-tested.
- No backend prints directly.
- Redact outputs before JSON.

**Commands implemented:**

```bash
miband9ctl doctor
miband9ctl phone info
miband9ctl app state
miband9ctl logs status
```

**Probe behavior:**

- `doctor`: check adb availability, device selection, package state, APK path, APK sha256, repo commit/dirty flag, Android model/release/API, root availability, and safety warnings.
- `phone info`: model, product, API, build fingerprint, Bluetooth enabled state if available.
- `app state`: package path/version, pid, launchable activity, debug package flag, original package read-only presence.
- `logs status`: identify current project-owned logcat captures if possible; warn about unrelated logcat rather than killing it.

**Verification:**

```bash
PYTHONPATH=tools/miband9ctl python3 -m miband9ctl doctor --json | python3 -m json.tool
PYTHONPATH=tools/miband9ctl python3 -m miband9ctl phone info --json | python3 -m json.tool
PYTHONPATH=tools/miband9ctl python3 -m miband9ctl app state --json | python3 -m json.tool
python3 -m unittest discover -s tools/miband9ctl/tests -p 'test_*.py'
```

**Commit:**

```bash
git add tools/miband9ctl
git commit -m "feat: add read-only adb probes to miband9ctl"
```

---

## Phase 3 — Safe mutating basics: build, install, setup, launch

**Objective:** Automate the current manual rooted Android setup while preserving rollback.

**Files:**

- Create: `tools/miband9ctl/miband9ctl/commands/build.py`
- Create: `tools/miband9ctl/miband9ctl/commands/install.py`
- Create: `tools/miband9ctl/miband9ctl/commands/setup.py`
- Create: `tools/miband9ctl/miband9ctl/core/install.py`
- Create: `tools/miband9ctl/miband9ctl/core/setup.py`
- Test: `tools/miband9ctl/tests/test_install_commands.py`
- Test: `tools/miband9ctl/tests/test_setup_commands.py`

**Commands implemented:**

```bash
miband9ctl build
miband9ctl install
miband9ctl setup
miband9ctl app launch
```

**Safety behavior:**

- Mutating commands hard-fail if `--package nodomain.freeyourgadget.gadgetbridge` is passed.
- They only operate on `.hfimu` or another explicit non-upstream package.
- `install` records preinstall side-by-side package state before changing anything.
- Default install path:
  1. Try `adb install -r <apk>`.
  2. If blocked on rooted MIUI, push to `/data/local/tmp/miband9-hfimu.apk` and run `pm install -r` under `su`.
  3. Never uninstall original Gadgetbridge.
- `build` uses `JAVA_HOME` if set; otherwise tries `/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home`; if unavailable return `gradle.no_jdk17`.
- `setup` starts app once if preferences do not exist; then uses `run-as` or `su` fallback to set only `intent_api_allow_debug_commands=true`.

**Setup backup policy:**

Before editing prefs:

- copy hfimu prefs XML to artifact dir if it exists
- record owner/mode/SELinux context when available
- print only backup path and changed key names, not full XML contents

On setup failure:

- restore prefs backup if it was changed
- restore owner/mode/context if possible
- force-stop hfimu if needed
- do not clear app data
- do not touch original Gadgetbridge

**Verification:**

```bash
PYTHONPATH=tools/miband9ctl python3 -m miband9ctl build --json | python3 -m json.tool
PYTHONPATH=tools/miband9ctl python3 -m miband9ctl install --json | python3 -m json.tool
PYTHONPATH=tools/miband9ctl python3 -m miband9ctl setup --json | python3 -m json.tool
PYTHONPATH=tools/miband9ctl python3 -m miband9ctl app launch --json | python3 -m json.tool
python3 -m unittest discover -s tools/miband9ctl/tests -p 'test_*.py'
```

**Commit:**

```bash
git add tools/miband9ctl
git commit -m "feat: add safe build install setup commands"
```

---

## Phase 4 — Packet engine and IMU command dry-run/send

**Objective:** Centralize IMU packet construction and prevent logic drift from the old script.

**Files:**

- Create: `tools/miband9ctl/miband9ctl/core/packets.py`
- Create: `tools/miband9ctl/miband9ctl/commands/imu.py`
- Modify: `tools/imu/send_imu_cmd.py` only after packet tests pass; keep it as compatibility wrapper.
- Test: `tools/miband9ctl/tests/test_packets.py`
- Test: `tools/miband9ctl/tests/test_imu_commands.py`

**Commands implemented:**

```bash
miband9ctl imu init
miband9ctl imu raw <hex>
miband9ctl imu data <payload-hex> --type 3
miband9ctl imu preset fuzz-fast --experimental
```

**Dry-run contract:**

```bash
miband9ctl imu init --dry-run --json
```

Dry-run JSON includes:

- constructed hex
- packet type
- payload length
- CRC
- target package
- target broadcast action
- `would_send=false`

Known init golden hex:

```text
a5a5020016001d4d0101030001000002020000fc03020020000402001027
```

**Real send is gated:**

- Real `imu init` should not be used as success proof until Android `debug-ping`, `dump-state`, target known-device selection, and preflight gates pass.
- If multiple initialized Xiaomi/Mi Band devices exist and no `--address` is provided, return `ambiguous_target`.

**Verification:**

```bash
PYTHONPATH=tools/miband9ctl python3 -m miband9ctl imu init --dry-run --json | python3 -m json.tool
python3 tools/imu/send_imu_cmd.py --init --dry-run
python3 -m unittest discover -s tools/miband9ctl/tests -p 'test_*.py'
```

**Commit:**

```bash
git add tools/miband9ctl tools/imu/send_imu_cmd.py
git commit -m "feat: add IMU packet commands to miband9ctl"
```

---

## Phase 5 — Log capture, parser, and artifact session directories

**Objective:** Turn logcat capture into reproducible evidence, not console spam.

**Files:**

- Create: `tools/miband9ctl/miband9ctl/core/artifacts.py`
- Create: `tools/miband9ctl/miband9ctl/core/logs.py`
- Create: `tools/miband9ctl/miband9ctl/core/collect.py`
- Extend: `tools/miband9ctl/miband9ctl/backends/logcat.py`
- Test: `tools/miband9ctl/tests/test_log_parser.py`
- Test: `tools/miband9ctl/tests/test_artifacts.py`
- Test: `tools/miband9ctl/tests/test_collect_summary.py`

**Commands implemented:**

```bash
miband9ctl imu collect --seconds 30
miband9ctl imu stats --from /tmp/miband9-hfimu/<session>/logcat_redacted.log
miband9ctl logs baseline
```

**Per-run artifact directory:**

```text
/tmp/miband9-hfimu/YYYYMMDD_HHMMSS_<session_id>/
```

Required files:

```text
manifest.json
commands.jsonl
doctor.json
state_before.json
state_after.json
logcat_raw.log
logcat_redacted.log
summary.json
adb_stdout_stderr.log
secret_scan.txt   # when a commit is about to be made
```

**Manifest fields:**

- session_id
- nonce
- repo commit
- dirty tree flag
- APK path + sha256
- target package
- adb serial
- phone model/API/build fingerprint
- command line, redacted
- start/end timestamps, UTC and local timezone
- artifact sha256 values
- redaction version

**Collect behavior:**

- create session_id and nonce before starting logcat
- record command args in `commands.jsonl` with redaction
- capture only allowlist tags by default:
  - `MI_HFIMU_RESULT`
  - `MI_HFIMU_STATE`
  - `MI_IMU_RAW_RX`
  - `MI_IMU_STATS`
  - `AndroidRuntime`
- use pid filter if safely available
- never use old `MI_IMU_RAW_RX` lines as current-run proof; require timestamp/nonce boundaries
- always write `summary.json`, even on zero packets or interruption
- stop only the logcat process created by this session

**Summary metrics:**

- raw packet lines
- stats lines
- first/last timestamps
- Android action request_id/nonce match count
- raw RX count after current nonce/start time
- observed packet rate if present
- sample rate only if classifier exists
- payload class if known, otherwise `unknown`
- gyro_present if known, otherwise `unknown`
- warning if zero current-run IMU packets

**Verification:**

```bash
PYTHONPATH=tools/miband9ctl python3 -m miband9ctl imu collect --seconds 5 --json | python3 -m json.tool
PYTHONPATH=tools/miband9ctl python3 -m miband9ctl imu stats --from /tmp/miband9-hfimu/<session>/logcat_redacted.log --json | python3 -m json.tool
python3 -m unittest discover -s tools/miband9ctl/tests -p 'test_*.py'
```

**Commit:**

```bash
git add tools/miband9ctl
git commit -m "feat: collect HF IMU log artifacts from miband9ctl"
```

---

## Phase 6 — Android debug control plane handshake

**Objective:** Prove Android app-side debug control is reachable and state is visible before scan/connect/raw experiments.

**Files:**

- Create: `app/src/main/java/nodomain/freeyourgadget/gadgetbridge/externalevents/HfImuDebugReceiver.java`
- Create: `app/src/main/java/nodomain/freeyourgadget/gadgetbridge/service/HfImuHeadlessController.java`
- Modify: `app/src/main/AndroidManifest.xml` if static registration is chosen; otherwise register from app/service startup deliberately.
- Modify: `app/src/main/java/nodomain/freeyourgadget/gadgetbridge/service/DeviceCommunicationService.java` if the controller should execute inside service context.
- Modify: `tools/miband9ctl/miband9ctl/commands/app.py`
- Create: `tools/miband9ctl/miband9ctl/commands/band.py`
- Test: Java build + Python fake parser tests

**Action namespace:**

Use package-derived actions:

```text
<pkg>.hfimu.debug.PING
<pkg>.hfimu.debug.DUMP_STATE
```

For default package:

```text
nodomain.freeyourgadget.gadgetbridge.hfimu.hfimu.debug.PING
nodomain.freeyourgadget.gadgetbridge.hfimu.hfimu.debug.DUMP_STATE
```

If the double `hfimu.hfimu` reads ugly in code, define one central helper to build the action and let CLI discover/construct the exact expected string. The important rule is package-derived and package-scoped, not global.

**Receiver rules:**

- Thin receiver only: validate action/package, debug pref, BuildConfig/debug package, parse request_id/nonce, hand off to controller.
- Do not scan, connect, or send raw bytes directly in `onReceive()`.
- Refuse `intent.getPackage()` empty or not equal to `BuildConfig.APPLICATION_ID`.
- Check `intent_api_allow_debug_commands=true`.
- Check `BuildConfig.DEBUG || BuildConfig.APPLICATION_ID.endsWith(".hfimu")`.

**Controller result logs:**

Emit one-line JSON logs under:

```text
MI_HFIMU_RESULT
MI_HFIMU_STATE
```

Every result must include:

- request_id
- nonce
- action
- ok
- status
- error_code if any
- target_address if any
- device_state if any

**State dump whitelist:**

Allowed fields:

- applicationId
- debugPrefEnabled
- serviceRunning
- bluetoothEnabled
- locationProviderEnabled if available
- permission booleans
- known devices: address/name/type/state/initialized/connected/connectable/bonded
- target match status
- auth_key_present boolean only, never the value

Forbidden fields:

- auth key value
- full shared preferences
- DB rows
- notifications/messages/calls
- arbitrary private app data

**CLI commands:**

```bash
miband9ctl app debug-ping --json
miband9ctl app dump-state --json
miband9ctl band list --json
miband9ctl band state --address <MAC> --json
```

**Verification:**

```bash
JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home ./gradlew --no-daemon :app:assembleMainlineDebug
PYTHONPATH=tools/miband9ctl python3 -m miband9ctl install --json | python3 -m json.tool
PYTHONPATH=tools/miband9ctl python3 -m miband9ctl setup --json | python3 -m json.tool
PYTHONPATH=tools/miband9ctl python3 -m miband9ctl app debug-ping --json | python3 -m json.tool
PYTHONPATH=tools/miband9ctl python3 -m miband9ctl app dump-state --json | python3 -m json.tool
```

**Acceptance:**

- CLI only reports success after matching current request_id/nonce in `MI_HFIMU_RESULT`.
- `am broadcast` completion alone is not success.
- State dump is redacted and whitelist-based.

**Commit:**

```bash
git add app/src/main/java app/src/main/AndroidManifest.xml tools/miband9ctl
git commit -m "feat: expose HF IMU debug control handshake"
```

---

## Phase 6.5 — Preflight gates before scan/connect/raw send

**Objective:** Refuse risky or meaningless scan/connect/raw commands until the device and app state make sense.

**Files:**

- Create: `tools/miband9ctl/miband9ctl/commands/preflight.py`
- Create: `tools/miband9ctl/miband9ctl/core/preflight.py`
- Test: `tools/miband9ctl/tests/test_preflight.py`

**Commands:**

```bash
miband9ctl preflight --json
miband9ctl logs baseline --json
```

**Required checks:**

- exactly one authorized ADB device or explicit serial
- expected device warning if not MI 9 SE / Android 9
- target package `.hfimu` by default
- original Gadgetbridge read-only state recorded, not mutated
- side-by-side APK path/sha/versionCode/versionName/repo commit recorded
- app process started or launchable
- debug receiver reachable via `debug-ping`
- `intent_api_allow_debug_commands=true` verified app-side, not just XML-side
- Bluetooth enabled
- Android 9 location permission and provider status checked
- MIUI background/battery restriction warning when not verifiable
- possible connection-stealing apps/processes noted if visible
- known devices list available
- target address, if provided, known to Gadgetbridge or bonded
- app not clearly stuck in onboarding if this is detectable
- logcat baseline starts from current time/nonce

**Outcomes:**

- `preflight.ok`: safe to attempt state/connect/raw.
- `preflight.needs_manual_onboarding`: app still requires first-run/manual UI.
- `preflight.needs_user_pairing_or_known_device`: unknown target; do not connect.
- `preflight.bluetooth_off`: ask/require enabling Bluetooth.
- `preflight.location_off`: scan unreliable on Android 9.

**Verification:**

```bash
PYTHONPATH=tools/miband9ctl python3 -m miband9ctl preflight --json | python3 -m json.tool
python3 -m unittest discover -s tools/miband9ctl/tests -p 'test_*.py'
```

**Commit:**

```bash
git add tools/miband9ctl
git commit -m "feat: add HF IMU preflight gates"
```

---

## Phase 7 — Known-device connect and target-specific raw send

**Objective:** Add guarded connection control only for already-known/bonded/Gadgetbridge-known Mi Band 9 devices.

**Files:**

- Extend: `app/src/main/java/nodomain/freeyourgadget/gadgetbridge/externalevents/HfImuDebugReceiver.java`
- Extend: `app/src/main/java/nodomain/freeyourgadget/gadgetbridge/service/HfImuHeadlessController.java`
- Modify if needed: `app/src/main/java/nodomain/freeyourgadget/gadgetbridge/model/DeviceService.java`
- Modify if needed: `app/src/main/java/nodomain/freeyourgadget/gadgetbridge/impl/GBDeviceService.java`
- Modify: `tools/miband9ctl/miband9ctl/commands/band.py`
- Modify: `tools/miband9ctl/miband9ctl/commands/imu.py`
- Test: Java build + fake parser tests

**Actions:**

```text
<pkg>.hfimu.debug.CONNECT
<pkg>.hfimu.debug.RECONNECT
<pkg>.hfimu.debug.SEND_RAW
```

**CLI commands:**

```bash
miband9ctl band list --json
miband9ctl band connect --address <MAC> --json
miband9ctl band reconnect --address <MAC> --json
miband9ctl imu init --address <MAC> --json
miband9ctl imu raw --address <MAC> <hex> --json
```

**Rules:**

- Do not create DB devices from CLI.
- Do not call `DebugActivity.createTestDevice()`.
- Do not copy auth keys.
- If target unknown, return `unknown_device` and `needs_manual_pairing_or_known_device`.
- If multiple initialized candidate devices and no address, return `ambiguous_target`.
- If target known but not initialized, connect first and poll state until timeout.
- Raw send must use target-specific service path: `GBApplication.deviceService(targetDevice).onDebugSendRawBytes(bytes)` or equivalent target-specific dispatch.
- If current architecture only exposes fan-out raw send, patch it before enabling CLI real send.

**Scan is not MVP:**

If added in this phase, it is candidate-only:

```bash
miband9ctl band scan --seconds 10 --json
```

Candidate-only scan may log nearby devices but must not auto-pair or auto-write DB records. Pairing/system/band confirmations return `needs_user_confirmation`.

**Verification:**

```bash
JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home ./gradlew --no-daemon :app:assembleMainlineDebug
PYTHONPATH=tools/miband9ctl python3 -m miband9ctl app dump-state --json | python3 -m json.tool
PYTHONPATH=tools/miband9ctl python3 -m miband9ctl band list --json | python3 -m json.tool
PYTHONPATH=tools/miband9ctl python3 -m miband9ctl band connect --address <MAC> --json | python3 -m json.tool
```

**Commit:**

```bash
git add app/src/main/java tools/miband9ctl
git commit -m "feat: add guarded headless known-device connect"
```

---

## Phase 8 — Dry-run experiment rehearsal

**Objective:** Prove the experiment harness produces safe artifacts without relying on successful band connection.

**Commands:**

```bash
miband9ctl doctor --json
miband9ctl setup --json
miband9ctl app debug-ping --json
miband9ctl app dump-state --json
miband9ctl preflight --json
miband9ctl imu init --dry-run --json
miband9ctl imu collect --seconds 5 --json
```

**Expected:**

- Artifact directory complete.
- Redacted logs exist.
- Summary JSON says zero IMU packets if no connected target.
- No stale logs counted as current evidence.
- Secret scan passes.
- No original Gadgetbridge mutation.

**Experiment note:**

```text
docs/recovery/experiments/YYYY-MM-DD-miband9ctl-dry-run-rehearsal.md
```

**Commit:**

```bash
git add docs/recovery/experiments
git commit -m "test: record miband9ctl dry-run rehearsal"
```

---

## Phase 9 — First real known-device SPP/init experiment

**Objective:** Run the current SPP/init path through the CLI, with no screen swiping except unavoidable Android/band confirmations.

**Command sequence:**

```bash
miband9ctl doctor --json
miband9ctl setup --json
miband9ctl app debug-ping --json
miband9ctl app dump-state --json
miband9ctl preflight --address <MAC> --json
miband9ctl band connect --address <MAC> --json
miband9ctl imu init --address <MAC> --json
miband9ctl imu collect --seconds 30 --json
miband9ctl imu stats --from <artifact>/logcat_redacted.log --json
```

**Experiment note:**

```text
docs/recovery/experiments/YYYY-MM-DD-miband9ctl-spp-init.md
```

Record:

- repo commit
- dirty flag
- APK sha256
- phone model/API/build fingerprint
- package name
- target device address, redacted if committed
- band firmware if visible
- state before/after connect
- init hex used
- raw packet count
- `MI_IMU_STATS` count
- packet-rate estimate
- sample-rate estimate only if classifier supports it
- payload class
- gyro presence
- whether result matches prior 25/50Hz ceiling
- next path if SPP remains capped

**Claim policy:**

- `transport/raw RX observed` is allowed if raw RX appears.
- `packet_rate_hz` can be recorded from packet/log statistics.
- `sample_rate_hz` requires packet parser/classifier evidence.
- `gyro_present` requires payload interpretation evidence.
- `>100Hz` requires at least two independent cold-start captures with classifier-backed sample rate.

**Commit:**

```bash
git add docs/recovery/experiments
git commit -m "test: record miband9ctl SPP init experiment"
```

---

## Failure Modes and Required CLI Outcomes

| Area | Failure | CLI outcome |
| --- | --- | --- |
| ADB | `adb` missing | `adb.not_found`, exit 2, install hint |
| ADB | no authorized device | `adb.no_device`, exit 2 |
| ADB | unauthorized/offline | `adb.device_not_ready`, exit 2 |
| ADB | multiple devices without serial | `adb.needs_serial`, exit 2 |
| Build | JDK17 missing | `gradle.no_jdk17`, exit 2 |
| Build | Gradle task failure | `gradle.build_failed`, exit 1, log artifact path |
| Install | APK path missing | `apk.not_found`, exit 2 |
| Install | signature/package mismatch | `install.signature_mismatch`, exit 1 |
| Install | rooted install denied | `install.root_pm_failed`, exit 1 |
| Safety | target original Gadgetbridge for mutation | `safety.refuse_original_package`, exit 3 |
| Root | `run-as` unavailable | warning; try `su` fallback if allowed |
| Root | `su` denied | `root.unavailable`, exit 2 for setup requiring root |
| Setup | prefs file missing | launch app once, retry; else `setup.prefs_missing` |
| Setup | prefs owner/mode/context wrong after edit | rollback prefs; `setup.pref_restore_required` |
| App | app not running and dynamic receiver absent | launch app; else `app.receiver_unreachable` |
| App | app crash loop | `app.crash_loop`, include AndroidRuntime artifact |
| App | onboarding still blocking | `app.needs_manual_onboarding` |
| Android | Bluetooth off | `android.bluetooth_off` |
| Android | Android 9 location off | `android.location_off` warning/failure for scan |
| Android | MIUI kills background service | `android.background_restricted` warning |
| Band | unknown address | `band.unknown_device`, do not connect |
| Band | known but no auth key | `band.auth_missing`, value never printed |
| Band | occupied by original GB/Mi Fitness | warning `band.possibly_occupied` |
| Band | connect state unchanged | `band.connect_timeout` |
| Band | system/band confirmation needed | `band.needs_user_confirmation` |
| IMU | raw send no initialized target | `imu.no_initialized_target` |
| IMU | multiple targets | `imu.ambiguous_target` |
| IMU | init accepted but no raw RX | `imu.zero_raw_rx`, not success |
| IMU | stale log line only | ignored; warning `logs.stale_evidence_ignored` |
| IMU | packet rate but no classifier | record packet_rate only; sample_rate null |
| Safety | secret detected in artifact/doc | block commit; `safety.secret_detected` |

---

## Testing Strategy

### Unit tests, no phone

Run by default:

```bash
python3 -m unittest discover -s tools/miband9ctl/tests -p 'test_*.py'
```

Coverage:

- result schema and exit-code mapping
- config precedence
- session lock/write/read/corruption recovery
- redaction patterns
- adb command construction with fake runner
- root `su -c` quoting helper
- package safety refusal
- packet construction and CRC golden vectors
- invalid/odd-length hex rejection
- dry-run does not send broadcast
- broadcast command construction
- logcat fixture parser
- nonce/session matching and stale log rejection
- zero-packet summaries
- interleaved old/new log lines
- truncated log lines
- AndroidRuntime crash lines
- packet/sec vs sample/sec separation

### Fake ADB transcript tests

Fixtures must cover:

- no device
- unauthorized device
- multiple devices
- serial mismatch
- su denied
- run-as denied
- install signature mismatch
- package not installed
- app not running
- broadcast completed but app logs debug not allowed
- Bluetooth off
- location off
- known-device empty
- connect attempted but state unchanged

### Device smoke tests, opt-in only

Never run by default. Require explicit flag/env such as:

```bash
MIBAND9CTL_DEVICE=1 python3 -m unittest discover -s tools/miband9ctl/tests_device -p 'test_*.py'
```

Smoke scope:

- doctor sees selected authorized device
- install targets `.hfimu` only
- setup flips only `intent_api_allow_debug_commands`
- app debug-ping returns current nonce result
- app dump-state returns redacted state
- collect creates artifact dir and valid summary JSON

Scan/connect/IMU collection are experiments, not ordinary tests.

### Secret scan before every commit

Minimum check:

```bash
git diff --cached --unified=0 | python3 tools/miband9ctl/scripts/secret_scan_staged.py
```

Until that script exists, use a local Python regex scan over staged added lines and manually inspect docs/artifacts. Block commit on auth key/token/password/private pref/database dumps.

---

## Artifact and Privacy Policy

Raw vs committed:

- Raw logs, prefs backups, full MAC addresses, and DB-derived sensitive data stay local and untracked.
- Committed experiment notes use redacted summaries only.
- Auth keys never enter the repo.
- If a sensitive local file must be referenced, record local path and sha256 only; do not copy contents.

Logcat policy:

- Prefer current-run nonce/timestamp filtering over clearing global logs.
- If using `logcat -c`, record that the buffer was cleared.
- Do not count historical `MI_IMU_RAW_RX` as current evidence.
- Parser must distinguish:
  - broadcast accepted by Android shell
  - app receiver handled action
  - service/controller executed action
  - raw RX observed
  - payload classified
  - sample rate derived

Redaction policy:

- Redact auth keys, tokens, passwords, OAuth strings, rclone config snippets, long suspicious secrets, private XML dumps, and database rows.
- Prefer partial or hashed MACs in committed notes.
- Local raw artifacts may keep exact MACs if needed for experiment continuity, but should be mode-restricted and never committed.

---

## Implementation Commit Sequence

Use these checkpoints unless implementation reveals a cleaner split:

1. `docs: plan headless Mi Band 9 CLI harness`
2. `feat: scaffold packaged miband9ctl CLI harness`
3. `feat: add read-only adb probes to miband9ctl`
4. `feat: add safe build install setup commands`
5. `feat: add IMU packet commands to miband9ctl`
6. `feat: collect HF IMU log artifacts from miband9ctl`
7. `feat: expose HF IMU debug control handshake`
8. `feat: add HF IMU preflight gates`
9. `feat: add guarded headless known-device connect`
10. `test: record miband9ctl dry-run rehearsal`
11. `test: record miband9ctl SPP init experiment`

Each checkpoint requires:

```bash
git diff --check
python3 -m unittest discover -s tools/miband9ctl/tests -p 'test_*.py'   # once tests exist
JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home ./gradlew --no-daemon :app:assembleMainlineDebug   # for Android changes
secret scan on staged added lines
git status --short --branch
```

---

## Immediate Next Slice

Start with Phase 1 only.

Do not touch Android scanner/connect code yet. The first useful deliverable is a safe local package skeleton that can say, in JSON, exactly what environment it sees and refuse unsafe targets. Once that scepter is solid, the dragon can stop poking the glass slab by hand.
