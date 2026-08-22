# Mi Band 9 SportXms/812 DeviceContact transport trace — 2026-05-31

Purpose: pin down what happens after Mi Fitness builds the SportXms `hns(8,26,812)` command, and define the smallest Gadgetbridge-native opener path without touching pairing or the working Mi Fitness bridge.

## Bottom line

The `hns` SportXms command is sent as Xiaomi wearable API type `101`:

```text
DeviceContact.call(did, hnsBytes, needResponse=true, timeout=15000)
→ DeviceContactEngineImpl.callTimeoutWithData(... type=101 ...)
→ ContactTaskQueue.enqueue(ContactCallTask)
→ IMiWearCoreClient.call(type=101, did, hnsBytes, needResponse, callback, timeout)
→ WearApiCall.call(...)
→ WearApiTask(type=101, data=hnsBytes)
→ TaskQueueV2.enqueue(...)
→ L2Packet(channel=PB/1, opCode=WRITE_ENC/2, payload=encryptDataV2(hnsBytes))
→ TransportV2 / TransportL1 DATA frame
→ TransportL0 fragments by MTU
→ BleChannel.send(...)
→ BLE service FE95 SAR write characteristic 0x005f, notify 0x005e
```

So the prior warning stands: the plaintext `hns` bytes are **not** raw BLE bytes. They are the payload placed into the encrypted PB/Protobuf channel.

Important correction from the successful live run: `type=101` is a transport route selector, not an extra protobuf envelope inside the payload. The Android opener failure was instead caused by a payload parity bug: `hfa.field2` timezone must be the `oe4` submessage (`12 02 08 20`), not a bare varint. The correct `vga.v()`-parity SportXms start payload is 26 bytes, not the earlier 24-byte approximation.

## Evidence chain

### DeviceContact binder layer

`DeviceContactEngineImpl.java`:

```java
call(did, packet, needResponse, callback)
  → callTimeoutWithData(did, 101, packet, needResponse, callback, 8000)

callTimeout(did, packet, needResponse, callback, timeout)
  → callTimeoutWithData(did, 101, packet, needResponse, callback, timeout)

callTimeoutWithData(... type, data ...)
  → callTaskQueues.get(did).enqueue(new ContactCallTask(... type, data ...))
```

`cgp.c(...)` uses `DeviceSyncManager.call(..., true, callback, 15000)`, so SportXms start uses type `101`, `needResponse=true`, timeout `15000`.

### Contact task queue

`ContactTaskQueue.java`:

```java
if (callTask.getType() == 101) {
    hns hnsVarB = ux5.b(callTask.getData());
    logi("enqueue: call type = " + hnsVarB.e + ", id = " + hnsVarB.f);
}
IMiWearCoreClient.INSTANCE.getInstance().call(
    callTask.getType(),
    callTask.getDid(),
    callTask.getData(),
    callTask.getNeedResponse(),
    callback(callTask),
    callTask.getTimeout()
);
```

The queue logs the `hns` type/id but sends the original serialized bytes unchanged.

### Wear API task

`WearApiCall.java`:

```java
WearApiTask task = new WearApiTask(mQueue, type, data, needResponse, callback, timeout, massId);
if (mConnected && mQueue != null) {
    mQueue.enqueue(task);
}
```

`WearApiTask.java` only stores the bytes/type/response flag and calls back on send/result; no extra command transformation happens there.

### TaskQueueV2 L2 wrapping

`TaskQueueV2.java`:

```java
byte channel = getChannel(apiTask);       // type 101 -> channel 1
boolean enc = needEncrypt(apiTask.type);  // type 101 -> true
byte opCode = getOpCode(enc);             // encrypted -> 2
byte[] data = apiTask.getData();
if (enc) data = wearApiCall.encryptDataV2(data);
L2Packet p = new L2Packet(channel, opCode, priority, data);
transport.sendPacket(p, callback);
```

Relevant mappings:

