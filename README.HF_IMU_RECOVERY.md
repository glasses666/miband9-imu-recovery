# Mi Band 9 HF IMU Recovery Workspace

Experimental public fork for recovering and productizing a 100 Hz Xiaomi Smart Band 9 / Mi Band 9 NFC IMU stream.

This is not an upstream-ready Gadgetbridge feature branch. It is a research fork with a side-by-side debug package, a headless Android agent, a Mac/Linux CLI, and public-safe documentation of the research chain.

## Current result

- `hfimucli` can reach Xiaomi/Gadgetbridge app-layer `INITIALIZED` using imported known-good state.
- RFCOMM/SPP port 5 control/init path is proven, but not treated as the high-rate IMU solution.
- GameSir/HID state-machine probing was implemented and bounded; normal initialized state did not reproduce a usable controller surface.
- Mi Fitness SportXms / Just Dance `sportType=812` is the verified route for official `WearSensorData` accel + gyro callbacks.
- The stream is validated at 100 sample/s from per-sample timestamps, with real motion-sensitive XYZ ranges.
- A local browser live dashboard renders a band-like model and supports calibration anchors.

## Public-safe starting points

1. `docs/recovery/PUBLIC_RESEARCH_CHAIN_20260530.md` — current full research/software chain.
2. `docs/recovery/RECOVERY_STATE.md` — current state and safety boundary.
3. `docs/recovery/path-reconstruction.md` — updated path reconstruction from old dead ends to the SportXms success route.
4. `docs/recovery/firmware-state-machine-recon-20260529.md` — historical firmware/GameSir recon, now annotated with the newer SportXms result.
5. `tools/miband9ctl/miband9ctl/cli.py` — CLI parser and command surface.
6. `tools/miband9ctl/live_sportxms_web.py` — local live IMU dashboard.

## Software chain

```text
Mi Band 9 + Mi Fitness selected device = Band 9, connected
  -> SportXmsService / Just Dance sportType=812
  -> WearSensorData accel[] + gyro[] callbacks
  -> hfimucli side-by-side Android agent
  -> ADB/logcat + miband9ctl parser
  -> local live dashboard / future controller mapper
  -> virtual Xbox 360 / XInput-compatible output
```

## Safety boundary

This repo intentionally excludes local/private artifacts:

- `artifacts/`
- APKs/AABs/keystores
- auth keys, pairing keys, tokens, signed URLs
- Mi Fitness / Gadgetbridge private database dumps
- exact device/account identifiers
- firmware blobs unless redistribution is explicitly safe

If proof is needed, use public-safe summaries, hashes, counts, and generated docs. Do not paste private credentials or raw phone artifacts into GitHub issues, docs, commits, or logs.

## Upstream relation

The base project is Gadgetbridge. This fork remains under the original licenses and keeps the upstream codebase intact where possible. The research-specific additions are local to this branch and are not presented as a polished upstream contribution.
