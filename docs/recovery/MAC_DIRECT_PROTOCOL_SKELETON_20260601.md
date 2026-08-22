# Mi Band 9 macOS direct protocol skeleton — 2026-06-01

Purpose: second macOS-direct step after proving CoreBluetooth can see/connect to the Band 9 and subscribe to FE95 `005E/005F`.

This checkpoint still does **not** send SportXms start/stop to the band. It lands the protocol skeleton needed before a controlled live write.

## Code landed

```text
tools/miband9ctl/miband9ctl/mac_direct_protocol.py
```

Provides tested pure-Python helpers for:

- Gadgetbridge-compatible Xiaomi SPP/BLE V2 `A5 A5` frame layout.
- Xiaomi CRC-16/ARC payload checksum from `XiaomiSppPacketV2`.
- Session-config start frame builder.
- DATA L2 payload builder: channel `1` / opcode `2` for encrypted protobuf-command payloads.
- SAR chunking and stream reassembly from BLE notification chunks.
- XiaomiAuthService session material derivation:
  - `computeAuthStep3Hmac(secretKey, phoneNonce, watchNonce)` shape;
  - `decryptionKey`, `encryptionKey`, `decryptionNonce`, `encryptionNonce` split.
- `encryptV2` / `decryptV2` equivalent:
  - AES/CTR/NoPadding;
  - key used as IV, matching Gadgetbridge's “I wish I was kidding” implementation.
- Minimal Xiaomi auth protobuf subset:
  - `build_phone_nonce_command(...)` for auth step 1 (`type=1`, `subtype=26`);
  - `parse_watch_nonce_command(...)` for extracting `WatchNonce` nonce/HMAC from the response payload.

Safety line: `build_data_frame_from_encrypted_payload(...)` only accepts already-encrypted payload bytes. It deliberately does not fake-encrypt or send plaintext SportXms `hns` bytes through opcode `2`.

## macOS capture tooling update

```text
tools/mac_direct/ble_notify_probe.swift
tools/mac_direct/ble_sar_write_probe.swift
tools/mac_direct/reassemble_notify.py
```

- `ble_notify_probe.swift` still only subscribes/listens by default; it does not write payloads.
- `ble_sar_write_probe.swift` subscribes to FE95 notify chars, writes exactly one caller-provided hex payload to a caller-selected FE95 characteristic, then listens and saves raw chunks locally. It is for auth/session gates only.
- `ble_notify_probe.swift` now keeps full notification chunk hex in the local JSON output for later SAR reassembly.
- `reassemble_notify.py` parses that local JSON and emits a redacted frame summary by default.

## Verification

Test command:

```bash
PYTHONPATH=tools/miband9ctl python3 -m unittest \
  tools/miband9ctl/tests/test_cli.py \
  tools/miband9ctl/tests/test_adb.py \
  tools/miband9ctl/tests/test_controller.py \
  tools/miband9ctl/tests/test_controller_net.py \
  tools/miband9ctl/tests/test_imu_static_calibration.py \
  tools/miband9ctl/tests/test_live_sportxms_web.py \
  tools/miband9ctl/tests/test_mac_direct_protocol.py -v
```

Result: earlier checkpoint was `Ran 46 tests ... OK`; after adding auth protobuf helpers the focused protocol test is `Ran 10 tests ... OK`.

Swift compile/live-safe smoke:

```text
compiled=5
ble_notify_probe: scanFound=true, connected=true
notifyState: 005E=notifying, 005F=notifying
event_count=0, frame_count=0, errors=[]
```

Live-safe smoke output path:

```text
/tmp/miband9_mac_direct_protocol_skeleton_verify_20260601_125149/
```

## Redacted auth-material inventory

The pre-unbind Android backup contains Gadgetbridge auth material for the known Band 9 address, without exposing the value here:

```text
package nodomain.freeyourgadget.gadgetbridge:
  address=AA:BB:CC:DD:EE:FF
  authkey_present=true
  authkey_format=hex32
  authkey_len=32
  authkey_sha256_16=1a5f7ce274843af5

package nodomain.freeyourgadget.gadgetbridge.hfimucli:
  address=AA:BB:CC:DD:EE:FF
  authkey_present=true
  authkey_format=hex32
  authkey_len=32
  authkey_sha256_16=1a5f7ce274843af5
```

Full redacted inventory:

```text
/path/to/local-user/.hermes/backups/miband9-mac-direct-preunbind-20260601_112515/mac_direct_probe_20260601_1225/auth_material_inventory_redacted.json
```

Do not print the raw authkey. If a local-only consumer needs it, read it from the backup/app prefs inside a 0700 local script or an env/file path that never enters chat/git.

## What is still missing before a live SportXms write

A safe live write needs all of these, in order:

1. **Handshake command encoding** above Xiaomi protobuf:
   - build `PhoneNonce` command (`type=1`, `subtype=26`) without requiring Android protobuf runtime; this is now covered by `build_phone_nonce_command(...)`.
2. **WatchNonce capture and parse** from FE95 SAR notifications:
   - subscribe to notify;
   - send only the session-config/auth step 1 candidate;
   - reassemble `A5 A5` frames;
   - parse channel/opcode/payload enough to identify auth subtype `26`; the minimal parser is now covered by `parse_watch_nonce_command(...)`.
3. **Session material derivation** using local-only secret key + phone/watch nonces:
   - derive keys/nonces;
   - verify watch HMAC before continuing;
   - never print key material.
4. **Auth step 2/3 command encoding and send**:
   - encrypted device info still uses AES-CCM from Gadgetbridge, not the V2 AES-CTR helper;
   - after auth response, mark session ready.
5. **Only then** encrypt the 26-byte SportXms `hns(8,26,812)` payload with `encryptV2`, wrap as DATA channel `1`, opcode `2`, chunk to FE95 SAR write, and watch for `8/53`.

## Current next gate

The next live gate should be **auth handshake only**, not SportXms start:

```text
connect macOS CoreBluetooth
→ subscribe FE95 005E/005F
→ send/receive enough to obtain WatchNonce
→ derive and verify session material locally
→ stop before SportXms start unless auth succeeds and the frame parser sees sane encrypted/protobuf traffic
```

Abort conditions:

- no notification after session-config/auth step 1;
- malformed `A5 A5` frames;
- authkey missing/mismatch;
- watch HMAC mismatch;
- unknown write/notify direction after a single controlled attempt;
- any macOS Bluetooth permission/pairing dialog needing Queen Glasser's manual decision.
