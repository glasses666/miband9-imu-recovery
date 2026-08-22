# Mi Band 9 HF IMU Next Plan

> For Hermes: continue from local branch `hf-imu-recovery`. Make small commits after each verified slice. Do not copy or print auth keys/tokens.

## Goal

Turn the recovered Gadgetbridge debug base into a repeatable experiment path for Xiaomi Smart Band 9 high-frequency IMU data, then move from the confirmed ~50Hz SPP/debug baseline toward hidden rawdata mode or firmware ODR unlock.

## Current project node

Repo:

`<repo>`

Branch:

`hf-imu-recovery`

Current commits:

- `8fb1070 docs: establish Mi Band 9 HF IMU recovery workspace`
- `57018bd feat: restore Mi Band 9 RFCOMM IMU debug path`

Implemented baseline:

- Clean Gadgetbridge base from `a0948ee` / 0.83.0 lineage.
- Critical decompiled APK evidence copied under `docs/recovery/references/apk-decompiled-critical/`.
- RFCOMM direct channel 5 support re-ported into `BtBRQueue` / `AbstractBTBRDeviceSupport`.
- `XiaomiConnectionSupport.sendRawBytes(...)` hook added.
- `XiaomiSppSupport` logs raw socket bytes to `MI_IMU_RAW_RX` and broadcasts parsed debug payloads.
- `XiaomiSupport.onTestNewFunction()` sends the recovered Mi Band 9 RFCOMM init frame and opens `ImuDebugActivity`.
- `ImuDebugActivity` + `activity_imu_debug.xml` restored.
- PC-side tools restored under `tools/imu/` and `tools/firmware/`.

Known limitation:

- Full Android compile/install is not yet verified because this Mac does not currently have an Android SDK path configured.
- GameSir/`865F`/`FF12` BLE trigger logic is preserved as reference, not yet re-ported.
- Firmware artifacts (`vela_ap.bin`, `system.bin`, `miband9_imu_mod_208hz.zip`, `btsnoop_hci.log`) are still missing.

---

## Phase 1 — Make the Android recovery APK buildable

Acceptance: `:app:assembleMainlineDebug` succeeds and produces a local debug APK.

Tasks:

1. Install or point to Android SDK.
   - Expected path: `~/Library/Android/sdk`
   - If already installed elsewhere, create `local.properties` with:
     ```properties
     sdk.dir=/absolute/path/to/Android/sdk
     ```

2. Verify Gradle task graph still loads:
   ```bash
   cd <repo>
   JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home ./gradlew --no-daemon -q projects
   ```

3. Build mainline debug APK:
   ```bash
   JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home ./gradlew --no-daemon :app:assembleMainlineDebug
   ```

4. If compile errors appear, fix only the reported recovered-code errors. Do not refactor unrelated Gadgetbridge code.

5. Commit:
   ```bash
   git add .
   git commit -m "build: make Mi Band 9 recovery APK compile"
   ```

---

## Phase 2 — SPP channel 5 smoke test on phone + band

Acceptance: pressing Gadgetbridge DebugActivity → Test New Function produces `MI_IMU_RAW_RX` lines or a clear connection/auth failure log.

Tasks:

1. Install APK:
   ```bash
   adb install -r app/build/outputs/apk/mainline/debug/*.apk
   ```

2. Pair/connect Mi Band 9 in the recovery Gadgetbridge build.

3. Start log capture:
   ```bash
   adb logcat -c
   adb logcat -s MI_IMU_RAW_RX MI_IMU_STATS Gadgetbridge > artifacts/logs/spp-channel5-smoke.log
   ```

4. In Gadgetbridge DebugActivity, press `Test New Function`.

5. In a second shell, run:
   ```bash
   python3 tools/imu/live_imu_forwarder.py
   ```

6. Save result summary to:

   `docs/recovery/experiments/YYYY-MM-DD-spp-channel5-smoke.md`

Record:

- phone model / Android version
- band firmware version
- whether Classic/SPP connected
- whether `MI_IMU_RAW_RX` appeared
- packet rate estimate
- whether payload looks accel-only or accel+gyro
- any auth/bonding errors

7. Commit experiment notes:
   ```bash
   git add docs/recovery/experiments artifacts/logs
   git commit -m "test: record SPP channel 5 smoke result"
   ```

