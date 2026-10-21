# Camera-SoC kernel — what the Ambarella Linux actually is

Pulled the GPL mirror `sin5678/DJI_Ambarella_Linux` (706 MB, Linux **3.10.71**) and
inspected it. This is the Linux that runs on the Phantom 3's camera SoC (`m0100`,
Ambarella A9SE). Analysis only — nothing built or flashed.

## It's the generic Ambarella AmbaLink BSP

One source tree covering many Ambarella SoCs via defconfigs (count by family):

```
a5s×1  a7l×1  a8×2  a9×3  a9s×7  a12×15  h1×5  h12×2  s2×2  s2e×1  s2l×2  s3×1  s3l×1
```

The **Phantom 3's A9SE maps to the `a9` family**, built with
`CONFIG_PLAT_AMBARELLA_S2_CORTEX=y` (Ambarella markets the "S2-Cortex" silicon as A9).
Relevant defconfig: `ambarella_a9_ambalink_boss_defconfig`.

No `phantom`/`dji` board names appear anywhere in `arch/arm/mach-ambarella/` or the
configs — it's the **generic Ambarella BSP**, so DJI's board-specific bits are not in
the GPL drop (common, and the usual GPL-completeness gripe).

## The key architecture: the camera SoC runs TWO operating systems at once

The camera chip is not a plain Linux box. It runs **Linux and a real-time OS (ThreadX)
side by side on the same SoC**, confirmed in the source:

- **BOSS** (`arch/arm/mach-ambarella/boss/boss.c`) is the supervisor that splits
  hardware between the two OSes — e.g. it assigns interrupts with
  `BOSS_IRQ_OWNER_RTOS` / `BOSS_INT_SET_RTOS`. Enabled by `CONFIG_PLAT_AMBARELLA_BOSS=y`.
- **AmbaLink** (`CONFIG_PLAT_AMBARELLA_AMBALINK=y`, `AMBALINK_MULTIPLE_CORE`) is the
  coupling layer: `arch/arm/mach-ambarella/ambalink/` has **AmbaIPC**
  (`aipc_router.c`, `aipc_mutex.c`, `aipc_slock.c`) and **AmbaFS** (a filesystem
  shared between the two OSes), over shared memory at `0xDC000000`.
- **rpmsg / remoteproc** (`drivers/rpmsg/ambarella/`, `drivers/remoteproc/ambarella/`,
  each with `host` + `clnt`) carry messages between the Linux core and the RTOS core.

Division of labour:

| RTOS core (ThreadX, not in this tree) | Linux core (this kernel) |
|---|---|
| Hard real-time: sensor → ISP → **H.264 encode** (the imaging/IAV pipeline) | Networking, **USB**, filesystem, the DJI camera app and services |

So the live video is produced on the RTOS side; the Linux side is what runs the
app-facing connectivity — including the **USB link to the phone** and the video relay.

## Relevance to the direct app

This is the camera/USB/video brain, not the flight path (that's the separate **A3**
flight controller). Its value here is understanding the camera side: the AOA
`UsbAccessoryService` and the video relay to the phone live on **this** Linux. The
control/telemetry DUML we care about for driving the bird terminates at the A3 FC, so
the kernel doesn't change the control plan — but it does explain how video + the USB
accessory are served, if live video becomes a milestone.

GPL note: the mirror is a genuine Ambarella AmbaLink BSP for the right SoC line, but a
single-commit community copy; DJI's own archive is empty, so it can't be byte-diffed
against DJI's exact build. Good enough to study the architecture; not a verified
reproduction of DJI's shipped kernel.
