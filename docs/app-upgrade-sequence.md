# DJI GO 4 firmware-push sequence (static, from the decompiled APK)

Static interoperability notes for the operator's own Phantom 3. Nothing was sent to any device.
No key, cipher-table, signing or ATSHA204 value was read or recorded; fields that may hold such material are named, not decoded.
Tags: **V** verified in decompiled code, **I** inferred, **U** unknown.
Already covered elsewhere, not repeated: `docs/ground-upgrade-path.md` (m1400), `docs/fpga-upgrade-path.md` (m0900),
`docs/air-id-and-stream-survey.md` (camera upgrade engine), `docs/apk-analysis.md`, `docs/apk-vs-dissector-gap-report-2026-10-23.md`,
`scripts/re/duml_catalog.py` (723 names), `app/packages/duml` (Dart codec).

## Source key

| Alias | Path under `tmp/apk/dynamic/decompiled/sources/dji/` |
|---|---|
| `M` | `midware/` |
| `P3` | `midware/data/model/P3/` |
| `TB` | `midware/transfer/base/` |
| `PC` | `pilot/publics/control/` |
| `RC` | `pilot/publics/control/rc/` |
| `LG` | `pilot/publics/control/a/` (legacy per-module sender) |
| `DB` | `dbox/upgrade/p4/` |

- Decompiler artefacts: jadx names (`a`, `b`, `f10927c`) are obfuscated, behaviour is read from bodies. One constant is mis-resolved (`Build.VERSION_CODES_FULL.ECLAIR` in `TB/FileTransferStrategies.java:10-11`, true value U).
- Byte order: all multi-byte fields are little-endian. V: `M/util/d.java:91-93` (`c(int)` 4 B), `:107-109` (`d(int)` 2 B), `:71-73` (`b(long)` 4 B), `:115-127` (`f(byte[],off,len)` read).

## 0. Findings up front

- V: no class in this APK ties `ProductType` Phantom 3 (litchiC/S/X, P34K) to a firmware-push engine. `DJIUpDeviceType` has no P3 entry (`DB/constants/DJIUpDeviceType.java:9-32`).
- V: four distinct push mechanisms exist, all on cmdset 0 (COMMON): (R) ground RC module push, (L) legacy per-module sender with no static callers, (T) P4-era tar/multi-file engine, (C) camera-hosted flow where the app only confirms.
- V: `RequestSendFiles`/`AckReceiveFiles`/`SetResendFiles` are the **media (photo/video) download** protocol, not firmware (`pilot/fpv/control/g.java:86,265,425-472`).
- V: classes named `DataCamera*` are the same COMMON cmdset-0 commands seen from the camera as peer. Model class = `"Data" + SenderDeviceName + CmdName` (`M/data/config/P3/c.java:24-26`, `CmdSet.java:195-202`). They are not cmdset 2.
- V: type 9 is `OFDM` (the m0900 MCU), type 19 is `FPGA` (m1900, air FPGA), type 20 is `FPGA_G` (ground FPGA, m2000-m2003) (`M/data/config/P3/DeviceType.java:15,25-26`). The brief's "m1900 = device type 19 / OFDM" is corrected: OFDM is 9.
- V: no code names receiver type 19 for 0x07/0x08/0x09/0x0A. The legacy sender (`LG/*`) would address it generically from a package entry, but has no callers (see sections 2.3, 3).

## 1. Message layouts

Frame (all commands): header/CRC per `M/e/c/a/d.java:14-51` (V): byte 4 = `(senderId<<5)|senderType`, byte 5 = `(receiverId<<5)|receiverType`, bytes 6-7 seq, byte 8 = `(cmdtype<<7)|(needack<<5)|encrypt`, then cmdset, cmdid, payload, CRC16.
`CMDTYPE` REQUEST=0 ACK=1; `NEEDACK` NO=0 YES_BY_PUSH=1 YES=2; encrypt 0 for every upgrade command (`M/data/config/P3/DataConfig.java`). V.
Sender is always `APP` (2), sender id 0 (V, every `start()`). `start(timeout, retry)` pairs below are the `.s`/`.t` fields of the request object (`M/e/c/a/d.java:10-11`); meaning timeout ms / retry count is I (field names only).
Ack payload in the tables excludes the ccode byte (`M/e/c/a/c.java:44-52`, V). Exception: GetVersion getters index from 1 (see section 4, U).
Ccode names/values: `M/data/config/P3/Ccode.java:6-45` (V); the ones that matter here are 224 INVALID_CMD, 227 INVALID_PARAM, 228 NOT_SUPPORT_CURRENT_STATE, 232 SDCARD_NOT_INSERTED, 233 SDCARD_FULL, 240 FM_NONSEQUENCE, 241 FM_LENGTH_WRONG, 242 FM_CRC_WRONG, 243 FLASH_C_WRONG, 244 FLASH_W_WRONG, 245 UPDATE_WRONG, 246 FIRM_MATCH_WRONG, 247 UPDATE_WAIT_FINISH, 249 UPDATE_MOTOR_WORKING, 251 DEVICE_LOW_POWER, 253 FLASH_FLUSHING, 254 UPDATE_NOCONNECT_CAMERA, 255 UNDEFINED.

### 1.1 Command ids (cmdset 0, `M/data/config/P3/CmdSet.java`)

