# DUML protection: XOR, component authentication, and pairing

> **2026-10-25 provenance clarification:** GO 4 remains the source for the native
> routine analysis below. Its applicability is independently supported by C1 code,
> emulation vectors and captured P3 traffic, which this audit preserves. Classic
> GO is `dji.pilot`, not enterprise Pilot; no new equivalence of its native code
> is asserted here. See the [2026-10-25 P3 evidence audit](dji-go-p3-evidence-audit-2026-10-25.md).

Reviewed 2026-10-24 against the locally unpacked DJI GO 4 v4.3.64 APK.
V = verified in the named artifact; I = inference; U = unresolved.
- Framing: DUML findings here are actuation risk over the wired interfaces (USB, UART,
  AOA), not vulnerabilities. Keep wording consistent with this.
The analysis below omits table bytes and device secrets. The shared, bundled SIMPLE
protocol table is now implemented in the Dart codec at the operator's request;
it is not a recovered per-device secret. No hardware commands sent for this work.

## App support (2026-10-24)

- The pure-Dart codec now encodes and decodes SIMPLE (`encrypt_type = 3`), using
  the matched table and packet sequence. Packet objects expose plaintext command
  set/ID/payload and retain the wire protection mode; `encode()` reapplies it.
- Header bytes 0–8 remain clear. CRC16 is verified over the original protected
  bytes before decoding; outgoing CRC16 is calculated after protection. Decoding
  does not mutate the received buffer. Modes other than 0 and 3 are rejected rather
  than interpreted as plaintext, including by the stream framer.
- The table has 21 bytes plus a zero terminator. Native code permits index 21;
  the table-index recurrence continues across command set, ID and payload, restarting
  per packet. It is not simply a repeating-key XOR starting at the payload.
- AOA writes support CONNECT intent extra `protection=auto|none|simple`.
  Default `auto` initially sends cleartext, follows CRC-valid received SIMPLE frames,
  and returns to cleartext after eligible clear packets, matching the APK's mode
  selection. State resets for a new connection.
- Automatic/forced link selection leaves COMMON commands and camera IDs
  `0x10`, `0x11`, `0x70`, `0x71` clear, as in the APK. Explicitly protected input
  frames are preserved without applying the transform twice. `none` disables
  automatic transformation; it does not rewrite explicitly supplied wire frames.
- All AOA callers, including UI, intents and PC-proxy writes, pass through the same
  selection logic. The issue #23 MVP routes only command-channel payloads into
  protection and telemetry (see `phone-bridge-operator-guide.md`).
  This change does not implement other protection modes,
  ATSHA204 provisioning or a per-pair key exchange.

`app/packages/duml/test/fixtures/simple_vectors.json` contains vectors computed
independently from the native disassembly and matched artifact table, including
the zero-terminator index and a maximum-length body. They are not live captures
or results of executing the native implementation. Regenerate using
`scripts/re/gen_simple_vectors.py --output app/packages/duml/test/fixtures/simple_vectors.json`.

Run `dart test` in `app/packages/duml` and `flutter test` in `app/awto_dji_app`.
Hardware interoperability remains to be tested; this change does not establish
that every endpoint supports SIMPLE or that it provides authentication.

Validation for this implementation: **28 DUML tests and 25 app tests passed**;
the DUML analyzer and analysis of the six changed app files passed. Full app
analysis still reports four pre-existing lint findings in unrelated files.
`flutter build apk --debug --no-pub` succeeded. The APK was built but not installed;
no new commands were transmitted to hardware.

### GO parity review

The transform was also checked by executing the actual APK AArch64 routine at `0x3438` and the C1 ARM routine at `0x400042e4` in Unicorn CPU emulation.
- **All 544 cases matched both native routines byte for byte**, including inverse transforms, sequence edge cases, lengths 0–65 and the maximum 1012-byte body.
- The Dart verifier also checked packet encoding/decoding for bodies of at least two bytes.
- This checks isolated native routines, not the whole GO application or hardware interoperability.
- Artifact hashes and results are retained in [the native review report](data/simple-native-review-2026-10-24.json).

