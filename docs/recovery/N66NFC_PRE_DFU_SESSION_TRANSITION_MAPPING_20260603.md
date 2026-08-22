# N66NFC pre-DFU / app-session transition mapping — 2026-06-03

## Scope

Continuation from the guarded Mi Fitness status-only run where `DeviceSender.getOtaStatus(...)` (`hns.e=2, f=90`) returned `errors=[-6]` with `dangerousCalls=[]`.

This pass is **static/passive mapping only**:

- no patched ZIP was opened in any app;
- no Notify/NFX firmware selection/install was performed;
- no live band connection was initiated for update-path work;
- no `prepareOta`, `startOta`, firmware body/chunks, `validate`, `upgrade`, recovery, or factory command was sent.

## Current corrected target

The next target is **pre-DFU session transition mapping**, not another naked GATT scan and not an OTA install.

We need to distinguish these states:

1. Android OS bond / ordinary GATT reachability.
2. App-layer authenticated/owned connection (`WearableDeviceModel.getIsDeviceConnected()` or Notify owner session).
3. Official/checkupdate status query (`hns.e=2, f=90`).
4. Device-side preflight/prepare boundary (`hns.e=2, f=5` or equivalent).
5. DFU V5 GATT profile visibility (`1530/1531/1532`) and DFU CPT commands.
6. Body transfer / validate / upgrade.

Only states 1–3 remain in the no-body domain. State 4 already includes firmware metadata. State 5 can be status-only only if DFU V5 is already visible. State 6 is blocked.

## Mi Fitness official app mapping

### Safe-ish status/query path

Decompiled source:

```text
/tmp/mifitness_latestver_20260602_172749/jadx/sources/com/mi/fitness/checkupdate/util/DeviceSender.java
```

`DeviceSender.getOtaStatus(...)`:

```text
hns.e = 2
hns.f = 90
DeviceContact.call(..., needResponse=true, callback=...)
```

This path carries no firmware path, no MD5, no size, no ZIP body, and creates no OTA executor. It is the path already called under Frida guards; it returned `-6` while the band was bonded but disconnected.

Adjacent non-body settings/status paths:

```text
getUpgradeSetting: hns.e=2, f=14, p8q.i.c=256
getHybridMode:     hns.e=2, f=14, p8q.i.c=4
```

These are not package admission results.

### Dangerous official metadata/transfer path

Same source, `DeviceSender.prepareOta(...)`:

```text
hns.e = 2
hns.f = 5
payload includes:
  force
  type
  firmwareVersion
  fileMd5
  fileSize
  changeLog
```

`DeviceSender.startOta(...)`:

```text
new HyOtaExecutor(...) or new GeneralOtaExecutor(...)
mOtaExecutor = executor
executor.start()
```

So the official install/upgrade button boundary is not no-body: it first sends `hns.e=2, f=5` metadata, then starts an OTA executor.

### Bluetooth upgrade ViewModel boundary

Decompiled source:

```text
/tmp/mifitness_latestver_20260602_172749/jadx/sources/com/mi/fitness/checkupdate/ui/bluetooth/BluetoothUpgradeViewModel.java
```

Relevant official flow:

```text
notifyInstall()
  -> CheckUpdateUtil.checkAndOpenBluetooth(...)
  -> DeviceSender.prepareOta(..., version, "", ...)

startGeneralOta(mode, file, listener)
  -> DeviceSender.prepareOta(..., version, md5, ...)
  -> if prepare reason == 0: startOta(mode, file, segmentLength, listener)
  -> DeviceSender.startOta(...)
```

This means merely entering the upgrade UI or opening Bluetooth is not the dangerous boundary; calling `prepareOta` is.

### DFU V5 profile/status details

Decompiled source:

```text
/tmp/mifitness_latestver_20260602_172749/jadx/sources/defpackage/pm.java
```

`NewDfuProfile` maps:

```text
service = v4v.C(5424) -> 00000000-1530-3512-2118-0009AF100700
CPT     = v4v.C(5425) -> 00000000-1531-3512-2118-0009AF100700
PKT     = v4v.C(5426) -> 00000000-1532-3512-2118-0009AF100700
```

