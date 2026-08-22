# Mi Band 9 macOS direct feasibility probe — 2026-06-01

Purpose: first low-risk macOS direct-connection feasibility pass after Android/Gadgetbridge-native SportXms start/stop was verified. This probe does **not** send SportXms start/stop and does **not** write Xiaomi protocol payloads. It only scans, connects, discovers GATT services/characteristics, reads readable characteristics, and enables notify on FE95 SAR candidates.

Local-only raw artifacts:

```text
/path/to/local-user/.hermes/backups/miband9-mac-direct-preunbind-20260601_112515/mac_direct_probe_20260601_1225/
```

Privacy/safety:
- Raw characteristic hex is kept in the local artifact folder only.
- Do not paste auth/session material or private app state into reports or chat.
- No owner reset, unbind action, SportXms start, or protocol write was performed in this probe.

## Environment

- Host: macOS 26.5, Apple N1 Bluetooth controller.
- Repo head before probe: `cbe98a25a Verify SportXms start-stop harness`.
- Android/GB/Mi Fitness app data backup already exists under:
  `/path/to/local-user/.hermes/backups/miband9-mac-direct-preunbind-20260601_112515/`

## Passive scan result

CoreBluetooth passive scan saw the target as:

```text
name: Xiaomi Smart Band 9 test-device
RSSI: about -26 to -28 dBm during probe
connectable: true
```

This is enough to proceed beyond “device invisible on macOS.”

## GATT service discovery result

macOS successfully connected to the band and discovered these services:

```text
FE95
  0050: read
  005E: writeWithoutResponse, notify
  005F: writeWithoutResponse, notify

FDAB
  0001: read
  0002: writeWithoutResponse, notify
  0003: writeWithoutResponse, notify

3802
  4A02: read, write, notify

CC353442-BE58-4EA2-876E-11D8D6976366
  C551C36A-0377-4A29-9657-74FFB655A188: read, write, notify

180A
  2A50: read

180F
  2A19: read, notify

180D
  2A37: notify
```

Key point: the Xiaomi FE95-family SAR candidates are visible from macOS. In this local run both `005E` and `005F` advertise `writeWithoutResponse + notify`; do not assume the one-way role solely from prior Android naming.

## Read probe result

Readable characteristics were read successfully. Chat/report only records lengths and short hashes:

```text
FE95/0050: len=3,  sha256_16=5c3fe0b568f94de2
FDAB/0001: len=1,  sha256_16=4bf5122f344554c5
3802/4A02: len=0,  sha256_16=e3b0c44298fc1c14
custom/C551...: len=0, sha256_16=e3b0c44298fc1c14
180A/2A50: len=7, sha256_16=847b68e04850722a
180F/2A19: len=1, sha256_16=18ac3e7343f01689
```

No read error or pairing/permission blocker occurred.

## Notify probe result

macOS enabled notification state on both FE95 SAR candidates without error:

```text
005E: notifying
005F: notifying
listen window: 8s
events observed without protocol write: 0
```

Zero events is expected because no Xiaomi session/protobuf payload or SportXms start was sent.

## Verdict

Mac direct is now past the first feasibility gate:

```text
macOS can see the Band 9
→ macOS can establish a BLE connection
→ macOS can discover FE95 SAR candidate characteristics
→ macOS can read basic/private-readable chars
→ macOS can enable notify on FE95/005E and FE95/005F
```

The remaining blocker is not basic macOS BLE reachability. The next real work is protocol/session implementation:

1. Map FE95 `005E/005F` roles by controlled Xiaomi-session traffic, not guessing.
2. Port enough Xiaomi BLE V2/SAR framing to macOS to send/receive L0/L1 safely.
3. Port or reuse Xiaomi auth/session material without printing secrets.
4. Reproduce encrypted PB channel `1`, opcode `2`, `A5 A5`/CRC/sequence/window/keepalive.
5. Only after session initialization, send the already-verified 26-byte SportXms `hns(8,26,812)` start through the proper encrypted channel.
6. Decode incoming `8/53` with the existing parser.

## Next suggested gate

Build a macOS BLE SAR skeleton that:

- connects to the CoreBluetooth peripheral by scanned identity/name;
- subscribes to FE95 `005E/005F`;
- implements packet capture/logging for notifications;
- does **not** send SportXms start yet;
- first sends only a minimal safe handshake/keepalive candidate after auth/session logic is understood from Gadgetbridge/Mi Fitness traces.

SPP/RFCOMM classic remains unproven from macOS in this pass. BLE FE95/SAR is the current strongest direct route because it is visible and connectable from CoreBluetooth.