```text
type 100/101 -> channel 1 (PB / protobuf command)
type 101     -> encrypted
type 112     -> encrypted
encrypted    -> L2 opcode 2 (WRITE_ENC)
plain        -> L2 opcode 1 (WRITE)
channel 1    -> priority 2
```

`L2Packet.java` serializes as:

```text
byte channel
byte opCode
bytes payload
```

### L1 / L0 BLE frame

`TransportL1.sendPacket(L2Packet)` wraps the L2 bytes into a DATA packet. `L1Packet` uses:

```text
8-byte header, little-endian:
  int16 magic = -23131 signed (A5 A5 on wire)
  byte  type/frx nibble
  byte  seq
  uint16 dataLength
  int16 crc(payload)
bytes payload = L2(channel/opCode/encryptedPayload)
```

`TransportL0.performSendPacket(...)` splits the L1 bytes by `channel.getMTU()` and calls `channel.send(...)` for each chunk.

### BLE SAR characteristic

`BleTaskQueueV2.java` initializes:

```java
serviceUUID = yn4.f42563a;          // MI_WEAR_SERVICE_UUID, 0xFE95 family
writeCharacteristicUUID = yn4.n;   // MIWEAR_MI_SERVICE_BLE_UUID_SAR_WRITE, 0x005f family
notifyCharacteristicUUID = yn4.m;  // MIWEAR_MI_SERVICE_BLE_UUID_SAR_NOTIFY, 0x005e family
return new BleChannel(bleManager, serviceUUID, writeCharacteristicUUID, notifyCharacteristicUUID);
```

`BleChannel.java` then:

```java
open():  hasCharacteristic(serviceUUID, writeUUID), register notify callback
send():  bleManager.g(serviceUUID, writeUUID, data, callback)
notify:  bleManager.l(serviceUUID, notifyUUID, response)
```

## Gadgetbridge comparison

Gadgetbridge currently has two relevant Xiaomi transports:

1. **BLE XiaomiCharacteristic path**
   - `XiaomiBleSupport` uses FE95 command read/write/activity/data-upload chars (`0x51`, `0x52`, `0x53`, `0x55`).
   - It wraps `XiaomiProto.Command.toByteArray()` in Gadgetbridge's `XiaomiCharacteristic` single/chunk protocol.
   - This is not the same as Mi Fitness' `BleTaskQueueV2` SAR write/notify path (`0x5f`/`0x5e`).
   - Therefore, for BLE-native parity, Gadgetbridge still needs a V2 SAR BLE sender equivalent to Mi Fitness `BleTaskQueueV2` / `BleChannel`.

2. **SPP / RFCOMM V2 path**
   - `XiaomiSppProtocolV2` already implements the `A5 A5` preamble packet, CRC, DATA packets, channel `ProtobufCommand`, and encrypted opcode.
   - `XiaomiSppPacketV2.DataPacket` maps:
     - `Channel.ProtobufCommand` -> raw channel `1`
     - encrypted opcode -> `2`
     - payload encryption -> `authService.encryptV2(payload)`
   - This is the closest existing Gadgetbridge-native opener path for the `hns` payload, especially with the existing Mi Band 9 RFCOMM port-5 work.

## Minimal Gadgetbridge-native opener skeleton

The first PoC should not add a new UI. It should add a guarded debug/ADB action that:

1. Requires device state `INITIALIZED`.
2. Builds the SportXms start command bytes:
   - `type=8`
   - `subtype=26`
   - `field10/uca.field20/hfa` with current timestamp, timezone, sportType `812`, proto state `0`, selectVersion `3`.
3. Sends those bytes through the authenticated Xiaomi protobuf/PB channel.
4. Logs the returned ack/response and checks for first SportXms/IMU packets.
5. Has a paired finish/stop action before this becomes a repeatable test.

Local standalone byte builder added in this pass:

```text
tools/miband9ctl/gadgetbridge_port_skeleton/XiaomiSportXms812Command.java
```

It intentionally only emits the plaintext `hns` payload. The Android-side sender must still choose the correct Xiaomi transport.

### Preferred Android/Gadgetbridge send seam