The Java review covered `DataBase.preprocessPack`/`start`, manager `P3/c.java`,
the receive parser `P3/i.java`, AOA manager `P3/h.java`, and USB channel routing.
It found and corrected these differences:

- Protection mode detection now removes AOA envelopes and observes only command
  channel `0x5749`; valid-looking DUML inside video cannot change the mode.
- Outgoing protection mutates a copy of the original wire frame, preserving
  reserved header bits, ORs mode 3 into byte 8, then refreshes CRC16, as GO does.
- TCP proxy input is framed incrementally, supporting split and coalesced reads.
- The DUML framer checks CRC8 before trusting length, preventing a corrupt long
  length from blocking the following valid frame.

Intentional differences: our auto mode resets on reconnect (GO's manager is a
singleton); `none`/forced `simple` are operator controls; unsupported protection
and unnamed ACK value 3 are rejected; low-level sequence 0 is retained rather
than auto-assigned. Reply payloads retain their result byte; GO's command-aware
semantic layer sometimes strips it. The subsequent
[issue #23](https://github.com/awto-au/awto-dji/issues/23) MVP adds full phone channel
routing and framed relay forwarding; automatic phone/PC verdict comparison is deferred.

To reproduce, install `pyelftools` and `unicorn` in an available Python environment,
then run from the repository root:

```sh
python3 scripts/re/verify_simple_native.py --vectors tmp/simple-native-vectors.json
cd app/packages/duml
dart run tool/verify_simple_native.dart ../../../tmp/simple-native-vectors.json
```

**Recorded-traffic evidence:** the saved 2026-10-23 AOA command channel contains 103 CRC-valid frames with wire mode 3.
- One is retained as `app/packages/duml/test/fixtures/captured_simple_frame.json`: sequence 15311, sender `0x0e` to app `0x02`, decoded command `09/0a`.
- Its wire bytes are an actual capture; the expected plaintext fields were independently computed from the traced transform, not captured separately.
- The Dart test verifies decoding and byte-exact re-encoding.
- This supersedes earlier uncertainty below about whether SIMPLE appears on the owner's recorded P3 link. New outgoing interoperability tests remain pending.

## Findings

| Mechanism | Evidence | What is established |
|---|---|---|
| DUML `SIMPLE` transform | V: APK `DataConfig.EncryptType.SIMPLE(3)`; `DataBase.preprocessPack`; manager `P3/c.java`; native routine below | XOR transformation of command set, command ID and payload, using a bundled table and packet sequence bytes. No per-device/pair input identified in this path. |
| Matching firmware implementation | V: C1 `m1601` 02.00.0006, table at file `0x10920`, ARM routine at `0x400042e4` | Ground USB firmware contains the same table and corresponding XOR/sequence logic; packet code calls it for SIMPLE frames. Exact silicon and use in the owner's GL300C remain to be confirmed. |
| ATSHA204 component authentication | Existing MCU trace in [cpu-reversing-proof.md](cpu-reversing-proof.md), secure-element/provisioning cluster near `m1400:0xf880` | A separate hardware authentication mechanism. Its key provisioning and uniqueness per component/pair have not been established by this APK trace. |
| RC master/slave connection | V: `DataRcSetConnectMaster`, `DataRcGetConnectMaster`, `DataRcGetSlaveList.RcModel`, `RcMasterSlaveView.java`, `CmdIdRc.CmdIdType.SetFrequency` (`FreqMode.MasterEnter/SlaveEnter/SubEnter`) | This is an RC-to-RC (or Wi-Fi-RC-to-RC) multi-controller linking feature — a second/subordinate RC joining the primary RC for shared control — not aircraft-radio binding. Its frames (`SetConnectMaster`, `GetConnectMaster`, `GetSlaveList`, `GetSearchMasters`, `SetFrequency`) are all built with `DataConfig.EncryptType.NO` in their `start()` methods: the password/connect flow is sent in cleartext DUML, not even passed through SIMPLE. |
| XOR table provenance (`simple_key`) | V: dynsym/relocation/disassembly trace below | `simple_key`/`simple_key_len`/`simple_stream_filter`/`simple_stream_part_filter` are exported dynamic symbols, but every reference to them found in the APK's own libraries and native disassembly is a **read**; no store instruction targets the table, no other bundled library imports the symbol, and the Java-visible native API has no setter. The pointer is fixed by a static `R_AARCH64_RELATIVE` PIE relocation to a `.rodata` offset at image load, not computed at runtime. |
| Aircraft/RC radio-link binding (DUML command catalog) | V: full `CmdSet.java` enum survey (COMMON/SPECIAL/CAMERA/FLYC/GIMBAL/CENTER/RC/WIFI/BATTERY/SMARTBATTERY/...) | The only "master/slave + password/auth-code" patterns in the entire command catalog are the RC-to-RC mechanism above and its Wi-Fi-RC analog (`CmdSet.WIFI`: `SetMasterSlaveAuthCode`/`ScanMasterList`/`ConnectMasterWithIdAuthCode`/`GetAuthCode`) plus unrelated multi-battery pairing (`CmdSet.SMARTBATTERY`: `GetPair`/`SetPair`/`Authentication`). No distinct aircraft<->single-RC binding/authentication command set was found; `ActiveStatus`/`GetPushActiveRequest`/`SetActiveResult` are DJI-account/SDK activation, not RF link auth. |
| Aircraft/RC radio protection (RF/physical layer) | U: FPGA radio datapath and over-the-air behaviour not established by any APK/command-catalog trace | This pass only covers the DUML command catalog as implemented in the app. It cannot speak to protection implemented purely in the FPGA/AD9363 physical layer, independent of DUML. |

## SIMPLE transform: where its inputs come from

Java paths below are relative to `tmp/apk/dynamic/decompiled/sources/`:

- `dji/midware/data/manager/P3/DataBase.java:304`: `preprocessPack` builds the frame,
  conditionally calls manager `b(frame, sequence)`, sets SIMPLE, and refreshes framing/CRC.
- `dji/midware/data/manager/P3/c.java:25-44`: both directions use
  `GroudStation.native_rcDataDeal`. The transformed region starts at frame byte 9 and
  ends before the final CRC16. Sender, receiver and sequence remain outside it.
- `dji/midware/e/c/a/d.java:28-35`: that second argument is the same sequence serialized
  into header bytes 6 and 7; it is not a serial number or pairing ID.
- `dji/midware/data/manager/P3/i.java:196-204`: received SIMPLE frames select the mode
  and are transformed using their header sequence. This is mode selection, not evidence
  of a secret-key exchange. Recorded P3 traffic evidence is described above.

Native artifact: `tmp/apk/raw/lib/arm64-v8a/libGroudStation.so`, SHA-256
`04a531f55d6011e68a9fc2d91b63da407cc877a36dec4767a60eef05a5bc3e76`.

- V: `native_rcDataDeal` at ELF VA `0x1fac` calls `simple_stream_filter` at `0x3438`.
- V: the filter reads a table through `simple_key` (pointer object at `0x15128`),
  XORs input bytes with table-derived bytes and alternating low/high sequence bytes.
- V: ELF relocation initializes `simple_key` to `0x3d70`, inside `.rodata`.
  The GOT slot at `0x14ff0` points to `simple_key`.
- V: full disassembly search found two loads through that GOT slot, in
  `simple_stream_filter` and `simple_stream_part_filter`, and no writer through that slot.
- I: the ordinary implementation uses a shared, bundled table rather than a per-pair
  secret. No setter or pairing-derived input was found in this library/Java call path.
  The exported pointer is writable; external native code could theoretically replace it.
  This pass does not prove the absence of all cross-library/runtime modification.

Reproduce without dumping table bytes:

```sh
sha256sum tmp/apk/raw/lib/arm64-v8a/libGroudStation.so
readelf -Ws tmp/apk/raw/lib/arm64-v8a/libGroudStation.so
readelf -rW tmp/apk/raw/lib/arm64-v8a/libGroudStation.so
readelf -SW tmp/apk/raw/lib/arm64-v8a/libGroudStation.so
aarch64-linux-gnu-objdump -d --start-address=0x1fac --stop-address=0x209c tmp/apk/raw/lib/arm64-v8a/libGroudStation.so
aarch64-linux-gnu-objdump -d --start-address=0x3438 --stop-address=0x354c tmp/apk/raw/lib/arm64-v8a/libGroudStation.so
```

## XOR table provenance and aircraft/RC binding (2026-10-24, issue #22)

Answers issue #22's two static-analysis questions. No key/table bytes reproduced.

### Cross-library references/writes to `simple_key`

- V: `readelf --dyn-syms` on `tmp/apk/raw/lib/arm64-v8a/libGroudStation.so` shows
  `simple_key` (`0x15128`), `simple_key_len` (`0x3d6c`), `simple_stream_filter`
  (`0x3438`) and `simple_stream_part_filter` (`0x34cc`) all `OBJECT/FUNC GLOBAL
  DEFAULT` — exported from the library, not file-local.
- V: full disassembly of both routines (`objdump -d --start-address=0x3438
  --stop-address=0x354c`) shows only `ldrb` (load byte) instructions reading through
  the table pointer (`ldrb w6, [x9, x6]` / `ldrb w7, [x10, x7]`). The only `strb`
  (store byte) instructions in either routine write to the destination buffer
  argument (register `x3`), never to the table. Neither routine contains a write
  to the table.
- V: `readelf -rW` lists 44 `.rela.dyn` entries, all `R_AARCH64_RELATIVE` (the
  loader's own PIE pointer fixups, applied once at image load — not a
  runtime/application write) plus one `R_AARCH64_GLOB_DAT` for `__stack_chk_guard`.
  The entry at GOT offset `0x14ff0` sets `simple_key` to `0x15128` -> `0x3d70`,
  inside `.rodata`: a compile-time constant address, not a computed one.
- V: `JNI_OnLoad` (`0x17ec`) only resolves the JNIEnv and calls
  `register_GroudStation`; `.init_array` has one entry (`0x1680`), itself a
  `__cxa_atexit`-registration stub. `.rela.plt` imports are limited to `malloc`,
  `free`, `__android_log_print`, `__stack_chk_fail`, `__cxa_atexit`,
  `__cxa_finalize` — no file, socket, or crypto-library imports exist for this
  library to load or derive a key from at startup.
- V: searched dynamic symbol tables of every other `.so` bundled in the APK
  (`manifest/`, `pilot_static/resources/`, `raw/`, arm64-v8a) for undefined
  references to `simple_key`, `simple_stream_filter`, `simple_stream_part_filter`
  or `native_rcDataDeal`: none found in any library other than the three copies
  of `libGroudStation.so` itself. No other bundled library writes to or reads
  this symbol.
- V: the complete Java-visible native surface of `GroudStation`
  (`tmp/apk/dynamic/decompiled/sources/dji/midware/natives/GroudStation.java`)
  is `native_calcCrc16/8`, `native_checkCRCForData`, `native_decodeData`,
  `native_encodeData`, `native_getCRCFromData`, `native_hashFromString`,
  `native_rcDataDeal`, `native_verifyCrc16/8`, `native_yuv422ToImage` — there is
  no exposed setter through which Java (account state, an ATSHA204 read, a
  server response) could inject a per-device/per-pair key or table.
- I: taken together, within everything shipped in this APK, `simple_key` behaves
  as a fixed build-time literal: nothing reads it except the two filter routines,
  nothing writes it, and no Java-reachable path can replace it. The existing
  caveat stands unchanged: the symbol is exported and its target is writable
  memory, so a binary *outside this APK* (not examined here) could in principle
  write through it — this pass narrows, but does not close, that possibility.
- I: a second, structurally identical copy of the routine exists in
  `tmp/apk/pilot_static/resources/lib/arm64-v8a/libGroudStation.so` at a
  different offset (`simple_stream_filter` at `0x3530`, table fixed to `0x3e6c`)
  — a different build bundled in the APK, not independent runtime evidence, but
  consistent with the table being baked in at compile time across builds rather
  than provisioned later.

### Aircraft/RC binding, independent of RC master/slave

- V: `DataRcSetConnectMaster.start()`, `DataRcGetConnectMaster`,
  `DataRcGetSlaveList.start()`, `DataRcGetSearchMasters.start()`, and
  `DataRcSetFrequency.start()` (all `dji/midware/data/model/P3/`) each build their
  frame with `dVar2.l = DataConfig.EncryptType.NO.value();` explicitly — this
  password/connect exchange is sent as **cleartext DUML**, not even passed through
  SIMPLE.
- V: `RcMasterSlaveView.java` (`dji/setting/ui/rc/`) and
  `DataRcSetFrequency.FreqMode` (`MasterEnter/SlaveEnter/SubEnter`) confirm the
  purpose: linking a second/subordinate RC to the primary RC for shared control —
  RC-to-RC, not RC-to-aircraft.
- V: full survey of `CmdSet.java`'s enum (`dji/midware/data/config/P3/`, all
  cmdsets: COMMON, SPECIAL, CAMERA, FLYC, GIMBAL, CENTER, RC, WIFI, DM368, BATTERY,
  SMARTBATTERY, and the remaining ones) for `Bind`/`Pair`/`Activ` finds exactly two
  other matches: `CmdSet.WIFI`'s `SetMasterSlaveAuthCode(131)` /
  `ScanMasterList(132)` / `ConnectMasterWithIdAuthCode(133)` / `GetAuthCode(137)`
  (the Wi-Fi-RC analog of the same RC-to-RC master/slave scheme, for Wi-Fi-linked
  products — not the P3 Pro's Lightbridge RC), and `CmdSet.SMARTBATTERY`'s
  `GetPair(21)` / `SetPair(22)` / `Authentication(35)` (multi-battery pairing,
  e.g. dual-battery systems — unrelated to the RF link). `ActiveStatus(50)`
  (COMMON), `GetPushActiveRequest(97)`/`SetActiveResult(98)` (FLYC) are
  DJI-account/SDK product activation, not RF link authentication.
- I: no command set in this catalog implements a distinct aircraft<->single-RC
  binding or authentication handshake. Combined with the RC master/slave finding,
  static analysis of the DUML command catalog as implemented in the app finds
  **no per-pair authentication of the aircraft<->RC radio link at the DUML layer**
  — only the shared, apparently-hardcoded SIMPLE transform (whose own routine has
  no MAC/replay check either, per the existing finding below). This does not
  establish or rule out protection implemented purely in the FPGA/AD9363 physical
  layer, independent of DUML — that is outside what a command-catalog/APK trace
  can see.

**Explicitly unaddressed by this pass (needs live hardware):** whether SIMPLE is
actually exercised on the owner's real P3 link beyond the one recorded frame
already in evidence above, and whether the RF/physical layer applies any
protection of its own. Both require a live-hardware passive capture session; this
was static analysis only, no capture was attempted, and none should be inferred
from the above.

## Firmware match (2026-10-24)

For USB roles, alternate bulk descriptors and PC access, see
[fx3-usb-modes.md](fx3-usb-modes.md). The XOR match alone did not identify a physical
connector or establish which path handles aircraft radio commands.

**V: exact table match and corresponding executable XOR code in ground USB module
`m1601`, rather than just an unused matching string.**

Searched all regular, non-symlink files under `firmware/` and `tmp/air/`:
678 files, 3,352,896,788 bytes (includes duplicate artifacts and packed containers).
The APK symbol `simple_key_len` specifies 21 bytes. The same table was independently
located from the APK's ARM32 library, confirming the ARM64 extraction.
The complete offsets and artifact hashes are retained in
[the scan results](data/duml-table-matches-2026-10-24.json).

| Artifact | Exact table file offset | Interpretation |
|---|---|---|
| APK ARM64 `libGroudStation.so` | `0x3d70` | Reference table |
| APK ARM32 `libGroudStation.so` | `0x447f` | Same 21 bytes |
| `firmware/unpacked/C1_FW_V01.06.0000/C1_FW_V01.06.0000_m1601.bin` | `0x10920` | Ground USB module, version 02.00.0006 |
| `firmware/unpacked/corpus_scan/C1/C1_FW_v01.07.0000_m1601.bin` | `0x10920` | Byte-identical module, not independent implementation evidence |
| 15 raw C1 firmware containers | Various; see retained scan results | Additional table occurrences; per-container module attribution not performed here |

Firmware module SHA-256:
`703d211d04bafa27f7c8fa95ec336d814440a7950740562bb28601bfdaa764a0`.
Its `.ini` identifies receiver USB `IG810 LB2_CY2014_RX ground`. The executable has
a sectioned Cypress `CY` boot header and ARM instructions. **I:** this is the Cypress
FX3-family USB processor; the exact chip marking is not established from this match.
It is separate from the ATSHA204 secure element and `m1400` (`gnd_rc_lpc1765`).

### Code references

- V: the CY image section at file `0x223c` loads at `0x40003000` for `0x10000` bytes.
  The table therefore loads at `0x400116e4`.
- V: a literal at file `0x3590` / VA `0x40004354` contains that table address.
  Instruction `0x400042f0` loads it into `r6`.
- V: routine `0x400042e4` XORs each input byte with a table-selected byte and alternates
  the low/high bytes of argument `r2`. The table-index recurrence and sequence-byte
  alternation correspond to the APK routine. The firmware operates in place.
- V: callers at `0x40007ee0`, `0x40008174` and `0x4000871c` invoke this routine.
  The first and third explicitly assemble `r2` from frame bytes 6/7.
- V: receive-side code at `0x4000857c` reads frame byte 8, masks its low nibble and
  compares with 3; an equal result branches to `0x40008700`, which loads the sequence
  and calls the XOR routine. Transmit-side code near `0x40007eb0` sets mode 3 before
  calling it, then rejoins the checksum-generation path.
- I: this establishes the USB processor as an endpoint for the SIMPLE transform in
  this C1 firmware build. It does not establish the mode used by the owner's GL300C,
  the exact external port/direction of every call, or the bytes subsequently sent over RF.

There were **no exact matches in the other searched unpacked modules**, including the
available aircraft FC/radio images. This is a bounded byte search: transformed,
compressed, encrypted, generated or differently versioned tables can be missed.
No conclusion about absence of other protection follows from a negative match.

Reproduce (pyelftools for matching; capstone for disassembly):

```sh
python3 -I scripts/re/match_duml_table.py --roots firmware tmp/air > tmp/duml-table-all-firmware.json
python3 -I scripts/re/match_duml_table.py --apk-library tmp/apk/manifest/lib/armeabi-v7a/libGroudStation.so --roots firmware/unpacked/C1_FW_V01.06.0000/C1_FW_V01.06.0000_m1601.bin tmp/apk/raw/lib/arm64-v8a/libGroudStation.so
python3 -I scripts/re/fx3_trace.py --image firmware/unpacked/C1_FW_V01.06.0000/C1_FW_V01.06.0000_m1601.bin --address 0x400042e4 --count 28
python3 -I scripts/re/fx3_trace.py --image firmware/unpacked/C1_FW_V01.06.0000/C1_FW_V01.06.0000_m1601.bin --callers 0x400042e4
python3 -I scripts/re/fx3_trace.py --image firmware/unpacked/C1_FW_V01.06.0000/C1_FW_V01.06.0000_m1601.bin --address 0x4000857c --count 8
```

No device communication, firmware modification or secret provisioning was performed.

## What remains to determine

SIMPLE alone has no demonstrated message-authentication tag or replay check in the
examined routine. A changing sequence is not a secret per-pair key. Its presence does
not establish resistance to deliberate command injection.

Cross-library references/writes to `simple_key` and the independent trace of
aircraft/RC binding are now done (see "XOR table provenance and aircraft/RC
binding" above, issue #22): the table is read-only everywhere examined in this
APK and has no Java-reachable setter; no DUML command set implements a distinct
aircraft<->single-RC binding/authentication step; RC master/slave is RC-to-RC and
sent in cleartext. **Still open and requiring live hardware, not attempted here:**
confirm SIMPLE's actual use (beyond the one recorded frame already in evidence) on
a passive capture of the owner's real P3 link, and whether the FPGA/AD9363
physical layer applies any protection of its own independent of DUML.
