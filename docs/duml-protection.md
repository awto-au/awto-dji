# DUML protection: XOR, component authentication, and pairing

Reviewed 2026-10-24 against the locally unpacked DJI GO 4 v4.3.64 APK.
V = verified in the named artifact; I = inference; U = unresolved.
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
| RC master/slave connection | V: `DataRcSetConnectMaster`, `DataRcGetConnectMaster`, `DataRcGetSlaveList.RcModel` | Connection record contains ID, name and a password field; `WrongPwd` is a named result. These facts alone do not identify aircraft-radio binding or prove cryptographic authentication. |
| Aircraft/RC radio protection | U: end-to-end binding and FPGA radio datapath not established here | Cannot infer absence of pair-specific protection from the APK's shared XOR transform. |

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

To settle the system-level question, inspect cross-library references/writes to
`simple_key`, confirm SIMPLE usage in a passive capture of the owner's P3, and trace
aircraft/RC binding independently of RC master/slave connection. No need to disclose
secret values to establish whether provisioning or session inputs are device-specific.
