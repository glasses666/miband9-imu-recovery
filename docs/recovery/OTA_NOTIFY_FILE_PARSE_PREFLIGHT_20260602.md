# Notify/NFX local firmware file parse preflight

Date: 2026-06-02

Scope: passive / no-body preflight after Queen Glasser manually selected the patched ZIP in Notify/NFX. **Install was not tapped.** No firmware metadata/body/chunks, `prepareTransfer`, `startTransfer`, `validate`, `upgrade`, recovery, or factory command was sent by Hermes.

## Bottom line

Notify/NFX accepted the patched `20000us` ZIP at the **host-side file admission** layer and showed:

```text
有效固件
新版本: 1.3.210
安装
```

This is a useful green light for the app parser, but it is **not** proof that the band/recovery will accept the patched image or that the OTA is no-brick safe.

Recommended state after this gate: stop here; do not tap `安装` without a separate live-OTA authorization and rollback plan.

## Artifact paths

- UI/screenshot/logcat artifact: `/tmp/miband9_notify_file_parsed_20260602_132723`
  - screenshot: `/tmp/miband9_notify_file_parsed_20260602_132723/screen.png`
  - UI dump: `/tmp/miband9_notify_file_parsed_20260602_132723/window.xml`
  - filtered logcat: `/tmp/miband9_notify_file_parsed_20260602_132723/logcat_filtered.txt`
- Notify local-log inspection artifact: `/tmp/miband9_notify_log_inspection_20260602_133130`
  - raw app databases and raw migrated logs were removed after inspection; only redacted filtered summaries / file lists remain.
- Phone-staged ZIP: `/sdcard/Download/wearablelog/mi_band9_n66nfc_sportxms_latency_20000us_patch_on_copy.zip`
- Notify private cache copy after selection: `/data/data/com.mc.xiaomi1/cache/firmware`

## ZIP identity

Patched ZIP selected by Notify/NFX:

```text
local source: /tmp/miband9_patch_on_copy_20260602_022409/mi_band9_n66nfc_sportxms_latency_20000us_patch_on_copy.zip
phone path:   /sdcard/Download/wearablelog/mi_band9_n66nfc_sportxms_latency_20000us_patch_on_copy.zip
sha256:       36f5ed2a8af93b7d22a71aa1ce13c4003eba2321ce437e5f30a00dce0cb13262
ota.json:     magic_string=n66, sw_version=1.3.210, firmware_type=all
```

After manual file selection, Notify copied the ZIP into its private cache:

```text
/data/data/com.mc.xiaomi1/cache/firmware
sha256: 36f5ed2a8af93b7d22a71aa1ce13c4003eba2321ce437e5f30a00dce0cb13262
mtime:  2026-06-02 13:19
size:   43905667
```

This proves the app was parsing the intended `20000us` ZIP, not another file.

## UI evidence

`uiautomator` visible text after selection:

```text
升级固件
当前固件版本
设备信息
手环识别器: 7014 - Mi Band 9
固件: 1.3.206
错误、损坏或不正确的文件可能导致变砖
有效固件
新版本: 1.3.210
安装
```

Interpretation: the patched ZIP passed Notify/NFX local file classification and enabled the start/install button.

## Passive logcat evidence

Filtered logcat from the preflight window did **not** show Notify/NFX transfer triggers:

```text
prepareTransfer: absent
startTransfer:   absent
firmwareFile:    absent
buttonStartUpdate/startUpdate: absent
upgrade:         absent in Notify/NFX context
```

Some filter words appeared in unrelated contexts and were discounted:

- `validate`: Google/Chimera APK/classloader validation, not Notify firmware validation.
- `recovery`: Xiaomi Market/system `RecoverySystem.readRescueFile`, not band recovery.
- `chunk`: Xiaomi Market/system `Unknown chunk type`, not Notify firmware chunks.

Observed Activity flow was file selection / return to `UpdateFirmwareActivity`, not an update transfer.

## Static parser evidence

Relevant decompiled code: `/tmp/mihuan_community_app_audit_20260602_030607/jadx-com-mc/sources/com/mc/xiaomi1/ui/updateFirmware/UpdateFirmwareActivity.java` and `i6/l.java`.

Safe file-pick path:

