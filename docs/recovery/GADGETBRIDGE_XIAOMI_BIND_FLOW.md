# Gadgetbridge / Xiaomi Smart Band 9 binding + auth flow

This note records the actual code path for Mi Band 9 binding in this recovery repo.
Do not store or paste raw auth keys here.

## Current conclusion

The previous `miband9ctl band pair` slice only completed Android OS Bluetooth bonding (`BOND_BONDED`). It did not complete Xiaomi/Gadgetbridge app-layer binding.

For the band, the correct success gate is `GBDevice.State.INITIALIZED` after `XiaomiAuthService` authentication and `XiaomiSupport.onAuthSuccess()`, matching the physical band entering normal service/main-screen mode.

## Device state model from Queen Glasser

1. State 1: unbound/activated, QR code shown, asks to download app to bind.
2. State 2: phone requests pairing; band shows confirm/cancel pairing buttons.
3. State 3: after confirm, band shows waiting for phone pairing; hidden countdown runs.
4. State 4: app-layer pairing/auth/sync not completed in time; binding fails and returns to state 1.
5. State 5: full pairing/auth/sync completed; band unlocks to normal service/main-screen mode and is visible only to the bound phone/device.

## Gadgetbridge pre-auth gates

Source: `app/src/main/java/nodomain/freeyourgadget/gadgetbridge/devices/xiaomi/XiaomiCoordinator.java`

- `MiBand9Coordinator` extends `XiaomiCoordinator`.
- `XiaomiCoordinator.getBondingStyle()` returns `BONDING_STYLE_REQUIRE_KEY`.
- `XiaomiCoordinator.getSupportedDeviceSpecificAuthenticationSettings()` returns `R.xml.devicesettings_pairingkey`.
- `XiaomiCoordinator.validateAuthKey()` accepts:
  - 32 hex chars
  - `0x` + 32 hex chars
  - numeric user id for plaintext devices

Source: `app/src/main/java/nodomain/freeyourgadget/gadgetbridge/activities/discovery/DiscoveryActivityV2.java`

- Before starting pair, Discovery checks device-specific prefs for `authkey`.
- If `authkey` is missing: warning `discovery_need_to_enter_authkey`, pairing does not continue.
- If invalid: warning `discovery_entered_invalid_authkey`, pairing does not continue.

Source: `app/src/main/java/nodomain/freeyourgadget/gadgetbridge/devices/miband/MiBandPairingActivity.java`

- For devices with auth settings, it reads `GBApplication.getDeviceSpecificSharedPrefs(device.getAddress()).getString("authkey", null)`.
- If empty, it writes a random authkey, which is wrong for an already-tokenized Mi Band 9 unless this path is doing a fresh protocol-supported generation.

## Gadgetbridge connect + auth chain

Normal UI path:

```text
DiscoveryActivityV2 item selected
  -> authkey exists + validates
  -> startPair(deviceCandidate, coordinator)
  -> BondingUtil.initiateCorrectBonding(...)
  -> Android createBond() / bonding broadcasts
  -> BondingUtil.attemptToFirstConnect(...)
  -> GBApplication.deviceService(device).connect(true)
  -> DeviceCommunicationService / device support
  -> XiaomiSupport.connect()
  -> XiaomiSppSupport.connect() or XiaomiBleSupport.connect()
  -> SetDeviceState INITIALIZING
  -> SetDeviceState AUTHENTICATING
  -> XiaomiAuthService handshake
  -> GBDevice.State.INITIALIZED
  -> XiaomiSupport.onAuthSuccess()
  -> Xiaomi service initialize() calls / sync
  -> physical band should reach state 5
```

## Xiaomi auth specifics

Source: `app/src/main/java/nodomain/freeyourgadget/gadgetbridge/service/devices/xiaomi/XiaomiAuthService.java`

Encrypted path:

```text
startEncryptedHandshake()
  -> secretKey = getSecretKey(device) from device-specific `authkey`
  -> send command subtype CMD_NONCE (`auth step 1`)
  -> handle watch nonce
  -> compute miwear-auth HMAC using phone nonce + watch nonce + secretKey
  -> verify watch HMAC
  -> send CMD_AUTH (`auth step 2`)
  -> on CMD_AUTH response: set device INITIALIZED and call onAuthSuccess()
```

Failure gates:

- Missing/wrong `authkey` means `getSecretKey()` returns zeros or wrong bytes.
- Watch HMAC mismatch leads to `handleWatchNonce returned null, disconnecting`.
- Auth status failure logs `Authentication failed, subtype=..., status=...` and disconnects.

## Current phone evidence

Safe evidence only; raw keys not recorded.

- Android OS Bluetooth state: hand band is currently `BOND_BONDED` as `Xiaomi Smart Band 9 test-device` at `AA:BB:CC:DD:EE:FF`.
- hfimucli app DB: `known-devices` returns `device_count=0`.
- Original Gadgetbridge DB has device record:
  - `NAME=Xiaomi Smart Band 9 test-device`
  - `IDENTIFIER=AA:BB:CC:DD:EE:FF`
  - `TYPE_NAME=MIBAND9`
  - `MODEL=M2346B1`
- Original Gadgetbridge device prefs contain `authkey`:
  - present: true
  - format: `hex32`
  - sha256_16 fingerprint: `1a5f7ce274843af5`
- Mi Fitness `/data/data/com.mi.health/databases/device_db` has matching row:
  - `model=miwear.watch.n66nfc`
  - name `小米手环9 NFC版`
  - detail JSON keys include `token`, `encrypt_key`, `beaconkey`, `irq_key`, `mac`, `phone_id`, `peripheral_id`, `sn`
  - `token` fingerprint matches original Gadgetbridge `authkey`: `1a5f7ce274843af5`

## Where the last attempt failed

It stopped before Gadgetbridge validation/auth.

`miband9ctl band pair` implemented a headless Android OS pairing state machine:

```text
HfImuCliReceiver pair
  -> HfImuCliService.startPair()
  -> BluetoothDevice.createBond()
  -> ACTION_PAIRING_REQUEST / ACTION_BOND_STATE_CHANGED
  -> terminal payload `pair_complete bond_state=BONDED`
```

It did not:

- import the original Gadgetbridge device row into hfimucli DB
- import `authkey` into hfimucli device-specific prefs
- call `GBApplication.deviceService(device).connect(true)` for the Mi Band 9
- reach `XiaomiSupport.connect()`
- reach `XiaomiAuthService.startEncryptedHandshake()`
- reach `GBDevice.State.INITIALIZED`
- reach `XiaomiSupport.onAuthSuccess()`

Therefore the physical band can still fall back to state 1 even while Android reports `BOND_BONDED`.

## Next implementation target

Add a real `band bind` / `band connect` lane, not another raw `pair` lane:

1. `auth sources --json`
   - read-only inventory from original Gadgetbridge and Mi Fitness
   - never print raw token by default; show source, address match, format, fingerprint
2. `state import --from original-gadgetbridge --address AA:BB:CC:DD:EE:FF --json`
   - copy only current device DB row and device-specific prefs into hfimucli
   - backup hfimucli DB/prefs first
3. `band bind --address AA:BB:CC:DD:EE:FF --json`
   - if physical band is state 1, remove stale OS bond first, then pair
   - after band-side confirm and `BOND_BONDED`, immediately call Gadgetbridge connect/auth
   - wait for terminal payloads: `bonded`, `auth_started`, `auth_ok`, `initialized`, `service_mode_ready`
4. Only after state 5, run SPP channel 5 / IMU init / collect.
