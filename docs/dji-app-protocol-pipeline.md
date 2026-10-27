# DJI app protocol comparison pipeline

> **2026-10-25 update:** static decompilation is sufficient for classic DJI GO
> 3.1.8; a device, sign-in and runtime memscan are not prerequisites for that build.
> The human/runtime workflow below applies to packed builds. Use the [2026-10-25 P3 evidence audit](dji-go-p3-evidence-audit-2026-10-25.md)
> and `apk_provenance.py` to pin identity, version, hashes and signature before
> comparing trees. `pilot_dynamic` is classic GO 3.1.83, not enterprise Pilot.

Goal: decompile every known DJI Android app and diff their DUML command
implementations to find real protocol variations across apps/aircraft generations.
Built 2026-10-24, validated against the two apps already decompiled this session
(`dji.go.v4`, `dji.pilot`).

## What's automated vs what needs the operator

**Packed-app workflow (not a universal requirement)** - inspect the manifest and static DEX first. For builds whose relevant code is only available at runtime, the existing workflow is:
1. Acquire the APK (see `sources/README.md`'s manifest convention - download it
   yourself and add an entry; no download link is hardcoded anywhere in this
   pipeline).
2. Install it and launch it on a rooted device.
3. Click through DJI's first-run consent/sign-in flow by hand - this includes a
   CAPTCHA at sign-in for at least one app this session (`dji.pilot`), which cannot
   be scripted. Some apps may not even require sign-in for the parts we care about;
   check as you go.
4. Reach a state where the real (post-consent) app code is actually loaded - for
   `dji.pilot` this meant navigating to its main screen, not just launching it cold.
5. **Confirmed gotcha (2026-10-24):** the first `apk_memscan.py` pass against
   `dji.pilot` scanned too early and found nothing but the AppGuard packer itself,
   with zero real app code. A second pass minutes later, same process, no app
   interaction needed in between, recovered thousands of real classes - the
   packer's decrypted payload residency in memory is timing-sensitive. If a scan
   comes back empty or packer-only, just re-run it before concluding the technique
   doesn't work for that app.

**Automated** (scripts below, once the app is running on a connected device and past
its consent flow):

### 1. `scripts/re/apk_memscan.py` - recover real source from a packed app

```sh
python3 -I scripts/re/apk_memscan.py --device <serial> --package <pkg> \
    --out tmp/apk/<name>_dynamic --decompile
```

Passive `/proc/<pid>/mem` read via root `su` - no code injection, doesn't touch the
app's running state. Carves dex files by their header's declared `file_size` (pure
offset arithmetic, no checksum), then runs jadx with
`-Pdex-input.verify-checksum=no` - **this flag is not optional**: a live/torn memory
read fails the real dex checksum but still parses correctly once that check is
skipped. The original `apk_dynamic_unpack.py` documented this flag as intended but
never actually passed it to jadx - that gap is why this generalized script passes it
explicitly.

dji.pilot runs use `apk_memscan.py --package dji.pilot` (the former `pilot_memscan.py`
wrapper was removed; its output path is unchanged).

### 2. `scripts/re/extract_duml_classes.py` - decompiled source to a comparable table

```sh
python3 -I scripts/re/extract_duml_classes.py <decompiled_source_root>... \
    --out tmp/apk/duml_tables/<app>.json
```

Walks `dji/midware/data/model/*/Data*.java`, regex-extracts (not a real Java parser)
each class's cmdset/cmdid/sender/receiver (the packet builder's `m`/`n`/`f`/`h`
fields - confirmed stable-named across both apps decompiled so far) and its payload
field layout from `doPack()` (`System.arraycopy` calls, direct
`this._sendData[N] = ` assignments, and `new byte[]{...}` literal initializers - all
three are real jadx decompile-style variations for the *same* bytecode, confirmed
2026-10-24 by hand-checking `DataGimbalAbsAngleControl`/`DataCameraSetImageSize`
against their raw source; the script normalizes all three before matching).

Tags each record `V` (cmdset+cmdid+at least one field all matched cleanly) or `U`
(didn't match cleanly - raw `doPack()` body kept for a human to read). Multiple
source roots merge into one table (needed for `dji.pilot`, whose memscan recovered
code split across several carved dex files) - dedupe by class name, first occurrence
wins.

### 3. `scripts/re/compare_duml_apps.py` - find real divergences

```sh
python3 -I scripts/re/compare_duml_apps.py tmp/apk/duml_tables/<a>.json \
    tmp/apk/duml_tables/<b>.json [more.json ...]
```

Matches by class name, only compares records both apps extracted at `V` confidence
(a mismatch against a `U` record is extractor noise, not a finding), and reports
classes present in only one app, classes that fully agree, and classes that diverge
(different cmdset/cmdid/field offsets).

**Known limitation, confirmed real, not hypothetical:** extraction is regex-based
over decompiled Java, and jadx has more than the three decompile-style variations
already normalized (cast prefixes, local-array aliasing, array-literal
initializers). Validated 2026-10-24 comparing `dji.go.v4` vs `dji.pilot`: before any
normalization, only 2 classes "agreed" and 46 "diverged"; after normalizing casts
and local-array aliasing, 44 agreed and 56 diverged; after also normalizing
array-literal initializers, 155 agreed and 61 diverged. Every divergence
hand-checked so far (`DataGimbalControl`, `DataGimbalAbsAngleControl`,
`DataGimbalSpeedControl` - already confirmed identical in both apps earlier this
session by direct source reading) turned out to be decompile-style noise, not a
real protocol difference. **Treat `compare_duml_apps.py`'s "DIVERGE" output as a
worklist to hand-check, not as confirmed findings** - the prior, based on everything
checked so far, is that most remaining divergences are further decompile-style
variations this tool doesn't normalize yet, not real cross-app protocol
differences. Improve the normalizer as new patterns are found rather than trusting
raw diff output.

## Candidate app list for future runs

Confirmed this session:
- `dji.go.v4` - DJI GO 4 (newer consumer aircraft: Mavic series, Phantom 4 series,
  Spark, DJI FPV).
- `dji.pilot` - DJI GO (classic, for older aircraft incl. Phantom 3, Inspire 1) -
  this is the one GO4 itself identified as correct for the operator's Phantom 3
  Professional (see awto-dji#16).

Unverified, from public web research (2026-10-24) - confirm the real package name
before spending a memscan pass on either:
- **DJI Fly** (newest consumer app: Mini/Air/Mavic current lineup) - one unverified
  forum claim gives package `dji.go.v5`. Not confirmed against an actual Play Store
  listing or APK.
- **DJI Pilot 2** (enterprise, Matrice series, "customized... deployed with
  FlightHub") - no package name found. Note: the string `dji.pilot2.*` already
  appears as an *internal Java class namespace* inside `dji.go.v4` itself (e.g.
  `dji.pilot2.account.sign.DJIAccountSignActivity`) - this is DJI's internal
  codebase architecture name, not evidence of a separate installable "DJI Pilot 2"
  package by that exact name. Don't confuse the two.