| Id | Name | Line | Class |
|---|---|---|---|
| 0x01 | GetVersion | 206 | `DataCommonGetVersion` |
| 0x07 | RequestUpgrade | 208 | `DataCommonRequestUpgrade` |
| 0x08 | RequestReceiveData | 209 | `DataCommonRequestReceiveData` |
| 0x09 | TranslateData | 210 | `DataCommonTranslateData` |
| 0x0A | TranslateComplete | 211 | `DataCommonTranslateComplete` |
| 0x0B | RestartDevice | 212 | `DataCommonRestartDevice` |
| 0x0C | GetDeviceStatus | 213 | `DataCommonGetDeviceStatus` |
| 0x0F | UpgradeSelfRequest | 215 | `DataUpgradeSelfRequest` |
| 0x22 | RequestSendFiles | 217 | `DataCameraRequestSendFiles` |
| 0x23 | AckReceiveFiles | 218 | `DataCameraAckReceiveFiles` |
| 0x25 | SetResendFiles | 220 | `DataCameraSetResendFiles` |
| 0x2A | TransferFile | 224 | `DataCommonTransferFile*` |
| 0x40 | GetPushRequestUpgrade | 227 | `DataCameraGetPushRequestUpgrade` |
| 0x41 | ControlUpgrade | 228 | `DataCommonControlUpgrade` / `DataCameraControlUpgrade` |
| 0x42 | GetPushUpgradeStatus | 229 | `DataCommonGetPushUpgradeStatus` / `DataCameraGetPushUpgradeStatus` |
| 0x43 | AckUpgradeStop | 230 | `DataCameraAckUpgradeStop` |

(V, values match `scripts/re/duml_catalog.py:10-30`.) OSD cmdset 9, id 0x10 `SetUpgradeTip` (`CmdSet.java:1656`, V) is used by the RC flow (1.9).

### 1.2 RequestUpgrade 0x07 (`P3/DataCommonRequestUpgrade.java`)

| Dir | Offset | Field | Notes |
|---|---|---|---|
| App to dev | 0 | encrypt u8 | 0 (`:99`) |
| | 1..8 | zero | array filled 0 (`:96-98`) V |
| Ack | 0 | tran-method bits | bit0 V1 (TranslateData path), bit1 FTP (`:58-85`, `:107-110`) |
| | 1 | file-method bits | bit0 single-file-serial, bit1 multi-file, bit2 big-package, bit3 copy-data (`:23-56`, `:102-105`) |

- V: default receiver `RC` id 0 (`:18-19`); `start()` defaults timeout 15000 ms, retry 1 (`:127-129,131-143`, I for units).
- V: legacy/ground callers ignore the ack content (`RC/c.java:547`, `LG/a.java:499`); the T engine and data-upgrade read it (`DB/statemachine/e.java:273-291`, `dji/data/upgrade/logic/a.java:133-146`).

### 1.3 RequestReceiveData 0x08 (`P3/DataCommonRequestReceiveData.java`)

| Dir | Offset | Field | Notes |
|---|---|---|---|
| App to dev | 0 | encrypt u8 | 0 |
| | 1..4 | data length u32 | total bytes to follow (`:39`, `d.b(long)`) |
| | 5..10 | zero | |
| | 11 | tran-method bits | as 1.2 ack byte 0; only set by the T engine (`:40-43`) |
| | 12 | file-method bits | as 1.2 ack byte 1; only set by the T engine (`:44-47`) |
| Ack (V1) | 0..1 | block length u16 | `getReceiveDataLength`, default 300 if ack shorter than 2 B (`:71-77`) |
| Ack (FTP) | 0..3 | IPv4, printed `b3.b2.b1.b0` | `getFtpIP` (`:55-61`) |
| | 4..5 | port u16 | `:63-69` |
| | 6.. | UTF-8 path | `getDir`, default string `/upgrade/dji_system.bin` (`:50-53`) |

- V: payload 13 B (`:36`). `start(timeout 15000, retry 2)` (`:104-107`). Receiver type/id set by caller.
- I: for the ground FPGA the ack block length is 0x0200 (`docs/ground-upgrade-path.md` Q1 table, m1400 `0x5218`).

### 1.4 TranslateData 0x09 (`P3/DataCommonTranslateData.java`)

| Dir | Offset | Field | Notes |
|---|---|---|---|
| App to dev | 0 | encrypt u8 | 0 |
| | 1..4 | sequence u32 | from 0 (`:47`) |
| | 5..6 | size u16 | bytes of data (`:48`) |
| | 7.. | data | `:49` |
| Ack | 0..3 | sequence u32 | last good / failing sequence (`getSequence` `:62-69`, `getFailSequence` `:54-60`) |

- V: acked variant `start(cb)`: NEEDACK YES, timeout 3000, retry 1 (`:96-110`). Unacked `start()`: NEEDACK NO (`:118-129`), used by the T engine for bulk packets (`DB/statemachine/e.java:802`).
- V: ack ccode `FM_NONSEQUENCE` (240) means resend from `failSeq+1` (`RC/c.java:588-598`, `LG/a.java:481-490`).

### 1.5 TranslateComplete 0x0A (`P3/DataCommonTranslateComplete.java`)

- Payload 17 B: `[0]` encrypt 0, `[1..16]` 16-byte field = MD5 of the module/file (`:30-42`, V; `RC/a.java:216` source `entry[20..35]`).
- V: timeout 10000 ms, 30000 ms when receiver is `DM368_G` or `TRANSFORM_G`; retry 1 (`:64-88`). T engine passes 10000 explicitly (`DB/statemachine/e.java:712`).
- V: for `FPGA_G` the 16-byte field instead carries a 16-bit sum of all module bytes, little-endian, in bytes 0-1, rest zero (`RC/c.java:563-567,601-605,624-653`). The sum is not MD5.

### 1.6 RestartDevice 0x0B and GetDeviceStatus 0x0C

| Cmd | Payload | Ack | Timing |
|---|---|---|---|
| RestartDevice (`P3/DataCommonRestartDevice.java:29-36,58-71`) | 14 B: `[0]` encrypt 0, `[1]` restart type (app only uses 0), `[2..5]` delay u32 (app uses 0 or 1000, units I ms), rest 0 | ccode only | receiver id forced 0 (`:63`), timeout 3000 |
| GetDeviceStatus (`P3/DataCommonGetDeviceStatus.java:28-35,53-67`) | 1 B: `[0]`=0; receiver id forced 0 | mode = `u32@1 & 1` (index base U) | timeout 5000, retry 1 |