Command mapping:

```text
D0 / -48: protocol-info query
D1 / -47: upgrade-status query
D2 / -46: prepare transfer; includes firmware type, size, CRC32, chunk size, mode
D3 / -45: start transfer
D4 / -44: transfer-continue response path
D5 / -43: validate
D6 / -42: upgrade
```

`pm.b(false)` / query status writes exactly:

```text
new byte[]{-47}  # 0xD1
```

and parses response into `UpgradeStatueResponse` / `UpgradeStatus`.

Important: our no-body GATT probe is still correctly stricter than the official code. It refuses to write `D1` unless service `1530` and CPT `1531` are actually discovered and notify is enabled. If `1530` is absent, write count remains `0`.

### FwCheck gate before upgrade

Decompiled source:

```text
/tmp/mifitness_latestver_20260602_172749/jadx/sources/defpackage/eb.java
/tmp/mifitness_latestver_20260602_172749/jadx/sources/defpackage/ne.java
```

Before allowing upgrade, `FwCheck` checks device state and, if DFU V5 feature `hasBase(0)` is present, calls the BLE device's DFU V5 status method:

```text
bleDevice.X3()
  -> if connected and NewDfuProfile.init() succeeds:
       k7.b(false)  # D1 status query
  -> otherwise returns UpgradeStatus.IDLE
```

This tells us why naked GATT absence is inconclusive:

- if service `1530` is not exposed, official code can simply fall back to `IDLE` in this check;
- DFU V5 visibility may be app-session/feature-state dependent, or it may appear only after `prepareOta` / update transition;
- without app-owned connected state, `getOtaStatus` can return `-6` before any meaningful device-side status exists.

## Notify/NFX mapping

Decompiled sources:

```text
/tmp/mihuan_community_app_audit_20260602_030607/jadx-com-mc/sources/com/mc/xiaomi1/ui/updateFirmware/UpdateFirmwareActivity.java
/tmp/mihuan_community_app_audit_20260602_030607/jadx-com-mc/sources/i6/l.java
/tmp/mihuan_community_app_audit_20260602_030607/jadx-com-mc/sources/com/mc/xiaomi1/bluetooth/BaseService.java
```

Host-side file admission:

```text
choose firmware file
  -> copy selected URI to getCacheDir()/firmware
  -> parser i6.l
  -> FIRMWARE5_ZIP if ZIP starts PK and contains ota.sh or ota.json
  -> h() true for FIRMWARE / FIRMWARE2 / FIRMWARE3 / FIRMWARE5_ZIP
  -> UI shows 有效固件 / 新版本 / enables 安装
```

Dangerous Notify boundary:

```text
buttonStartUpdate onClick
  -> broadcast action 302ff3b3-953f-4a3c-8c3e-b8451f20fe53
  -> extras: firmwareFile, forceValidFirmware, firmwareType
  -> BaseService receives
  -> for normal firmware: f20632b.J.F(uri, forceValidFirmware)
```

Prior decompile notes show the service path then opens/copies firmware and sends an upgrade-like preflight (`type=2/subtype=5`) before upload/chunks (`type=22/subtype=0`, `D1(104, chunkBytes, ...)`).

Therefore Notify/NFX `有效固件` remains only host-side parser success. Tapping `安装` is outside no-body scope.

## Interpretation of the latest `-6`

The guarded official status result:

```text
called only: DeviceSender.getOtaStatus / hns.e=2 f=90
status=null
errors=[-6]
dangerousCalls=[]
```

combined with contemporaneous Bluetooth evidence:

```text
Band bonded: Xiaomi Smart Band 9 test-device
ConnectionState: STATE_DISCONNECTED
scan: 0 Xiaomi devices
```

means:

```text
Mi Fitness / device channel did not have a real app-owned connected OTA/status session.
```

It does **not** mean:

- patched package accepted;
- patched package rejected;
- signature failed;
- DFU V5 is impossible;
- it is safe to tap install.

