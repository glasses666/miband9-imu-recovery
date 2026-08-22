# Mi Band 9 macOS direct RFCOMM SportXms/IMU gate — 2026-06-01

## Summary

The macOS direct IMU gate passed via the Band 9's classic Serial Port / RFCOMM channel 5 path.

This run was started after the BLE FE95 path became non-advertising from CoreBluetooth while macOS still showed the band as paired/visible. The earlier auto-run watcher was too narrow: it scan-gated on BLE advertising even though the live device had moved into a macOS paired/retrievable state and exposed Serial Port over IOBluetooth.

## What was fixed during this pass

- Stopped the stale scan-only watcher.
- Confirmed `system_profiler` / `blueutil` showed `Xiaomi Smart Band 9 test-device` paired/visible to macOS.
- Confirmed CoreBluetooth FE95 scan/retrieve could not connect in that state.
- Queried IOBluetooth SDP and found:
  - service name: `Serial Port`
  - RFCOMM channel: `5`
- Added a macOS RFCOMM auth/SportXms probe using `IOBluetoothRFCOMMChannel`.

## Live run

Artifact root:

```text
/tmp/miband9_mac_direct_imu_rfcomm_20260601_145840/sportxms_rfcomm5
```

Transport:

```text
macOS IOBluetooth RFCOMM channel 5
```

Sequence:

```text
session_config
→ auth_step1_phone_nonce
→ WatchNonce/HMAC verify locally
→ auth_step3
→ encrypted_sportxms_start
→ capture window
→ encrypted_sportxms_stop
→ redacted decode summary
```

Raw auth keys, nonces, session material, encrypted frames, and full payloads remain local-only in the artifact directory and are not included in this report.

## Redacted result

From `sportxms_summary.redacted.json`:

```text
ok=true
connected=true
watch_hmac_verified=true
auth_step3_queued=true
sportxms_start_queued=true
sportxms_stop_queued=true
notification_count=146
frame_count=155
encrypted_frame_count=148
unique_frame_count=155
8/53 packets=129
accel samples=1290
gyro samples=1290
complete_payload_packets=129
truncated_or_prefix_packets=0
```

Command counts:

```text
8/26: 2
8/50: 12
8/53: 129
10/3: 1
17/7: 2
18/0: 1
2/42: 1
```

Decoder evidence:

```text
first 8/53 payload top fields: 1=8, 2=53
uca/fga path decoded
fga.field5 → accel
fga.field6 → gyro
sample_rows=1290
```

## Quiet-after verification

A follow-up RFCOMM auth + encrypted device-info sanity run was performed after the stop, with no SportXms start/stop queued.

Artifact root:

```text
/tmp/miband9_mac_direct_quiet_rfcomm_20260601_150302/quiet_after_stop_rfcomm5
```

Redacted result:

```text
connected=true
auth_step3_queued=true
device_info_queued=true
sportxms_start_queued=false
sportxms_stop_queued=false
notification_count=7
8/53 packets=0
accel samples=0
gyro samples=0
```

Command counts:

```text
2/2: 1
2/42: 1
10/3: 1
17/7: 2
18/0: 1
```

This is the quiet-after evidence: after the stop, a fresh authenticated encrypted command pass did not observe continued SportXms `8/53` IMU packets.

## Acceptance status

Passed:

- macOS direct transport opened without Android.
- Xiaomi auth/session completed locally.
- SportXms start was queued/sent from macOS.
- SportXms stop was queued/sent from macOS.
- `8/53` packets were captured and decoded.
- Accel and gyro samples were both nonzero.
- Quiet-after check showed no continued `8/53` stream.

Caveat:

- This success used macOS classic RFCOMM channel 5, not the BLE FE95 CoreBluetooth path. That is still a valid Mac-direct path because no Android/phone transport was used, but the BLE-only auto-run gate should not be used as the sole reconnection condition after the band exposes macOS Serial Port.