- V: GetDeviceStatus mode bit0: callers treat 1 as "in upgrade mode" after RequestUpgrade (`LG/a.java:226-229`, `RC/c.java:231-235`) and 0 as "normal" after restart (`LG/b.java:207-209`, `RC/c.java:284-291`).
- I: cross-check with m1400 Q1 table (`docs/ground-upgrade-path.md`): status 0xF2/0xF6/0xE3/0xF4/0xFF there = Ccode 242/246/227/244/255.

### 1.7 ControlUpgrade 0x41, GetPushUpgradeStatus 0x42, GetPushRequestUpgrade 0x40, AckUpgradeStop 0x43, UpgradeSelfRequest 0x0F

ControlUpgrade (`P3/DataCommonControlUpgrade.java`, camera twin `P3/DataCameraControlUpgrade.java`):
- Payload 1 B = control: Cancel 0, Start 1, Pause 2, Stop 3, StopPush 4, Restart 5, OTHER 7 (`:24-56,70-73`; camera `:18-50,59-62`). V.
- V: Common variant defaults receiver `DM368` id 0 (`:19,22`); callers override (`DB/statemachine/f.java:88` DM368 id 1 Stop; `DB/statemachine/c.java:152,331-333` StopPush to the pushing device). Camera variant is fixed to receiver `CAMERA` (1) id 0 (`DataCameraControlUpgrade.java:69-80`).

GetPushUpgradeStatus, Common layout (`P3/DataCommonGetPushUpgradeStatus.java`, parse `:167-198`, item `:134-143`), device to app push:

| Offset | Field | Notes |
|---|---|---|
| 0 | step u8 | Verify 1, UserConfirm 2, Upgrading 3, Complete 4, DataUpgrading 5 (`:93-124`) |
| 1 | by step | UserConfirm: user time; Upgrading: progress %; Complete: result code; DataUpgrading: progress % |
| 2 | by step | UserConfirm: reserve; Upgrading: bits7-5 current index, bits4-0 item count; Complete: item count u8; DataUpgrading: status (list below) |
| 3.. | items, 8 B each, count from byte 2 | `[0]` bits0-4 device type, bits5-7 device id; `[1]` firmware type; version u32 (see below); `[6]` status; `[7]` progress |

- Complete result values (`:55-91`): Success 1, Failure 2, FirmwareError 3, SameVersion 4, UserCancel 5, TimeOut 6, MotorWorking 7, FirmNotMatch 8, IllegalDegrade 9, NoConnectRC 10, OTHER 100.
- DataUpgrading status (`:201-241`): Success 0, Failure 1, FirmwareErr 2, TimeOut 3, AirDataLinkError 4, AirSdrError 5, GdSdrError 6, TransFromAirToGdError 7, AirCtrLinkError 8, ReqAirToRecvError 9, DataParseError 10, verifyError 11, DataCopyError 12, FtpError 13.
- V quirk: item version is read with `d.f(bArr, 2)` (absolute index 2, not `i2+2`) for every item (`:139`). Whether that is a decompiler artefact is U.
- V: app also *sends* this command (app to OSD id 0, `pushProgressStatus`/`pushEndStatus`, payload `[step, progress|reason]`, `:264-271,312-340`) to mirror progress on the RC (`DB/statemachine/e.java:869,876`).

GetPushUpgradeStatus, camera layout (`P3/DataCameraGetPushUpgradeStatus.java`), pushed by the camera:

| Offset | Field | Notes |
|---|---|---|
| 0 | step u8 | Check 1, Ack 2, Progress 3, End 4 (`:121-151,203-205`) |
| 1 | value u8 | progress / countdown / end cause (`:164-170,195-197`); end cause: Success 1, Failed 2, FirmwareError 3, VersionSame 4, UserCancel 5, TimeoutCancel 6, MotorUp 7 (`:78-111`) |
| 1 (low 3 bits) | round | `getRound` (`:199-201`) |
| 2 (low 5 bits) | firmware count | `getFirmwareCount` (`:172-174`) |
| 3.. | items, 8 B | `[0]` device type (whole byte), `[1]` firmware type Loader 1/Sys 2/App 3, `[2..5]` version bytes printed `v b2.b3.b4.b5`, `[6]` status Success 0/Progressing 1/Waiting 2/Error 3/CanotCheck 4, `[7]` degree (`:14-76,176-193`) |

GetPushRequestUpgrade (`P3/DataCameraGetPushRequestUpgrade.java:33-49`, push): items of 10 B: `[0]` device type, `[1]` firmware type, `[2..5]` version bytes, `[6..9]` size u32. V. No caller outside the model class.

AckUpgradeStop (`P3/DataCameraAckUpgradeStop.java:24-45`): app-built ACK to the camera, payload `[0]`=0, echoes the incoming seq; incoming `[0]` = result. V. No caller found (U whether the camera ever sends 0x43).

UpgradeSelfRequest (`P3/DataUpgradeSelfRequest.java`): device to app request; app answers with an ACK (same cmdid, same seq, receiver = original sender) payload `[ccode OK=0, ctl]`, ctl UNDO 0 / DO 1 (`:18-46,60-64,87-107`); incoming `[0]==1` is the device's flag (`:55-58`). V. Not sent when motors are up (`:89-95`). Subscribers `pilot/home/rc/activity/DJIRcMainActivity.java:499`, `pilot2/main/fragment/DJINewDeviceFragment.java:804`, UI dialog `pilot/publics/objects/i.java:42,71`. Meaning "device asks permission to self-upgrade" is I.