## Next safe gate

Recommended next work is still **owner-session mapping before firmware selection**:

1. Static/passive: find or hook the exact app-connected state predicates:
   - Mi Fitness: current `WearableDeviceModel`, `getIsDeviceConnected()`, `readWatchInfo()`, `DeviceContact.call` return/errors for `e=2/f=90`.
   - Notify/NFX: main connected device page / owner session, without entering firmware upgrade.
2. If live UI is authorized later, first reach app-connected main/device page only.
3. Under the same hard Frida blockers, retry only one of:
   - official `getOtaStatus` (`hns.e=2 f=90`), or
   - naked DFU `D1` status only if `1530/1531` is already visible.
4. Stop immediately on any request to call:
   - `prepareOta` / `hns.e=2 f=5`;
   - Notify install broadcast with `firmwareFile`;
   - DFU `D2/D3/D5/D6`;
   - body/chunks / validate / upgrade.

## 2026-06-03 Mi Fitness connected status-only rerun

After Queen Glasser reported that the phone-side Mi Fitness app was connected, the no-body status gate was rerun.

Scope remained unchanged:

- no upgrade page navigation;
- no ZIP/file selection;
- no `prepareOta` / `hns.e=2 f=5`;
- no `startOta`, OTA executor, body/chunks, `validate`, `upgrade`, recovery, or factory command.

Artifact root:

```text
/tmp/miband9_mihealth_f90_20260603_150152
```

Preflight evidence:

```text
foreground: com.mi.health/com.xiaomi.fitness.main.MainActivity
processes:  com.mi.health + com.mi.health:device
Bluetooth:  ON
band:       Xiaomi Smart Band 9 test-device bonded
UI text:    小米手环9 NFC版 / 已连接 / 电量100%，充电中
```

Guarded Frida blockers were installed before calling status:

```text
DeviceSender.prepareOta: BLOCKED
DeviceSender.startOta: BLOCKED
DeviceSender.notifyForceUpgrade: BLOCKED
BluetoothOtaManager.startUpgrade: BLOCKED
BluetoothOtaManager.prepareOta: BLOCKED
GeneralOtaExecutor.start: BLOCKED
HyOtaExecutor.start: BLOCKED
```

Called only:

```text
DeviceSender.getOtaStatus(...)
packet: hns.e=2 f=90
safety: no file/md5/size/path
```

Result in both main and device processes:

```text
instanceMode=INSTANCE
status=null
errors=["1"]
dangerousCalls=[]
```

Redacted logcat evidence showed the request now reached the app/device sync layer instead of immediately failing as disconnected:

```text
enqueue: call type = 2, id = 90
Device(... ) callback, type=101
dispatchMessage(... type = 101, data = 7)
DeviceDataHandler-handlePacket:type=101, packet type=2, packet id=90
Type(101) call error ..., code=1
```

The visible app state after the run was still the normal device page:

```text
小米手环9 NFC版
已连接
电量100%，充电中
```

Interpretation:

- This is progress over the previous `-6` disconnected/session error: the `f=90` request reached the device/contact response path.
- The response still did not yield a parsed OTA status object; it returned callback error code `1`.
- Because `dangerousCalls=[]` and no firmware metadata/body path was touched, this remains a safe no-body result.
- `code=1` is now the next research target: determine whether it means unsupported/current-idle/no-OTA-context/malformed handler, or whether the `b7q` response exists but is routed as an error by `DeviceContact`.

## 2026-06-03 `code=1` decoded

Static traceback through the Mi Fitness contact stack now pins down the meaning of the connected `f=90` result.

Evidence chain:

```text
DeviceSender.getOtaStatus:
  hns.e = 2
  hns.f = 90
  needResponse = true

ContactTaskQueue.dispatchMessage(type=101):
  parse response bytes as hns
  match response e/f against waiting request e/f
  callback code = response field #100 if present and non-zero, else 0

ContactCallTask.onResult:
  code == 0 -> onSyncSuccess(... SyncResult(code=0, packet))
  code != 0 -> onSyncError(... code), packet is dropped before DeviceSender callback

SyncResult helpers:
  isSuccess()    = code == 0
  isNotSupport() = code == 1
```

