# Mi Band 9 HF IMU Recovery Artifacts

This repository is the clean recovery workspace. Large/private source artifacts stay outside git unless explicitly copied in later.

## External artifacts kept outside this repo

- Windows1 clues root: `<private-artifacts>/windows1-miband9-imu-clues-20260529`
- Recovered modified Gadgetbridge APK: `<private-artifacts>/windows1-miband9-imu-clues-20260529/apk/app-mainline-debug-windows1-20260109.apk`
  - sha256: `eb196dc801186f203820ceabc5e099da8086e8508b03ea263b5015ca252cf1ea`
- Full jadx decompile: `<private-artifacts>/windows1-miband9-imu-clues-20260529/apk/jadx-app-mainline-debug-20260109`
- Vela/RPK clue: `<private-artifacts>/windows1-miband9-imu-clues-20260529/Downloads/com.xiaomi.xms.wearable.demo.release.1.0.0.rpk`
- Windows auth/key log document: kept outside this repo; do not copy or print secrets.

## References copied into git

- `docs/recovery/path-reconstruction.md` — reconstructed historical route.
- `docs/recovery/references/apk-decompiled-critical/` — only the critical decompiled files needed to re-port the lost APK logic.
- `docs/recovery/references/win1-brain/` — selected non-secret old agent task/walkthrough/firmware notes.
- `tools/imu/` — PC-side ADB/logcat IMU tools recovered from Windows1 notes.
- `tools/firmware/` — firmware/ODR search and patch notes/scripts; dangerous until original firmware and rollback are recovered.

## Missing artifacts to keep searching for

- `vela_ap.bin`
- `system.bin`
- `miband9_imu_mod_208hz.zip`
- `btsnoop_hci.log`
- original buildable modified Gadgetbridge source tree