### 1.8 TransferFile 0x2A: Request / Data / DataExtended / Verify / RealTimeData

One cmdid; payload byte 0 selects the variant (`TB/ITransferFileObject.java:86-102`): REQUEST 1, DATA 2, VERIFY 3, DATA_EXTENDED 4, REAL_TIME_DATA 5. Receiver type/id set by caller, default `CAMERA` (`P3/DataCommonTransferFile.java:19-37`). V.
Enums: file type FIRMWARE 1, PANORAMA 2, QUICK_SHOT 3, AUDIO 4, OTHER 255 (`:7-23`); verify type MD5 1, CRC16 2, CRC32 3 (`:55-84`); protocol PROTOCOL_1 0, PROTOCOL_2 1 (`:25-53`); error SUCCESS 0, SDCARD_NON 232, SDCARD_NOT_ENOUGH 233, FILE_VERIFY_ERROR 242, FILE_WRITE_ERROR 244 (`:104-135`). V.

| Variant | Payload (app to dev) | Ack | start params |
|---|---|---|---|
| REQUEST 1 (`P3/DataCommonTransferFileRequest.java:62-95`) | `[0]`=1; `[1..4]` file size u32; `[5]` name length (incl NUL); name ASCII + NUL; file-type u8; extra length u8; extra bytes | `[0..1]` packet length u16; `[2..3]` window size u16; `[4]` verify type; `[5]` protocol (absent means PROTOCOL_1) (`:44-60,118-124`) | `DataCommonTransferFile.start`: timeout 5000, retry 4 (`P3/DataCommonTransferFile.java:50-51`) |
| DATA 2 (`P3/DataCommonTransferFileData.java:82-99`) | `[0]`=2; `[1..4]` sequence u32; `[5..]` data | P1: `[0..3]` ack seq, `[4..7]` next consecutive seq (`:74-80,140-146`). P2: `[0..3]` max seq then ranges: start u32 at `4+8i`, count u32 at `8+8i` (`:48-72`) | NEEDACK YES, retry 0, timeout 3000, special channel, returns <0 if busy (`:119-132`) |
| DATA_EXTENDED 4 (`P3/DataCommonTransferFileDataExtended.java:44-61`) | same layout as DATA with `[0]`=4 | as DATA (P2 ranges) | same (`:72-85`) |
| VERIFY 3 (`P3/DataCommonTransferFileVerify.java:58-80`) | `[0]`=3; then 16 B (MD5), 2 B (CRC16) or 4 B (CRC32), only if the supplied array length matches | `[0..3]` index u32 if ack longer than 3 B (`:82-88`) | timeout 5000, retry 10 (`:101-102`) |
| REAL_TIME_DATA 5 (`P3/DataCommonTransferFileRealTimeData.java:60-79`) | `[0]`=5; `[1..4]` seq u32; `[5]` flag u8; `[6..7]` value u16; `[8..]` data | `[0..3]`, `[4..7]` (`:52-58,111-117`) | NEEDACK YES, retry 0, timeout 3000 (`:86-99`) |

- V: incoming TransferFile pushes whose sender is `OFDM` are rerouted to the RealTimeData model (`P3/DataCommonTransferFileData.java:105-112`). No class sends RealTimeData or reads it (only grep hits are the model files): purpose U.
- I: SDCARD_* error codes imply the receiver writes the file to an SD card.

### 1.9 Camera-set-named media classes (not firmware)

| Cmd | Payload | Notes |
|---|---|---|
| RequestSendFiles 0x22 (`P3/DataCameraRequestSendFiles.java:85-106`) | 1 B mode: CURRENT 0, NEXT 1 | receiver CAMERA; errors FileNotFound 34 (0x22), INVALID_CMD 224 (`:18-46`) |
| AckReceiveFiles 0x23 (`P3/DataCameraAckReceiveFiles.java`) | app ACK, 1 B: Success 0, UnableReceive 34, NoMemory 35, NoSupport 224 (`:18-48,57-60,91-106`) | incoming push getters overlap: size u64@0, type u8@8, MD5 16 B@8 (!), time u32@9, isAllPath u8@24, name @25 (`:62-84`); layout ambiguity U |
| SetResendFiles 0x25 (`P3/DataCameraSetResendFiles.java:25-49`) | index u32 | timeout 1, retry 0 |

- V: the only user is the album downloader `pilot/fpv/control/g.java` (file types 0/2/3 accepted, `:425-472`). Not part of any upgrade flow.

### 1.10 SetUpgradeTip (OSD set, cmdset 9 id 0x10)

- `P3/DataOsdSetUpgradeTip.java:10-69`: payload 1 B: START 1, SUCCESS 2, FAIL 3; receiver `OSD` (14); timeout 300, retry 1. V. Used by the RC flow at start/success/fail (`RC/b.java:682,1335,1351,1363,1601`).

## 2. Orchestrators

### 2.1 Package container (the format the app parses)

Parsed by `PC/upgrade/c.java` (V; `RC/a.java:97-219` is an older copy). Expected product string comes from `f/k/e/d.java:156-185` (V): Inspire 1 family "WM610", P3 Advanced/Professional (litchiS/litchiX) **"P3XS"**, P3 Standard (litchiC) **"P3C"**, P3 4K (P34K) **"P3XW"**, OSMO "OSMO", others as listed. RC packages use "C1" (`RC/b.java:847-849`).

| Offset | Size | Field (jadx name) | Use |
|---|---|---|---|
| 0 | u32 | `a` | read, unused here (U) |
| 4 | u16 | `b` | read, unused here (U) |
| 6 | u16 | `c` header length incl. trailer | must equal `64 + 52*count + 2` (`PC/upgrade/c.java:119,206`) |
| 8 | u32 | `d` | U |
| 12 | 16 B string | `e` | NUL-terminated (`:208`), U |
| 28 | 16 B string | `f` product id | must `equalsIgnoreCase` the expected id (`:113,209`) |
| 44 | u16 | `g` entry count | `:210` |
| 46 | 18 B | `h` | copied raw, U |
| 64 + 52n | 52 B | entry n | below |
| `c-2` | u16 | CRC16 | over bytes `0..c-3`, via `GroudStation.native_calcCrc16`, stored LE (`:115-119`) |

