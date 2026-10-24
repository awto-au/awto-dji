# Read-only identity queries (RC over USB-serial DUML)

Tags: V = verified on hardware, I = inferred, U = untested / unknown.

## Setup
- RC micro-USB: `/dev/ttyACM4` (2ca3:0008), 115200 8N1, RTS=1 DTR=0 set before open.
- Frames: sender 0x0a (PC), receiver wire byte 0x0e (OSD, "1400"), ack=2; framing/CRC reused from `scripts/duml_probe.py`.
- Script: `scripts/re/get_identity.py` (whitelist of queries only; no free-form cmd/payload; receivers limited to 0e/08/0d/06).
- Log: `captures/sessions/<date>/get_identity.log` (tracked - real-hardware data). Raw frames are printed before sending.
- Not sent: aircraft port `/dev/ttyACM11` (silent to DUML, no transport); phone/AOA link.

## Queries
"Verified read-only" = Get/Query name in the o-gs dissector (`comm_dissector/wireshark/dji-dumlv1-general.lua`, `dji-dumlv1-proto.lua`) AND in our catalog (`scripts/re/duml_catalog.py`) AND an APK class with an empty/index-only request payload.

| Query | cmdset/id | Payload | Receiver (APK) | Read-only | Result on RC (rcv 0x0e) |
|---|---|---|---|---|---|
| GetDeviceState | 00/0c | - | any | yes | V: replied, payload `e30000000000` (state, undecoded) |
| GetVersion | 00/01 | - | any (`DataCommonGetVersion`) | yes | V: replied, hw `GL300C`; payload `0010474c333030430000000000000000000007010103001c18054302000000`; fw bytes [24..21] = 24.28.00.03 per APK layout (I) |
| GetDeviceInfo | 00/ff | - | DM368 default (`DataCommonGetDeviceInfo`) | yes | V: replied `WM320 A7_LPC1 20170828/00` (ASCII) |
| GetSerialNum BoardNum | 00/51 | 01 | DM368 0x08 (`DataCommonGetDeviceSerialNumber`) | yes | V: no reply from 0x0e |
| GetSerialNum ChipId | 00/51 | 02 | same | yes | V: no reply from 0x0e |
| GetSerialNum ModuleNum | 00/51 | 03 | same | yes | V: no reply from 0x0e |
| GetSerialNum FlycNum | 00/51 | 04 | same | yes | V: no reply (FC-only; reply layout skips 6 bytes then ASCII) |
| RcGetName | 06/09 | - | OSD 0x0e (`DataRcGetName`) | yes | V: no reply |
| RcGetMaster | 06/07 | - | OSD 0x0e (`DataRcGetMaster`) | yes | V: replied `00` (mode bits 7:6 = 0, connected bit 5 = 0 per APK decode: RC reports not connected to a master) |
| RcGetConnectMaster | 06/0d | - | OSD 0x0e (`DataRcGetConnectMaster`) | yes | V: no reply (reply would be id u32 + name 6B + pairing pw u16; pw elided in script output) |

## Receivers tried
- 0x0e (OSD/RC): answers 00/0c, 00/01, 00/ff, 06/07 only.
- 0x08 (DM368), 0x0d (DM368_G), 0x06 (RC type): all 10 queries each, no reply (V).
- No RC serial, aircraft serial, camera, gimbal or battery ID was returned by any query.

## Deliberately not sent
- Set/Write/Control/Loader/Update/Reboot/Reset/Calibrate/Unlock/Activate/file transfer: none in script.
- General 0x30 Encrypt Config state queries (`comm_og_service_tool.py`): carry board SN + cipher key material, skipped.
- RC 0x0b Password Get: pairing secret.
- FLYC 0x03/0x34 GetPlaneName, GIMBAL 0x04/0x1f GetSerialParams (payload `00 02`), camera/gimbal GetVersion: would be forwarded to the aircraft; not tried.

## Aircraft: safe queries once a transport exists
- To FLYC (rcv 0x03): COMMON 00/01 GetVersion, 00/ff GetDeviceInfo, 00/51 GetSerialNum payload 04 (FlycNum), FLYC 03/34 GetPlaneName.
- To GIMBAL (0x04): GIMBAL 04/1f GetSerialParams payload `00 02` (APK `DataGimbalGetSerialParams`); 00/01 GetVersion.
- To CAMERA (0x01): 00/01 GetVersion, 00/ff GetDeviceInfo.
- Battery: dissector has p3 batt proto (SBS, not DUML); needs separate verification (U).
- Re-verify each against dissector + catalog before sending; the FLYC serial reply layout is `len(u16) + 4B + ASCII` (APK, I).

## Reproduce
```
python3 -I scripts/duml_probe.py --selftest
python3 -I scripts/re/get_identity.py --dry-run --receivers 0e,08,0d,06
python3 -I scripts/re/get_identity.py --port /dev/ttyACM4 --receivers 0e
python3 -I scripts/re/get_identity.py --port /dev/ttyACM4 --receivers 08,0d,06
```
- Run 2026-10-24T11:05+11:00; DJI Assistant must be closed (holds the port).

## Open
- RC answers GetVersion/DeviceInfo only; serial likely needs a different path (FW layer that serves 0x51 may be the DM368/aircraft side, not the LPC1765 RC MCU) (I).
