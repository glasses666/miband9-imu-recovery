# Mi Band 9 high-frequency IMU — public research and software chain

Date: 2026-05-30

This document is the public-safe handoff for the Xiaomi Smart Band 9 / Mi Band 9 NFC high-frequency IMU recovery work in this fork. It intentionally omits auth keys, account identifiers, device IDs, private app database rows, signed firmware URLs, and raw phone artifacts.

## One-line result

A repeatable 100 Hz accel + gyro stream was recovered through the official Mi Fitness SportXms / Just Dance path (`sportType=812`), then bridged into a side-by-side Gadgetbridge-derived Android agent plus a Mac/Linux CLI and local live dashboard.

## Current verified state

- Target family: Xiaomi Smart Band 9 NFC / `M2346B1` / `miwear.watch.n66nfc`.
- Auth state: side-by-side `hfimucli` package can import the known-good Gadgetbridge state and reach Xiaomi/Gadgetbridge app-layer `INITIALIZED`.
- Transport baseline: RFCOMM/SPP port 5 opens and responds to an A5 control/init frame, but this is only transport/control evidence, not the high-rate IMU route.
- GameSir/controller route: investigated as a state-machine clue; normal initialized state did not expose a reproducible GameSir/HID surface. It is not the current success path.
- Current success path: Mi Fitness SportXms / Just Dance body-sensing route; the selected Mi Fitness device must be the Band 9 and connected, then `startSport(812)` yields official `WearSensorData` callbacks.
- IMU stream: accel + gyro, 10 samples per callback packet, verified at 100 sample/s from per-sample timestamps, not from packet count alone.
- Motion validity: deliberate wrist/arm movement changes accel/gyro XYZ ranges substantially; this is a real motion-sensitive stream, not just a counter or fake packet feed.
- Live demo: a local browser dashboard expands batched packets into a responsive 100 Hz-ish sample queue and renders a band model with calibration support.

## Why this fork exists

The original work was fragmented across old local experiments, decompiled APK evidence, phone state, and notes. The first recovery task was to turn that into a clean, rollbackable Git branch:

1. preserve public-safe research evidence under `docs/recovery/`;
2. rebuild only the needed Android/headless-agent pieces in source;
3. keep raw artifacts, private phone databases, APKs, firmware blobs, and signed URLs out of Git;
4. commit each verified checkpoint before continuing.

## Research chain

### 1. Dead ends and lower-value routes

- Windows direct Bluetooth and generic controller APIs were unreliable for this device class.
- Android packet capture / Frida / direct official-app tracing did not produce a stable repeatable high-rate collector.
- Vela / companion-app style routes are useful baselines, but were not enough for 100 Hz accel + gyro game-controller work.
- Historical firmware/ODR notes remain useful, but the actual firmware blobs and patch outputs were not recovered in this repository; flashing or firmware patching is not part of the current public chain.

### 2. Recovered Gadgetbridge / Xiaomi baseline

The branch rebuilds enough of the app-layer path to operate safely:

- side-by-side debug package (`hfimucli`) so the normal known-good app/data is not overwritten;
- state import from the known-good Gadgetbridge install with redacted summaries only;
- ADB-driven Mac/Linux CLI (`miband9ctl`) for install/setup/connect/probe workflows;
- app-layer connection/auth proof to `INITIALIZED` instead of stopping at OS `BOND_BONDED`.

### 3. SPP port proof

Classic RFCOMM/SPP port probing showed port 5 can be opened after the app-layer state is initialized. The known A5 init/control path returns a 30-byte response.

This proved a transport/control path, but it did **not** prove high-rate IMU. The project therefore kept searching.

### 4. GameSir / controller-personality investigation

Historical evidence showed a GameSir-like BLE/HID surface and UUID set. This fork added a matrix-style probe instead of blindly replaying old bytes:

- scan/direct-address probing;
- service/characteristic discovery;
- optional bond and controlled historical writes;
- structured output for candidates, services, writes, notifications, and rates.

Cold-state and direct-address tests did not reproduce a usable GameSir/HID sensor stream in normal initialized state. That route is now a secondary clue, not the main path.

### 5. SportXms / Just Dance route

Mi Fitness contains a SportXms / Just Dance body-sensing stack. The important condition was not just binding the service: Mi Fitness had to have the Band 9 selected as the current connected device.

Once that was true, `startSport(812)` produced `WearSensorData` callbacks with accel and gyro arrays.

The public-safe evidence chain is recorded in source, docs, and parser behavior. Raw private app DB rows and exact device identifiers are intentionally excluded.

### 6. Rate and motion validation

The stream was validated using three layers:

- callback packet structure: each callback carries 10 accel samples and 10 gyro samples;
- timestamp math: packet-internal and inter-packet sample timestamps correspond to 100 Hz;
- deliberate motion: accel/gyro XYZ ranges shift with real movement.

This distinction is important: packet/s alone is never treated as sample/s.

### 7. Live dashboard and calibration

The live dashboard path avoids flaky desktop GUI windows by serving a local browser dashboard. It:

- reads the live SportXms/logcat stream;
- expands batched packets into samples;
- renders a band-like model, accel/gyro values, and motion state;
- supports static calibration anchors and gyro-bias handling.

Current calibration direction: use physical poses and optionally the Mac screen as a calibration fixture. The screen can provide a practical plane/edge reference for axis mapping and relative yaw zero, but absolute yaw will still drift without a magnetometer or external reference.

## Software chain

```text
Mi Band 9 / Mi Fitness current device = Band 9, connected
  -> Mi Fitness SportXmsService / Just Dance sportType=812
  -> WearSensorData accel[] + gyro[] callbacks
  -> hfimucli Android side-by-side agent
  -> ADB/logcat + miband9ctl CLI parsers
  -> live_sportxms_web.py local dashboard
  -> future controller mapper
  -> virtual Xbox 360 / XInput-compatible output
```

## Game-controller product direction

The final product target is not a perfect absolute 3D tracker. It is a game-controller input device:

- use pitch/roll/gyro and gestures as relative controls;
- use smoothing, dead zones, response curves, clamps, snap-to-neutral, and recenter;
- treat yaw as relative and short-term accurate, not absolute forever;
- output as a virtual Xbox 360 / XInput-compatible controller for Windows game compatibility;
- use band vibration as haptic feedback and mode/recenter confirmation, while excluding vibration windows from calibration and stillness detection.

## Public safety boundary

Do not commit or publish:

- auth keys, pairing keys, account tokens, cookies, Authorization headers, or signed URLs;
- private Mi Fitness / Gadgetbridge database dumps;
- exact device IDs / DID values / private account rows;
- raw firmware blobs unless their redistribution status is explicitly acceptable;
- raw phone logs that may contain private identifiers.

Use redacted summaries, hashes, counts, and public-safe generated docs instead.

## Remaining work

- Add SportXms finish/cleanup so `sportType=812` is explicitly stopped after capture.
- Finish axis mapping/calibration using desk, side, and screen-plane anchors.
- Add a segmented motion calibration script: static -> lift -> left/right shake -> fast rotate.
- Build a controller-mapping layer with dead zone, smoothing, recenter, and response curves.
- Add a Windows receiver / virtual Xbox 360 output path.
- Add haptic feedback commands and gate IMU stillness/bias updates during vibration windows.