Entry (52 B, `PC/upgrade/c.java:574-589`, `RC/a.java:205-219`):

| Offset | Size | Field | Notes |
|---|---|---|---|
| 0 | u8 | bits0-4 device type, bits5-7 module id | module id is also the receiver id for the legacy sender (`LG/a.java:314`) |
| 1,2,3 | u8 x3 | `c`,`d`,`e` | meaning U |
| 4 | u32 | version | non-camera shown `b7.b6.b5.b4`; camera shown `b7.b6.(u16@4/100).(u16@4%100)` (`:591-597`); compared to the device's current version (`RC/b.java:741-753`) |
| 8 | u32 | data offset in the package | `seek` base (`LG/e.java:79`) |
| 12 | u32 | data length | |
| 16 | u32 | `i` | U |
| 20 | 16 B | MD5 of the module data | optional check over `[off, off+len)` (`PC/upgrade/c.java:522-547`), sent in TranslateComplete |
| 36 | 16 B | `k` | purpose U (not read or recorded) |

- V: min file length 272 (`:99`). Module id string is `DDMM` = device type 2 digits + module id 2 digits (`pilot/upgrade/FirmwareVersion.java:20-24`).
- V: server-side pack list names modules `m<DDMM>` (e.g. m0900, m1900, m2000-m2003) with `version&flag` strings plus `packurl`/`rcurl`/`rc1url`/`rcversion` (`pilot/publics/model/DJIUpgradePackListModel.java:57-127`). P3 mapping: litchiX to `versionlistx`, litchiS to `versionlists`, litchiC to `versionlistc`, P34K to `versionlistxw` (`:232-273`). V.
- V: P3 module lists the app compares (`pilot/upgrade/f/`): P3 Advanced `x.java:40` and P3 Pro `z.java:40` = 0305, 0306, 0400, 0900, 1100, 1101, 1200-1203, 1500, 1700, 1701, **1900**, 0100, 0101; P3 Standard `w.java:44` = 0400, 1100, 1101, 0100, 0101, 0305, 0306, 0700, 0900, 1200-1203, 1400, 2700 (no 1900); P3 4K `v.java:44` adds 1700, 1701. P3 RC packs: `y.java:40` (P3 Adv RC) 1300, 1400, 1401, 1600, 1601, **2000**, 2001, 2002; `a0.java:40` (P3 Pro RC) adds 1301.
- V: P4 engine uses a different container (tar or multi-file with `.cfg.sig`/`_verify.xml`, `DB/constants/DJIUpDeviceType.java:34-36`); not P3, names only.

### 2.2 Flow R: RC (ground) module push (`RC/b.java` + `RC/c.java`)

Ordered per module (V):
1. Module list: if DM368_G answers GetVersion use `{DM368_G 13, TRANSFORM_G 16, FPGA_G 20, OSD 14}` else drop DM368_G (`RC/b.java:46-47,429-438`). Package from file `RC_FW_V<ver>.bin` (`:86-87,845-846`), header product "C1" (`:847-849`).
2. For each type pick matching entries, push when `current < package` or when forced; OSD entry is moved to the front when `H==1` (`:694-809`, `:764-767`). Totals counted from entry length (`:782-784`).
3. `RC/c.java` per module (retry limit 5 per step, `:48,415,443,525,546,616`):

| Step | Cmd | Receiver | Wait/next |
|---|---|---|---|
| a (only when flag `r` set) | RestartDevice delay 1000 (`:429-431,526`) | module type, id 0 | then step b |
| b | RequestUpgrade 0x07 (`:547`) | module type, id 0 | 50 ms then c |
| c | GetDeviceStatus 0x0C, expects mode bit0 = 1 else re-send b (`:226-236`) | same | |
| d | RequestReceiveData 0x08 with module length (`:515`) | same | ack u16 = block length `n` (`:237-246`) |
| e | (FPGA_G only) wait 130000 ms before data, with simulated progress (`:40,571-575`, I: erase time) | | |
| f | TranslateData 0x09 seq 0.. in `n`-byte blocks, each acked, resend on non-ack up to 5 (`:413-420,554-611`) | same | FM_NONSEQUENCE resync to `failSeq+1` (`:588-608`) |
| g | TranslateComplete 0x0A with MD5 (FPGA_G: u16 sum) (`:441-448`) | same | retry <5 |
| h (only when flag `r` set) | RestartDevice delay 0 (`:526`), then wait 2200 ms (`:41,162-183`) | same | |
| i (only when flag `r` set) | GetDeviceStatus, expects mode 0 (`:278-293`) | same | module done |

- V: flag `r` is set only for the OSD entry when `H==1` (`RC/b.java:764-767`, `RC/c.java:480-482`); without it step g completes the module (`RC/c.java:523-533`, `b(0)`). Meaning of `H` is U.

4. Between modules: tip START (OSD `SetUpgradeTip`), wait 2600 ms, next module (`RC/b.java:67,682,1346-1366`); on completion tip SUCCESS (`:1329-1340`); on error FAIL (`:1601`). A 10000 ms wait and `a(FPGA_G,true)` follow an FPGA_G step when none remain (`:79,1352,404-405`, meaning U).
5. Extra pause: when the RC flow-control flag is set the handler re-queues the message after 6000 ms (`RC/c.java:42,199-206`; `TB/e.java:530-533` for TransferFile). V.

