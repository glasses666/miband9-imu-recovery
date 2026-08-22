# macOS direct BLE probes for Mi Band 9

Experimental local-only CoreBluetooth probes and guarded write harnesses used while porting Xiaomi BLE V2/SAR auth/session to macOS.

These tools are intentionally conservative:

- `ble_scan.swift` scans BLE advertisements only.
- `ble_discover.swift` connects and discovers services/characteristics.
- `ble_read_probe.swift` reads readable characteristics and records full values only to the chosen local output file.
- `ble_notify_probe.swift` enables notify on FE95 `005E`/`005F`, listens without sending Xiaomi protocol payloads, and writes full notification hex to its local JSON output for later SAR reassembly. Keep that output local; do not paste raw chunks into chat.
- `ble_sar_write_probe.swift` is the first controlled-write harness: subscribe to FE95 notify chars, write exactly one caller-provided hex payload to a caller-chosen FE95 characteristic (default `005F`), then listen and save raw chunks locally. Use it only for session/auth gates, never SportXms start until auth/session is proven.
- `ble_sar_sequence_probe.swift` sends a local-only sequence of caller-provided auth/session frames in one connection.
- `ble_sar_auth_probe.swift` drives the first full Xiaomi auth ladder: session-config → PhoneNonce → auto-ACK WatchNonce → local-only auth step 3 build → auth final response capture.
- `build_auth_step3_from_events.py` is the local-only Python helper used by the auth probe to derive session material and build auth step 3 from live WatchNonce events and the backed-up authkey. It requires `cryptography` for AES-CCM. It can also prepare post-auth encrypted frames such as System/device-info sanity or SportXms start/stop, still local-only.
- `summarize_encrypted_sanity.py` emits a redacted encrypted-traffic summary from local auth artifacts: frame metadata plus decrypted protobuf type/subtype only, never raw keys/nonces/session/plaintext/ciphertext.
- `rfcomm_auth_probe.swift` uses macOS IOBluetooth RFCOMM channel 5 for the paired Band 9 Serial Port path when CoreBluetooth FE95 is not advertising/connectable. It reuses the same auth helper, ACK logic, post-auth SportXms frame queue, and local-only artifact policy. It records per-callback ISO and monotonic receive timestamps and accepts an optional SportXms start→stop delay for static/latency baselines.
- `summarize_sportxms_live.py` emits a redacted SportXms/IMU summary from local auth artifacts and decoded `8/53` payloads, never raw auth/session material.

The BLE probes do **not** send SportXms start/stop unless explicitly passed post-auth actions after the auth gate. Auth/session support is still split deliberately:

- Python pure-logic helpers can build/parse minimal auth frames and derive/encrypt session material.
- Swift live tooling can perform one controlled FE95 write when explicitly given a payload.
- No tool combines these into a SportXms start path until the auth gate below succeeds.

## Build examples

```bash
mkdir -p /tmp/miband9-mac-direct-bin
swiftc tools/mac_direct/ble_scan.swift -o /tmp/miband9-mac-direct-bin/ble_scan
swiftc tools/mac_direct/ble_discover.swift -o /tmp/miband9-mac-direct-bin/ble_discover
swiftc tools/mac_direct/ble_read_probe.swift -o /tmp/miband9-mac-direct-bin/ble_read_probe
swiftc tools/mac_direct/ble_notify_probe.swift -o /tmp/miband9-mac-direct-bin/ble_notify_probe
swiftc tools/mac_direct/ble_sar_write_probe.swift -o /tmp/miband9-mac-direct-bin/ble_sar_write_probe
swiftc tools/mac_direct/ble_sar_sequence_probe.swift -o /tmp/miband9-mac-direct-bin/ble_sar_sequence_probe
swiftc tools/mac_direct/ble_sar_auth_probe.swift -o /tmp/miband9-mac-direct-bin/ble_sar_auth_probe
swiftc -framework IOBluetooth tools/mac_direct/rfcomm_auth_probe.swift -o /tmp/miband9-mac-direct-bin/rfcomm_auth_probe
```

## Run examples

```bash
/tmp/miband9-mac-direct-bin/ble_scan 12
/tmp/miband9-mac-direct-bin/ble_discover 'Xiaomi Smart Band 9' 30
/tmp/miband9-mac-direct-bin/ble_read_probe 'Xiaomi Smart Band 9' 35
/tmp/miband9-mac-direct-bin/ble_notify_probe 'Xiaomi Smart Band 9' 8
```

Use a local artifact directory for raw outputs, for example:

```bash
OUT=/tmp/miband9_mac_direct_probe_$(date +%Y%m%d_%H%M%S)
mkdir -p "$OUT"
/tmp/miband9-mac-direct-bin/ble_notify_probe 'Xiaomi Smart Band 9' 8 > "$OUT/notify.json" 2> "$OUT/notify.stderr"
python3 tools/mac_direct/reassemble_notify.py "$OUT/notify.json" > "$OUT/notify_frames.summary.json"
```

