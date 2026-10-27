# Task: Renode emulation of `m0900` to capture the AD9363 config

**Status (2026-10-27): steps 1 to 4 done, step 5 not done.** Results and open items: `docs/phy-params.md`, #2. Step 5 (Verilated FPGA co-sim) has no input: no decoded FPGA netlist exists (`fpga-images.md`).

**Owner:** next agent (Selwyn or a spawned session). **Goal:** close the one open PHY-params
proof in `HANDOVER.md` — recover the exact OFDM channel parameters (centre frequency, channel
bandwidth, sample rate, gains) by **emulating the air MCU `m0900` (`air_router_stm32f103`) in Renode and
capturing the SPI register writes it makes to the AD9363**, then decoding them against the
public ADI UG-570 register map.

Why emulation: the AD9363 config is **runtime-computed** in `m0900`, not a static table
(`docs/cpu-reversing-proof.md`), so it can only be read by running the init and capturing the
SPI traffic. A raw-CPU emulator (Unicorn) diverged because it models no peripherals; Renode
models the STM32 peripherals and runs the firmware.

## Build Renode from source — NOT the packaged release

Use the **full source build**, not the apt/portable package:

```
git clone --recursive https://github.com/renode/renode
cd renode
./build.sh            # needs the prerequisites in renode's README (mono/dotnet, etc.)
```

Reason: this task needs to (a) add a **custom peripheral model** for the FPGA-facing bus and
an **SPI tap** that logs every AD9363 transaction, (b) write a custom `.repl` platform for the
exact `STM32F103` part, and (c) optionally co-simulate a Verilated FPGA subnetlist. The
packaged release is not set up for adding/modifying peripheral models and HDL co-sim; the
source tree is. Build from source so these are editable.

## Inputs you must obtain (not in this repo)

- `m0900` firmware (`P3X_FW_V01.11.0020_m0900.bin`, STM32F103, app at `0x08008000`,
  SP `0x20004cb8`, reset `0x08008201`). See `HANDOVER.md` → "DATA NOT IN THE REPO" and
  `docs/code-provenance.md` for how to obtain/unpack DJI xV4 firmware.
- ADI **UG-570** (AD9361/AD9363 register map) — public, for decoding the captured writes.

## Steps

1. Build Renode from source (above).
2. Write a `.repl` platform for the STM32F103 (`m0900`): core, RAM at `0x20000000`, flash at
   `0x08000000`, and the SPI peripheral it uses for the AD9363 (SPI1 `0x40013000` / SPI2
   `0x40003800` — both are referenced; confirm which drives the AD9363). Model the AD9363 as
   an SPI slave stub that **logs address+data of every 16-bit transaction**
   (R/W bit15, addr bits0-9).
3. Load the `m0900` image, boot it, let it reach the AD9363 bring-up, and dump the full SPI
   write sequence.
4. Decode the sequence against UG-570 -> BBPLL / sample-rate / RF-PLL (centre freq) / RX-TX
   bandwidth / gain. Write the result to `docs/phy-params.md` with the raw sequence + decode.
5. (Optional) attach a Verilated subnetlist of the FPGA LFSR/framing as a Renode peripheral
   for the co-sim described in `docs/debris/fpga-emulation-plan.md`.

## Deliverable

`docs/phy-params.md`: the captured AD9363 register sequence and the decoded channel
parameters, which turn the SDR/demod side from blind estimation into a near-turnkey receiver.
Update the PHY-params row in `docs/cpu-reversing-proof.md` / `HANDOVER.md` from "open" to the
result.

## Scope / safety

Scope & safety: see `SAFETY.md`.
