# Mi Band 9 direct-connect inventory — 2026-05-31

Purpose: preserve the evidence collected before moving from the working phone/Mi Fitness/SportXms Binder bridge toward a more direct Gadgetbridge/native or Mac-direct path.

Boundary for this pass: read-only/static collection. No Bluetooth disconnect, no pairing reset, no Mi Fitness data mutation beyond already-existing source/artifact reads.

## Current known-good route to preserve

The working high-rate route remains:

```text
Mi Band 9 initialized by Gadgetbridge/hfimucli
+ Mi Fitness current device connected
+ SportXms Binder startSport(812)
→ WearSensorData accel+gyro callback batches
→ Mac/HUD/controller pipeline
```

Do not break this while experimenting with direct connection.

Motion/XInput/HUD checkpoint before this pivot:

- Commit: `20eaf9fdc Checkpoint Mi Band motion controller state`
- Prior code checkpoint: `5663f9faa Add Mi Band motion channel HUD`
- State doc: `docs/recovery/CONTROLLER_MOTION_STATE_20260531.md`

## Local artifacts captured

Mi Fitness was pulled read-only from the attached Android phone:

- Device visible through ADB: `c8f9a1da device`
- APK source on phone: `package:/data/app/com.mi.health-rAz61YczP4wVSCkmHe3gjg==/base.apk`
- Local private artifact: `tools/miband9ctl/artifacts/direct_connect/20260531_145638/com.mi.health.base.apk`
- Decompiled source: `tools/miband9ctl/artifacts/direct_connect/20260531_145638/jadx-mi-health/sources/`
- JADX logs:
  - `tools/miband9ctl/artifacts/direct_connect/20260531_145638/jadx_stdout.txt`
  - `tools/miband9ctl/artifacts/direct_connect/20260531_145638/jadx_stderr.txt`
- Static hit summary: `tools/miband9ctl/artifacts/direct_connect/20260531_145638/sportxms_static_hits.txt`

These artifacts stay under ignored `tools/miband9ctl/artifacts/`; do not commit APK/decompiled bulk.

No prior `*.btsnoop*` / HCI / pcap artifact was found in the repo during this pass.

## Mi Fitness SportXms service surface

`SportXmsHelperImpl` confirms the exported helper route used by external apps:

- Service action: `com.xiaomi.fitness.SPORT_XMS_SERVICE`
- Primary package: `com.mi.health`
- Fallback package: `com.xiaomi.wearable`
- Binder interface: `com.xiaomi.fitness.sport_xms.launch.ISportXmsApi`
- Source: `.../com/xiaomi/fitness/sport_xms/SportXmsHelperImpl.java`

Important helper calls:

- `bindXmsService(...)` creates an intent with action `com.xiaomi.fitness.SPORT_XMS_SERVICE` and package `com.mi.health`, then binds.
- `startSport(long time, String did)` constructs:

```java
new SportXmsRequestData(
  (int) (time / 1000),
  (int) (TimeUnit.MILLISECONDS.toMinutes(FitnessDateUtils.getTZOffsetInMilli(time)) / 15),
  812,
  1,
  0
)
```

Then calls `fod.startSport(did, sportXmsRequestData)`.

- `finishSport(did)` calls `finishSportByType(did, 812)`.
- `pauseSport(did)` calls `pauseSport(did, 812)`.
- `resumeSport(did)` calls `restartSport(did, 812)`.
- Sensor listener path only forwards `wearSensorData.getAccel()` in this helper, but the lower `WearSensorData` parcel contains both `accel` and `gyro`; our existing custom Binder callback reads both.

## Binder transaction map

From decompiled `defpackage/fod.java` (`ISportXmsApi`):

- `1`: `startSport(String did, SportXmsRequestData request)`
- `2`: `pauseSport(String did, int sportType)`
- `3`: `resumeSport(String did, int sportType)`
- `4`: `finishSport(String did, SportXmsFinishData finishData)`
- `5`: `restartSport(String did, int sportType)`
- `7`: `setSportStateChangedListener(kmd)`
- `8`: `setSportXmsDataChangedListener(imd)`
- `9`: `setSportXmsSensorDataChangedListener(jmd)`
- `11`: `isDeviceConnected()`
- `14`: `getDeviceBattery()`
- `15`: `isSupportSomatosensoryGame()`
- `23`: `getDeviceInfo()`
- `24`: `finishSportByType(String did, int sportType)`

Existing Gadgetbridge-side `HfImuCliService` mirrors this map:

- Constants at lines ~79–92 define service/action/interface/transaction numbers.
- `performSportXmsProbe()` calls device info, registers sensor/state listeners, optionally starts sport type `812`, captures, then finishes/cleans up.
- `transactSportXmsStartSport(...)` writes parcel fields in exact order:

```text
interfaceToken: com.xiaomi.fitness.sport_xms.launch.ISportXmsApi
String did
int present = 1
int timestamp_seconds
int timezone_quarter_hours
int sportType
int sportState
int courseId = 0
```

