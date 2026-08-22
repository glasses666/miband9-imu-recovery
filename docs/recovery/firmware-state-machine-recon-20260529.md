# Mi Band 9 firmware / GameSir state-machine recon — updated 2026-05-30

## Current status

This document began as the firmware/GameSir state-machine reconstruction note. It is now a historical and secondary-route note.

The current verified high-rate route is **not** firmware patching and not blind GameSir/FF12 replay. It is Mi Fitness SportXms / Just Dance `sportType=812`, which yields official `WearSensorData` accel + gyro callbacks at 100 sample/s when Mi Fitness has the Band 9 selected and connected.

See `PUBLIC_RESEARCH_CHAIN_20260530.md` for the current full research/software chain.

## Route comparison

| Route | What it is | Current evidence | Current role | Risk |
|---|---|---|---|---|
| Normal Xiaomi/Gadgetbridge SPP | Authenticated Gadgetbridge/Xiaomi app-layer state plus Classic RFCOMM/SPP port 5 | `INITIALIZED` proven; port 5 opens; A5 init returns a control response | Control/debug baseline, not the high-rate stream | Low |
| GameSir/controller personality | BLE/controller/HID-like side mode seen in old evidence | Probe implemented; normal initialized state did not reproduce a usable HID stream | Secondary state-machine clue | Medium |
| Mi Fitness SportXms / Just Dance | Official body-sensing path, `sportType=812` | Verified `WearSensorData` accel + gyro stream, 10 samples/packet, 100 sample/s, motion-sensitive XYZ | Current success route | Medium operational dependency on Mi Fitness state |
| Firmware / ODR route | Static analysis / firmware sensor-driver work | Historical notes mention ODR strings and missing firmware artifacts | Future explanation or last-resort research | High if patching/flashing; low if read-only |

## Public-safe known identifiers

- Product family: Xiaomi Smart Band 9 NFC / Mi Band 9 NFC.
- Model clues: `M2346B1`, `miwear.watch.n66nfc`.
- Observed firmware line: `1.3.206` on the tested band.

Private device identifiers, DIDs, auth keys, account rows, and signed URLs are intentionally excluded.

## Firmware retrieval evidence and limits

Mi Fitness contains OTA/checkupdate paths and logs can expose firmware-family clues, but the public repo must not include signed URLs or private auth material. The exact firmware artifacts historically mentioned in old notes are not part of this repo.

Safe stance:

- firmware strings and ODR hypotheses are useful context;
- do not flash or publish patched firmware without a verified original, rollback path, and redistribution review;
- prefer official/debug software routes before firmware patching.

## GameSir / HID state-machine evidence

Historical clues included service/characteristic families around GameSir/controller mode and HID. This branch implements probing as a matrix collector rather than assuming one byte sequence unlocks the mode.

The gate for claiming GameSir success remains strict:

- same sequence works from cold state twice;
- services/chars/notifications are visible and stable;
- sustained notifications contain sample-like payloads;
- sample rate is computed from payload samples and timestamps, not callback count.

That gate has not been met in the current branch.

## SportXms supersession

The SportXms route *has* met the important gates:

- service bind succeeds;
- current selected device is confirmed as Band 9 and connected;
- `startSport(812)` starts body-sensing mode;
- callbacks contain accel and gyro arrays;
- three validation runs show 100 Hz sample cadence after outlier cleanup;
- a deliberate movement run confirms motion-sensitive XYZ ranges.

Therefore the active software chain should build on SportXms/812 first, with GameSir and firmware kept as supporting research paths.

## Next implementation targets

1. Add SportXms finish/cleanup after capture.
2. Complete dashboard axis mapping and calibration.
3. Build game-controller mapping and virtual Xbox 360 / XInput output.
4. Add haptic feedback as output, while ignoring/gating IMU stillness/bias updates during vibration windows.
