# m0800 (air DM368 encoder): what is TI reference code and what DJI changed

Module `m0800` of `P3X_FW_V01.11.0020` (3,363,336 B, SHA-256 `672aff07...7f3f8c6`). Tags:
**V** = shown by a reproducible comparison or by reading the file, **I** = inferred,
**U** = unknown. Only analysis is committed here. The decrypted DJI files are not.

## Bottom line

- **V:** DJI built the encoder on **TI DVSDK 4.02.00.06 for DM368**, and the build paths prove
  it. `encode_usb` embeds `/home/DJI2/Project/enc_nohdmi_wm610/src/dvsdk/dvsdk_dm368_4_02_00_06/`
  together with the exact DVSDK component versions:

  | Component | Version |
  |---|---|
  | codec-engine | 2_26_02_11 |
  | framework-components | 2_26_00_01 |
  | dmai | 2_20_00_15 |
  | linuxutils | 2_26_01_02 |
  | xdais | 6_26_01_03 |
  | xdctools | 3_16_03_36 |
  | codecs-dm365 | 4_02_00_00 |

  The toolchain is TI's (CodeSourcery G++ Lite 2009q1-203).
- **V:** most of the package is unchanged TI or upstream code, measured message by message
  against public reference sources (§3).
- **V:** DJI's changes are thin and well-defined:
  - version banners,
  - a redundant NAND environment and boot defaults in U-Boot,
  - clock/DDR tables in the UBL,
  - a few kernel drivers and patches (an ADV761x HDMI receiver, I2C bus recovery, AEMIF
    debug, a UBIFS backport),
  - two Cypress FX2 USB drivers,
  - **all of the application logic**: `encode_usb`'s 8 DJI source files and the DJI tools
    `monitor`, `update*`, `setsecurity` and `libcommon`.

## 1. Decryption and contents (V)

The m0800 payload starts with `Salted__`. It is OpenSSL `enc` 3DES with an MD5-derived key,
using the static packaging password that dji-firmware-tools documents. The same password
appears in plaintext in the package's own `etc/rcS` and in `usbupdate`, which runs
`openssl des3 -d -k ...` on device. It is a fixed packaging password, not a per-device secret.

```
python3 scripts/re/xv4_extract.py P3X_FW_V01.11.0020.bin OUT m0800
openssl des3 -md md5 -d -k <documented password> -in OUT/P3X_FW_V01.11.0020_m0800.bin | tar -xz
```

The result is a `.tar.gz` (dated 2015-11-03) holding a 34-file `dji/` tree that gets
installed to `/opt/dji`:

| Path | What |
|---|---|
| `data/u-boot.img`, `data/uImage`, `data/ubl_{297,432,486}m_{1,2}.img` | bootloaders and kernel. `etc/updatefinish` writes them to NAND at 0x20000/0x40000 (UBL copies 1/2), 0x320000 (U-Boot) and 0x4a0000 (kernel). |
| `modules/` | `cmemk edmak irqk dm365mmap` (TI); `usb_68013 usb_cy7c68013a` (DJI) |
| `bin/` | `encode_usb monitor update update68013 usbupdate setsecurity mtderase mtdwritefile fxload Vend_Ax.iic` plus shell scripts |
| `lib/libcommon.so`, `etc/{rcS,boot.sh,version,updatestart,updatefinish}` | DJI common library and init scripts. Version `0.13.0.7`. |

DJI's binaries are **not stripped**. They keep DWARF compile units, which name every source
file and its build directory (§4).

## 2. References used (all public, hashes verified)

| Reference | Source | Check |
|---|---|---|
| TI linuxutils 2.26.01.02 (CMEM/EDMA/IRQ source) | software-dl.ti.com `.../linuxutils/2_26_01_02/exports/` | same version DJI built against |
| TI DVSDK 4.02.00.06 sources ISO (Arago GPL sources, incl. `u-boot-davinci` git 1af61f3b, U-Boot 2010.12-rc2) | software-dl.ti.com `.../DVSDK_4_00/4_02_00_06/exports/dvsdk_4_02_00_06_sources.iso` | MD5 `1afd703e...` = TI `md5sum.txt` |
| TI DVSDK 3.10 `flash-utils-davinci` (DM36x UBL source) and `linux-davinci-staging` (2.6.32-rc2 + TI DaVinci) | software-dl.ti.com `.../DVSDK_3_10/latest/exports/` | MD5s = TI `md5sum.txt` |
| Linux 2.6.32.17 mainline | cdn.kernel.org `v2.6/linux-2.6.32.17.tar.xz` | SHA-256 = kernel.org `sha256sums.asc` |