Line anchors from JADX:

```text
DeviceSender.java:355-361        getOtaStatus builds e=2/f=90
DeviceSender.java:137-153        success parses packet.E().o().f; error returns code only
ContactTaskQueue.java:108-110   log data length, so data=7 means 7 bytes
ContactTaskQueue.java:135-153   parse hns; field #100 -> callback code; still broadcasts packet
ContactCallTask.java:53-70      code!=0 goes to onSyncError without packet
ContactCallTask.java:114-117    packet existed at onReceiveResponse(code, packet)
SyncResult.java:79-84           code=1 is named not-support
hns.java:274-277, 564-566, 613-618  field #100 parse/write/accessor
b7q.java:198-254                OTA status payload b7q.e has int fields c/d
UpgradeStatus.java:11-20        status ints if success payload exists
```

The live log's `data = 7` is not status `7`; it is byte length. The shortest HNS response matching `e=2`, `f=90`, `field100=1` is exactly 7 bytes:

```text
08 02 10 5a a0 06 01
field #1 e      = 2
field #2 f      = 90
field #100 code = 1
len             = 7
```

Interpretation is now high-confidence:

- `code=1` is a **device/contact HNS response status** for the exact `e=2/f=90` request.
- Mi Fitness names contact `code=1` as **not support**.
- It is not a naked GATT-scan failure, not a timeout, not handler-routing failure, and not `Packet has not been handle` causing the error.
- A response packet exists at `ContactCallTask.onReceiveResponse(code, packet)`, but `ContactCallTask.onResult` drops that packet before `DeviceSender.C14391.onError`, so the high-level callback only sees `1`.
- A successful OTA-status response would instead be `hns.e=2/f=90` with field #100 absent/0 and payload `hns.E().o().f`, where `b7q.e.c` is the status int and `b7q.e.d` is an auxiliary int not used by the current checkupdate path.

Safe dynamic instrumentation result:

```text
active caller script:  tools/recovery/mihealth_f90_raw_guarded_v3.js
passive device script: tools/recovery/mihealth_f90_raw_passive_device_v4.js
artifact:              /tmp/miband9_mihealth_f90_raw_split_v4_20260603_153651
command note:          use frida -D [ANDROID_SERIAL_REDACTED], not bare -U, because two USB Frida targets were present.
```

Split-process run:

```text
com.mi.health:device passive observer:
  incoming type=101 candidate
  rawHex=08 02 10 5a a0 06 01
  dataLen=7
  f=90
  hasStatusField100=true
  statusField100=1
  hasN8q=false
  hasB7q=false
  hasB7qStatus=false

  ContactCallTask.onReceiveResponse:
  code=1
  f=90
  hasStatusField100=true
  statusField100=1
  hasN8q=false

com.mi.health active caller:
  calling DeviceSender.getOtaStatus only
  ota_status_error=1
  dangerousCalls=[]
```

An earlier active-caller attachment to `com.mi.health:device` crashed that device process after hooks were armed. That crash is an instrumentation pitfall, not a firmware result. Future raw-packet capture should keep the split roles above:

```text
com.mi.health:device  -> passive raw ContactTaskQueue.dispatchMessage observer only
com.mi.health         -> active getOtaStatus caller with blockers
```

Do not rerun the active caller/blocker script against `com.mi.health:device`.

## Current conclusion

The next boundary is not “scan harder.” It is:

```text
app-owned connected session -> status-only query -> device returns not-support for f90
```

and the first truly dangerous line remains:

```text
official: DeviceSender.prepareOta / hns.e=2 f=5
Notify:  buttonStartUpdate broadcast with firmwareFile -> BaseService -> J.F(...)
DFU V5:  D2 prepareTransfer or later
```

Keep the patched candidate `NOT_FOR_INSTALL` until a separately authorized runbook crosses one of those boundaries with explicit rollback limits.
