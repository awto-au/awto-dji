# USB device emulation and Android/PC proxy research

Date: 2026-10-26
Tracking: [#70](https://github.com/awto-au/awto-dji/issues/70)
Status: research/design, not hardware verification

## Executive finding

For the Phantom 3 Professional GL300C, **the existing Android phone is already a functioning AOA accessory and a bidirectional network bridge**. The project does not need to build another generic AOA transport to get started. It does need to resolve current loss/decoding limitations (especially #64) before describing the recorded telemetry as complete.

For *arbitrary USB device emulation*, the host-side USB ports on a conventional Linux desktop cannot simply be turned into USB peripherals. A peripheral-capable USB device controller (UDC) or dedicated emulation hardware is required.

Three complementary approaches:

1. **Existing phone + awto-dji app**: least work for the DJI AOA *application payload*. No arbitrary USB descriptor/control endpoint ownership.
2. **Raspberry Pi Zero 2 W or other gadget-capable Linux board**: low-cost reconfigurable USB peripheral using ConfigFS / FunctionFS; software USB protocol can be developed on PC and forwarded to the board.
3. **Cynthion + Facedancer**: programmable USB device behavior and USB research/interposition with a controlling PC; hardware/software supported speeds and proxy modes must be checked against intended target.

Rooted Android can be a fourth route **only if the specific phone kernel provides UDC and the necessary gadget-function support**. Root privileges alone do not add missing hardware or drivers.

## 1. Terminology and physical topology

- **USB host** initiates bus transactions and enumerates attached devices. Desktop PC ports normally operate as hosts.
- **USB device/peripheral** responds to enumeration, supplies descriptors and handles endpoint traffic.
- **USB OTG/dual-role** controllers can potentially implement either role; hardware capability and kernel driver support both matter.
- **AOA** (Android Open Accessory) is a protocol in which an external USB *host* discovers/configures an Android device to act as a USB accessory, and the Android application opens streams to the accessory.
- **Application-level proxy** forwards data *after* the USB stack has already established the connection; it does not necessarily expose or relay the USB descriptor/EP0 stage.
- **USB device emulator** controls descriptors, vendor/class-specific setup requests, and endpoint payloads.
- **USB man-in-the-middle/interposer** sits between an existing USB host and USB device, requiring appropriate upstream device-facing and downstream host-facing interfaces or specialized hardware.

These are not interchangeable capabilities.

### Existing known-good direction

```text
DJI GL300C USB-A (USB host)
           |
        USB cable
           |
Samsung S9 / LineageOS (Android AOA accessory)
           |
    awto_dji_app
    AoaTransport / AoaMux
           |
      Wi-Fi (TCP/UDP)
           |
Linux desktop: aoa_relay_server.py, DUML commands, capture and analysis
```

This topology is already documented in [phone-bridge-operator-guide.md](phone-bridge-operator-guide.md). The PC can inject DUML through an existing command FIFO and inspect received data; it **cannot directly control the phone's EP0 descriptors or the AOA negotiation** through that path.

## 2. Existing awto-dji implementation and pitfalls

- `app/awto_dji_app/lib/transport/aoa_transport.dart` opens the Android accessory and routes AOA bytes.
- `app/awto_dji_app/lib/transport/aoa_mux.dart` parses USB content; it is not USB bus-level enumeration.
- `app/awto_dji_app/lib/debug/tcp_relay.dart` forwards channel-tagged messages and supports reverse command injection.
- `app/awto_dji_app/lib/debug/udp_raw_relay.dart` sends raw incoming chunks independently to the PC.
- `scripts/re/aoa_relay_server.py` decodes received data, accepts hex-encoded DUML commands via `tmp/aoa_send.fifo`, and logs independently derived frames.
- `docs/phone-bridge-operator-guide.md` covers adb wireless access, installation, and intent-based operation.

**Important correctness note:** issue [#64](https://github.com/awto-au/awto-dji/issues/64) reports that the envelope-only mux discards 32-42% of raw bytes in the captured sessions and misses valid unwrapped DUML frames. Do not assume current TCP demultiplexed output is lossless. Compare it with independent raw UDP and/or live PC captures; track the decoder fix under #64. Issue [#23](https://github.com/awto-au/awto-dji/issues/23) already scopes previous framing work. Issue [#65](https://github.com/awto-au/awto-dji/issues/65) separately investigates possible idle/shutdown behavior.

## 3. Candidate software and hardware

| Candidate | Role | Need root/admin? | Descriptor/EP0 control | Generic vendor endpoints | PC interface | Principal limitation |
|---|---|---|---|---|---|---|
| awto-dji app on Android | Existing AOA application proxy | No root | No: Android manages its side of AOA | Not arbitrary USB gadget endpoints | Wi-Fi TCP/UDP + adb | AOA data only; parser correctness and reconnect issues |
| DJI Android Bridge App | DJI SDK remote bridge | Normally no root | No | Not a generic USB device emulator | DJI SDK-specific network bridging | Must inspect repository/API version and P3 compatibility |
| Android USB Gadget Tool | Rooted phone gadget setup | Root; compatible kernel | Changes kernel-supported gadget descriptors/functions | Only if supporting function is present | Phone software, possibly network | UI/configuration tool, not a generic endpoint emulator |
| Linux ConfigFS + FunctionFS | Linux gadget userspace function | Administrative setup; kernel support | ConfigFS gadget setup, FunctionFS userspace protocol handlers | Yes for implemented endpoints/functions | TCP, local sockets, or direct program | UDC mandatory, implementation/latency constraints |
| Raspberry Pi Zero 2 W | Linux USB-device hardware | Admin on Pi | Yes, within gadget framework | Yes using FunctionFS/custom functions | Wi-Fi, SSH, network socket | USB device-side port must be correct; check throughput |
| Cynthion / Facedancer | Protocol-research USB peripheral emulator | No Android root | Programmable | Yes, subject to Facedancer backend/hardware limits | PC-driven control API | Verify high-speed/bulk throughput, endpoint/timing needs |
| Cynthion USB proxy tooling | USB traffic observation/interposition | Not applicable | Depends on mode | Observes/possibly modifies USB data | Dedicated hardware + PC tools | Not the same as merely presenting a synthetic device |

This is a **capability comparison for research**, not a claim that each item has been bench-tested in awto-dji.

### Relevant upstream references

- [DJI official Android Bridge App](https://github.com/dji-sdk/Android-Bridge-App): compare architecture and supported SDK/aircraft; SDK-mediated bridging should not be mistaken for fully raw USB proxying.
- [Android USB host/accessory documentation](https://developer.android.com/develop/connectivity/usb): AOA/API distinction and permissions.
- [USB Gadget Tool for Android](https://github.com/tejado/android-usb-gadget): gadget configuration on supported rooted Android devices; verify maintained status and device-specific kernel prerequisites.
- [Linux ConfigFS gadget documentation](https://docs.kernel.org/usb/gadget_configfs.html): descriptor and function setup.
- [Linux FunctionFS](https://docs.kernel.org/usb/functionfs.html): userspace endpoint handling with supporting gadget kernel.
- [Raspberry Pi USB gadget tooling](https://github.com/raspberrypi/rpi-usb-gadget): useful starting point for Pi gadget setup; check model and connector.
- [Cynthion documentation](https://cynthion.readthedocs.io/): USB research device.
- [Facedancer](https://github.com/greatscottgadgets/facedancer): Python-facing USB device emulation concepts.

## 4. Can we do this with the existing phone?

Possibly for more than AOA, but establish the facts first. On the Samsung S9/LineageOS test phone, **non-destructive** inventory:

```sh
adb shell getprop ro.build.version.release
adb shell 'ls -ld /config/usb_gadget /sys/class/udc 2>&1'
adb shell 'ls /sys/class/udc 2>&1'
adb shell 'ls /config/usb_gadget 2>&1'
adb shell 'cat /proc/config.gz 2>/dev/null | gzip -dc | grep -E "CONFIG_USB_(CONFIGFS|F_FS|GADGET)="'
```

Absence of `/proc/config.gz` is inconclusive. Confirm current SELinux, USB gadget configuration and permissions without assuming root access. **Do not unbind the active USB gadget** on the only phone while relying on its ADB/USB connection for recovery. Prefer Wi-Fi ADB plus a spare device if testing changes to the active gadget configuration.

If FunctionFS is available, prototype a single read-only endpoint/control-request service. Custom AOA-identity emulation requires reproducing the actual host-controller handshake and descriptors, not merely setting matching manufacturer/product text.

### Candidate phone: Pixel 3 XL (2026-10-26, #70)
- **V (checked on device):** bootloader shows unlocked, not rooted; reachable over USB and over WiFi adb (`adb tcpip 5555`, lost on reboot; Developer Options "Wireless debugging" persists).
- **V:** stock kernel has `CONFIG_USB_MON` not set. usbmon needs a custom kernel, as on the Samsung S9 (tracked in `awtoau/awto-samsung-s9#1`).
- **I:** Pixel kernel source and toolchain pins are published, so a custom kernel should be smoother than the S9's stale-toolchain build. Not tried.
- **Plan (not started):** extract the stock boot image, patch with `magiskboot`, `fastboot boot` the patched image to test before flashing. The exact stock build is not on Google's page or common mirrors; nearest is a 4.34 GB factory zip.
- AOA/accessory mode needs no root. USB-C phone to the RC's USB-A port needs an adapter.
- Bluetooth: Pixel 3 XL and S9 are the same hardware generation (both Bluetooth 5.0). No BLE advantage.

## 5. Recommended research order

### A. Keep the known working Android bridge

Run the current app and server per the operator guide, capture raw UDP independently, quantify packet loss, and leave issue #64 to resolve demux correctness. Measure reconnection reliability and RC idle behavior separately (#65).

### B. Inspect existing gadget implementations

Compare upstream DJI Bridge App, USB Gadget Tool, Raspberry Pi ConfigFS/FunctionFS examples and Facedancer. For each, record supported USB class/vendor requests, how device identity is exposed, any example code, throughput, device/kernel dependencies and developer workflow.

### C. Build a synthetic device on dedicated hardware

Start with Pi Zero 2 W or Cynthion, not the in-use Samsung S9. Implement an intentionally simple test gadget with known VID/PID, a basic configuration descriptor, one bulk endpoint pair and a benign vendor-specific setup request. Connect to a normal Linux USB host for enumeration and trace it using usbmon/Wireshark or appropriate USB tooling. Confirm behavior at USB reset and reconnect, not just steady-state streaming.

### D. Evaluate DJI-specific emulation

With the GL300C *on the bench and propellers removed*, log enumeration and AOA handshake behavior. Determine what can be reproduced using a Pi/Facedancer and what is negotiated by Android system components. Start passively/read-only, then test only bounded known-safe commands once the transport is understood. No flight-control takeover or bypass of safety systems is in scope.

### E. Make an engineering choice

- **Goal: send/receive DUML with the GL300C** - stay with current Android AOA bridge; improve correctness.
- **Goal: emulate arbitrary USB devices from a PC** - use Pi gadget + FunctionFS, or Cynthion/Facedancer when explicit USB transactions and experimentation matter more than low cost.
- **Goal: sit between USB host and a real device** - use a proper USB interposer/proxy with both roles, not just a single-port gadget.
- **Goal: small universal plug-in dongle** - only consider an FX3/dual-controller custom PCB after recording the gaps, costs and throughput of the above devices.

## 6. Testing/decision matrix to fill in

For each candidate, capture:

1. Hardware model and USB device controller, supported link speed and confirmed device-facing connector.
2. Operating system/kernel/root/privilege requirement and installed firmware version.
3. Ability to choose VID/PID, strings, configurations and interfaces.
4. Handling of arbitrary EP0 SETUP requests and bulk/interrupt endpoint traffic.
5. Host enumeration capture; reset/reconnect behavior; missing and malformed traffic.
6. PC control transport, measured sustained throughput and latency (especially video bulk data).
7. Implementation time, approximate hardware cost, maintenance/security considerations.
8. Reproducible commands, scripts and independently verified test result.
9. Whether emulation can work without the phone or commercial DJI SDK installed.

A working application relay is **not evidence** of full USB device emulation, and a device enumerating successfully is **not evidence** of protocol compatibility.

## 7. Initial conclusion

**Do not design a new USB PCB yet.** The Android phone already satisfies the immediate DJI application transport requirement; issue #64 is more urgent than another transport rewrite. For the missing ability to impersonate other USB devices, compare a Pi Zero 2 W running the Linux gadget framework against Cynthion/Facedancer, using a reproducible synthetic USB device test. Retain the rooted-phone alternative if the actual S9 kernel supports it, but avoid risking the current reference device.
