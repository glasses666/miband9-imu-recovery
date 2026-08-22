# N66 NFC OTA pre-DFU safe gate map: Mi Fitness + Notify/NFX

Date: 2026-06-04
Scope: local/static only. No updater was opened, no firmware ZIP was selected in an app, no Bluetooth bond/phone state was changed, no live OTA/device command was sent.

## Bottom line

Notify/NFX **does have a relevant firmware/update path**. It is not just watchface/RPK handling:

- `com.mc.xiaomi1` contains a custom firmware picker/update UI and a service path that accepts Vela/Xiaomi `FIRMWARE5_ZIP` host-side when the ZIP contains `ota.sh` or `ota.json`.
- Host-side labels such as `有效固件`, `新版本`, or `安装` prove only app parser admission. They do **not** prove that the band accepts the package, signature, or transition.
- The next safe Notify/NFX gate is **main connected/authenticated owner-session mapping before firmware selection**: confirm the app-owned connected device page/session predicates, then stop before the firmware picker/install button.

Mi Fitness remains the official no-body status lane:

- `DeviceSender.getOtaStatus(...)` / `hns.e=2 f=90` is status-only: no firmware path, md5, size, ZIP body, or OTA executor.
- `DeviceSender.prepareOta(...)` / `hns.e=2 f=5`, `startOta`, body/chunks, validate, upgrade, recovery, and factory-mode commands remain blocked.

## Guard/tool update

`tools/firmware/ota_preflight_guard.py` now exposes a source-specific gate map in JSON output:

- `mi_fitness/app_owned_connected_status_only` — no-body `f90` status lane; live use still requires explicit authorization.
- `dfu_v5_gatt/dfu_status_d1_only_if_1530_visible` — D1 status only after `1530/1531` are already visible; D2/D3/D5/D6 blocked.
- `notify_nfx/main_connected_owner_session` — safe next gate before firmware selection.
- `notify_nfx/pairing_key_auth_acquisition` — static-only mapping; raw key/DID/session material must remain redacted.
- `notify_nfx/firmware5_zip_host_admission` — host parser only; install broadcast blocked.

New local-safe mapping actions:

```text
map_app_session_states
map_mi_fitness_status_path
map_notify_owner_session
```

New blocked actions include:

```text
notify_firmware_selection
notify_install_broadcast
mi_fitness_prepare_ota
mi_fitness_start_ota
dfu_prepare_transfer
dfu_start_transfer
dfu_validate
dfu_upgrade
```

## Evidence: Notify/NFX main connected owner-session gate

Decompiled source under `/tmp/mihuan_community_app_audit_20260602_030607/jadx-com-mc/sources`:

- `com/mc/xiaomi1/ui/MainAppActivity.java:1961-1974` handles disconnected broadcast `531c5b6c-3915-4e61-a172-d7748ada773f`, sets `P=false`, then refreshes repair/UI state via `o1()`.
- `com/mc/xiaomi1/ui/MainAppActivity.java:1976-1982` handles connected broadcast `70bb932c-16ad-47f5-bb2d-6863fddaa60c`, shows `notification_status_watch_connected`, sets `P=true`, then calls `o1()`.
- `com/mc/xiaomi1/ui/MainAppActivity.java:1984-1986` also mirrors a boolean `connected` extra from `f35750d9-99fa-4dc5-8298-15784aebb6b4` into `P` and refreshes `o1()`.
- `com/mc/xiaomi1/ui/b.java:1226-1231` hides/shows `navigationRepairBand` based on `P`, which is a visible main-page predicate for connected owner-session state.
- `com/mc/xiaomi1/ui/b.java:1045-1102` routes connection helper `W0(...)` / `e(...)` through the app's `t1` connection layer before UI callbacks.

This is the safe Notify/NFX next gate: owner-session/main-device-page state. It stops before any firmware picker or install broadcast.

## Evidence: Notify/NFX pairing-key/auth acquisition is relevant but sensitive

