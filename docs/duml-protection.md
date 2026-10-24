# DUML protection: XOR, component authentication, and pairing

Reviewed 2026-10-24 against the locally unpacked DJI GO 4 v4.3.64 APK.
V = verified in the named artifact; I = inference; U = unresolved.
No key-table bytes or device secrets are reproduced here. No hardware commands sent.

## Findings

| Mechanism | Evidence | What is established |
|---|---|---|
| DUML `SIMPLE` transform | V: APK `DataConfig.EncryptType.SIMPLE(3)`; `DataBase.preprocessPack`; manager `P3/c.java`; native routine below | XOR transformation of command set, command ID and payload, using a bundled table and packet sequence bytes. No per-device/pair input identified in this path. |
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
  of a secret-key exchange. Actual use on the owner's P3 remains unverified by this trace.

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

## What remains to determine

SIMPLE alone has no demonstrated message-authentication tag or replay check in the
examined routine. A changing sequence is not a secret per-pair key. Its presence does
not establish resistance to deliberate command injection.

To settle the system-level question, inspect cross-library references/writes to
`simple_key`, confirm SIMPLE usage in a passive capture of the owner's P3, and trace
aircraft/RC binding independently of RC master/slave connection. No need to disclose
secret values to establish whether provisioning or session inputs are device-specific.
