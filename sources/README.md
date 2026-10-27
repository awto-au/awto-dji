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

## lightbridge-ig800-firmware/

Firmware for the standalone retail DJI Lightbridge (hardware family `IG800`, not the
Phantom-3-integrated module) - decrypted ground-decoder UBL/U-Boot/kernel plus an
encrypted (password unknown) final-version update package, recovered from a 2016
phantompilots.com forum thread (DJI itself never published firmware for this product -
see manifest). Full provenance, SHA-256s, source URLs: `lightbridge-ig800-firmware/PROVENANCE.md`.
Background/analysis: `../docs/standalone-lightbridge-ig800.md`.

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
- **Why it matters**: GO4 itself selected classic GO for this exact aircraft.
  **Superseded:** the original "not yet decompiled/analyzed" status. Issue #16
  records a successful runtime rescan and gimbal comparisons. The earlier runtime
  input was not hash-pinned; this does not prove its bytes match a later download.
- **New official download verified 2026-10-25**: SHA-256
  `880b67803c60ea35b488882727936b4fa885f37b014aa9495411298224513109`,
  same manifest version/code/size. Signature passes Google apksig 8.7.3 (v1).
  Full result: `docs/data/dji-go-3.1.83-provenance.json`.

## apk/dji.pilot-3.1.8.apk

- **What**: original consumer DJI GO, package `dji.pilot`, label DJI GO.
- **Version**: 3.1.8 / 31018968, minSdk 16, targetSdk 17.
- **Why this version**: DJI's 2017-07-06 P3 Pro release notes pair it with
  firmware 1.11.20, the project's `P3X_FW_V01.11.0020` target.
- **Obtained 2026-10-25**: https://mobile.softpedia.com/apk/dji-go/3.1.8/ - select
  3.1.8 in its download dialog; follow the generated download-start link, then the
  manual APK link. Generated Softpedia links expire. APKMirror's release listing
  independently publishes the same size/hash. Its direct request returned 403 in
  this session; Softpedia supplied the actual bytes.
- **Size / SHA-256**: 101,595,742 /
  `f7a4eaaf0adf6bee86d1cd50c4a221824b17e97132807f0f4172f9b68b9f1965`.
- **Signature**: passes Google apksig 8.7.3 v1 verification, zero errors;
  certificate SHA-256 matches the current official 3.1.83 APK:
  `01a42c94aa87020f41e8c252598df98b86a0acf6c05ff61c75f18fa29cad1dd4`.
  Full metadata/warnings: `docs/data/dji-go-3.1.8-provenance.json`.
- **Analysis**: statically decompiled with jadx 1.5.3 into
  `tmp/apk/go_3.1.8/static/`; four on-disk DEX files, no device execution or sign-in.
  See `docs/dji-go-p3-evidence-audit-2026-10-25.md` for coverage and errors.
