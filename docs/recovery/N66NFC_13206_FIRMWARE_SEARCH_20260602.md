# n66nfc 1.3.206 firmware package search

Date: 2026-06-02

Scope: locate an official Xiaomi Smart Band 9 NFC (`miwear.watch.n66nfc`) firmware package matching the currently installed `1.3.206` line. Search only; no OTA write, no Notify install, no firmware body transfer.

## Why this search matters

The current on-device firmware is `1.3.206`, while the locally available official full OTA package is `1.3.210`:

```text
/tmp/miband9_windows_firmware_20260601_2140/673e64214a0c42412771243b5f3a47bb_upd_miwear.watch.n66nfc.zip
ota.json sw_version = 1.3.210
```

A same-version `1.3.206` full package would reduce variables versus patching a cross-version `1.3.210` upgrade package.

## Windows1 check

Windows1 was initially asleep / unreachable on LAN and Tailnet. It was woken with the existing Wake-on-LAN helper:

```text
/path/to/local-user/bin/wake-windows1 --wait
```

A staged read-only PowerShell file search then checked likely user/download/project roots for firmware-like filenames:

- `C:\Users\user\Downloads`
- `C:\Users\user\Documents`
- `C:\Users\user\Desktop`
- `%LOCALAPPDATA%\Temp`
- `%APPDATA%`
- `D:\`
- `F:\`

High-signal hit:

```text
C:\Users\user\Downloads\673e64214a0c42412771243b5f3a47bb_upd_miwear.watch.n66nfc.zip
size: 43,934,358 bytes
lastWrite: 2026-01-10 01:46:01
```

This is the already-known `1.3.210` package. No `1.3.206` OTA ZIP/BIN package was found on Windows1 in this pass.

Notes:

- Everything CLI was not available/running (`es_candidates=[]`), so the search used scoped PowerShell traversal.
- Many unrelated `miband9-imu-collector` build artifacts were found under WeChat file storage, but not a `1.3.206` firmware package.

## Phone / Mi Fitness cache check

Searched public external storage and Mi Fitness private files for firmware-like ZIP/BIN/JSON names containing `n66`, `miwear`, `upd`, `firmware`, `ota`, `1.3.206`, `1.3.210`, or known hashes.

Only high-signal external file:

```text
/sdcard/Download/wearablelog/mi_band9_n66nfc_sportxms_latency_20000us_patch_on_copy.zip
```

This is the patched candidate previously uploaded for Notify/NFX parse testing, not an official `1.3.206` package.

Mi Fitness logs did include historical update-check evidence:

```text
readWatchInfo success firmwareVersion = 1.3.206
healthapp/device/latest_ver requested
```

Historical `getLatestVersion success` lines found stock update URLs for other/latest packages such as:

```text
0c3c4243588208edab25df7d1707d0e4_upd_miwear.watch.n66nfc.bin
10da5fc876134b4c523ab5e643a0e4f6_upd_miwear.watch.n66nfc.bin
```

Those signed/logged CDN URLs returned HTTP 403 when retried later, including with the logged query string. No usable `1.3.206` package URL was recovered from this log bundle.

Raw logs and signed query strings were not retained in the repo.

## Public web search

Queries run through local SearXNG / direct search engines included:

```text
"miwear.watch.n66nfc" "1.3.206"
"n66nfc" "1.3.206" firmware
"小米手环9 NFC" "1.3.206" 固件
"upd_miwear.watch.n66nfc"
"miwear.watch.n66nfc.zip"
"n66" "1.3.206" "ota.json"
site:bandbbs.cn n66nfc 1.3.206
site:bandbbs.cn 小米手环9 NFC 1.3.206 固件
"673e64214a0c42412771243b5f3a47bb"
"0c3c4243588208edab25df7d1707d0e4"
"10da5fc876134b4c523ab5e643a0e4f6"
```

Relevant public hit:

```text
https://habr.com/ru/articles/928370/
```

The Habr article contains Mi Band 9 / n66/n66nfc `1.3.206` watchface Lua memory-address mappings, e.g. `miwear.watch.n66nfc` + `1.3.206`, but it does **not** publish an OTA firmware ZIP/BIN package.

No public indexed `1.3.206` n66nfc OTA package was found in this pass.

BandBBS direct search attempts returned HTTP 502/403 from this environment; no direct BandBBS result was retrieved.

## CDN direct probes

Tried direct unsigned CDN paths for known firmware-like filenames:

```text
https://cdn.cnbj0.fds.api.mi-img.com/miio_fw/673e64214a0c42412771243b5f3a47bb_upd_miwear.watch.n66nfc.zip -> 404
https://cdn.cnbj0.fds.api.mi-img.com/miio_fw/0c3c4243588208edab25df7d1707d0e4_upd_miwear.watch.n66nfc.bin -> 403
https://cdn.cnbj0.fds.api.mi-img.com/miio_fw/10da5fc876134b4c523ab5e643a0e4f6_upd_miwear.watch.n66nfc.bin -> 403
```

Interpretation: these firmware CDN paths appear to require valid signed query parameters and/or headers. Direct hash-based URL guessing is not enough.

## Current status

`1.3.206` package acquisition is not solved yet.

- Windows1: no `1.3.206` package found; only known `1.3.210` package.
- Phone cache: no official `1.3.206` package found.
- Public indexed web: Habr confirms `1.3.206` model/version usage but no package.
- Direct CDN: known filenames are not publicly fetchable without valid signing.

## Next acquisition directions

1. Search BandBBS manually or through an authenticated/browser path, because direct HTTP search from this environment hit 502/403.
2. Use Mi Fitness authenticated `latest_ver` path only in a local-only/redacted workflow. Do not print service tokens, cookies, signed query strings, device IDs, or account identifiers.
3. Look for historical firmware URL/version caches in older Mi Fitness logs/backups beyond the current `wearablelog` bundle.
4. Search public mirrors / Telegram / Russian community terms around `miwear.watch.n66nfc`, `1.3.206`, and the Habr watchface ecosystem, but treat watchface memory maps as clues, not firmware packages.
