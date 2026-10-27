# Phantom 3 Professional: DJI GO identity and APK evidence audit

Audit of main at `49ac404a08771f923603166a2ed85bee9d698934`, for
[#30](https://github.com/awto-au/awto-dji/issues/30) and
[#19](https://github.com/awto-au/awto-dji/issues/19). **V** means verified in the
specified artifact, **I** inference, **U** unresolved. Static app code establishes
what that build implements; it does not establish what the owned aircraft accepts.
No APK was installed or executed, and no hardware commands were sent in this audit.

## Identity: the issue's premise needs a correction

The original consumer **DJI GO** uses Android package **`dji.pilot`**. The package
name, internal `dji.pilot2.*` namespace and `pilot_dynamic` directory do not make it
the later enterprise DJI Pilot application. DJI's own [Phantom 3 Pro SDK tutorial](https://dji-dev.gitbooks.io/mobile-sdk-tutorials/content/en/Android/FPVDemo/FPVDemo_en.html)
links DJI GO to Google Play's `id=dji.pilot` (Viewing your Images section).
The [current DJI GO download page](https://www.dji.com/downloads/djiapp/dji-go-3)
lists Phantom 3 Professional and supplies Android 3.1.83. This is separate from
[DJI GO 4](https://www.dji.com/downloads/djiapp/dji-go-4) and the
[enterprise Pilot product](https://www.dji.com/downloads/djiapp/dji-pilot).

Classic GO had **already been obtained and partly analysed** before #30:

- `sources/README.md`, added in `898e59d`, records `dji.pilot` 3.1.83, code
  36020963, 187,813,358 bytes, obtained through GO 4's redirect for the owned P3 Pro.
- [Issue #16's identity report](https://github.com/awto-au/awto-dji/issues/16#issuecomment-6379899225)
  records that redirect. Its [successful rescan](https://github.com/awto-au/awto-dji/issues/16#issuecomment-6380412512)
  and [gimbal UI trace](https://github.com/awto-au/awto-dji/issues/16#issuecomment-6380975625)
  are completed work to preserve, not enterprise-app evidence to discard.
- `dji-app-protocol-pipeline.md` already correctly identifies this package as classic
  GO. The missing pieces were the firmware-era build, central provenance and a
  systematic correction of older GO 4 extrapolations.
- The earlier 3.1.83 runtime dump was not hash-pinned. Matching reported metadata
  does not prove that dump is byte-identical to this audit's newly downloaded APK.

## Choose 3.1.8 for firmware 1.11.20; retain 3.1.83 as a current comparison

DJI's [release notes dated 2017-07-06](https://dl.djicdn.com/downloads/phantom_3/20170706/Phantom+3+Professional+Release+Notes.pdf),
page 1, pair P3 Pro firmware **1.11.20** with **Android DJI GO 3.1.8** (iOS 3.1.13).
They specify Android 3.1.6 or later for the stated flight-limit condition. Thus 3.1.8
is an evidence-based contemporary analysis target, not a claim that it is the only
compatible version or a recommendation to install an old build.

| Artifact, acquired 2026-10-25 | Manifest identity | Size | SHA-256 |
|---|---|---|---|
| `sources/apk/dji.pilot-3.1.8.apk` | DJI GO, `dji.pilot`, 3.1.8 / 31018968, min 16 / target 17 | 101,595,742 | `f7a4eaaf0adf6bee86d1cd50c4a221824b17e97132807f0f4172f9b68b9f1965` |
| `sources/apk/dji.pilot-3.1.83.apk` | DJI GO, `dji.pilot`, 3.1.83 / 36020963, min 16 / target 26 | 187,813,358 | `880b67803c60ea35b488882727936b4fa885f37b014aa9495411298224513109` |

3.1.8 was obtained from [Softpedia's historical release](https://mobile.softpedia.com/apk/dji-go/3.1.8/)
using its version-specific download selector. Its bytes match the SHA-256 and size
published by [APKMirror](https://www.apkmirror.com/apk/dji-technology-co-ltd/dji-go/dji-go-3-1-8-release/dji-go-3-1-8-android-apk-download/).
The archive is an acquisition source, not authority for protocol conclusions.
3.1.83 came from DJI's [official service page](https://service-adhoc.dji.com/download/app/android/be36a032-050d-4184-92cc-ac5aa1eb2eef),
linked from its GO download page; the page resolved to DJI's `terra-2-g.djicdn.com`
GO3 `251028-11-20963_go3_official_sec.apk`. Temporary signed CDN query strings are
not stable provenance links.

**Both APKs pass Google's apksig 8.7.3 signature verification** (v1, no v2), with
zero errors and the same signer-certificate SHA-256:
`01a42c94aa87020f41e8c252598df98b86a0acf6c05ff61c75f18fa29cad1dd4`.
This anchors the archived build to the current official DJI signer, beyond matching
a filename or trusting an archive's label. apksig warns about unsigned `META-INF`
metadata entries; full warning lists are retained in the JSON records. Signature
verification is not an assertion that all ZIP metadata is signed.

Machine-readable results: [3.1.8 provenance](data/dji-go-3.1.8-provenance.json) and
[3.1.83 provenance](data/dji-go-3.1.83-provenance.json). No APK or decompiled code is committed.

## Firmware upgrade reassessment

**Superseded:** treating failure to find a P3 push path in GO 4 as a capability
finding about the P3 Pro, or proposing another GO 4 version as the decisive check.
Also superseded as a cross-version assertion: the legacy per-module sender has
no callers. Classic GO 3.1.8 has real callers of that sender.

**Documented update method (V, vendor documentation):** DJI's
[Firmware Update Guide v1.4](https://dl.djicdn.com/downloads/phantom_3/User%20Manual/Firmware_Update_Guide_en_v1.4_.pdf)
separates P3 Pro/Advanced aircraft and battery updates using a microSD card from RC
updates through GO (P3 RC firmware 1.3.20 or later). Printed page 10's FAQ says
aircraft/battery updating through GO was unsupported at that guide's date. This is
a dated vendor statement, not proof of every later build's capabilities.

**3.1.8 implementation (V, bounded trace):** the normal upgrade UI's connected-product
gate uses `isFromWifi()` or LonganMobile (`pilot2/upgrade/b.java:351-363`);
`ProductType.litchiX` is P3 Professional with its Wi-Fi flag false
(`midware/data/config/P3/ProductType.java:9-14,40-57`). The generic `p3cupgrade`
manager has live callers, and `b.java:833-865,924-968` can instantiate a per-module
DUML sender or FTP task according to the selected upgrade group. That is real
firmware-push machinery, but **a traced normal P3 Pro aircraft-push path has not
been established**. Product upgrade-group configuration is loaded from an encrypted
resource via native code (`publics/control/upgrade/a.java:35-57`); its contents and
every factory/rollback path were not resolved here. Do not infer global impossibility
from the normal UI gate, or infer P3 Pro support merely from generic machinery.

The RC sender remains separate. In 3.1.8 `pilot/publics/control/rc/c.java` implements
the RequestUpgrade / GetDeviceStatus / RequestReceiveData / TranslateData /
TranslateComplete / RestartDevice sequence. It retains FPGA_G's 130,000 ms wait
and two-byte sum in the completion field (`:40,97-100,314-325,383-404`).
`pilot/upgrade/b.java:395-403` maps litchiX to a P3x RC component. These are app-code
facts; the firmware-side interpretation remains independently sourced.

Camera confirmation also exists: `pilot/publics/objects/DJIBaseActivity.java:340-366`
answers the camera's Ack upgrade step with ControlUpgrade Start, and `:489` sends
Restart after success. Confirming an on-camera update is not transferring the package.
Together with the independently documented camera UEG engine, this is consistent
with the SD-card method. The air FPGA's image-byte route remains U.

### Selected wire implementation comparison

Paths below are relative to `tmp/apk/go_3.1.8/static/sources/dji/` (**G318**).
The GO 4 column cites the existing hash-pinned 4.3.64 report in
`app-upgrade-sequence.md`; its runtime tree is not present in this new checkout, so
this is a comparison with that report, not a fresh decompilation of GO 4.

| Claim | G318 locator and result | Disposition versus GO 4 report |
|---|---|---|
| COMMON IDs 01,07,08,09,0A,0B,0C,40-43 | `midware/data/config/P3/q.java:129-155` | Same selected names and IDs; preserve |
| RequestUpgrade | `DataCommonRequestUpgrade.java`, doPack/start | Same 9-byte request; file-method parser only has bits 0-2, not GO 4's extra copy-data bit 3 |
| RequestReceiveData | `DataCommonRequestReceiveData.java:58-92` | Same 13-byte request and 300-byte fallback; default timeout/retries **10000/1**, versus reported GO 4 **15000/2** |
| TranslateData | `DataCommonTranslateData.java`, doPack/start | Same 7-byte prefix, sequence u32 at 1, size u16 at 5, data at 7; ACK and unACK variants exist |
| TranslateComplete | `DataCommonTranslateComplete.java:49-52` | 1 + supplied digest length, rather than an unconditional fixed 17 bytes; 16-byte input produces 17 |
| RestartDevice | `DataCommonRestartDevice.java:61-87` | Same 14-byte layout; **setReceiveIdForce** is present in G318; ordinary setReceiveId is ignored by start unless forced |
| GetDeviceStatus | `DataCommonGetDeviceStatus.java:50-57` | Same one-byte request / mode getter at receive index 1; parsing-index caveat retained |
| Newer TransferFile / GetSerialNum surfaces | G318 COMMON enum; searches of model sources | No `TransferFile(42)` enum or `DataCommonTransferFile*` / `DataCommonGetDeviceSerialNumber` class found in this static tree; do not carry these GO 4-specific APIs over as P3 Pro firmware support |
| Legacy per-module sender callers | `pilot/publics/control/p3cupgrade/b.java:833-865`; UI callers in `pilot2/upgrade/b.java:227-242` | **Changed:** sender is wired in G318. Product/path qualification still required |

Model paths in the table are under `midware/data/model/P3/` unless otherwise stated.
None of these rows authorizes executing the speculative flashing recipes in the old report.

## Other P3-specific assertions: disposition ledger

This covers the APK-derived claim families in the affected docs and their downstream
references. A source-code namespace named P3 is shared across products and is not
a compatibility matrix. Neither a positive class-name search nor a negative search
establishes an endpoint's behaviour.

| Area / original source | Audit disposition | Evidence / remaining limit |
|---|---|---|
| GO 4 supports P3 Pro (`apk-analysis` §1) | **Superseded** | Existing #16 observed GO 4 rejecting it and redirecting to classic GO; current DJI product listing agrees |
| P3 Pro's primary link is Wi-Fi (#30) | **Corrected** | P3 Pro uses Lightbridge to RC, USB/AOA to phone; G318 ProductType distinguishes litchiX from Wi-Fi litchiC/P34K. Direct bird Wi-Fi control remains unestablished |
| AOA envelope and video (`apk-analysis` §§1,4,7) | **Reconfirmed in G318; preserve capture evidence** | `midware/usb/P3/UsbAccessoryService.java:115-176`: 55 CC, six-byte secondary header, type 22345 DUML / 22346 video. Old no-demux-header statement superseded; firmware/capture proofs in `ground-fx3-m1601.md` stand |
| All 723 GO 4 commands are P3 commands (`gap-report`, catalogs) | **Superseded interpretation; retain dataset** | Catalogue remains GO 4-specific inventory. No blanket P3 support claim; P3 namespace and vision command presence do not prove a P3 feature |
| Joystick 0x8E versus public 0x29 (`gap-report`) | **Reconfirmed ID, semantics U** | G318 `q.java:634,693`: FunctionControl 42 / JoyStick 142. Difference is not explained away by selecting classic GO; no claim that P3 accepts 0x8E for manual flight |
| Flight/activation sequence inferred from names (`gap-report`, `apk-analysis` §6) | **Downgraded to cross-product hypothesis** | Names alone do not prove order, authority, server dependence or P3 execution; no flight or activation replay performed |
| Gimbal UI / speed command (`known-telemetry`, #16) | **Reconfirmed, preserve earlier work** | G318 `pilot/fpv/view/DJIFpvGimbalPitchView.java:183-213`: speed sends, 100 ms initial delay / 40 ms period, zero speed + permission false on release. Model has 7-byte yaw/roll/pitch int16 fields and permission bit7; cmdset 4 / id 12 in `q.java:837` |
| Angle/AbsAngle layouts and mandatory permission | **Keep prior 3.1.83 comparison with provenance caveat; no universal requirement** | #16 already found the single-pilot UI uses SpeedControl, not a separate permission handshake. This does not settle why every earlier physical-move attempt failed |
| OSD Common dual registration | **Reconfirmed structure, live result U** | G318 `q.java:655,1414`: 03/43 and 09/01 reference the same model. That does not establish either push appears in the saved P3 stream |
| Motor interlock enum/getters | **Reconfirmed structure, applicability qualified** | G318 `DataOsdGetPushCommon.java:192-199,234-235,525-632`: cause bytes 38/51, gimbal causes, REMOTE_USB_CONNECTED range 200-255. Enum presence does not prove a phone's normal AOA connection blocks P3 arming |
| Version getters | **Reconfirmed structure** | G318 `DataCommonGetVersion.java:77-145`: hardware at receive index 1, loader 17-20, firmware 21-24, flags at 25; actual wire/result-byte handling still needs command-aware corroboration |
| Signal quality | **Reconfirmed structure** | G318 `DataOsdGetPushSignalQuality.java:32-75`: direction bit7, low 7-bit aggregate quality, secondary antenna fields. A 0-127 representation does not itself calibrate a percentage of RF link performance |
| RestartDevice / #28 report | **Envelope reconfirmed, aircraft effect U** | G318 14-byte builder and selectable receiver are real. GO 4 FLYC call-sites and a successful RC restart do not prove that P3 FC restart via any given port works; preserve independent observed RC result |
| No FPGA die-ID over DUML (`gap-report`, `air-survey`) | **Global absence superseded** | Negative searches cover specified builds only. GO 4 DM368 destination need not identify the silicon ultimately queried. Existing firmware offsets/weak negatives survive; no new proof of an FPGA query or of its impossibility |
| SIMPLE / CRC / framing (`duml-protection`, `protocol-verification`) | **Preserved independent evidence** | Captures, native-emulation vectors and C1 firmware comparisons do not depend on GO 4 supporting P3. No new G318 native-SIMPLE behavioural equivalence is asserted |
| Aircraft UEG and FPGA update path (`air-survey`, `fpga-upgrade-path`) | **Preserved firmware findings** | Firmware bytes/addresses are separate from app identity; how image data reaches receiver 19 remains U |
| `litchis` namespace / TLV / Wi-Fi master-slave (`apk-analysis`) | **Product applicability U** | Names and shared libraries alone are insufficient; old "not P3" inference is withdrawn |
| GO 4 modern hardware tables / diagnostics | **Source-scoped** | Keep findings as GO 4 code facts. Require G318 product gate or independent P3 firmware/capture evidence before claiming a P3 capability |

## Reproduction and coverage limits

Obtain the APKs through the stable pages above. Verify before use; do not substitute
another archive's variant just because its displayed version is 3.1.8. This audit's
3.1.8 is the 101,595,742-byte build, not a differently sized build with that name.

```sh
python3 -m venv tmp/apk-audit-venv
tmp/apk-audit-venv/bin/pip install androguard==4.1.4 JPype1==1.7.1
curl -fL -o tmp/apksig-8.7.3.jar https://dl.google.com/dl/android/maven2/com/android/tools/build/apksig/8.7.3/apksig-8.7.3.jar
tmp/apk-audit-venv/bin/python scripts/re/apk_provenance.py sources/apk/dji.pilot-3.1.8.apk --apksig-jar tmp/apksig-8.7.3.jar --source-url https://mobile.softpedia.com/apk/dji-go/3.1.8/ --acquired-on 2026-10-25 --out tmp/go-3.1.8-provenance.json
tmp/tools/jadx/bin/jadx --no-res --log-level ERROR -j 6 -d tmp/apk/go_3.1.8/static sources/apk/dji.pilot-3.1.8.apk
```

jadx **1.5.3** produced 10,808 Java files (6,841 decompiler work items) and
reported 30 errors (non-zero exit). Its output contains unresolved decompiler stubs in the firmware-package parser
`pilot/publics/control/upgrade/e.java` and upgrade-manager method
`pilot/publics/control/p3cupgrade/b.java` `v()`. These limit the negative findings.
The inspected request builders, UI gates and gimbal methods have readable bodies;
this is not a complete source recovery. Obfuscated command enums are reconstructed
inside `q.java`; imports may name classes that jadx inlined there. Negative searches
are bounded by that output. Record paths/methods as well as line numbers when using
another jadx version.

3.1.83 static extraction exposed a 1,623-class AppGuard/third-party DEX; it did not
recover the real DJI method bodies. The older runtime trees `dynamic` and
`pilot_dynamic` are absent in this checkout, so their earlier findings are cited
as existing reports. No new device memory dump or APK execution occurred.

**Still open:** a complete P3 Pro aircraft-push trace, encrypted upgrade-group
configuration and unresolved factory/rollback reachability; air FPGA data route;
per-endpoint command acceptance; remaining telemetry/ACK details; full version-by-version
native-library equivalence. These limits keep #19/#30 from being silently treated
as fully closed by this documentation correction.

Vendor reference hashes (downloaded and text-extracted locally): release-notes PDF
274,178 bytes, SHA-256 `1c9ab0c534d5f1c53cdeae765bae1accad597e5a2915603ed7da1d5bc29ae28e`;
update-guide PDF 10,147,914 bytes, SHA-256
`455ee81c51cb49eb98f07f166ea467a29380122956a18f38283c61b16b3f5ab5`.
