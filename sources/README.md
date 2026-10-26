# sources/

Downloaded binaries used for RE, not committed (see `.gitignore`) - re-download or
re-extract per the entry below, don't ask for a copy.

## dji-fpga-images/

DJI FPGA firmware images (Lightbridge-generation `m1900`/`m2000`-`m2003` modules) gathered
for the FPGA config-flash writer gap (issue #18). Full manifest, source URLs, SHA-256s and
dead-end notes: `dji-fpga-images/PROVENANCE.md`.

## lightbridge-iq/

Public SDR IQ capture datasets of DJI (and other-vendor) drone RF links - GENESYS hovering-UAV
Lightbridge captures, Tampere/Zenodo DJI RC+video recordings, KU Leuven drone RF dataset -
gathered to actually feed `analyze_iq.py` (issue #71 / PR #62). ~54 GB total, three
datasets. Full manifest, source URLs, checksums and a caveat on which captures are actually
confirmed Lightbridge vs. other DJI link protocols: `lightbridge-iq/PROVENANCE.md`.

## apk/dji.pilot-3.1.83.apk

- **What**: `dji.pilot` (DJI's classic "DJI GO" app, for older aircraft incl. Phantom 3 -
  distinct from `dji.go.v4` "DJI GO 4", already analyzed in `docs/duml-protection.md` etc.)
- **Version**: versionName=3.1.83, versionCode=36020963, minSdk=16, targetSdk=26
- **How obtained**: 2026-10-24, live on operator's own aircraft - signed into DJI GO 4
  (`dji.go.v4` v4.3.64) with the RC connected over AOA; GO4's own "Current DJI Device:
  phantom3 professional / Use the DJI GO app for this DJI device" screen redirected to
  `https://service-adhoc.dji.com/download/app/android/be36a032-050d-4184-92cc-ac5aa1eb2eef`,
  which serves this APK. Installed as a genuinely separate package (`dji.pilot`), not an
  update to `dji.go.v4`.
- **Good copy check**: 187,813,358 bytes as downloaded; installed `base.apk` on device is
  187,813,358 bytes too (same, not re-compressed by install).
- **Why it matters**: GO4 itself decided this is the correct control app for this exact
  aircraft - not yet decompiled/analyzed. Candidate for the missing gimbal
  AngleControl/permission-gating logic (awto-dji#16).
