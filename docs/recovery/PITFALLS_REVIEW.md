# Deep pitfalls review — Mi Band 9 high-frequency IMU project

Generated: 2026-05-29 10:38 CST

## Executive verdict

The project did not fail because the reports were thin. The reports are unusually complete. The main problem was route confusion: several layers looked like they were “the IMU path”, but each solved a different subproblem.

The target was always stricter than most intermediate wins:

```text
Mi Band 9 high-frequency IMU packets
>100 Hz preferred
gyro required if possible
raw packet evidence required
```

A 25/50 Hz accelerometer stream, a successful Bluetooth connection, an A5/A5 packet, or a wearable mini-app demo is useful evidence, but not the final target.

The current best reading of the evidence is:

```text
Mac = research/build/reverse-engineering brain
Android phone = live Bluetooth/app/logcat hand
Mi Band 9 = target
Gadgetbridge SPP ch5 + A5 = recovered debug bridge / baseline
GameSir/game mode = stateful side-channel clue, not a deterministic one-command unlock yet
Firmware/ODR/debug-rawdata = likely final route for >100 Hz
```

## Pitfall 1 — treating archive completeness as project completeness

What happened:

- The Google Drive folder downloaded and verified cleanly: 4890 files, 0 rclone differences.
- But the Drive package was an earlier Windows feasibility bundle, not the later complete IMU/app-layer research state.
- The missing material lived on Windows1: RPK, Gemini/agent brain docs, WeChat `miband9-imu-collector`, and the old modified APK.

Why it hurt:

- “Download complete” was easy to misread as “research complete”.
- That would have killed the later Vela / Gadgetbridge / GameSir / firmware trail.

Evidence:

- Drive check log: `<private-artifacts>/drive_rclone_check_current.log`
- Windows1 evidence directory: `<private-artifacts>/windows1-miband9-imu-clues-20260529`
- Path reconstruction: `docs/recovery/path-reconstruction.md`

Rule now:

- Always split completeness into two axes:
  - archive completeness: did we mirror the remote source?
  - research completeness: did we recover all later local artifacts and build outputs?

## Pitfall 2 — Windows Bluetooth direct path was a dead end, but consumed attention

What happened:

- Windows direct Bluetooth pairing/auth/RFCOMM attempts were explored heavily.
- The OS profile state, Xiaomi auth, HID/controller personality, BLE/Classic split, and application protocol all overlapped.
- Windows could see pieces of the device story, but did not reliably produce the authenticated high-frequency IMU path.

Why it hurt:

- It encouraged debugging transport symptoms instead of the hidden device mode.
- Pairing success/failure was not equivalent to IMU stream capability.

Root cause:

- The band’s relevant state is controlled by Xiaomi app/Gadgetbridge-like protocol state, not just Windows Bluetooth stack state.
- Windows was useful for old artifacts and logs, not as the final live extraction host.

Rule now:

- Do not reopen Windows direct Bluetooth as a primary route.
- Use Windows1 only as an evidence freezer unless a specific missing file/log is needed.

## Pitfall 3 — Android official-app capture was not enough by itself

What happened:

- Official app / Frida / HCI / btsnoop attempts were explored.
- Some logs say btsnoop once worked, but the actual `btsnoop_hci.log` artifact was not recovered.
- Frida-style work was unstable and at one point reportedly crashed the phone.

Why it hurt:

- Capturing the official app is tempting because it is “close to the truth”.
- But without a stable artifact and reproducible hook point, it becomes a memory, not evidence.

Root cause:

- Xiaomi protocol state, encryption, app-specific timing, and phone stability make official-app capture brittle.
- A log reference to success is not the same as a reusable capture artifact.

Rule now:

- Official app/HCI is a secondary evidence source.
- If revived, it must produce durable artifacts immediately:
  - btsnoop file
  - timestamped steps
  - phone/app version
  - band firmware version
  - exact trigger action
  - hash of capture file

## Pitfall 4 — Vela / wearable mini-app baseline looked promising but likely capped the wrong layer

What happened:

- The Vela/Quick App route existed and was real enough to recover as an RPK.
- It could use wearable-side APIs such as `@system.sensor` and send through Interconnect.
- Reports point to roughly game/best-effort accelerometer sampling, around 25/50 Hz baseline.

Why it hurt:

- It proved a pipeline but not the target.
- A clean app-layer demo can seduce the project into optimizing the wrong ceiling.

Root cause:

- The mini-app sensor API likely exposes an OS-managed stream, not raw high-ODR IMU driver data.
- It may not expose gyro or raw packets at the required rate.

Rule now:

- Treat Vela/Interconnect as baseline and UX/protocol scaffolding only.
- It is not a success path unless it produces >100 Hz and gyro/raw evidence.

## Pitfall 5 — Gadgetbridge source loss hid the most valuable bridge

What happened:

- The original modified Gadgetbridge source/git branch was not recovered.
- Windows1 had an APK: `app-mainline-debug-windows1-20260109.apk`.
- JADX decompilation recovered enough evidence to reconstruct the useful parts:
  - Mi Band 9 forced BT Classic/SPP
  - RFCOMM channel 5
  - A5/A5 init frame
  - `MI_IMU_RAW_RX` logcat
  - `ImuDebugActivity`
  - raw send hook

Why it hurt:

- The project almost looked source-dead.
- Without decompiling the APK, we would have missed the most concrete bridge implementation.

Root cause:

- No small git checkpoint existed at the moment the old branch worked.
- Build outputs survived; source did not.

Rule now:

- Every coherent experimental slice gets a git checkpoint before moving on.
- Build artifacts are valid recovery oracles, but clean source must be reconstructed manually.

Current fix:

- Recovery repo: `<repo>`
- Branch: `hf-imu-recovery`
- Recovery commits preserve evidence, code, and next plan.

## Pitfall 6 — SPP channel 5 + A5/A5 was a bridge, not proof of high frequency

What happened:

- The recovered APK uses Classic Bluetooth SPP channel 5 and sends an A5/A5 init frame.
- Old task notes say this path was abandoned/maxed around ~50 Hz.
- Current code logs raw bytes as `MI_IMU_RAW_RX`, which is exactly what we need for baseline verification.

Why it hurt:

- Transport success can look like sensor success.
- A channel opening and raw bytes appearing does not prove >100 Hz, gyro, or raw driver data.

Root cause:

- The SPP bridge may only expose a debug/app stream already capped by firmware or mode state.
- The packet rate is not necessarily the sample rate; one packet can contain multiple samples, or one sample can be split.

Rule now:

- For every capture, record separately:
  - socket/channel status
  - packet rate
  - sample count per packet
  - derived sample rate
  - axis fields present
  - gyro present/absent
  - raw payload evidence

Current static caveat:

- `XiaomiSppSupport.handleActivityOrImu()` currently treats all Activity-channel payloads as possible IMU payloads. This is fine for early raw visibility, but final analysis must classify payload type before calling it true IMU.

## Pitfall 7 — GameSir / game mode was treated too much like a replayable command

What happened:

- Old logs mention GameSir/Nova/controller-like names and services/chars such as `0x865F`, `0xFF12`, `0xFF10`, `0xFF11`, `0x8655`.
- One important clue: `FF12: 01 01 03` once led to `865F: 24 01 05 48 72`.
- This supports the memory that a third-party/game mode exposed a different interface.

Why it hurt:

- It is tempting to assume one GATT write is the unlock key.
- More likely, it depends on state/timing/personality/bonding/advertising mode.

Root cause:

- Controller/game mode is a state machine, not a stateless packet endpoint.
- The third-party device may trigger a mode transition that then changes services, sampling, or transport behavior.

Rule now:

- GameSir experiments must log a state matrix:
  - before/after scan services
  - bond state
  - advertised name
  - BLE vs Classic status
  - exact write timing
  - notification subscription state
  - response bytes

Do not call GameSir reproduced until the same sequence works twice from a cold state.

## Pitfall 8 — firmware/ODR plans were strong, but artifacts are missing

What happened:

- Old reports identify firmware/ODR as the likely final route.
- Clues include LSM6DSO/BMI270, `lsm6dso_enable_acc_gyro`, base address `0x1FBC0000`, and ODR values:
  - `0x30` / `10 30` = 52 Hz
  - `0x40` / `10 40` = 104 Hz
  - planned `0x50` / `10 50` = 208 Hz
- Old plans mention `miband9_imu_mod_208hz.zip` / patched firmware outputs, but files were not recovered.

Why it hurt:

- A generated patch script or plan can look like an executed firmware mod.
- Without original firmware and rollback path, patching is too risky.

Root cause:

- Firmware work needs binary provenance, not just code snippets.
- The project has analysis breadcrumbs but not the full artifact chain.

Rule now:

- Firmware hard patch remains last resort.
- Before any flash:
  - original firmware zip/bin recovered
  - hash recorded
  - unpack/repack understood
  - signature/update mechanism understood
  - recovery/rollback path written
  - patch diff explained at instruction/register level