- `SportXmsSensorCallback.onTransact(code=1)` reads `WearSensorData` as:

```text
int present
TypedList<SensorData> accel
TypedList<SensorData> gyro
```

Each `SensorData` parcel is:

```text
long timestamp
float x
float y
float z
```

## Mi Fitness internal flow behind `startSport(812)`

Static APK triage shows `SportXmsApiImpl` is not itself the direct BLE writer. It is a Binder façade into Mi Fitness sport manager layers:

```text
external caller / helper
→ ISportXmsApi.startSport(... SportXmsRequestData ...)
→ SportXmsApiImpl.startSport(...)
→ addSportDataChangedListener("SportXmsApiImpl", ...)
→ addSportSensorDataChangedListener("SportXmsApiImpl", ...)
→ addSportStateChangedListener(...)
→ build SportRequestData from SportXmsRequestData
→ SportManagerExtKt.getInstance(ISportRemoteState).startSport(currentDid, SportRequestData, callback)
→ SportDataCaller / SportDataServer / lower sport manager
→ WearSensorData callbacks
```

Evidence:

- `SportXmsApiImpl.java` lines ~720–735 add data/sensor/state listeners and call `ISportRemoteState.startSport(...)`.
- `SportXmsApiImpl$iSportSensorDataChangedListener$1.java` forwards `WearSensorData` to the registered remote `jmd` listener.
- `SportDataCaller.java` implements `ISportRemoteData` and passes `addSportSensorDataChangedListener` down to a Binder/server layer.
- `SportDataServer.java` registers a sensor listener and subscribes to an event bus-like path.
- `SportManagerExtKt.java` resolves implementations from Hilt entry points, not static global singletons we can directly port to Mac.

Implication: copying only `ISportXmsApi` Binder calls gives the current phone/Mi Fitness bridge, not a Mac-direct BLE protocol. For real direct connect, the next sequence to extract is below `ISportRemoteState.startSport`: `SportDataServer` / `SportState` / sport manager → wearable device protocol.

## Capability gate

`SportXmsApiImpl.isSupportSomatosensoryGame()` checks current device capability bit `512`:

```java
(DeviceManagerExtKt.getInstance(...).getDeviceCapability(currentDid) & 512) != 0
```

So direct experiments must ensure the selected/current device is the Mi Band 9 and connected, otherwise Binder/service calls can succeed while returning no usable IMU packets.

## Current direct-connect hypothesis

The visible working switch is still **SportXms / Just Dance sport type `812`**, not a public IMU GATT toggle.

Two possible lower-level routes remain:

1. **Gadgetbridge-native opener**
   - Keep Android/Gadgetbridge as authenticated Xiaomi session owner.
   - Port the lower sequence under Mi Fitness `ISportRemoteState.startSport(812)` into Gadgetbridge if it can be extracted.
   - Preferred next step because Gadgetbridge already handles Xiaomi auth/session and initialized state.

2. **Mac CoreBluetooth/direct daemon**
   - Requires both Xiaomi auth/session and the SportXms/812 command sequence.
   - Heavier and riskier; do after Android/Gadgetbridge-native opener proves the command sequence.

## Lower wearable command checkpoint

The next static pass reached the first concrete Xiaomi wearable command object below the SportXms Binder façade.

Details are in:

- `docs/recovery/SPORTXMS_812_WEAR_PACKET_20260531.md`
- helper encoder: `tools/miband9ctl/sportxms_812_packet_skeleton.py`

Key extracted shape:

```text
SportXms Binder startSport(812)
→ SportXmsApiImpl.startSport(...)
→ ISportRemoteState.startSport(...)
→ SportWearSender / cgp.l(...)
→ DeviceSyncManager.call(did, hns, needResponse=true, timeout=15s)

hns {
  field 1: 8,
  field 2: 26,
  field 10: uca {
    field 20: hfa {
      field 1: timestamp_seconds,
      field 2: oe4 { field 1: timezone_value },
      field 3: 812,
      field 4: 0,      # start state, from vga.x(1)
      field 6: 3       # selectVersion
    }
  }
}
```

This is not raw BLE bytes. `DeviceContact` still wraps/fragments/encrypts/session-frames the `hns` object.

Follow-up transport trace now pinned down the first lower layer:

- `docs/recovery/DEVICECONTACT_TRANSPORT_TRACE_20260531.md`
- plaintext `hns` is sent as wearable API type `101`;
- type `101` maps to encrypted PB/protobuf channel `1`, L2 opcode `2`;
- Mi Fitness BLE V2 then writes L1/SAR-framed bytes to FE95-family SAR write/notify characteristics (`0x005f`/`0x005e`);
- Gadgetbridge's existing SPP V2 path is the closest native opener because it already implements the A5A5/channel/encrypted-opcode frame for `Channel.ProtobufCommand`.
