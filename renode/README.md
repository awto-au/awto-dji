# Renode emulation of m0900 (Lightbridge air MCU)

Implements HANDOVER.md next-step 3: capture the AD9363 SPI register writes from `m0900`
(STM32F103) so they can be decoded against UG-570 to close the PHY-params item.

Uses the full-source Renode build at `/mnt/2tb/git_mirror/renode` (shared source store, not
cloned again) via a project worktree at `/mnt/2tb/git/awto-renode` (branch
`awto-dji-m0900`), not the packaged/distro version - needed for the ad-hoc C# peripheral
compile path (`include *.cs`), which the package build also supports, but the full source
checkout is what Mistral/other awto RE projects already standardize on.

## What's here

- `platforms/m0900.repl` - extends Renode's generic `stm32f103.repl` with `spi1`/`spi2`
  (`SPI.STM32SPI`), each with an `AD9363Spy` attached. Which SPIx is the real AD9363 vs FPGA
  config line is **unconfirmed** (see comment in the file) - both are spied so the firmware's
  own RCC enable sequence tells us.
- `peripherals/AD9363Spy.cs` - capture-only `ISPIPeripheral`. Logs raw transaction bytes via
  Renode's logger; does **not** decode AD9361/63 register semantics (unverified from memory -
  decode offline against UG-570 once we have real captures, not hardcoded here).
- `m0900_boot.resc` - boots the platform; pass `$firmware=@/path/to/m0900.bin` before
  including it. Logs to `tmp/logs/m0900-renode.log` (`$logPath` to override); grep for
  `AD9363Spy transaction` to pull the captures.

Verified so far (no firmware yet): the platform loads, the C# peripheral compiles and
resolves (type must live under an `Antmicro.Renode*` namespace - `TypeManager` only scans
that prefix for ad-hoc `include`d types), and `LoadBinary` places a dummy blob at the flash
base. Run:

```
cd /mnt/2tb/git/awto-dji
/mnt/2tb/git_mirror/renode/renode --console --plain --disable-xwt \
  -e '$firmware=@/path/to/m0900.bin' \
  -e 'include @renode/m0900_boot.resc'
```

## Blocked on

**`m0900.bin` isn't on this machine.** Per HANDOVER.md "DATA NOT IN THE REPO", the firmware
(unpacked from `P3X_FW_V01.11.0020` via `dji-firmware-tools`' `dji_xv4_fwcon.py`) lived only
in the cloud session's ephemeral scratch. Nothing will actually boot/run here until it's
re-obtained and unpacked. See HANDOVER.md step 1-2 for the exact procedure.

## Open follow-ups

- Confirm spi1 vs spi2 = AD9363 once the firmware disassembly shows the RCC `SPI1EN`/
  `SPI2EN` enable + which base address the config routine touches.
- Decode captured register writes against ADI UG-570 (separate step, not in `AD9363Spy.cs`).
- GPIO config/reset line tracing (FPGA side) isn't modeled yet - can be added as a
  `machine.gpioPortX.PinX AddStateChangedHook` in the `.resc`, no new C# needed.
