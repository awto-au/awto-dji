# Ground USB firmware: interface modes and PC access

2026-10-24. V = verified in the named artifact; I = interpretation; U = unresolved.
Read-only static analysis plus cached USB descriptor inspection. No mode changes,
DUML requests, firmware writes or USB vendor requests were sent during this review.

## Result

**V: C1 `m1601` contains executable USB peripheral-mode setup and multiple bulk
interface descriptors, in addition to the host/phone path.** This is a concrete
candidate for PC access. **U:** which of these paths the owner's GL300C implements,
which physical connector reaches it, and how it can be selected on that hardware.
There is no demonstrated factory-mode PC connection yet.

Artifact: `firmware/unpacked/C1_FW_V01.06.0000/C1_FW_V01.06.0000_m1601.bin`,
module version 02.00.0006, SHA-256
`703d211d04bafa27f7c8fa95ec336d814440a7950740562bb28601bfdaa764a0`.
Its `.ini` names `IG810 LB2_CY2014_RX ground`. The exact silicon on the owner's RC
has not been confirmed. [duml-protection.md](duml-protection.md) records the matching
APK/firmware SIMPLE XOR implementation.

Infineon's [FX3 Firmware API Guide](https://community.infineon.com/gfawx74859/attachments/gfawx74859/jpusbsuperspeed/3587/1/FX3APIGuide.pdf)
documents separate USB host, peripheral and OTG operation. It also documents descriptor
registration and GPIO input APIs; the names attributed to stripped functions below
are inferred from their call signatures and behavior, not recovered symbols or
byte-exact SDK binary matches. Chip capability alone does not establish board support.

## Descriptors and the code that selects them

The stored device descriptor is at file `0x28494` / VA `0x40030460`, initially
USB 2.0, device class 0, VID:PID `2ca3:1004`, one configuration. Startup code
changes VID/PID bytes in RAM before registering it. Using the initial descriptor
alone would miss one of the identities.

All endpoints below are **bulk**. IN/OUT are relative to the USB host: IN means
data to the PC when the PC is host. All configurations have value 1 and self-powered
attribute `0xc0`. Endpoint payload roles are not established by descriptors alone.

| Descriptor file offset / VA | Interfaces | Endpoint addresses | Max packet |
|---|---|---|---|
| `0x109bc` / `0x40011780` | IF0 alt0 class/subclass/protocol `ff/f0/00`; IF1 alt0 no endpoints, alt1 `ff/f0/01` | IF0 OUT `01`, IN `81`; IF1 alt1 OUT `03`, IN `83` | 512 bytes |
| `0x10a1c` / `0x400117e0` | Same layout | Same | 64 bytes |
| `0x10afc` / `0x400118c0` | IF0 alt0 `ff/00/00` | OUT `02`, IN `86`, OUT `04`, IN `88` | 512 bytes |
| `0x10a9c` / `0x40011860` | Same layout | Same | 64 bytes |
| `0x10adc` / `0x400118a0` | IF0 alt0 `ff/00/00` | OUT `02`, IN `86` | 512 bytes |
| `0x10b5c` / `0x40011920` | Same layout | Same | 64 bytes |

V: routine `0x400068b8` registers these descriptors through `0x4001b850`
(I: `CyU3PUsbSetDesc`). Descriptor-type arguments 1/2/3/4/5/8 and the
device/configuration/string pointers correspond to the SDK's registration scheme.
The 512-byte and 64-byte configurations are registered for high and full speed.

## Mode selection

These names are local descriptions, not DJI's original variable names:

- **P:** GPIO 41 (`0x29`) input, read at `0x40008cb8`, normalized and stored at
  `0x40031818`. Getter `0x40008de8` returns P.
- GPIO 42 (`0x2a`) is also read, at `0x40008cdc`, and cached at `0x40031817`.
  Its complete role is not resolved here.
- **K:** a stored configuration field loaded into `0x400339e4` at `0x4000e398`.
  Getter `0x4000e410` tests whether it equals 1.
- **M:** getter `0x40008e08` returns true when K equals 1 or P is high.

V: the configuration loader at `0x4000e2dc` reads a 16-byte record from storage
address `0x60000` through `0x400042dc` / `0x4000f170`; validates checksums, a marker,
and a 0/1 field; and supplies K from record offset 4. Invalid records are rebuilt
with that field 0 and written through `0x400042e0` / `0x4000f0b4`.
I: this is persistent configuration; the precise external storage device is not
identified by this trace.

| Inputs | Verified descriptor setup | Startup interpretation |
|---|---|---|
| P low, K=0 (M=false) | `2ca3:1004`; IF0 `01/81`, IF1 alt1 `03/83` | Initializer table at `0x40011710` directly calls peripheral setup. Nearby `MFI` / `iAP Interface` strings suggest an Apple accessory personality (I), not an established PC service mode. |
| P low, K=1 (M=true) | Peripheral setup, when invoked, uses `2ca3:1004`, IF0 `02/86/04/88` | Initializer table at `0x40011734` calls OTG setup first. Host/peripheral selection has further runtime gates; setting K does not itself prove PC enumeration. |
| P high (M=true) | `0547:1002`, IF0 `02/86` | Startup calls peripheral setup directly. This identity also appears in the aircraft Linux `68013.ko` driver analysis, so it could be an internal processor-facing interface; physical routing remains U. |

Descriptor registration locations:

