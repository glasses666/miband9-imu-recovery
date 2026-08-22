# Mi Band 9 macOS direct SportXms variant matrix — 2026-06-01

## Summary

A bounded SportXms app/protocol-level variant matrix was run over the proven macOS direct RFCOMM channel 5 route.

Goal: test whether sourced SportXms protobuf variants can change the observed `8/53` batching behavior (`10` accel + `10` gyro samples per packet, ~100 ms packet cadence) before escalating to firmware research.

Result: **no tested app/protocol variant changed the batch size**.

All successful variants still produced:

```text
samples_per_packet_rows=10.0
accel sample count per 8/53 packet=10
gyro sample count per 8/53 packet=10
packet cadence p50≈99-100ms
```

This supports the working hypothesis that the `10 samples / packet` behavior is internal to the SportXms service/firmware-side batching path, not exposed through the sourced `hfa` SportXms fields tested here.

Raw auth keys, nonces, session material, encrypted frames, and full payloads remain local-only and are not included in this report.

## Harness changes

To run variants without hardcoding plaintext secrets or raw frames into git:

- `tools/miband9ctl/sportxms_812_packet_skeleton.py`
  - allows omitting `selectVersion` field 6.
- `tools/mac_direct/build_auth_step3_from_events.py`
  - accepts sourced SportXms variant args for post-auth start/stop frame construction:
    - `--sportxms-sport-type`
    - `--sportxms-select-version` (`omit` supported)
    - `--sportxms-accessory-wear-mode`
    - `--sportxms-timezone-value`
- `tools/mac_direct/rfcomm_auth_probe.swift`
  - can forward helper-only extra args to the local auth/post-auth frame builder.

A harness correction was also confirmed during this pass: RFCOMM auth step 1 must use DATA sequence `0`, matching earlier successful artifacts. A generated test payload using sequence `1` produced no WatchNonce response and was discarded before the matrix.

## Artifact root

```text
/tmp/miband9_sportxms_variant_matrix_20260601_192606
```

Redacted matrix summary:

```text
/tmp/miband9_sportxms_variant_matrix_20260601_192606/analysis_matrix.redacted.json
```

Final quiet-after artifact:

```text
/tmp/miband9_sportxms_variant_matrix_20260601_192606/final_quiet_after_matrix
```

## Matrix

Each variant used:

```text
auth -> encrypted SportXms start variant -> ~5s capture -> encrypted SportXms stop
```

Then a final delayed quiet-after pass used:

```text
auth -> encrypted device-info get only
```

| Variant | sportType | selectVersion | accessoryWearMode | 8/53 packets | sample rows | accel samples | gyro samples | rows/packet | 8/53 p50 ms | 8/53 p95 ms | accel counts | gyro counts |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| baseline_select3_812 | 812 | 3 | — | 52 | 520 | 520 | 520 | 10.0 | 99.97 | 121.33 | [10] | [10] |
| select2_812 | 812 | 2 | — | 53 | 530 | 530 | 530 | 10.0 | 98.72 | 122.39 | [10] | [10] |
| select4_812 | 812 | 4 | — | 53 | 530 | 530 | 530 | 10.0 | 100.04 | 124.15 | [10] | [10] |
| select_omit_812 | 812 | omitted | — | 53 | 530 | 530 | 530 | 10.0 | 99.99 | 125.14 | [10] | [10] |
| wear0_812 | 812 | 3 | 0 | 53 | 530 | 530 | 530 | 10.0 | 99.97 | 119.82 | [10] | [10] |
| wear3_812 | 812 | 3 | 3 | 53 | 530 | 530 | 530 | 10.0 | 99.95 | 107.19 | [10] | [10] |
| sport810_select3 | 810 | 3 | — | 52 | 520 | 520 | 520 | 10.0 | 100.15 | 112.89 | [10] | [10] |

Notes:

- Short-run p95 differences are not meaningful enough to call one variant lower latency. They are within short capture/jitter variance.
- The decisive field is stable across all rows: every decoded `8/53` packet still carried 10 accel and 10 gyro samples.
- Sport type `810` also produced the same `8/53` high-rate IMU shape under this route.

## Quiet-after

A delayed quiet-after run succeeded after the matrix:

```text
connected=true
auth_step3_queued=true
sportxms_start_queued=false
sportxms_stop_queued=false
8/53 packets=0
command_counts={2/2:1, 2/42:1, 10/3:1, 17/7:2, 18/0:1}
```

Immediate per-variant quiet attempts were too close to RFCOMM close and failed to reopen channel 5 (`rfcomm_open_failed_-536870212`). The final delayed quiet-after is the relevant stop-residue check and showed no continued SportXms stream.

## Interpretation

The sourced app/protocol candidates tested here do not expose a batch-size knob:

- `selectVersion` field 6:
  - `2`, `3`, `4`, and omitted all preserve 10 samples per packet.
- `accessoryWearMode` field 10:
  - `0` and `3` preserve 10 samples per packet.
- nearby `sportType=810`:
  - still produces 10 samples per packet when used through the same SportXms path.

Current best read:

```text
SportXms samples internally at 100Hz, then emits 10-sample accel + gyro batches as 8/53 packets.
```

The app-level `hfa` start fields tested here select session/mode metadata, not report interval.

## Next research direction

Do not jump straight to firmware patching yet. The next best target is the lower-level `HMProSensorDataProfile` path found in Mi Fitness decompile:

```text
x6v / n6v
config: {1, sensorMask, modeByte}
start:  {2}
stop:   {3}
GSENSOR=1
GYRO=16
TIME=128
accel+gyro mask=17
accel+gyro+time mask=145
```

That path may be a lower-level sensor profile separate from SportXms. It deserves static trace first:

1. Find official call sites for `x6v.o(...)` / `HMProSensorDataProfile`.
2. Determine whether mode byte controls callback/report behavior.
3. Identify transport/service path and whether it can be sent post-auth over the same RFCOMM channel.
4. Only then consider a live read/write probe.

Firmware static indexing becomes justified if both are true:

- `HMProSensorDataProfile` has no accessible call path or behaves the same; and
- all sourced SportXms variants keep the 10-sample batch.

This matrix satisfies the second condition for the tested SportXms fields, but not the first condition for the lower-level sensor profile.
