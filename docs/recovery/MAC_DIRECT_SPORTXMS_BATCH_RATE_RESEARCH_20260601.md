# Mi Band 9 SportXms batch/rate static research — 2026-06-01

## Scope

This pass is static/read-only. It looks for app/protocol-level knobs that could explain or change the observed macOS direct SportXms behavior:

- 100 Hz IMU samples
- 10 accel + 10 gyro samples per `8/53` packet
- ~100 ms packet/callback cadence

No live packet variants were sent in this pass. No firmware was modified or flashed.

## Current measured baseline

The proven macOS route is:

`Mi Band 9 -> macOS IOBluetooth RFCOMM channel 5 -> Xiaomi auth/session -> encrypted SportXms start -> 8/53 IMU -> encrypted SportXms stop`

Static baseline:

- sample tick: 10 ms
- per `8/53`: 10 accel + 10 gyro samples
- packet cadence p50 ~= 99.99 ms
- packet cadence p95 ~= 125.29 ms
- stable sample rate ~= 100 Hz

This means the main latency floor is batching, not raw sample rate.

## Findings

### 1. Public SportXms API does not expose batch/rate fields

Decompiled Mi Fitness `SportXmsRequestData` has only five fields:

- `timeStamp`
- `timeZone`
- `sportType`
- `sportState`
- `courseId`

Source:

- `tools/miband9ctl/artifacts/direct_connect/20260531_145638/jadx-mi-health/sources/com/xiaomi/fitness/sport_xms/data/SportXmsRequestData.java`

`SportXmsApiImpl.startSport()` logs and forwards only four of them into the internal sport manager request:

```java
new SportRequestData.a()
    .B(sportXmsRequestData.getSportType())
    .z(sportXmsRequestData.getSportState())
    .D((long) sportXmsRequestData.getTimeStamp(), TimeUnit.SECONDS)
    .G(sportXmsRequestData.getTimeZone())
    .p();
```

The `courseId` from `SportXmsRequestData` is not forwarded there. No `sampleRate`, `batchSize`, `reportInterval`, or `frequency` field appears in this public XMS request path.

### 2. Internal SportRequestData has more sport fields, but still no obvious IMU cadence knob

Internal `SportRequestData` supports:

- `supportVersions`
- `sportLaunchType`
- `sportTargetArr`
- `sportCourse`
- `isNotSport`
- `disableAudioBroadcast`
- `accessoryWearMode`
- `finishSportData`
- route/pre-route/course/plan fields

Source:

- `tools/miband9ctl/artifacts/direct_connect/20260531_145638/jadx-mi-health/sources/com/xiaomi/fitness/sport_manager_export/data/SportRequestData.java`

These look like sport UI/session metadata rather than sensor report rate or batching controls.

### 3. The protobuf start object (`hfa`) has optional fields, but none is clearly batch/rate

Decompiled nano protobuf class `hfa` serializes fields:

- field 1: timestamp (`c`)
- field 2: timezone submessage (`d` / `oe4`)
- field 3: sport type (`e`)
- field 4: sport state (`g`)
- field 5: ids bytes (`h`)
- field 6: support/select version (`i`)
- field 7: sport target array (`j`)
- field 8: finish data (`afa`)
- field 9: sport launch type (`f`)
- field 10: accessory wear mode (`l`, allowed 0..3)
- field 11: sport course / course-like data (`cfa`)

Source:

- `tools/miband9ctl/artifacts/direct_connect/20260531_145638/jadx-mi-health/sources/defpackage/hfa.java`

The app's normal converter `vga.v(SportRequestData)` sets:

```java
hfaVar.c = sportRequestData.timeStamp;
hfaVar.d = timezoneSubmessage;
hfaVar.e = y(sportRequestData.sportType);
hfaVar.g = x(sportRequestData.sportState);
if (sportRequestData.isAcessoryDevice) {
    hfaVar.l = sportRequestData.accessoryWearMode;
}
hfaVar.i = 3;
if (sportRequestData.sportTargetArr != null) {
    hfaVar.j = ...;
}
```

Source:

- `tools/miband9ctl/artifacts/direct_connect/20260531_145638/jadx-mi-health/sources/defpackage/vga.java`