- `0x400068ec` through `0x4000691c`: first branch writes `2ca3:1004`.
- `0x40006940` / `0x40006954`: IF0/IF1 descriptor pair.
- `0x40006b58` through `0x40006b9c`: conditional `0547:1002` versus `2ca3:1004`.
- `0x40006bcc` / `0x40006be0`: four-endpoint pair when P is low.
- `0x40006dc0` / `0x40006dd4`: two-endpoint pair when P is high.
- `0x40004534` onward: startup selects initializer paths using M and P.
- `0x40004474`: OTG-style initialization; callback at `0x40004384` can reach
  peripheral setup at `0x40004464`. Specific event meanings remain inferred.

## Service/configuration commands present in the module

V: dispatch routine `0x40007c70` compares frame command-set/ID bytes against
8-byte records and calls their handler. Tables at `0x40030480` and `0x40030498`
include the following. Names are interpretations of traced handlers.

| Set/ID | Handler | Observed behavior |
|---|---|---|
| `08/01` | `0x40007618` | Configuration setters; selected fields go through `0x4000e1c4`, which writes the record at `0x60000`. |
| `08/02` | `0x400078e0` | Configuration getter; calls `0x4000e160`. |
| `06/3a` | `0x40007588` | Payload branches write configuration field 0 as 0 or 1 through the same setter. |
| `00/01`, `00/0c`, `00/ff` | `0x40007858`, `0x4000780c`, `0x4000755c` | Version, ping, build-information paths. |
| `00/07`, `00/08`, `00/09`, `00/0a` | `0x4000752c`, `0x40007b34`, `0x40007a84`, `0x40007740` | Upgrade-related handlers; not exercised. |
| `00/0b` | `0x400076c4` | Schedules a delayed action through `0x4000772c`, which eventually calls reset-like code (I). |

These are firmware capabilities, **not verified commands for the currently attached
serial port**. Receiver routing, authorization, the active dispatch table and required
state still need tracing. The persistent setter changes the backing record; this
trace does not show immediate refresh of cached K. Reboot/application timing is U.
No configuration-setting commands were sent.

## What the PC can use today

V: the connected controller's **cached** descriptor (`lsusb -v -d 2ca3:0008`,
2026-10-24) is CDC ACM, USB 1.10/full speed, one configuration:

- IF0: CDC control, interrupt IN `81` (16-byte maximum packet).
- IF1: CDC data, bulk OUT `02`, IN `82` (64-byte maximum packet).

The sandbox could not open the device, so that inspection used cached descriptors;
it did not claim interfaces or send application traffic. The USB-ID database's
product label is not reliable model identification. Prior owner-hardware observations
in [p3-usb-observations-2026-10-23.md](p3-usb-observations-2026-10-23.md) establish DUML
query replies on this port at 115200 8N1, RTS=1 / DTR=0 set before opening.

This is a **working PC serial path for the previously verified queries**. It has
different descriptors from the FX3 bulk personalities above. Video forwarding and
full aircraft command routing through it have not been established.

For a future PC bulk transport, discover the live descriptors rather than hardcoding
all endpoints found in firmware. Vendor class `ff` suggests a libusb/WinUSB-style
transport (I); it does not make the interface serial. The PC must see the controller
as a USB peripheral. In the already-observed Android/AOA mode the controller is host,
so a normal PC host connection cannot substitute for the phone without role changes
or an accessory-capable device between them. See Infineon's API guide for role support.

## Remaining work before calling the alternative usable

1. Confirm the USB chip and installed firmware in the owner's GL300C; map its physical
   connectors, USB ID/VBUS wiring and GPIO41/42 connections.
2. Finish the OTG event/role selection and endpoint DMA-to-DUML/video routing traces.
   Establish what each bulk endpoint carries and whether a startup handshake is needed.
3. Trace routing to the configuration getter/setter and read the existing state before
   considering a persistent change. Mode presence is not a reason to write the flag.
4. Validate a peripheral-mode enumeration on that hardware, then implement the PC
   transport against its actual descriptors and captured traffic.

We have found a firmware-supported alternate interface candidate; we have not proved
an externally accessible factory/test mode or a complete PC video/control interface.

## Reproduce

Descriptor inventory, offsets and candidate code references are retained in
[data/fx3-usb-inventory-2026-10-24.json](data/fx3-usb-inventory-2026-10-24.json).

```sh
python3 -I scripts/re/fx3_usb_inventory.py --image firmware/unpacked/C1_FW_V01.06.0000/C1_FW_V01.06.0000_m1601.bin
python3 -I scripts/re/fx3_trace.py --image firmware/unpacked/C1_FW_V01.06.0000/C1_FW_V01.06.0000_m1601.bin --address 0x400068b8 --count 365
python3 -I scripts/re/fx3_trace.py --image firmware/unpacked/C1_FW_V01.06.0000/C1_FW_V01.06.0000_m1601.bin --address 0x40008ca8 --count 35
python3 -I scripts/re/fx3_trace.py --image firmware/unpacked/C1_FW_V01.06.0000/C1_FW_V01.06.0000_m1601.bin --address 0x4000e2dc --count 85
python3 -I scripts/re/fx3_trace.py --image firmware/unpacked/C1_FW_V01.06.0000/C1_FW_V01.06.0000_m1601.bin --address 0x40007588 --count 101
lsusb -v -d 2ca3:0008
```
