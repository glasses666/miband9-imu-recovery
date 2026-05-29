# Mi Band 9 high-frequency IMU path reconstruction

Date: 2026-05-30

This is the public-safe updated path reconstruction. Earlier private/local notes referenced absolute machine paths and sensitive evidence locations; those details are intentionally omitted here.

## Bottom line

The old conclusion — that firmware/ODR work was the only plausible high-frequency route — has been superseded.

The current verified route is:

1. recover a safe Android/Gadgetbridge-derived side-by-side agent (`hfimucli`);
2. import known-good app state without publishing secrets;
3. authenticate the Band 9 to app-layer `INITIALIZED`;
4. make sure Mi Fitness has the Band 9 selected as the current connected device;
5. call Mi Fitness SportXms / Just Dance `startSport(812)`;
6. parse official `WearSensorData` accel + gyro callbacks;
7. expand 10-sample callback packets into a 100 sample/s stream;
8. feed the stream into a local dashboard / future game-controller mapper.

## Reconstructed timeline

### 1. Windows and direct Bluetooth routes

Windows direct Bluetooth and generic controller APIs were useful for observation but not for repeatable control. The device could appear in different personalities, but the PC path did not provide a reliable way to authenticate, trigger the right state, and stream usable IMU samples.

### 2. Android capture and official-app tracing attempts

Android packet-capture, HCI, and Frida-style attempts did not produce a stable repeatable high-rate collector. They did, however, point back to the fact that the official app contains the state needed to unlock richer sensor paths.

### 3. Recovered Gadgetbridge / SPP path

A previous APK and notes showed an Android/Gadgetbridge-based experiment around Classic RFCOMM/SPP port 5 and Xiaomi A5 packets.

The recovered fork rebuilt this safely:

- side-by-side package identity;
- headless ADB command surface;
- state import with redacted summaries;
- app-layer `INITIALIZED` proof;
- RFCOMM/SPP port probing.

Port 5 can open and return a control response, but that is not enough to claim high-rate IMU.

### 4. GameSir / controller personality

Historical evidence suggested a GameSir-like BLE/HID surface involving UUID families around `8650`, `865F`, `FF10`, `FF12`, and HID `1812/2A4D`.

This branch treats that as a state-machine clue, not a magic unlock packet. The implemented probe records scan candidates, services, characteristics, writes, notifications, and rate evidence. Normal initialized state did not reproduce the controller surface, so the route is secondary for now.

### 5. SportXms / Just Dance success route

The breakthrough route is Mi Fitness SportXms / Just Dance body-sensing mode.

Important condition:

- Mi Fitness must have the Band 9 selected as the current connected device.
- Binding the SportXms service alone is insufficient if Mi Fitness is currently pointing at another band or disconnected state.

Once selected and connected, `sportType=812` yields official `WearSensorData` with accel and gyro arrays.

### 6. Rate validation

The stream is intentionally batched. The correct validation is sample-based:

- each valid callback packet contains 10 accel samples and 10 gyro samples;
- sample timestamps show 100 Hz spacing;
- startup/backlog outliers are excluded;
- wall-clock and timestamp-derived rates agree around 100 sample/s.

Packet/s is never used as sample/s.

### 7. Motion validation

A deliberate movement run showed large accel/gyro XYZ range changes. This confirms the data responds to real movement and is useful for a controller pipeline.

### 8. Live display / controller prototype

The local dashboard expands batched packets, renders a band model, and supports calibration anchors. The final product direction is a PC game-controller input path:

```text
100 Hz IMU
  -> bias correction / filtering / dead zone / response curve / recenter
  -> virtual Xbox 360 / XInput axes and buttons
  -> optional band haptic feedback
```

## What remains historically useful

- SPP port 5 and A5 packets remain useful control-path evidence.
- GameSir/HID traces remain useful for understanding possible hidden personalities.
- Firmware/ODR notes remain useful if an official/debug path later proves insufficient.

But none of those should be described as the current verified high-rate route. The current verified route is SportXms / Just Dance `sportType=812`.

## Public evidence boundary

Public docs should use relative source paths and redacted summaries. Raw app databases, account/device IDs, auth keys, signed URLs, phone logs, and private artifact paths stay out of GitHub.