- V: the RC flow sends TranslateData with receiver type 20 (FPGA_G), id 0 (`RC/c.java:416`). I: `docs/ground-upgrade-path.md` shows m1400 has no 0x09 handler and ignores it, so another RC component must consume them; which one is U.
- V: no air-side module (types 1, 3, 4, 8, 9, 19) appears in the RC type arrays.

### 2.3 Flow L: legacy per-module sender (`LG/b.java`, `LG/a.java`, `LG/e.java`)

- V: no static caller of `LG/a`/`LG/b` in the decompiled tree (grep over all sources); reflection or dead code is U. Sender thread name `...p3cupgrade.UpgradeTranslateData` (`LG/e.java:126`) points at P3C (I).
- V sequence (`LG/b.java:260-345,385-435`): RequestUpgrade (x5, retry delay 1000 ms) then 5000 ms, GetDeviceStatus (x10; success moves on, mode not checked in this class), RequestReceiveData (length = entry length), TranslateData loop (`LG/e.java:74-122`: block = ack length, per block `x(…,20,1000)` = 20 attempts, 1000 ms apart, progress `i*100/total`), TranslateComplete (MD5), RestartDevice (type 0, delay 1000) then 8000 ms, GetDeviceStatus expecting mode 0, done. Receiver = device type + module id from the entry.
- V: variant `LG/a.java` restarts with delay 0 and waits 2200 ms (`:440,159`), retry cap 5, pauses 4000 ms on flow control (`:30,187`).

### 2.4 Flow T: P4-era engine (`DB/statemachine/*`)

- V: scope is the `DJIUpDeviceType` list (wm220..wm335, rc00x/rc2xx, rm500, wm100ac, gl811): no P3.
- V: default target `DM368` (8) id 1 (`DB/model/a.java:42-43,145-147`; `DB/statemachine/e.java:71-74`).
- V steps (`DB/statemachine/e.java`):
  1. Preconditions: motors not up with RC link OK (`DB/statemachine/b.java:39-41`), battery minimum 40 (MC) / 30 / 20 (RC) percent by device (`:88-115`, `:43-79`); returns -2 motors up, else required level or 0.
  2. RequestUpgrade `x(…,3,2000)` (`:628-630`). Ack must show V1 or FTP; big-package for tar, multi-file when required (`:273-289`). Then sleep 5000 ms (`:293`).
  3. RequestReceiveData (`:599-620`): length = package size; tran method FTP only for wm100ac over Wi-Fi link, else V1 (`:611-615`); file method multi-file or big-package (`:601-605`). `x(…,3,2000)`.
  4. V1 path (`:664-688`): block = ack u16 (`:691`); packets sent unacked; every `z`-th sent with ack (z default 4000; 200 / 1000 / 1 / 250 for specific products, `:667-677`; sleep `A` ms between packets, default 2, `:80,795-800`); progress pushed to OSD (`:869`). Multi-file: `dji.midware.k.b` sends each file through TransferFile (2.5). Reverse-link switch for wm240 (`:720-729`).
  5. FTP path (`:736-768`): connect ip:port from ack, login `anonymous`, cd to ack dir, upload with connection timeout 20000 ms; retry up to 20 times, 1000 ms apart (`:932-951`).
  6. TranslateComplete with MD5 of the tar, timeout 10000 (`:709-717`).
- V status handling (`DB/statemachine/c.java:261-342`): step Verify shows "verifying", UserConfirm shows "user confirm", Upgrading maps progress (100 shown as 99), Complete: send ControlUpgrade `StopPush` to the pushing device, mirror to OSD, report reason (`:322-342`). The app never sends ControlUpgrade `Start` in this engine (only Stop/StopPush: `f.java:88`, `c.java:273,333`); the device runs UserConfirm on a timer (I).
- V: restart-timeout from `DataNotifyDisconnect` (device announces disconnect time, doubled) drives a fake progress timer (`:181-193,162-171`).

### 2.5 TransferFile engine (`TB/*`, `midware/k/b.java`)

- V: multi-file driver `midware/k/b.java:196-205`: each file as TransferFile type FIRMWARE with 1-byte extra `[0x01]` (`:39,56`); runs sequentially (`:67-74`).
- V per file (`TB/e.java`): Request (`:476-480`); ack sets packet length (default 40), window (default 5), verify type, protocol (`:86-87,111-120`). Protocol 1 (`TB/a.java`): sliding window, per-packet resend after `packTimeoutMillisecond`, abort after `packSendRetryMaxTimes`; ack `[ackSeq,nextConsecutive]` (`:106-191`). Protocol 2 (`TB/b.java`): DATA_EXTENDED, ack carries lost ranges, resend list, constants 1000 / 30000 / 400 ms (`:17-24`), abort reason "wait ack timeout" (`:109`) with a 30000 ms timer armed at `:184` (I: linked). After last ack: Verify with MD5 (whole file) or CRC16 (native CRC16 over the file), `transferVerifyMaxTimes` tries with 1000 ms retry (`:510-528,129-135`).
- V strategy table (`TB/FileTransferStrategies.java:8-18`): fields `packSendPeriodMax/MinNanosecond, packSendRetryMaxTimes, packTimeoutMillisecond, transferVerifyMaxTimes`:

| Strategy | max period ns | min period ns | retries | timeout ms | verify tries |
|---|---|---|---|---|---|
| APP_AOA_RC_SDR_UAV | 1000000 | 250000 | 30 | 1000 | 3 |
| APP_TCP_3399_TCP_RC_SDR_UAV | 1000000 | 1000000 | 30 | 2000 | 1 |
| APP_TCP_3399_TCP_RC | ECLAIR (U) | ECLAIR (U) | 20 | 1000 | 1 |
| APP_AOA_RC_WIFI_UAV | 2000000 | ECLAIR (U) | 10 | 5000 | 1 |
| APP_AOA_RC | 1000000 | 1000000 | 30 | 3000 | 1 |

