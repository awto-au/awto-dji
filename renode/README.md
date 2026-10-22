# Renode emulation of `m0900` — AD9363 SPI capture

Tooling to close the open **PHY-params** proof in `HANDOVER.md`: recover the DJI Phantom 3
OFDM channel parameters (centre frequency, channel bandwidth, sample rate, gains) by
emulating the air MCU **`m0900` (STM32F103)** in Renode and capturing the SPI register
writes it makes to the **AD9363** transceiver, then decoding them against ADI **UG-570**.

The AD9363 config is *runtime-computed* in `m0900`, not a static table
(`docs/cpu-reversing-proof.md`), so it can only be read by running the init and capturing
the SPI traffic. See `docs/renode-task.md` for the full task spec and
`docs/phy-params.md` for the result slot + decode method.

## Why build Renode from source

Per the task spec, Renode is **built from source** (not the apt/portable release) so we can
add a custom SPI-tap peripheral and a custom STM32F103 platform, and optionally co-simulate
a Verilated FPGA subnetlist later. Build:

```
git clone --recursive https://github.com/renode/renode
cd renode
sudo apt-get install -y dotnet-sdk-8.0 libc6-dev libicu-dev gcc cmake python3 python3-pip
./build.sh --no-gui          # headless build; produces output/bin/Release/Renode.dll
```

Run the headless monitor with `./renode --console` (or `--disable-xwt`).

## Files here

| File | What |
|---|---|
| `peripherals/AD9363SpiTap.cs` | SPI-slave peripheral. Taps every AD9361/AD9363 SPI transaction, self-frames from the 16-bit header (`R/W` bit15, byte-count bits14:13, addr bits12:0), logs each decoded `W/R addr [data…]`, and keeps a lossless raw MOSI byte log. Returns tunable readback values so the bring-up can proceed. |
| `platforms/m0900.repl` | STM32F103 platform: extends Renode's stock `stm32f103.repl` and adds `spi1` (0x40013000) + `spi2` (0x40003800), each with an `AD9363SpiTap` attached. |
| `scripts/m0900_capture.resc` | Loads the tap, the platform, the `m0900` firmware (you supply it), boots from the app vector table at `0x08008000`, and captures the SPI config. |
| `scripts/m0900_selftest.resc` | **Firmware-free** smoke test: drives a few SPI transactions at the controller to prove the tap frames + decodes correctly. |

## Quick self-test (no firmware needed)

From the repo root, with the built Renode on `PATH`:

```
renode --console -e "i @renode/scripts/m0900_selftest.resc"
# then in the monitor (the tap is a child of the controller: spi1.ad9363_spi1):
(m0900-selftest) spi1.ad9363_spi1 TransactionCount    # -> 3
(m0900-selftest) spi2.ad9363_spi2 TransactionCount    # -> 0
(m0900-selftest) spi1.ad9363_spi1 SaveCapture @selftest-capture.txt
```

Expected decoded capture (verified against the built Renode 1.17.0):

```
W 0x017 [0x05]  ; ENSM / state
W 0x000 [0x00]  ; SPI config / soft reset
R 0x037 [0x0A]  ; product id
```

## Running the real capture

1. Obtain + unpack the `m0900` firmware (`P3X_FW_V01.11.0020_m0900.bin`). It is **not** in
   this repo — see `HANDOVER.md` → "DATA NOT IN THE REPO" and `docs/code-provenance.md`
   (DJI xV4 container, unpacked with dji-firmware-tools `dji_xv4_fwcon.py`). Verified source:
   `https://dl.djicdn.com/downloads/phantom_3/20170706/P3P_FW_V01.11.0020.bin.zip` (DJI's own
   CDN) — check both the container and the unpacked module against the SHA-256s in
   `docs/data-manifest.md`.
2. Put it where the script expects it, or override the path:

   ```
   renode --console -e "\$fw=@/abs/path/P3X_FW_V01.11.0020_m0900.bin; i @renode/scripts/m0900_capture.resc; start"
   ```

3. **Known prerequisite:** the stock `stm32f103.repl` doesn't model RCC, which pre-tags
   `RCC_CR` but not `RCC_CFGR` — without a value there, `m0900`'s clock-switch-to-PLL wait
   spins forever. `m0900.repl` already adds `Tag <0x40021004, 0x40021007> "RCC_CFGR"
   0x00000008` (SWS=PLL) to work around it.
4. Run for real (simulated) time rather than just `start` — a one-shot `-e "start"` with
   nothing after it pauses almost immediately. Use the monitor's `emulation RunFor
   "00:00:NN"` to advance deterministically (no wall-clock sleep):

   ```
   emulation RunFor "00:00:15"
   spi1.ad9363_spi1 TransactionCount
   spi2.ad9363_spi2 TransactionCount
   ```

   **Cold-boot finding:** both counts are 0 because the board straps (PA0, PC15, PC14) read 0
   in Renode, so `main` skips FPGA and AD9363 bring-up. With PA0 set the firmware starts the
   FPGA boot itself and stalls on FPGA reg 0x8A. See `docs/fpga-bringup.md`. The AD9363
   profile is captured with `scripts/re/m0900_capture.py` (direct calls, `renode/scripts/m0900_trigger_capture.resc`).
5. If/when it does reach a status-read spin instead (watch the log for a tight read loop on
   one address), seed that register's "done/lock" value and restart:

   ```
   ad9363_spi1 SetReadDefault 0x037 0x0A      # product id
   ad9363_spi1 SetReadDefault <addr> <value>  # PLL-lock / cal-done, as needed
   ```

6. Dump the capture:

   ```
   ad9363_spi1 SaveCapture @spi1-capture.txt     # decoded transactions
   ad9363_spi1 SaveRaw     @spi1-raw.txt          # lossless MOSI bytes (re-framing fallback)
   ```

   Check `TransactionCount` on both taps to confirm which SPI is the AD9363 bus.
7. Decode the sequence against UG-570 and fill in `docs/phy-params.md`.

## Scope

Interoperability for an owned aircraft (`CLAUDE.md`): structural RF-parameter recovery using
the public UG-570 register map. No key extraction, no geofence/flight-restriction work. The
tap records SPI traffic; it does not model the radio.
