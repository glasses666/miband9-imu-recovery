# Mi Band 9 macOS direct auth handshake — 2026-06-01

Purpose: push the macOS direct path beyond BLE reachability into Xiaomi SPP/BLE V2 auth, while keeping SportXms locked.

## Live result

Mac-side CoreBluetooth completed the Xiaomi auth ladder over FE95 `005F` write / `005E`+`005F` notify:

```text
scan/connect target: Xiaomi Smart Band 9 test-device
notify: 005E=notifying, 005F=notifying
writes:
  1. session_config
  2. auth_step1_phone_nonce
  3. ack_rx_data_0
  4. auth_step3
  5. ack_rx_data_1
responses:
  SESSION_CONFIG response
  ACK for auth step 1
  DATA auth WatchNonce, subtype 26
  ACK for auth step 3
  DATA auth final response, subtype 27
```

The final DATA command parsed as:

```text
command_type=1
command_subtype=27
auth_fields=[33]
```

In Gadgetbridge's `XiaomiAuthService`, subtype `27` is the encrypted-auth success path and marks the session initialized.

## Secret-safe verification

No raw authkey, nonces, HMAC, or session material should be pasted into chat or committed.

Redacted local verification from the successful run:

```text
authkey_present=true
authkey_format=hex32
authkey_sha256_16=1a5f7ce274843af5
watch_hmac_verified=true
session_material_derived=true
```

Artifacts are local-only:

```text
/tmp/miband9_mac_direct_auth_step1_20260601_132645/
/tmp/miband9_mac_direct_full_auth_20260601_133347/
/tmp/miband9_after_auth_visibility_20260601_133832/
```

After auth, macOS System Profiler listed the band under `device_connected` with BLE service flags, while passive scan no longer saw the advertising name. Treat this as macOS connection established, not just advertisement visibility.

## New tooling

```text
tools/mac_direct/ble_sar_sequence_probe.swift
tools/mac_direct/ble_sar_auth_probe.swift
tools/mac_direct/build_auth_step3_from_events.py
```

`ble_sar_auth_probe.swift` is the first macOS live auth driver. It:

1. subscribes to FE95 notify chars;
2. sends session-config;
3. sends PhoneNonce auth step 1;
4. auto-ACKs inbound DATA frames;
5. calls the local Python helper to build auth step 3 from the live WatchNonce and local-only authkey;
6. sends auth step 3;
7. captures final auth response to local JSON.

The Python helper requires AES-CCM support from `cryptography`.

## Boundary

This proves macOS direct Xiaomi auth/session entry. It still does **not** prove:

- keepalive cadence;
- encrypted protobuf command sanity beyond auth;
- SportXms start/stop over macOS;
- `8/53` IMU stream over macOS.

Next safe gate: send one encrypted low-risk protobuf request or keepalive after auth, parse/decrypt the response, then and only then allow the 26-byte SportXms `hns(8,26,812)` payload.