- V: strategy picked per product by `DJIUpDeviceType.getStrategy` (`DB/constants/DJIUpDeviceType.java:84-96`); default `APP_AOA_RC_WIFI_UAV` (`TB/e.java:69`). Flow-control from the RC (`DataRcGetPushFlowControl`) pauses sending (`TB/e.java:530-533,725-730`).

### 2.6 Flow C: camera-hosted (aircraft pushes, app confirms)

V sequence from the app side (`pilot/publics/objects/DJIBaseActivity.java`; same code in `pilot2/DJIFragmentActivityNoFullScreen.java:315,445`):
1. Camera pushes 0x42 (camera layout 1.7). On step change to **Ack** (2) the app sends ControlUpgrade `Start` (1) to the camera (`:583-593,367-369`).
2. Camera pushes Progress / End; app shows end cause (`:322-365`).
3. On `Success` the app waits `upgradeRestartTime` (5 s, 1 s ticks) then sends ControlUpgrade `Restart` (5) to the camera (`:167-177`).
- I: the package must already be on the camera side (SD card) for this flow; the camera upgrade engine reads it (`docs/air-id-and-stream-survey.md:38-45`). V: no code in the classes read here copies a package to an SD card.
- I: step Check/Ack are the camera's own verify and "ask user" states, matching Verify/UserConfirm in the Common layout.

### 2.7 Other

- I: `dji/data/upgrade/logic/a.java` is the flight-data (map/NFZ data) upgrade, not firmware: same RequestUpgrade ack check (`:133-146`), requires copy-data support (`:139-143`), DataUpgrading status. V for the code, I for the purpose.
- V: `GetPushCheckStatus`/`SetStartModuleChecking` exist in the COMMON table (`CmdSet.java:242-245`); not traced as part of the push path (U).

## 3. How the package reaches the aircraft, by module

| Path | Evidence | Modules | Tag |
|---|---|---|---|
| RC DUML, TranslateData | Flow R (2.2) | ground: DM368_G (m13xx), TRANSFORM_G (m16xx), FPGA_G (m2000-m2002), OSD (m14xx). RC-only | V |
| Wi-Fi/FTP (anonymous) | `DB/statemachine/e.java:736-768`; legacy `PC/upgrade/b.java:124-164` (login anonymous/`dji`, no callers) | whatever device returns ip/port/dir in the 0x08 ack; socket provider binds the Wi-Fi network (`M/l/a.java`) | V mechanism; module set U |
| TransferFile 0x2A | Flow T multi-file (2.5) | receiver from `DB/model/a.java` (DM368 id 1 default) | V mechanism; not shown used for P3 |
| SD card | camera-hosted (2.6) + SD error codes (1.8) | aircraft modules via camera engine | I |
| Per-module DUML push to the aircraft | `LG/*` (2.3) | any type+module from package entry | V code, no callers (U use) |

- **Air FPGA (m1900, type 19)**: V: listed in the P3 module lists (`pilot/upgrade/f/x.java:40`, `z.java:40`), version query `DeviceType.FPGA` (`PC/DJIUpgradeControl.java:791`), field `m1900` in the pack list (`DJIUpgradePackListModel.java:102`). U: how bytes reach it. No app class sends 0x07-0x0A to type 19. `docs/fpga-upgrade-path.md` shows m0900 handles Enter/Confirm/Finish for receiver 0x13 and has no TranslateData handler, so the data stage does not pass through m0900 (V there). I: the camera-hosted engine distributes it (`docs/air-id-and-stream-survey.md:40-45`, which also notes its type-19 routing as untraced).
- **Ground FPGA (m2000-m2002, type 20)**: V: pushed by the app over RC DUML with the RC flow's FPGA_G special-casing (u16 byte-sum instead of MD5, 130 s pre-data wait, `RC/c.java:349-352,563-575,624-653`). Data consumer on the RC U (m1400 ignores 0x09: `docs/ground-upgrade-path.md` Q2).
- **m0900 (type 9)**: V in pack list and P3 lists; not pushed by any traced app flow. Air MCU modules 0305/0306/0400/1100/1200-1203/1500/1700/1701: same status as 1900 (U).

## 4. What the app learns before it will push

- V: version list built in `PC/DJIUpgradeControl.java:772-830`: GetVersion to DM368_G, OSD, TRANSFORM_G, FPGA_G, WIFI_G(0), SINGLE(0,1), CAMERA(0,1,4), FLYC, BATTERY, GIMBAL(0..3), CENTER, DM368(0,1,7), OFDM, DIGITAL(0..3), TRANSFORM(0,1), FPGA, WIFI(0). First probe is OSD (`:741`, timeout 1000, retry 1). Module id goes in the receiver-id field (`P3/DataCommonGetVersion.java:248-251,262-270`).
- V: component version check (`pilot/upgrade/b.java:127-147`): per `DDMM`, `GetVersion` with `start(…,500,5)`; DM368_G/FPGA_G/TRANSFORM_G/OSD and camera 0/1 queried without module id. Camera 0/1 and FLYC module 5 use the *loader* version, others the *firmware* version (`:51-59`). Ground modules are rejected when the ack's loader byte 2 differs from the module id (`:62-69`). Version integer = `b0*2^24 + b1*2^16 + b2*2^8 + b3` (camera 0/1: last two parts concatenated) (`pilot/upgrade/FirmwareVersion.java:26-36`).
- V ack getters (`P3/DataCommonGetVersion.java`): hardware string 16 B at index 1 (`:119-130`), loader bytes 17..20 (`:144-163`), firmware bytes 21..24 printed `b24.b23.b22.b21` (camera: `b24.b23.(u16@21/100).(%100)`, `:79-101`), flags u32 at 25: bit31 production, bit30 safe-upgrade supported (`:132-142`). The index base against the ccode is U (getters start at 1 while other getters start at 0 after ccode stripping); see `scripts/re/get_identity.py`.
- V: product identity: GetVersion to `OSD` populates the product type (`P3/DataCommonGetVersion.java:196-225`); package must carry the matching product string (2.1). P4 engine reads the hardware string and matches substrings `wm330`, `wm331`, `rc001`, `de01`, ... (`DB/statemachine/h.java:98-125`, `:295-330`).
- V connection gates: `ServiceManager.isRemoteOK()` and `isOK()` for aircraft components (`pilot/upgrade/f/x.java:44-46`); RC components need only `isOK()` (`f/a0.java:45`); motors not up (`DB/statemachine/b.java:39-41`, `P3/DataUpgradeSelfRequest.java:89-95`); battery minimum (2.4); `DataCommonRequestUpgrade` ack flags (1.2).
- V: size/precondition errors the device can return: Ccode 233 SDCARD_FULL, 232 SDCARD_NOT_INSERTED, 249 UPDATE_MOTOR_WORKING, 251 DEVICE_LOW_POWER, 246 FIRM_MATCH_WRONG, 245 UPDATE_WRONG, 242 FM_CRC_WRONG.