Add a raw protobuf-channel seam instead of raw socket bytes:

```java
// XiaomiConnectionSupport.java
public void sendRawProtobufCommandBytes(String taskName, byte[] bytes, XiaomiCharacteristic.SendCallback cb) {
    throw new UnsupportedOperationException("not implemented for this transport");
}
```

```java
// XiaomiSppSupport.java -- closest path today
@Override
public void sendRawProtobufCommandBytes(String taskName, byte[] bytes, XiaomiCharacteristic.SendCallback cb) {
    TransactionBuilder builder = this.commsSupport.createTransactionBuilder("send " + taskName);
    builder.write(mProtocol.encodePacket(Channel.ProtobufCommand, bytes));
    builder.queue(this.commsSupport.getQueue());
    if (cb != null) cb.onSend();
}
```

For BLE, do **not** route this through current `XiaomiBleSupport.characteristicCommandWrite` and declare parity. Add or port a `BleTaskQueueV2`-style SAR channel first, or keep BLE as a later phase.

### Alternative if avoiding a new raw seam

Because the `hns` bytes are also a valid top-level protobuf with `field1=type`, `field2=subtype`, `field10=payload`, Gadgetbridge may be able to parse and preserve the unknown nested `Health` fields:

```java
XiaomiProto.Command cmd = XiaomiProto.Command.parseFrom(hnsBytes);
getSupport().sendCommand("sportxms 812 start", cmd);
```

This is worth a quick proof, but the safer skeleton is the raw protobuf-channel seam above, because it avoids any generated-protobuf unknown-field reserialization surprises.

## Live Gadgetbridge SPP opener attempt — 2026-05-31

Implemented the first guarded opener as an hfimucli command:

```text
miband9ctl band gb-sport-xms-open --capture-ms <ms>
```

App-side gate behavior:

```text
known device present + credential_present=true
if device_state != INITIALIZED: refuse with reason=device_not_initialized
if initialized: build SportXms/812 payload and send over Xiaomi SPP V2 Channel.ProtobufCommand
```

Live run evidence on the MI 9 SE:

```text
Mi Fitness initially active -> hfimucli connect stayed NOT_CONNECTED and opener refused to send
force-stop com.mi.health temporarily -> hfimucli reached INITIALIZED (state_ordinal=9)
first opener run: payload_built -> protobuf_send_requested -> opener_complete
second opener run: payload_built -> protobuf_send_requested -> opener_complete
payload_bytes=24
sample payload_hex=0808101A5212A2010F0896DEBDCD06102018AC0620003003
```

Observed limitation:

```text
No new SportXms/812 IMU stream or clear command response was observed during the 15s/5s capture windows.
```

Interpretation:

The guarded seam proves that Gadgetbridge can connect/authenticate and can queue the recovered `hns(8,26,812)` protobuf bytes over encrypted SPP V2 `Channel.ProtobufCommand`. It does **not** yet prove that this is enough to trigger the same SportXms mode as Mi Fitness. The likely missing piece is the official `DeviceContact.call`/wearable API `type=101` outer call semantics or a direction/transport mismatch: Gadgetbridge's normal protobuf command channel may not be equivalent to Mi Fitness's BLE SAR V2 wearable-call wrapper even when the inner `hns` command bytes are identical.

Mi Fitness was relaunched after the attempt; no pairing data was cleared.

## SPP RX probe instrumentation — follow-up

A second guarded pass adds observability without changing the send semantics:

```text
XiaomiSppSupport.onPacketReceived(...)
→ LocalBroadcast ACTION_DEBUG_SPP_PACKET
→ HfImuCliService gb-sport-xms-open capture window
→ log spp_packet samples and opener_complete summary
```

The opener now reports:

```text
spp_packets
protobuf_packets
activity_packets
other_spp_packets
first_spp_channel / first_spp_hex
last_spp_channel / last_spp_hex
spp_packet_samples[] in miband9ctl JSON
```

Verification:

```text
./gradlew assembleMainlineHfimucli  # BUILD SUCCESSFUL
./gradlew installMainlineHfimucli   # installed on MI 9 SE
```