- `com/mc/xiaomi1/ui/b.java:489-492` opens `AuthKeyActivity` from the connection-failure/auth-key dialog path.
- `je/b.java:431-442` shows the Mi Fitness folder picker dialog for `authkey_mifitness_folder`.
- `je/b.java:445-449` offers `authkey_mifitness_procedure` and `authkey_online_procedure` (freemyband source).
- `je/b.java:516-537` copies/imports the chosen source into app cache, matches the selected MAC, extracts a key-like value, and passes it to the app's key/profile helper.

Do not log or commit raw key/account/DID/session/wearablelog contents. This only explains how Notify/NFX can become the owner of an authenticated session.

## Evidence: Notify/NFX host firmware admission is not device acceptance

- `com/mc/xiaomi1/ui/updateFirmware/UpdateFirmwareActivity.java:726-730` is the hard install boundary: `buttonStartUpdate` sends broadcast `302ff3b3-953f-4a3c-8c3e-b8451f20fe53` with extras `firmwareFile`, `forceValidFirmware`, and `firmwareType`.
- `i6/l.java:86-88` recognizes `FIRMWARE5_ZIP` when the input is ZIP-like and `i(inputStream)` succeeds.
- `i6/l.java:145-171` scans ZIP entries, recognizes `ota.sh` / `ota.json`, and extracts `sw_version` from `ota.json`.
- `i6/l.java:140-143` returns firmware-valid for `FIRMWARE`, `FIRMWARE2`, `FIRMWARE3`, or `FIRMWARE5_ZIP`.

Therefore `有效固件 / 新版本 / 安装` is a host-side parser result only. It does not prove the band accepts patched firmware or that DFU V5 `1530` will appear safely.

## Evidence: Notify/NFX install crosses into app-owned preflight/body lane

- `e6/c.java:2442-2473` implements `F(Uri, boolean)`: opens the selected firmware URI, copies it into cache file `fwUpload`, then calls `p2(...)`.
- `e6/c.java:4219-4231` implements `p2(...)`: creates a request with `f36565q = 2`, `f36562c = 5`, fills firmware/preflight metadata, then sends through `B1(...)`.

That is equivalent in risk class to an OTA prepare/preflight lane. It is not no-body status. Do not cross it in this task slice.

## Mi Fitness no-body vs dangerous boundary

Repository evidence already captured in `docs/recovery/OTA_LIVE_DFU_STATUS_ATTEMPT_20260602.md:244-249`:

- `DeviceSender.getOtaStatus(...)` sends `hns.e=2 f=90` and carries no firmware path/md5/size/body/executor.
- `DeviceSender.prepareOta(...)` sends `hns.e=2 f=5` with firmware metadata.
- `DeviceSender.startOta(...)` constructs OTA executors and starts transfer.
- `BluetoothOtaManager.startUpgrade(...)` can call prepare/start and is not a no-body boundary.

Connected Mi Fitness f90 work later decoded `code=1` as Mi Fitness "not support" for the exact f90 path, while older disconnected runs returned `-6`. That is still status/query evidence, not package admission.

## Next safe action

1. Keep using `tools/firmware/ota_preflight_guard.py` for local policy checks.
2. For Notify/NFX, map only these pre-selection predicates:
   - `MainAppActivity.P=true` via connected broadcast;
   - visible main/device page with repair UI hidden;
   - app service/device object state that proves Notify owns the authenticated session.
3. Stop before:
   - firmware picker / local ZIP selection;
   - `buttonStartUpdate`;
   - broadcast `302ff3b3-953f-4a3c-8c3e-b8451f20fe53` with `firmwareFile`;
   - `F(Uri, boolean)` / `fwUpload` / `p2(type=2, subtype=5)`;
   - DFU D2/D3/D5/D6, body/chunks, validate, upgrade, recovery/factory.
4. For Mi Fitness, only a guarded no-body f90 status observation is in-scope after explicit authorization; `prepareOta f=5` and `startOta` remain blocked.
