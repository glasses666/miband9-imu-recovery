# Mi Band 9 macOS Direct Encrypted Traffic Sanity — 2026-06-01

## Scope

This was the first post-auth macOS direct encrypted protobuf sanity pass after the Band 9
visibly unlocked and the previous auth/session gate succeeded.

Allowed action:

1. reconnect/reuse `Xiaomi Smart Band 9` over CoreBluetooth/FE95;
2. run the already gated Xiaomi auth path again:
   - session-config;
   - PhoneNonce;
   - WatchNonce capture;
   - local HMAC verification;
   - auth step 3;
3. after final auth success, send one encrypted low-risk protobuf request:
   - Xiaomi System service `type=2`, `subtype=2` (`get device info`);
4. capture and decrypt inbound encrypted protobuf metadata into a redacted local summary.

Explicitly not allowed / not done:

- no SportXms start;
- no `hns(8,26,812)`;
- no IMU stream request;
- no raw authkey, nonce, session material, plaintext, ciphertext, or Android private data in git or chat.

## Live artifact

Local artifact directory:

```text
/tmp/miband9_mac_direct_encrypted_sanity_20260601_140043
```

Redacted summary:

```text
/tmp/miband9_mac_direct_encrypted_sanity_20260601_140043/encrypted_sanity.redacted.json
```

The raw live state and helper outputs in this directory are local-only and may contain
runtime auth/session material. Do not paste or commit them.

## Result

The encrypted sanity gate passed for the intended narrow claim:

- CoreBluetooth connected/reused the Band 9 connection.
- Auth step 3 was queued and sent.
- The post-auth encrypted sanity request was queued and sent:
  - write label: `encrypted_device_info_get`.
- Notifications were captured after the encrypted request.
- The redacted local summary could derive the session locally and decrypt inbound encrypted protobuf DATA frames.
- `watch_hmac_verified=true` in the redacted summary.

Observed redacted counts:

```text
connected=true
scan_found=true
auth_step3_queued=true
encrypted_sanity_queued=true
notification_count=25
frame_count=25
unique_frame_count=10
encrypted_protobuf_decoded_count=20
```

Decrypted inbound protobuf command type/subtype metadata observed after auth:

```text
2/42
18/0
17/7
17/7
10/3
```

These repeated because CoreBluetooth notifications surfaced duplicate/cumulative frame
values during the listen window. The important gate is that encrypted DATA frames were
well-formed and decryptable with the locally derived session material.

## Caveat

The one encrypted `get device info` request was sent, but the captured decrypted inbound
commands in this short window were unsolicited/post-auth watch-to-phone traffic rather
than an obvious `type=2/subtype=2` device-info response. That is still enough to clear
"encrypted channel decrypts real post-auth traffic"; it is not yet a full initialization
sequence or keepalive proof.

## Next gate

Next safe step is **keepalive / initialization sanity**, still not SportXms:

1. keep auth/session flow as-is;
2. send one minimal known post-auth command at a time;
3. capture ACK/DATA and decrypt redacted metadata;
4. only after stable encrypted roundtrip/keepalive should we unlock the SportXms gate.

SportXms remains locked until that next gate passes.