## 2026-06-01 first-pass result

The first pass proved:

```text
macOS can see Xiaomi Smart Band 9 test-device
macOS can connect with CoreBluetooth
FE95 is discoverable
FE95/005E and FE95/005F support writeWithoutResponse + notify in this run
FE95/005E and FE95/005F notification state can be enabled without error
```

Raw local artifacts for that run:

```text
/path/to/local-user/.hermes/backups/miband9-mac-direct-preunbind-20260601_112515/mac_direct_probe_20260601_1225/
```

See also:

```text
docs/recovery/MAC_DIRECT_FEASIBILITY_PROBE_20260601.md
```

## Next implementation boundary

The next step is not to blast the 26-byte SportXms command at FE95 directly. The command must go through the Xiaomi app-layer session:

```text
BLE SAR / FE95
→ Xiaomi L0/L1 framing and fragmentation
→ A5 A5, CRC, seq/window, keepalive
→ encryptV2 session
→ PB channel 1, encrypted opcode 2
→ SportXms hns(8,26,812) payload
```

Until the auth gate succeeds, these probes should stay read/notify-only except for a single controlled session/auth write with `ble_sar_write_probe.swift`.

## Next live gate before any SportXms write

Allowed next live action: **one auth/session probe only**, not SportXms.

Evidence required to pass the gate:

1. `ble_sar_write_probe` writes exactly one session/auth entry payload to FE95 `005F` after `005E`/`005F` notify are enabled.
2. The local JSON output contains one or more FE95 notification chunks.
3. `reassemble_notify.py` reconstructs valid `A5 A5` frames with good CRC and no malformed tail.
4. The frame payload decodes to DATA channel/opcode carrying Xiaomi auth subtype `26` (`WatchNonce`).
5. Local-only authkey inventory shows one matching hex32 authkey for the known band address; the raw key is never printed.
6. `parse_watch_nonce_command(...)` extracts a 16-byte watch nonce and 32-byte HMAC.
7. `derive_session_material(...)` verifies the watch HMAC using the local-only authkey and phone nonce.

Abort on any failure above. Only after that should the next slice build auth step 2/3 and keepalive. SportXms start remains blocked until authenticated encrypted protobuf traffic is proven sane.

## 2026-06-01 auth + encrypted sanity results

Auth/session gate passed and is documented in:

```text
docs/recovery/MAC_DIRECT_AUTH_HANDSHAKE_20260601.md
```

The first encrypted traffic sanity pass is documented in:

```text
docs/recovery/MAC_DIRECT_ENCRYPTED_SANITY_20260601.md
```

Observed redacted evidence:

```text
auth_step3_queued=true
encrypted_sanity_queued=true
watch_hmac_verified=true
encrypted_protobuf_decoded_count=20
unique_frame_count=10
```

The sanity request did **not** send SportXms. It sent one encrypted System/device-info get and then proved post-auth encrypted protobuf traffic could be decrypted to well-formed command type/subtype metadata.

## 2026-06-01 macOS direct RFCOMM SportXms/IMU result

After the band stopped advertising over CoreBluetooth FE95 but remained paired/visible to macOS, SDP showed a classic Serial Port service on RFCOMM channel 5. The macOS direct IMU gate passed over that channel and is documented in:

```text
docs/recovery/MAC_DIRECT_RFCOMM_SPORTXMS_IMU_20260601.md
```

Redacted evidence:

```text
transport=macOS IOBluetooth RFCOMM channel 5
connected=true
watch_hmac_verified=true
sportxms_start_queued=true
sportxms_stop_queued=true
8/53 packets=129
accel samples=1290
gyro samples=1290
quiet-after 8/53 packets=0
```

This is Mac-direct IMU success without Android transport. The BLE FE95 route remains useful when the band advertises/connects over CoreBluetooth; the watcher must not treat BLE advertising as the only possible Mac-direct gate once RFCOMM Serial Port is available.

## 2026-06-01 static baseline timing/noise result

A still-pose static baseline is documented in:

```text
docs/recovery/MAC_DIRECT_STATIC_BASELINE_20260601.md
```

Redacted evidence:

```text
8/53 packets=266
unique 8/53 frames=236
accel samples=2660
gyro samples=2660
largest contiguous sample segment=2357 rows / 23.56s / 100Hz
unique 8/53 receive interval p50=99.99ms
unique 8/53 receive interval p95=125.29ms
quiet-after 8/53 packets=0
```

This measures link cadence/jitter and still-pose noise. It does not measure physical motion-to-Mac latency because no external tap/flick marker was introduced.