---

## Phase 3 — Restore ADB hot-command injection

Acceptance: `tools/imu/send_imu_cmd.py --hex ...` can send a raw/debug command through the app without manually tapping DebugActivity.

Tasks:

1. Inspect old script:
   ```bash
   sed -n '1,180p' tools/imu/send_imu_cmd.py
   ```

2. Add an internal/exported-off receiver or reuse `IntentApiReceiver` to accept the old action:

   `nodomain.freeyourgadget.gadgetbridge.SEND_IMU_CMD`

3. Receiver must:

   - parse a hex payload extra
   - refuse empty/invalid payloads
   - call the active Xiaomi SPP support raw send path
   - log only packet length and redacted command family, not secrets

4. Add docs:

   `docs/recovery/ADB_COMMANDS.md`

5. Verify with logcat and commit:
   ```bash
   git commit -m "feat: restore ADB IMU command injection"
   ```

---

## Phase 4 — Re-port GameSir / game-mode trigger as a guarded experiment

Acceptance: a feature-gated debug action can reproduce or falsify the `865F` / `FF12` trigger path without corrupting the SPP baseline.

Tasks:

1. Read reference first:

   `docs/recovery/references/apk-decompiled-critical/sources__nodomain__freeyourgadget__gadgetbridge__service__devices__xiaomi__XiaomiSupport.java`

2. Re-port into a separate helper class, not directly into normal Xiaomi connection flow:

   `app/src/main/java/nodomain/freeyourgadget/gadgetbridge/service/devices/xiaomi/debug/MiBand9GameModeProbe.java`

3. Make the trigger explicit and reversible:

   - scan for GameSir/Nova/Wireless Controller names
   - connect GATT with transport LE
   - write `865F` prime
   - write `FF12` unlock payload
   - subscribe to `2A4D` or discovered candidate notify characteristic
   - stop/disconnect cleanly

4. Log evidence tags:

   - `MI_GAME_MODE_SCAN`
   - `MI_GAME_MODE_GATT`
   - `MI_GAME_MODE_RAW`

5. Verification must include a logcat slice and a before/after Bluetooth scan result.

6. Commit:
   ```bash
   git commit -m "feat: add guarded Mi Band 9 game-mode probe"
   ```

---

## Phase 5 — Firmware / ODR path, soft unlock first

Acceptance: identify a non-destructive command path or produce a documented firmware map with rollback requirements before any patch/flash attempt.

Tasks:

1. Search/recover missing artifacts again before patching:

   - `vela_ap.bin`
   - `system.bin`
   - `miband9_imu_mod_208hz.zip`
   - `btsnoop_hci.log`
   - `sensor_dump.bin`

2. If firmware is recovered, hash and store outside git:

   `docs/recovery/firmware/ARTIFACT_HASHES.md`

3. Run analysis tools on copies only:
   ```bash
   python3 tools/firmware/search_odr.py /path/to/firmware.bin
   python3 tools/firmware/scan_lsm6dso_code.py /path/to/firmware.bin
   ```

4. Prefer soft unlock:

   - locate `ENUM_MODE_DEBUG_RAWDATA`
   - locate command handler / factory test dispatch
   - derive command family and payload shape
   - try through Phase 3 ADB hot-command sender

5. Hard ODR patch is last resort only after:

   - original firmware is archived
   - rollback/flash path is verified
   - target byte pattern has unique disassembly context
   - risk is explicitly accepted

6. Commit only notes/scripts, not private firmware blobs:
   ```bash
   git commit -m "docs: map firmware ODR and debug rawdata path"
   ```

---

## Stop conditions

Stop and reassess if any of these happen:

- SPP channel 5 cannot connect even with known-good pairing.
- Raw data appears but is fixed at ~50Hz with no gyro channel.
- Game-mode probe changes band pairing state or causes unstable reconnect loops.
- Firmware patch requires flashing without verified rollback.
- Any auth key/token/credential appears in git diff.

## Immediate next command after this plan

The next mechanical step is Android SDK setup/build verification:

```bash
cd <repo>
JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home ./gradlew --no-daemon :app:assembleMainlineDebug
```

Expected current blocker if SDK is still absent:

`SDK location not found`