**Gap:** DJI's exact kernel base (TI PSP 03.21, `2.6.32.17-davinci1`) and the DVSDK `encode`
demo ship only inside TI's `dvsdk_dm368-evm_4_02_00_06_setuplinux` installer, which was not
run here. The kernel comparison therefore uses the union of mainline 2.6.32.17 and TI's older
DaVinci staging tree. Anything TI added between those and PSP 03.21 would show up as "not in
reference" even though it is TI code. Those cases are marked I below.

## 3. Message-level comparison (V; `scripts/re/ref_string_diff.py`)

| Binary | Reference | Messages | In reference | Not in reference |
|---|---|---|---|---|
| `cmemk.ko` | linuxutils cmem | 59 | **59** | 0 |
| `edmak.ko` | linuxutils edma | 13 | **13** | 0 |
| `irqk.ko` | linuxutils irq | 10 | **10** | 0 |
| `u-boot.img` | TI u-boot-davinci 2010.12-rc2 | 1025 | **1004** | 21 |
| `ubl_*m_1.img` (each) | TI flash-utils DM36x UBL | 22 | **20** | 2 |
| `uImage` (raw Image, uncompressed) | mainline 2.6.32.17 + TI staging | 4528 | **4428** | 100 |
| `usb_68013.ko` | mainline drivers/usb | 5 | 0 | 5 (DJI driver) |

What the unmatched messages are:

- **TI kernel modules:** none. The only difference is the build path that the `__FILE__`
  banner embeds. They also have TI `author`/`description` modinfo. I: built unmodified from
  linuxutils (string-level evidence, not a binary rebuild).
- **U-Boot (DJI):**
  - banner `U-Boot 2010.12-rc2-svn3205-Dji` and `DJI-ENC-Uboot-%d.%d-rc%d`;
  - a **redundant two-copy NAND environment** ("No Valid First/Second Environment Area found",
    "Use the first/second environment", per-copy erase/write/save messages);
  - "Press ESC to abort autoboot";
  - DJI default environment: `bootcmd` loads the kernel from NAND 0x4A0000 and **falls back to
    0x900000**; `bootargs` has `mem=48MB`, `davinci_enc_mngr.ch0_output=COMPOSITE ch0_mode=pal`,
    `root=ubi0:rootfs` (UBIFS on mtd2) and `dm365_imp.oper_mode=0`;
  - `mtdparts=davinci_nand.0:25m(bootloader)ro,4m(kernel),118m(filesystem)`.

  The remaining unmatched lines are USB/format-string variants of TI messages.
- **UBL (DJI):**
  - only the banners `UBL Product Vesion : DJI-<freq>-UBL-1.0-rc0(2015-10-30)` and
    `Dji UBL Version:`;
  - copies `_1`/`_2` differ in **one byte** (offset 12: copy index 1/2);
  - the 297/432/486 MHz images differ only in a table of PLL/DDR constants (offsets
    ~2145-2560).
  - `updatefinish` picks the image by reading **PLL2 PLLM** (`devmem 0x01c40d10`: 0x51 = 486,
    0x09 = 432, 0x63 = 297). I: one board design shipped with several DM368 speed grades.