Live status for the initial follow-up run:

```text
Known Band 9 device and credential were present.
Bluetooth was ON and the Band 9 bond was still present.
hfimucli connect did not reach INITIALIZED this run; it stayed NOT_CONNECTED.
gb-sport-xms-open refused to send with reason=device_not_initialized.
No 812 payload was sent in this follow-up run.
hfimucli was stopped afterwards and Mi Fitness was relaunched.
```

This preserves the important safety invariant: the new probe can only observe inbound SPP V2 packets during a guarded opener window, and the opener still refuses to send unless Gadgetbridge reports `INITIALIZED`.

## Time-fixed guarded live run — follow-up

A later run found the MI 9 SE test phone clock was stale even with Android `auto_time=1`:

```text
Mac/current time:     2026-05-31 21:39:13 +0800
Android before fix:  2026-03-10 11:08:21 +0800
Android after fix:   2026-05-31 21:39:13 +0800
```

After correcting only the test phone clock, with no pairing reset and no Bluetooth reset, the guarded live path was repeated:

```text
force-stop com.mi.health temporarily
→ start hfimucli service
→ connect Band 9
→ device_state=INITIALIZED, state_ordinal=9
→ wait 10s to drain initialization traffic
→ gb-sport-xms-open --capture-ms 20000
→ stop hfimucli
→ relaunch Mi Fitness
```

Result:

```text
payload_built
protobuf_send_requested
opener_complete
payload_bytes=24
payload_hex=0808101A5212A2010F08ABF4F0D006102018AC0620003003
spp_packets=0
protobuf_packets=0
activity_packets=0
other_spp_packets=0
```

The earlier observed 10 inbound `ProtobufCommand` packets during the immediate-after-connect window decode as normal Gadgetbridge/Xiaomi command traffic (`type=2`, `type=17`, `type=10`, etc.) rather than a SportXms response. With the 10s idle window and corrected timestamp, the band produced no response and no Activity/IMU stream. Therefore the stale Android clock was a real test hygiene bug, but not the root cause of the SportXms-native opener failure.

Current interpretation:

```text
Gadgetbridge SPP V2 Channel.ProtobufCommand is equivalent to Xiaomi channel=1/opcode=2/encryptV2 framing,
but sending the recovered hns bytes over that SPP path still does not trigger SportXms/812.
```

The next missing piece is likely one of:

```text
1. Mi Fitness BLE SAR V2 path has device-side semantics not mirrored by GB's SPP V2 path.
2. SportXms requires a preceding official service/state transition before DeviceContact.call(hns) is accepted.
3. The hns command is correct, but the response/trigger path is only visible through a BLE SAR or official-service callback route.
```

## BLE SAR V2 parity seam — static implementation

A third pass adds the smallest BLE-side seam needed for a controlled Mi Fitness SAR-path comparison. This is intentionally a **debug sender skeleton**, not an automatic live action.

Touched code:

```text
XiaomiUuids.java
→ FE95 UUID set now exposes optional SAR notify/write characteristics:
   0000005e-0000-1000-8000-00805f9b34fb  # notify
   0000005f-0000-1000-8000-00805f9b34fb  # write

XiaomiBleSupport.java
→ discovers optional SAR notify/write characteristics during initializeDevice
→ enables SAR notify when present
→ logs inbound SAR notify bytes with a bounded hex prefix
→ adds sendRawProtobufCommandBytes(...) for BLE transports
→ wraps raw protobuf bytes in XiaomiSppPacketV2 DataPacket:
   channel = ProtobufCommand / 1
   opcode  = encrypted channel opcode / 2
   payload = hns bytes
   encode(authService) => A5 A5 + L1/L2 + encryptV2 + CRC
→ fragments encoded bytes by current MTU-derived chunk size
→ writes chunks to SAR write 0x005f
```

Verification:

```text
./gradlew assembleMainlineHfimucli  # BUILD SUCCESSFUL
```

Safety status:

```text
No live BLE SAR send was triggered in this pass.
No pairing reset, Bluetooth reset, or Mi Fitness state change was performed.
The existing hfimucli opener still gates at app/device INITIALIZED before requesting any send.
```

Current limitation:

```text
This seam proves the code path can compile and queue a SAR V2 protobuf-channel packet when the FE95 0x005f/0x005e characteristics are present.
It has not yet proved that Mi Band 9 exposes those characteristics through the current Gadgetbridge BLE connection, nor that the SAR packet byte shape exactly matches Mi Fitness runtime traffic.
```

## Controlled live run: SAR seam not exercised because hfimucli selected SPP

Run artifact:

```text
/tmp/miband9_sar_live_retry_20260531_223309/
```

Preflight / safety:

```text
Android date: 2026-05-31 22:33 CST
Known device: Xiaomi Smart Band 9 test-device, address redacted in notes
Mi Fitness was force-stopped only to release the BLE/SPP link.
No pairing reset, Bluetooth reset, or data wipe was performed.
hfimucli was stopped afterwards and Mi Fitness was relaunched.
```

Result:

```text
connect: INITIALIZED, state_ordinal=9
gb-sport-xms-open: opener_complete
payload_bytes=24
spp_packets=0
protobuf_packets=0
activity_packets=0
```

Critical log finding:

```text
XiaomiSppSupport.sendRawProtobufCommandBytes(): sending 24 protobuf-channel bytes for task 'sport xms 812 opener'
```

Negative SAR evidence in the same filtered log window:

```text
Queued Xiaomi SAR V2 protobuf payload: not seen
Received Xiaomi SAR V2 notify bytes: not seen
SAR write/notify missing warning: not seen
```

Interpretation:

```text
The new BLE SAR seam compiled and installed, but this live opener did not exercise it.
The current hfimucli Band 9 connection selected the SPP/RFCOMM connection support, so XiaomiSupport dispatched onDebugSendRawProtobufCommand through XiaomiSppSupport instead of XiaomiBleSupport.
This means the failed/no-response opener is still evidence against the SPP protobuf-channel route, not evidence against the BLE SAR V2 route.
```

## Controlled live run: force BLE selected, but BLE path did not initialize

Run artifact:

```text
/tmp/miband9_force_ble_sar_20260531_230750/
```

Code/live gate changes in this pass:

```text
HfImuCliContract / cli.py
→ added --force-connection-type BLE|BT_CLASSIC|BOTH for band connect.

HfImuCliReceiver
→ forwards force_connection_type from the broadcast into HfImuCliService.

HfImuCliService
→ reads force_connection_type and sets a non-persistent debug override.

XiaomiSupport
→ non-persistent HF-IMU debug override can force createConnectionSpecificSupport() to BLE/BT_CLASSIC/BOTH.
```

Important correction:

```text
A prior attempt wrote pref_force_connection_type through device-specific prefs, but hfimucli still created XiaomiSppSupport.
That run did not prove BLE selection because the Service never received the force_connection_type extra.
The missing hop was HfImuCliReceiver -> HfImuCliService extra forwarding.
```

Verified force-BLE evidence:

```text
connect_started includes force_connection_type=BLE
XiaomiSupport: Using HF-IMU debug forced Xiaomi connection type BLE
```

Live result:

```text
connect_force_ble exit_code=1
final device_state=WAITING_FOR_RECONNECT
initialized=false
gb-sport-xms-open was not run
open_skipped_reason=device_not_initialized
```

Observed state loop under forced BLE:

```text
CONNECTING
→ NOT_CONNECTED
→ WAITING_FOR_RECONNECT
→ retry CONNECTING / NOT_CONNECTED / WAITING_FOR_RECONNECT
→ connect_timeout
```

Safety status:

```text
Mi Fitness was force-stopped only for the test window and relaunched afterward.
hfimucli was force-stopped afterward.
No pairing reset, Bluetooth reset, or data wipe was performed.
```

Interpretation:

```text
This pass finally proves the force-BLE gate itself works, but BLE-only Gadgetbridge did not reach INITIALIZED on this Band 9 in the current environment.
Therefore the guarded SportXms opener correctly did not send the 24-byte hns payload, and SAR 0x005f/0x005e was still not exercised.
This is now a BLE-INITIALIZED blocker, not an SPP-opener blocker.
```

## Controlled live run: band-side unbind/state-1 handoff

Run artifacts:

```text
/tmp/miband9_state1_gb_bind2_20260531_234530/
/tmp/miband9_connect_default_after_state1_20260531_235042.json
/tmp/miband9_open_after_state1_20260531_235058.json
/tmp/miband9_after_state1_logcat_20260531_235134.log
```

User action before the run:

```text
Band-side owner/mobile link was released into practical state 1: unbound/QR/waiting for app bind.
This was not a factory reset.
Mi Fitness was not relaunched during the Gadgetbridge takeover attempt.
```

Pairing result:

```text
First reset-bond pair attempt removed the stale phone bond, requested createBond, then hit a MIUI/Android pairing-confirmation failure and ended BOND_NONE.
A second pair attempt without reset-bond succeeded:
  pair_complete
  bond_state=BONDED
```

Gadgetbridge takeover result:

```text
Default Gadgetbridge/hfimucli connect after state-1 handoff succeeded:
  device_state=INITIALIZED
  state_ordinal=9
  initialized=true
```

Forced BLE result after the same handoff:

```text
connect --force-connection-type BLE still did not reach INITIALIZED.
The usable initialized route remains the default SPP/RFCOMM Xiaomi support path.
```

SportXms opener result after state-1 handoff:

```text
gb-sport-xms-open: opener_complete
payload_bytes=24
spp_packets=0
protobuf_packets=0
activity_packets=0
```

Route evidence:

```text
XiaomiSupport: Sending 24 recovered Mi Band 9 SportXms protobuf-channel debug bytes
XiaomiSppSupport.sendRawProtobufCommandBytes(): sending 24 protobuf-channel bytes for task 'sport xms 812 opener'
Queued Xiaomi SAR V2 protobuf payload: not seen
Received Xiaomi SAR V2 notify bytes: not seen
```

Interpretation:

```text
Queen Glasser's band-side unbind/state-1 hypothesis was correct for owner/session takeover: Gadgetbridge default connect can become INITIALIZED after the band releases the previous phone/app owner.
It does not by itself force the BLE SAR V2 path. The first tested SportXms opener still routed through SPP and remained silent.
This interim blocker was later resolved without adding a `type=101` inner envelope: the failure was a payload parity bug in the Android opener's timezone field. See the successful `vga.v` parity run below.
```

## Controlled live run: vga.v parity payload succeeds on initialized SPP route

Run artifact:

```text
/tmp/miband9_type101_parity_20260601_000928/
```

Code/protocol correction in this pass:

```text
`type=101` is not an inner protobuf envelope.
TaskQueueV2 uses type=101 to choose channel=1 and encrypted opcode=2.
The `hns` bytes themselves must match Mi Fitness `vga.v()` exactly.
```

The bug in the previous Android opener was the timezone field:

```text
Wrong 24-byte approximation:
  hfa.field2 = varint timezone

Correct Mi Fitness parity:
  hfa.field2 = oe4 submessage
  oe4.field1 = timezone
  hex fragment: 12 02 08 20
```

Corrected live payload example:

```text
payload_schema=devicecontact_hns_vga_v_parity
payload_bytes=26
payload_hex=0808101A5214A2011108E7C0F1D0061202082018AC0620003003
```

Live route and result:

```text
After reinstalling the counter build, hfimucli was reconnected on the default Gadgetbridge route.
connect_after_counter_install:
  message=initialized
  device_state=INITIALIZED
  initialized=true

gb-sport-xms-open --capture-ms 10000:
  message=opener_complete
  device_state=INITIALIZED
  send_requested=true
  payload_bytes=26
  spp_packets=105
  protobuf_packets=105
  activity_packets=0
  xms_response_8_26_packets=1
  xms_status_8_50_packets=9
  xms_sensor_8_53_packets=95
```