## 5. Reproducing it from our own code (plan only, nothing sent)

**This is a plan. No frame below has been sent to any device. Nothing here authorises flashing; vendor images are signature-checked (`libUpgradeVerify`, not analysed) and the check location (app vs device) is U.**

Prerequisites (all V from the app): link up (RC and aircraft OK), motors off, battery at or above 40 percent, package for this exact product (header product string equal), package module versions newer than installed unless forced.
Sender is type 2 (APP), sender id 0; request, NEEDACK YES: byte 8 = `0x40`, cmdset 0.
Tooling gap: `scripts/re/duml_proto.py` and `app/packages/duml/lib/src/packet.dart` define device types only up to 6/10/14; add 1 camera, 8 DM368, 9 OFDM, 13 DM368_G, 14 OSD, 16 TRANSFORM_G, 19 FPGA, 20 FPGA_G (`M/data/config/P3/DeviceType.java:6-30`). Catalog names exist (`duml_catalog.py:10-30`); payload builders for the structs in section 1 do not.

Candidate A (generic block push to the camera main, receiver type and id U; P4 engine uses DM368/1, P3 evidence favours CAMERA/0, I):

| # | Frame (receiver) | Set/Id | Payload | Wait / expect |
|---|---|---|---|---|
| 1 | GetVersion (each type in 4) | 00/01 | empty | read-only; record versions |
| 2 | RequestUpgrade (T) | 00/07 | `00` + 8 x `00` | ack: tran bits, file bits; stop if neither V1 nor FTP |
| 3 | GetDeviceStatus (T) | 00/0C | `00` | repeat until mode bit0 = 1 (<=5 tries) |
| 4 | RequestReceiveData (T) | 00/08 | `00`, length u32 LE, 6 x `00`, tran bits (`01`), file bits (`04` if big package else `00`) | ack u16 = block length N |
| 5 | TranslateData (T) x ceil(len/N) | 00/09 | `00`, seq u32 LE, size u16 LE, data | per-packet ack; on ccode 240 resume at ack seq + 1; give up after 5 failures per packet |
| 6 | TranslateComplete (T) | 00/0A | `00` + MD5 (16 B) of the transferred bytes | timeout 10 s; ccode 0 |
| 7 | observe 0x42 pushes from the camera | 00/42 | none to send | Check, Ack, Progress, End (1.7) |
| 8 | ControlUpgrade Start (camera) | 00/41 | `01` | on camera step Ack |
| 9 | ControlUpgrade StopPush | 00/41 | `04` | after End (app does this in Flow T) |
| 10 | ControlUpgrade Restart (camera) | 00/41 | `05` | after End = Success, 5 s later (Flow C) |

Candidate B (TransferFile, multi-file engine; used by newer products): GetVersion; RequestUpgrade (as 2); RequestReceiveData with file method multi-file (`02`) and tran method V1; then per file: TransferFile REQUEST (`01`, size u32, name+NUL, type `01`, extra len `01`, extra `01`), DATA or DATA_EXTENDED per the ack protocol with window and packet length from the ack, VERIFY (`03` + MD5), then TranslateComplete and steps 7-10. Whether P3 firmware accepts B is U.

Candidate C (ground only, vendor flow R): per module type 13/16/20/14 receiver id 0: RequestUpgrade, GetDeviceStatus, RequestReceiveData, TranslateData xN, TranslateComplete (type 20: u16 byte-sum), RestartDevice (`00`, `00`, delay u32), GetDeviceStatus until mode 0. Bounds from 2.2.

Unknowns that block a faithful P3 replay (U): see section 6.

## 6. Unknown

- U: which flow, if any, GO 4 uses to move a P3 aircraft package: `LG/*` has no callers, T excludes P3, C needs the package already on the camera.
- U: how the file gets onto the camera (SD) for Flow C; receiver type/id for Candidate A.
- U: route of TranslateData frames addressed to type 20 inside the RC, and to type 19 on the air side.
- U: meaning of header fields `0`, `4`, `8`, `46..63`, entry bytes `1..3`, `16`, `36..51`; signature enforcement (`libUpgradeVerify`) and where it runs.
- U: GetVersion/GetDeviceStatus ack index base; GetPushUpgradeStatus item-version offset quirk; AckReceiveFiles overlapping getters.
- U: `ECLAIR` constants in `FileTransferStrategies`; units of start() timeout/retry and RestartDevice delay (I: ms).
- U: whether any device ever sends 0x43 AckUpgradeStop or 0x40 GetPushRequestUpgrade (no app code consumes them beyond the model).