Preferred route:

- Find hidden debug/rawdata command first, then use firmware analysis to explain it.

## Pitfall 9 — `set_work_mode` and similar strings can be false friends

What happened:

- Old notes found mode/work-mode strings.
- Later reconstruction says `set_work_mode` was likely touch-panel debug, not IMU.

Why it hurt:

- Generic debug strings can redirect attention to the wrong subsystem.

Rule now:

- A firmware symbol is only relevant if tied to one of:
  - sensor driver path
  - IMU chip init/config
  - activity/rawdata packet emission
  - command handler reachable from phone/band protocol

## Pitfall 10 — environment/tooling blockers masqueraded as project blockers

What happened:

- Default Java 26 is not the right runtime for this Gradle/Groovy project.
- Android SDK path was missing from the repo environment.
- JitPack no longer resolves the pinned greenDAO commit coordinate.
- Public Google Drive tooling hit API/403 limits before rclone solved it.

Why it hurt:

- These are not research failures, but they blocked forward motion.

Current fixes:

- Use JDK 17:
  `/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home`
- Use SDK root:
  `/opt/homebrew/share/android-commandlinetools`
- `local.properties` points at that SDK.
- `GBDaoGenerator` now uses JitPack `fyg-SNAPSHOT` for the recovered build.
- rclone is the proven Drive method for this archive.

Rule now:

- Keep environment failures documented separately from protocol failures.
- Do not let a build/dependency failure change the research conclusion.

## Pitfall 11 — sensitive notes mixed with evidence

What happened:

- `Mi Band Auth Key.md` and rclone config contain sensitive material or token-like data.
- Those files are useful historically but dangerous to quote or commit.

Rule now:

- Auth keys, OAuth tokens, refresh tokens, pairing keys, passwords, API keys: never paste, never commit.
- Reports may mention the file exists and what category of evidence it contains, with values redacted.
- Added-lines secret scan must run before every checkpoint.

## Pitfall 12 — packet-rate math can lie if the counter is wrong

What happened:

- The recovered debug UI path initially used one counter as both window-rate counter and total packet count.
- That means displayed “total packets” could reset every rate window.

Why it matters:

- This project lives or dies on rate claims.
- Bad instrumentation can create false success or false failure.

Current fix:

- The recovered code now keeps separate counters for window packet rate and total packets.
- Final success still needs sample-per-packet parsing, not just packet/sec.

Rule now:
  - total packets since start
  - packets in current window
  - samples per packet
  - derived samples/sec
- Any final claim must include raw log evidence and parser version.

## Pitfall 13 — Mac role was under-described

What happened:

- “Mac should not be the Bluetooth direct采集端” could sound like “Mac is not useful”.
- That is wrong.

Correct role:

- Mac is the project brain:
  - repo rebuild
  - compile/assemble
  - ADB/logcat capture
  - JADX/Ghidra/binwalk/radare2 analysis
  - Python protocol parsing
  - evidence indexing
  - agent-driven search

Wrong role:

- Mac as the primary direct Bluetooth host for Xiaomi auth/game-mode/high-rate stream.

Rule now:

- Keep Mac central, but keep live Bluetooth state on Android unless a Linux sniffer/dongle becomes necessary.

## Current route classification

| Route | Status | Why |
|---|---|---|
| Drive archive | complete as archive | rclone verified, but not full research state |
| Windows direct Bluetooth | dead / evidence only | pairing/auth/profile stack not enough |
| Android official app capture | secondary | unstable without durable capture artifact |
| Vela mini-app / Interconnect | baseline | likely 25/50 Hz, not final HF raw IMU |
| Recovered Gadgetbridge SPP ch5 | active baseline bridge | now buildable; can generate live raw logs |
| GameSir/game mode | active clue, not reproduced | stateful side-channel, needs controlled state matrix |
| Hidden debug/rawdata command | preferred final route | likely avoids dangerous firmware patch |
| Firmware ODR patch | last resort | needs original firmware + rollback path |

## Forward discipline

Every future test should produce a small evidence bundle:

```text
timestamp
repo commit
APK sha256
phone model / Android version / rooted state
band model / firmware version / battery state
connection route
trigger command
logcat raw excerpt
parser output
packet rate
sample rate
gyro present/absent
conclusion: baseline / dead end / active lead / final success
```

No more “I remember it worked” without an artifact. Harsh, but fair. Very dragon-approved.
