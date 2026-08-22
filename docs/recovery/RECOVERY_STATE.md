# Current recovery state

Date: 2026-05-30

Base: Gadgetbridge `a0948ee` / 0.83.0 lineage, continued on local branch `hfimucli-headless-mvp`.

This branch is an experimental recovery and controller-prototype fork. It is public-safe only after excluding local artifacts and private identifiers.

## Current bottom line

The project has moved beyond the old firmware/ODR speculation stage. A 100 Hz accel + gyro stream is now repeatably available through the Mi Fitness SportXms / Just Dance route (`sportType=812`) when Mi Fitness has the Band 9 selected as the current connected device.

## Verified facts

- `hfimucli` side-by-side package can import known-good Gadgetbridge state and reach app-layer `INITIALIZED`.
- RFCOMM/SPP port 5 opens after initialization and returns an A5 control response; this is a control/transport proof, not the final IMU path.
- GameSir/controller probing exists and is bounded, but normal initialized state did not reveal a reproducible high-rate HID stream.
- SportXms / Just Dance `sportType=812` yields official `WearSensorData` accel + gyro callbacks.
- The callback batching is 10 samples per packet; timestamp validation shows 100 sample/s.
- Deliberate motion changes accel/gyro XYZ ranges, confirming the stream is motion-sensitive and usable.
- The local live dashboard now renders a band model and supports calibration anchors.

## Software components in this branch

- Android side-by-side agent under `app/src/main/java/.../externalevents/hfimu/`.
- `miband9ctl` CLI under `tools/miband9ctl/`.
- Live dashboard: `tools/miband9ctl/live_sportxms_web.py`.
- Recovery docs under `docs/recovery/`.

## Public safety boundary

Do not publish:

- auth keys, pairing keys, OAuth/session tokens, signed firmware URLs, cookies, or Authorization headers;
- exact DID/account/device private rows from Mi Fitness or Gadgetbridge databases;
- raw private database dumps or phone logs;
- local APKs, firmware blobs, keystores, or patch zips unless separately cleared.

This repo uses `.gitignore` to keep `artifacts/`, APKs, firmware blobs, key stores, and private recovery material out of Git.

## Current open work

1. SportXms cleanup/finish: explicitly stop `sportType=812` after capture.
2. Calibration: finish axis mapping with flat, side, and Mac-screen-plane anchors.
3. Segmented motion calibration: static -> lift -> left/right shake -> fast rotate.
4. Controller layer: map filtered IMU to virtual Xbox 360 / XInput axes and buttons.
5. Haptics: add band vibration feedback while gating IMU calibration during vibration windows.

## Historical notes superseded

Older docs that say the only viable route is firmware/ODR work are preserved as history but are now superseded by the verified SportXms/812 path. Firmware analysis remains useful for explanation and future research, but is no longer required to obtain the current 100 Hz stream.
