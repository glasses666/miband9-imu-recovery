# Mi Band 9 macOS direct static baseline — 2026-06-01

## Summary

A static-position macOS direct capture was run over the already-proven RFCOMM channel 5 path.

Goal: measure link stability, packet cadence, receive jitter, and still-pose sensor noise. This is not a full physical event latency test because no external motion/impact marker was introduced.

## Live run

Artifact root:

```text
/tmp/miband9_static_rfcomm_20260601_154803/static_30s_rfcomm5
```

Transport:

```text
macOS IOBluetooth RFCOMM channel 5
```

Sequence:

```text
session_config
→ auth_step1_phone_nonce
→ WatchNonce/HMAC verify locally
→ auth_step3
→ encrypted_sportxms_start
→ ~30s static capture window
→ encrypted_sportxms_stop
→ redacted decode summary
```

Raw auth keys, nonces, session material, encrypted frames, and full payloads remain local-only.

## Redacted result

From local redacted summaries:

```text
connected=true
watch_hmac_verified=true
sportxms_start_queued=true
sportxms_stop_queued=true
8/53 packets=266
unique 8/53 frames=236
8/53 duplicate/retransmit frames=30
accel samples=2660
gyro samples=2660
largest contiguous sample segment=2357 rows / 23.56s / 100Hz
```

A follow-up quiet-after pass was run after stop:

```text
/tmp/miband9_static_quiet_rfcomm_20260601_155034/quiet_after_static_rfcomm5
```

Quiet-after result:

```text
connected=true
device_info_queued=true
8/53 packets=0
accel samples=0
gyro samples=0
```

## Timing / cadence

Sensor sample timestamps in the largest contiguous segment remain exactly 10 ms apart:

```text
sample interval=10ms
sample rate=100Hz
```

RFCOMM receive timing for unique `8/53` frames, using monotonic timestamps captured in the macOS RFCOMM callback:

```text
unique 8/53 interval count=235
p50=99.99ms
p90=120.79ms
p95=125.29ms
p99=192.27ms
max=210.45ms
mean=99.90ms
```

Interpretation:

- The SportXms stream is still 100Hz samples batched into about 100ms `8/53` packets.
- Mac receive cadence is centered at ~100ms per unique packet.
- The p95 jitter is about 125ms for unique packets in this static run.
- Total-frame timing included retransmits/duplicates and auth/stop gaps, so the unique `8/53` timing above is the more useful steady-stream metric.

## Still-pose noise floor

Using a stable middle segment of the static capture, robust approximate stats:

```text
accel_x mean=8.3882 stdev=0.0234 m/s²
accel_y mean=-2.9510 stdev=0.0249 m/s²
accel_z mean=-4.3441 stdev=0.0173 m/s²
accel_norm mean=9.8965 stdev=0.0228 m/s²

gyro_x mean=-0.00356 stdev=0.00108 rad/s
gyro_y mean=-0.00345 stdev=0.00174 rad/s
gyro_z mean=-0.00253 stdev=0.00095 rad/s
gyro_norm mean=0.00585 stdev=0.00134 rad/s
```

There were startup/transition outliers and retransmit duplicates outside the stable segment. They should be excluded for noise-floor calibration and latency claims.

## What this does and does not prove

Proves:

- Mac direct RFCOMM SportXms stream remains stable while the band is still.
- Static stream cadence is 100Hz sample rate with ~100ms packet cadence.
- Unique packet arrival cadence has p50 ~100ms and p95 ~125ms in this run.
- Stop/quiet-after check shows no continued `8/53` stream.

Does not prove:

- Physical motion-to-Mac end-to-end latency. That requires an explicit external marker such as a tap/impact, deliberate wrist flick, or controlled haptic marker.

Next latency gate:

```text
quiet → tap/flick marker → quiet
```

Record macOS RFCOMM callback monotonic time plus decoded sample ticks, then compute marker-to-arrival p50/p95.