First response sample:

```text
channel=ProtobufCommand
payload_length=36
command_type=8
command_subtype=26
payload_hex=0808101A521EAA011B08001A1508AC0610E7C0F1D0061A02084028003001380240012802
```

First high-rate SportXms sample:

```text
channel=ProtobufCommand
payload_length=490
command_type=8
command_subtype=53
payload starts with 0808103552E3037AE0032A1608...
```

Interpretation:

```text
This is the first positive Gadgetbridge-native SportXms opener proof.
The handoff requires band-side state-1/unbound owner release plus Gadgetbridge default route INITIALIZED.
The correct 26-byte vga.v-parity hns payload sent over encrypted SPP V2 Channel.ProtobufCommand triggers an 8/26 response and sustained 8/53 SportXms data packets.
```

Current remaining work is no longer "start SportXms". The follow-up pass added the paired stop path and the first 8/53 decoder.

## Guarded stop/finish command — 2026-06-01

Mi Fitness finish/stop still uses `hns(type=8, subtype=26, uca.field20=hfa)`; only the `hfa.field4` value changes through `vga.x(...)`:

```text
SportRequestData.sportState=1 → hfa.field4=0  # start
SportRequestData.sportState=2 → hfa.field4=1
SportRequestData.sportState=3 → hfa.field4=2
other / finish path       → hfa.field4=3
```

hfimucli now exposes a paired guarded command:

```text
miband9ctl band gb-sport-xms-stop --capture-ms <ms>
```

It reuses the same 26-byte `vga.v()` parity builder, keeps the `INITIALIZED` safety gate, and sends `sport_state=4` / `proto_sport_state=3` over the existing encrypted SPP V2 `Channel.ProtobufCommand` path.

Live stop proof after reconnecting default Gadgetbridge/hfimucli to `INITIALIZED`:

```text
artifact=/tmp/miband9_stop812_live_20260601_011946/
connect: device_state=INITIALIZED, initialized=true
stop_live: message=stop_complete
payload_bytes=26
sport_state=4
proto_sport_state=3
send_requested=true
spp_packets=19
protobuf_packets=19
xms_response_8_26_packets=1
xms_sensor_8_53_packets=0
```

The stop command is therefore safe enough to run after opener tests before longer decoding sessions.

## First 8/53 decoder result — 2026-06-01

Added:

```text
tools/miband9ctl/decode_xms53_packets.py
```

Using the existing start artifact:

```text
/tmp/miband9_type101_parity_20260601_000928/open_counter_live.json
```

The decoder confirms the high-rate stream is a protobuf-nano packet:

```text
hns.field1 = 8
hns.field2 = 53
hns.field10 declared length = 483
uca.field15 declared length = 480
uca.field15 = fga
fga.field5 = repeated ee4 samples
```

Mi Fitness class mapping:

```text
uca.field15 -> fga
fga.field5 / field6 -> repeated ee4

ee4.field1 -> tick/timestamp varint
ee4.field2 -> float32 x
ee4.field3 -> float32 y
ee4.field4 -> float32 z
```

The current app logs truncate `payload_hex` to a 64-byte prefix, but even that prefix contains two complete `ee4` samples. The declared field length (`480`) implies about 20 samples per full `8/53` packet. First decoded sample from the start artifact:

```text
t=193187029500
x=-9.5426
y=0.1795
z=0.5271
```

Those values are accelerometer-scale float triples, so `8/53` is not just a status/ACK channel. Next decoder pass should log full payload hex/raw bytes and calibrate axes/sample cadence.

## Full-payload decoder/live harness checkpoint — 2026-06-01

Follow-up implementation removed the old SPP debug prefix ceiling and made the start/stop harness artifact-first:

```text
XiaomiSppSupport ACTION_DEBUG_SPP_PACKET
→ EXTRA_PAYLOAD_HEX now contains full payload bytes, not a 64-byte prefix

miband9ctl band gb-sport-xms-open --out-dir <dir>
miband9ctl band gb-sport-xms-stop --out-dir <dir>
→ writes result JSON, matching app log, all SPP packets JSONL, filtered 8/53 JSONL, manifest JSON
```

Live evidence:

```text
artifact=/tmp/miband9_fullpayload_live_20260601_030233/
connect before run: INITIALIZED, state_ordinal=9
open: opener_complete, packet_logs=102, xms53_payload_packets=92, payload_lengths=[490]
stop: stop_complete, xms53_payload_packets=0
```

2026-06-01 retag/harness correction: the original Android SPP packet debug lines were hardcoded as `command=gb-sport-xms-open`, so a stop capture could falsely look empty in the CLI manifest. The receiver now logs `spp_packet` rows under the active command name. A stop command issued while the stream is still running can contain one in-flight `8/53` before the stop response; use the bundled harness' `stop_verify` window as the quiescent post-stop proof.

```text
miband9ctl band gb-sport-xms-start-stop \
  --address <band> \
  --capture-ms 10000 \
  --stop-capture-ms 4000 \
  --verify-capture-ms 2500 \
  --stop-verify-settle-ms 750 \
  --sport-type 812 \
  --out-dir <artifact>

artifact=/tmp/miband9_start_stop_cli_20260601_070938/
open:        packet_logs=106, xms53_payload_packets=96, payload_lengths=[490]
stop:        packet_logs=2,   xms53_payload_packets=1   # in-flight pre/around stop response
stop_verify: packet_logs=1,   xms53_payload_packets=0   # post-stop quiet proof
decode: packets=96, sample_rows=960, accel=960, gyro=960, truncated_or_prefix_packets=0
```

Decoder evidence:

```text
python3 tools/miband9ctl/decode_xms53_packets.py \
  /tmp/miband9_fullpayload_live_20260601_030233/open/xms53_payloads.jsonl \
  --out-jsonl /tmp/miband9_fullpayload_live_20260601_030233/open/decoded_samples.jsonl \
  --out-csv /tmp/miband9_fullpayload_live_20260601_030233/open/decoded_samples.csv \
  --summary /tmp/miband9_fullpayload_live_20260601_030233/open/decode_summary.json

packets=92
decoded_packets=92
complete_payload_packets=92
truncated_or_prefix_packets=0
total_accel_samples=920
total_gyro_samples=920
sample_rows=920
```

Official Mi Fitness parser alignment is now concrete:

```text
hns.field10 -> uca.field15 -> fga
qg6.l(fga): fga.field5 -> WearSensorData.accel
qg6.l(fga): fga.field6 -> WearSensorData.gyro
ee4.field1 -> tick/timestamp; field2/3/4 -> float32 x/y/z
```

Safety/rollback notes:

```text
Known-good side-by-side hfimucli package/data was preserved before reinstall.
No band reset, bond reset, factory reset, or Mi Fitness owner takeover was performed.
The stop command was run after the capture and confirmed no 8/53 stream in the stop window.
```

## Next gate

Do not keep testing the old 24-byte payload or invent an extra `type=101` protobuf wrapper. The current real gates are:

```text
Gate A — calibration/motion validity:
→ use decoded JSONL/CSV rows as the input
→ verify sample cadence from per-sample ticks and wall-clock window
→ collect deliberate movement vs static baseline
→ map axes/sign/pitch-roll and gyro bias

Gate B — repeatable start/stop harness hardening:
→ keep `gb-sport-xms-open --out-dir` then `gb-sport-xms-stop --out-dir`
→ assert start has complete 8/53 accel+gyro rows and stop has 8/53 == 0
→ preserve manifests/summaries for each run

Gate C — transport portability / Mac-direct gap:
→ SPP through initialized Android/Gadgetbridge is the working native opener/capture route
→ pure Mac direct still requires porting Xiaomi auth/session + SPP/BLE framing and the 26-byte SportXms/812 command path
→ BLE SAR remains separate; do not overclaim it from the SPP success
```