```text
buttonChooseFirmwareFile click
  -> ACTION_GET_CONTENT requestCode=10037
  -> on returned URI / activity intent
  -> x1(uri, true)
  -> copy selected URI to getCacheDir()/firmware
  -> w1(false) background parser
```

Parser behavior in `i6.l`:

```text
- classify as FIRMWARE5_ZIP when first bytes are PK and ZIP contains ota.sh or ota.json
- if ota.json exists, parse JSON and read sw_version
- h() returns true for FIRMWARE / FIRMWARE2 / FIRMWARE3 / FIRMWARE5_ZIP
```

UI enable behavior:

```text
handler.post(new h(this.D.a()))
  -> buttonStartUpdate.setEnabled(true)
  -> textViewNewVersion = "新版本: " + sw_version
  -> E1("有效固件")
```

Actual dangerous boundary:

```text
buttonStartUpdate onClick -> k0.b()
  -> intent action 302ff3b3-953f-4a3c-8c3e-b8451f20fe53
  -> extras:
       firmwareFile = f29285c
       forceValidFirmware = f29286d
       firmwareType = D.c().d()
  -> broadcasts to the service/update path
```

Therefore, the observed state is still host-side parsing. Tapping `安装` is the first known transition into the update service path.

## Notify / log-file inspection

Filesystem inspection found:

- Current relevant Notify artifact:
  - `/data/data/com.mc.xiaomi1/cache/firmware` — the copied ZIP, current timestamp, SHA matches patched file.
- External staging dir:
  - `/sdcard/Download/wearablelog/mi_band9_n66nfc_sportxms_latency_20000us_patch_on_copy.zip`
  - `/sdcard/Download/wearablelog/1768062082368log.zip`
- Old migrated Mi Fitness logs in Notify cache / wearablelog zip:
  - `XiaomiFit.device.log`, `XiaomiFit.main.log`, `Transfer.device.log`, etc.
  - timestamps around `2026-01-11 00:21`, not current Notify parse logs.
  - redacted filtered lines show Mi Fitness `UPGRADE_IDLE`, current firmware `1.3.206`, official check-update metadata, and no current Notify install transfer.
- Current Crashlytics session files had no firmware/OTA/DFU/transfer hits in the filtered scan.
- The main Notify app database could not be schema-read cleanly (`database disk image is malformed` during sqlite inspection); raw DB copies were deleted and no DB contents were reported.

Conclusion: Notify/NFX did not expose a useful current validation log file for the selected ZIP. The strongest current evidence is the UI state, cache-file SHA, logcat absence of transfer triggers, and decompiled parser path.

## Risk verdict for "有效固件"

For an unmodified stock package, `有效固件` in Notify/NFX is usually a good sign that the app will let the install start.

For this patched package, `有效固件` means only:

```text
Notify local parser accepted the file shape/version and enabled install.
```

It does **not** prove:

- the device-side DFU prepare step accepts the file metadata;
- all body chunks transfer successfully;
- `validate` accepts the patched `vela_ap.bin`;
- hidden signature / boot verification accepts the image;
- failure happens before destructive writes;
- rollback to the current firmware is guaranteed.

Positive evidence:

- The package is same target line (`n66`, displayed as Mi Band 9 / 7014).
- Visible per-section md5 in `ota.json` was updated by the patch-on-copy workflow.
- ZIP test/local classifier passed earlier.
- Notify parser recognized it as `FIRMWARE5_ZIP`-like and displayed version `1.3.210`.

Residual risk:

- Notify's parser is shallow: PK ZIP + `ota.sh`/`ota.json` + `sw_version` is enough to show valid.
- Device/recovery validation remains unproven.
- Tapping `安装` leaves the no-body preflight domain and becomes a real OTA attempt.

## Recommended next action

Stay stopped at the valid-file screen or exit back out of the upgrade page. If a live OTA attempt is later authorized, use only the conservative `20000us` ZIP and prepare a separate runbook:

1. confirm exact file SHA on phone and in Notify cache;
2. keep phone charged / awake / foregrounded;
3. stop Mi Fitness from competing for the connection if needed;
4. start bounded logcat capture before tapping `安装`;
5. record every transition: prepare, progress, validate, upgrade, reboot;
6. after reboot, verify firmware version and rerun SportXms `8/53` packet cadence;
7. be ready to stop/report on any failed validation or abnormal reboot.

Until that stronger authorization exists: **do not tap `安装`.**