- **Kernel, DJI (V by naming/Chinglish, absent from both references):**
  - banner `Kernel Product Vesion : DJI-WIFI-WM610-Kernel-...` (built "Mon Nov 2 15:28:34 CST
    2015", `root@xueb-VirtualBox`);
  - an **`adv761x` HDMI-receiver driver** (`adv761x_probe`, "HDMI video input detected
    (%ux%u%c@%dHZ)", EDID write). I: an ADV7611-class HDMI input; mainline had no such
    driver in 2.6.32;
  - "timeout when try recovery i2c bus" (an I2C bus-recovery patch);
  - `aemif addr/value0/value1` debug prints (AEMIF, the DM36x async external memory
    interface);
  - board input `tvp5151 cvbs`;
  - **UBIFS "free space fixup"**, a backport from Linux 3.x;
  - MUSB tweaks ("version 6.0, pio, host", "usb bus error").
- **Kernel, probably TI PSP 03.21 rather than DJI (I):**
  - machine name `DaVinci DM36x EVM` (TI renamed the DM365 EVM board for DM368);
  - DM368 VENC/PLL messages ("PLL's doesnot yield required VENC clk", timeperframe checks);
  - `DaVinciPreviewer`.

  DJI **kept TI's EVM board identity** and did not register a new machine.
- **Kernel, noise:** crypto self-test vectors and SCSI `[%s]` format variants.

## 4. DJI application code, from DWARF compile units (V)

| Binary | DJI sources (comp_dir `.../enc_nohdmi_wm610/src/app/src/...`) | Other code linked in |
|---|---|---|
| `encode_usb` | `main.c video.c capture.c codecs.c ctrl.c ui.c led.c serial/enc_serial.c` | TI DMAI 2.20 (19 CUs, comp_dir `/home/u/dm368/dvsdk_dm368_4_02_00_06/dmai_2_20_00_15`), TI MPEG4 encoder lib, H264VENC_TI 02.30.00.06, Ittiam AAC-LC, Codec Engine/FC/XDAIS |
| `monitor`, `update`, `update68013` | own `.c` + `common/{common,serial,queue,mylibusb,sha256}.c` | glibc, OpenSSL 0.9.8e MD5 (`monitor`) |
| `libcommon.so` | `common/*` + `common/cross/at88.c` | |
| `fxload` | `fxload/{fxload,ezusb}.c` | I: the open-source linux-hotplug `fxload`, rebuilt |
| `setsecurity`, `usbupdate`, `mtderase`, `mtdwritefile` | one DJI `.c` each | |

- **`encode_usb` is TI's DVSDK `encode` demo, reworked (I, strong).**
  - Its `main.c video.c capture.c codecs.c ctrl.c ui.c` match the demo's file set. It keeps
    the demo's help text verbatim ("1 D1 @ 30 fps (NTSC) ... 11 1080P @ 60 fps - for DM368")
    and the demo's OSD UI (`UI_create`, `UI_incTransparency`, `osdThrFxn`, "inc/dec/hide").
  - DJI dropped the demo's file writer and audio/speech threads and added `led.c` and
    `serial/enc_serial.c`.
  - Confirming this at code level needs the demo source from the TI installer (§2 gap).
- **DJI-only functions** (DWARF subprogram names):
  - `video.c`: **`AddSerialDataToFrame`**, `getEncodedSliceProvideSpace`, `sendMsgToMonitor`,
    `gblSetVideoBitRate`, USB status.
  - `ctrl.c`: `checkUsbID`, `getUsbBusStatus`, `msgAction`, `gblSetSkipFrame`/`ForceFrame`,
    `encryptThrFxn`.
  - `led.c`: `usbPhyLinkCheck/Reset/Restore`, **`getCanLinkStatus`**, GPIO LED.
  - `enc_serial.c`: a DJI command/ack protocol on `/dev/ttyS1` (`Enc_Serial_SendWaitAck`,
    `_Get_Version`, `_Enter_Loader`, `_Reboot`, `_Ctrl_Set/Get`, `Reset68013`,
    `PustABDM368SelfCheck`, `Enc_Serial_Encrypt_*`, `Enc_Serial_Is_Stream_Disable`,
    `Enc_Serial_Get_Encode_Mode`).
  - Status format: `T:%d:%d R:%d H:%d L:%d USB:%d BW:%d SBR:%d SFR:%d`.
- `setsecurity`, `common/cross/at88.c`
  (I: Atmel AT88 CryptoMemory) and the `encryptThrFxn`/`/etc/key.bin` path are the component
  authentication / "encrypt query" already noted in `air-id-and-stream-survey.md`. They were
  inventoried, not analysed.

## 5. What this adds to the system model

- **Air video path (dataflow.md §5 item 3, was U).**
  - V: the DM368 runs as **USB host** to a Cypress **CY7C68013A (FX2)**:
    - DJI drivers `usb_68013.ko` / `usb_cy7c68013a.ko` bind USB `0547:1002`;
    - `boot.sh` loads `usb_68013.ko` and then starts `encode_usb -a -s`;
    - `update68013` / `fxload` / `Vend_Ax.iic` (a Cypress dev-kit `0xC2` EEPROM image) load
      FX2 firmware.
  - I: H.264 leaves the DM368 over USB into the FX2, and from there into the air FPGA.
    `/dev/68013` is opened by `monitor`; how `encode_usb` writes the stream (usbfs via
    `mylibusb.c`, or the misc device) is U.
- **DUML/video multiplexing (§5 item 6).** ~~I, from the function name: `AddSerialDataToFrame`
  suggests the DM368 inserts serial data into the frames.~~ **Retracted after disassembly (§7):**
  the function is dead code, and the DM368 sends raw H.264 slices.
- **Correction (same day): the DM368 does not put serial data in the video.** See §7.
- **Camera to DM368 input.** I: the `adv761x` HDMI receiver plus `autoDetectVideoIput` suggest
  the camera feeds the DM368 over HDMI. The project name `enc_nohdmi_wm610` and the WM610
  (Inspire 1) banners show that **one encoder build is shared across aircraft**; P3P-specific
  wiring is U.

## 6. Reproduce

```
# DJI side
python3 scripts/re/xv4_extract.py P3X_FW_V01.11.0020.bin OUT m0800
openssl des3 -md md5 -d -k <documented password> -in OUT/P3X_FW_V01.11.0020_m0800.bin | tar -xz -C M
tail -c +65 M/dji/data/uImage > Image          # uImage compression = none
readelf --debug-dump=info M/dji/bin/encode_usb | grep -A3 DW_TAG_compile_unit
# references: see §2 URLs; then e.g.
python3 scripts/re/ref_string_diff.py M/dji/modules/cmemk.ko linuxutils_2_26_01_02/packages/ti/sdo/linuxutils/cmem
python3 scripts/re/ref_string_diff.py M/dji/data/u-boot.img u-boot-davinci/git
python3 scripts/re/ref_string_diff.py M/dji/data/ubl_432m_1.img flash_utils/DM36x flash_utils/Common
python3 scripts/re/ref_string_diff.py Image linux-2.6.32.17 linux-davinci-staging/git
```

**Next, to close the I items:** extract TI's `dvsdk_dm368-evm_4_02_00_06_setuplinux` (PSP 03.21
kernel and the `encode` demo) on a disposable machine, then rerun the kernel diff and do a
function-level diff of `encode_usb` against the demo.

## 7. Where the video bytes go, and where DUML does NOT go (V, disassembly)

`encode_usb` is built without optimisation and keeps its symbols and DWARF, so the functions
below read directly as C. Tools: capstone, ARM mode; `readelf -s/-r`.

1. **`AddSerialDataToFrame` (`0x127e0`, `video.c:118`, `int f(int offset)`) is dead code.**
   - It calls `Enc_Serial_Fill_Forward_Data(outBuf + offset, 0xb3ffa)`.
   - Every 300th call (`osdDataCnt % 300`, magic `0x1b4e81b5`) it hex-dumps the result as
     `serialData[...]`.
   - `Enc_Serial_Fill_Forward_Data` (`0x153e8`) is a **stub**: it stores its two arguments and
     returns 0.
   - Nothing calls `AddSerialDataToFrame`. A sweep of `.text` finds no `bl`/`b` to it, and its
     address appears in no literal pool or function table. So in this build no serial data is
     added to any frame. I: a leftover from a shared WM610 code base.
2. **Per-slice output.**
   - `videoThrFxn` puts `getEncodedSliceProvideSpace` (`0x1298c`) into the H.264 encoder's
     dynamic parameters at `0x130d8`. This is TI H264VENC's data-sync, slice-level output
     callback.
   - For each slice it:
     - reads the NAL type `buf[4] & 0x1f` after the `00 00 00 01` start code (1 = P, 5 = IDR)
       and counts `Pslice`/`Islice`;
     - optionally `fwrite`s to a debug file (`outFile`, set from a command-line option);
     - unless `nooutput`/`nostream`/`usbErr` is set, calls
       **`libusb_Send(slice, len, &sent, 100)`**, failing with `send slice data error-%d`;
     - then re-arms the capture buffer (V4L2 ioctl `0x40045644`).
   - There is no header, length prefix or trailer.
3. **`libusb_Send`** (`libcommon.so` `0x61a0`, `mylibusb.c`) is not libusb. It fills a 20-byte
   request `{u8 type=0, u8 ep=2, ptr data, u32 len, ..., u32 timeout}` and calls
   `ioctl(fd, 0x1001, &req)` on DJI's device (`init_libusb`, `/dev/68013`).
4. **`usb_68013.ko` `usb_68013_ioctl`**, case `0x1001`:
   - `copy_from_user` copies the data to **offset 0** of the URB buffer, in chunks of at most
     the buffer size;
   - the pipe is `0xC0000000 | ep<<15 | devnum<<8`, i.e. **bulk OUT EP2**;
   - then `usb_submit_urb` with completion `usb_68013_UsbDeviceTransport_Complete`.
   - The driver adds nothing. Case `0x1000` is a `usb_bulk_msg` read, the EP6 IN direction.
     Its consumer in user space is U.
5. **FX2 (`m1500`).** This matches the earlier decode in `air-id-and-stream-survey.md`:
   - descriptor `0547:1002`, one vendor interface;
   - `IFCONFIG=0x03`: slave FIFO with an external clock;
   - `EP2CFG=0xA0` / `EP2FIFOCFG=0x10`: bulk OUT 512 B, **AUTOOUT**;
   - `EP6CFG=0xE0` / `EP6FIFOCFG=0x08`: bulk IN, **AUTOIN**.
   - USB data flows to and from the FIFO without the 8051 touching it, so the FX2 cannot insert
     DUML either.

6. **Control link is DUML on a UART, not USB.** `Enc_Serial_Init` opens `/dev/ttyS1`.
   `Enc_Serial_PackAndSend` builds standard DUML: sync `0x55`, `CalCrc8` with seed `0x77`,
   `CalCrc16` with seed `0x3692`. This is the same framing as m0900 (`m0900-can-channels.md`
   §4). So the DM368 is an ordinary DUML node (I: receiver type 8, per the UEG table) for
   version, loader, reboot, encode mode, stream enable and the encrypt check. The peer at the
   other end of `ttyS1` is U.

**Result.** On the air side, the H.264 elementary stream (Annex-B slices) reaches the FIFO
master **unframed and alone**. V: the path is DM368 → USB EP2 → FX2 → 8-bit slave FIFO. I: the
FIFO master is the air FPGA. DUML reaches the air FPGA separately, over m0900 USART3 (V route,
`dataflow.md` §3). So **by elimination, DUML and video are multiplexed inside the air FPGA**
(I). Pinning down the format needs an FPGA or SDR capture: `dataflow.md` §5 item 6.

The ground side depends on the RC revision (dji-firmware-tools wiki pages for m1300, m1600
and m1601, read 2026-10-24; I for anything not in this repo):
- **GL300a:** ground FPGA → FX2 (`m1600`) → DM368 (`m1300`) → USB to the phone.
- **GL300b/c:** the DM368 is removed, and the ground FPGA feeds a **Cypress FX3 / CYUSB2014
  (`m1601`, ThreadX, ~190 KB)**, which is itself the USB device the phone talks to.

The operator's controller is a **GL300C** (`fc-usb-port.md`). So on the owner's hardware the
phone-facing USB endpoint, for video down and DUML both ways, is the `m1601` firmware. That is
the module to reverse for ground control. `duml-protection.md` already places a DUML
SIMPLE-frame table in it (`0x10920`, routine `0x400042e4`).