The current corrected opener matches this minimal path. There is no obvious `sampleRate`, `batchSize`, `reportInterval`, or sensor ODR field in the app-level opener.

### 4. Lower-level `HMProSensorDataProfile` has sensor-mask config, but it is a separate path from SportXms 812

A separate decompiled sensor profile exists:

- `x6v` = `HMProSensorDataProfile`
- `n6v` = `HMProSensorDataController`
- sensor masks from `vr.java`:
  - `GSENSOR = 1`
  - `GYRO = 16`
  - `TIME = 128`
  - others: PPG/ECG/GEO/HR/etc.

The profile config command is:

```java
P(new byte[]{1, (byte) i, b2});
```

and for newer profile versions:

```java
P(new byte[]{1,
  (byte) (i & 255),
  (byte) ((i >> 8) & 255),
  (byte) ((i >> 16) & 255),
  (byte) ((i >> 24) & 255),
  b2});
```

Then start/stop/watchdog are:

```java
start: P(new byte[]{2})
stop:  P(new byte[]{3})
watchdog: send new byte[]{0}
```

Sources:

- `tools/miband9ctl/artifacts/direct_connect/20260531_145638/jadx-mi-health/sources/defpackage/x6v.java`
- `tools/miband9ctl/artifacts/direct_connect/20260531_145638/jadx-mi-health/sources/defpackage/n6v.java`
- `tools/miband9ctl/artifacts/direct_connect/20260531_145638/jadx-mi-health/sources/defpackage/vr.java`

This is the best non-firmware clue found in this pass, but it is **not the same as the SportXms 812 opener**. It may be an older/direct sensor profile or an internal module. It could be worth tracing later, but it is not yet evidence that SportXms batching is configurable.

## Current conclusion

No clear app/protocol-level `batchSize` or `sampleRate` knob was found in the SportXms 812 start path.

The observed `10 samples / packet` is likely one of:

1. SportXms service-internal batching policy on the band;
2. profile/reporting implementation detail tied to sport type 812;
3. lower-level HMPro sensor profile behavior not exposed by the public SportXms API;
4. firmware-side sensor service batching.

I would not jump directly to firmware patching yet. The next best move is a bounded live variant matrix using only sourced fields and immediate stop/quiet verification.

## Safe next experiment matrix

All variants should use:

`auth -> start variant -> 5s capture -> stop -> quiet-after`

Pass metrics:

- start accepted / rejected
- nonzero `8/53`
- accel sample count
- gyro sample count
- samples per packet
- packet cadence p50/p95
- truncated/prefix packets
- stop-after quiet (`8/53=0`)

### Variant group A: start object optional fields

Use the same SportXms 812 command path, changing one sourced optional field at a time.

1. Baseline repeat: exact current payload.
2. `supportVersions/selectVersion` field 6:
   - current known-good value: `3`
   - candidates: omit, `2`, maybe `4` only if encoding/build accepts it.
   - risk: medium-low; likely accepted/rejected, not destructive.
3. accessory wear mode field 10:
   - candidates: `0`, `1`, `2`, `3`
   - only because `hfa` explicitly accepts 0..3.
   - expectation: may change orientation/semantics, less likely cadence.
4. sport target field 7:
   - likely not cadence-related; lower priority.

### Variant group B: sport type variants

Try only sourced sport types near current route:

- `812` baseline
- `810` nearby allowed value in `vga.y()`/`hfa`

Do not broad-fuzz sport types yet.

### Variant group C: lower-level HMProSensorDataProfile trace only

Before live use, trace whether Mi Fitness ever invokes `n6v/x6v` for Band 9 / somatosensory mode and what `(sensorMask, modeByte)` it uses.

The interesting mask for accel+gyro would be:

- `GSENSOR | GYRO = 1 | 16 = 17`
- optionally `TIME = 128`, so `145`

This path should be treated as a separate protocol route, not a SportXms variant.

## Firmware status

Firmware analysis is not yet required as the first mainline. It becomes justified if:

- all SportXms optional-field variants still produce exactly 10 samples/packet;
- HMPro sensor profile is unavailable or also fixed-batch;
- no original app path emits a smaller batch or lower-latency mode.

If we do firmware next, first pass should be static strings/constants only: no patching, no flashing.
