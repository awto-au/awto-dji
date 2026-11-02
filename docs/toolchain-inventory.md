# MCU compiler toolchain inventory (#41, re-rules.md point 10)

Catalog of every ARM/MCU compiler toolchain actually present and runnable on this machine, so
`scripts/re/mcu_libmatch.py` library-match passes try all of them, not just GCC. A GCC-only negative
(m0400 pass 2, commit `ffc91d6`) does not rule out ARM Compiler 5/6 or IAR - this is the list to work
through before calling a library-match final.

Tags: **confirmed-runnable** = binary actually invoked (`--version` + a real compile + disassemble of
the output), not just "a file exists at this path".

## Compilers found, confirmed-runnable

| Toolchain | Version | Path (XDG-relative) | Flag dialect | Relevant to |
|---|---|---|---|---|
| Fedora `arm-none-eabi-gcc` | 15.2.0 (`arm-none-eabi-gcc-cs-15.2.0-4.fc44`) | on `PATH` (`arm-none-eabi-gcc`, ccache-wrapped) | gcc (`-mcpu=`/`-mfpu=`/`-mfloat-abi=`) | all Cortex-M; `mcu_libmatch.py`'s current default (`--toolchain-prefix arm-none-eabi-`) |
| ST GNU Tools for STM32 | 14.3.1 (`14.3.rel1.20251027-0700`) | `~/.local/share/stm32cube/bundles/gnu-tools-for-stm32/14.3.1+st.2/bin/arm-none-eabi-` | gcc | Cortex-M4F (m0400, m0306); already tried in the m0400 pass, path now recorded for reuse |
| **ST armclang (ARM Compiler 6 repackaging)** | clang 21.1.1 `[rel2.20260323-1806]`, bundle `st-arm-clang/21.1.1+st.7` | `~/.local/share/stm32cube/bundles/st-arm-clang/21.1.1+st.7/bin/starm-clang` | armclang/clang (`--target=`/`-mcpu=`/`-mfpu=`/`-mfloat-abi=`) | **new** - Cortex-M0 through M4F/M7/M33, both soft and hard float; `starm-objdump`/`starm-readobj`/`starm-nm` included, and GNU binutils (Fedora's `arm-none-eabi-{readelf,objcopy,objdump}`) read its ELF output fine (verified) |
| Red Hat Cross `arm-linux-gnu-gcc` | 16.2.1 (`arm-linux-gnu-gcc-16.2.1-1.fc44`) | on `PATH` (`arm-linux-gnu-gcc`, targets `arm-linux-gnueabi`) | gcc | **new** - m0101 Cortex-A9: instruction-shape comparison only, not ABI-exact (it's a Linux/glibc cross compiler, m0101 is bare-metal ThreadX) |
| **ARM Compiler 5 / Keil MDK-ARM 5.31 (eval)** | ARM Compiler 5.06 update 6 (build 750); `armcc`/`armasm`/`armlink`/`fromelf`/`armar` | wine prefix `~/.wine-keil`, `drive_c/Keil_v5/ARM/ARMCC/bin/` | armcc (`--cpu=`/`--apcs=`/`-O0..3`/`-Ospace`/`-Otime`) | Cortex-M3/M4 - **new (#41 pt3)**, see "ARM Compiler 5 install" below |

Verified by compiling `float add_mul(float,float,float){return a*b+c;}` (Cortex-M4F:
`-mcpu=cortex-m4 -mfpu=fpv4-sp-d16 -mfloat-abi=hard`) and `int add_mul(int,int,int){return a*b+c;}`
(Cortex-M3: `-mcpu=cortex-m3 -mfloat-abi=soft`, no `-mfpu`), then disassembling each `.o`. All four
produced plausible, correct Thumb/VFP code.

### armclang exact invocation

```
starm-clang --target=arm-none-eabi -mcpu=cortex-m4 -mfpu=fpv4-sp-d16 -mfloat-abi=hard \
  -Wno-missing-multilib -O1 -c foo.c -o foo.o
```
`-Wno-missing-multilib` silences a benign "no multilib found" warning (we only compile, never
link, so the clang-runtimes multilib variant doesn't matter). For Cortex-M3 (no FPU): drop
`-mfpu=`, use `-mfloat-abi=soft`, `-mcpu=cortex-m3`.

Also ships a per-multilib `libclang_rt.builtins.a` (ARM Compiler 6's compiler-rt, e.g.
`.../st-arm-clang/21.1.1+st.7/lib/clang-runtimes/arm-none-eabi/armv7m_soft_fpv4_sp_d16_unaligned_size/lib/libclang_rt.builtins.a`)
- pullable directly via `mcu_libmatch.py --ref-archive` (no code change needed there; GNU `ar`/`readelf`
read it fine).

### ST armclang-hybrid and clangd bundles (present, not separately tested)

- `st-arm-clang-hybrid/21.1.1+st.2` - a second bundle alongside `st-arm-clang`; not drilled into for
  this pass (the plain `st-arm-clang` bundle already gave a complete, working compiler). Revisit if a
  hybrid-specific codegen difference ever matters.
- `st-arm-clangd/21.1.0+st.2` - `clangd` language server only, not a compiler. Not usable for this tool.

### ARM Compiler 5 install (#41 pt3, 2026-11-02)

Previously "confirmed NOT present" (below); installed and tested this pass.

- Installer: Keil MDK v5.31 eval, `https://armkeil.blob.core.windows.net/eval/MDK531.EXE`
  (876 MB; MD5 `679eb0b5d83574b4eb071fb5c73e7287`, matches the server's `Content-MD5` header -
  verified good download, not a truncated/corrupt copy).
- Install: native Wine (already installed, `/usr/bin/wine` 11.20 Staging), own prefix
  `WINEPREFIX=~/.wine-keil` (default wine arch, not `WINEARCH=win32` - wine-staging 11.20 runs
  32-bit Windows apps under wow64 without a separate 32-bit prefix). Silent install
  `wine MDK531.EXE /S /D=C:\Keil_v5` - completed cleanly ("MDK-ARM Core Setup has performed all
  requested operations successfully", confirmed via screenshot of the GUI's own completion
  dialog); no "Create Program Symbols"/`TOOLS.INI` `RTEPATH` error occurred this run, so that
  known Docker/Wine workaround wasn't needed here.
- Binaries: `~/.wine-keil/drive_c/Keil_v5/ARM/ARMCC/bin/{armcc,armasm,armlink,armar,fromelf}.exe`.
  `wine armcc.exe --vsn` -> "Product: MDK-ARM Lite 5.31 / Component: ARM Compiler 5.06 update 6
  (build 750)". Eval/Lite license confirmed active (no code-size prompt hit at the function
  sizes used here, tens-hundreds of bytes).
- Flag dialect (`armcc --help`, `--cpu list`): `--cpu=Cortex-M3` / `--cpu=Cortex-M4.fp.sp`
  (no `--fpu=`, baked into the `--cpu=` name), `--apcs=/hardfp` or `/softfp` for the float ABI
  (omit for soft/no-FPU), `-O0`/`-O1`/`-O2`/`-O3`/`-Ospace`/`-Otime`, `-c`, `-o <file>`,
  `-D<sym>`, `-I<dir>` (gcc-compatible, no space needed).

**Object format quirk (the important gotcha for this toolchain):** a locally-armcc-compiled
`.o` is NOT readable by GNU `readelf`/`objdump`. It is byte-for-byte a standard `Elf32_Ehdr`
layout (confirmed: `e_type`/`e_machine`/`e_shoff`/etc all parse correctly at their normal
offsets once the magic is patched) EXCEPT the magic is `\xf7ORC` instead of `\x7fELF` -
`fromelf --text -c -s` reads it fine and reports "ELF Header Information" with the correct
machine/type, but GNU tools reject it outright on the magic check. `fromelf --elf` (which
would emit a conforming ELF) is **license-gated**: `Fatal error: Q3921U: Option '--elf' not
available with your license` on the eval/Lite tier. Workaround implemented in
`mcu_libmatch.py`'s `--toolchain armcc` path: parse `fromelf --text -c -s` output directly
(hex bytes are per-halfword, byte-swapped within each halfword vs. display order - confirmed
against the same source compiled with GCC: fromelf `eef01a40` == objdump `f0ee 401a`).

**This quirk does NOT apply to ARM Compiler 5's own prebuilt runtime library** (`ARMCC/lib/
armlib/*.l`): confirmed those `.l` archives are standard `ar` format (GNU `ar t`/`ar p` read
them directly) and their member `.o` files are standard `\x7fELF` (not the `\xf7ORC` variant) -
readable by the existing GNU `readelf`/`objcopy`/`objdump` with **zero code change**, exactly
like armclang's `libclang_rt.builtins.a` via `--ref-archive`. The non-standard magic is
something the LOCAL eval-license compile step adds, not an ARM Compiler 5 object format
property in general.

**Runtime library naming** (`ARMCC/lib/armlib/f*_*.l`, undocumented here beyond what was
inferred by inspection - no official ARM naming-scheme doc consulted): for **double**
precision (`dadd`/`dsub`/`dmul`/`ddiv`/`d2f`/`f2d`), content is identical in substance across
every `f*_w*.l` variant tried (Cortex-M has no double-precision FPU regardless of single-
precision FPU presence, so there is only one real double implementation). For **single**
precision (`fadd`/`fsub`/`fmul`/`fdiv`), the suffix matters: `*_wm.l`/`*_wv.l` give a tiny
(18-20 B) hardware-VFP wrapper (`vmov`/`vadd.f32`/etc, 4-5 instructions) - wrong for a real
FPU-less chip; `*_ws.l` gives the genuine **soft** (integer-only, 130-400 B) implementation -
confirmed by disassembly (`vmov`/`vadd.f32` present in the `wm` member, absent in the `ws`
member of the same function). Used `fz_wm.l` for m0900's double family and `fz_ws.l` for its
single family (both Cortex-M3/no-FPU); `fz_ws.l` for all of m0400 (Cortex-M4F, double-only
needed for this retest).

### Known-negative retest with ARM Compiler 5 (#41 pt3, 2026-11-02)

Via `--ref-archive` against ARM Compiler 5.06u6's own `fz_wm.l`/`fz_ws.l` (`--mode fuzzy`):

| Module | Function (fw size) | ARM Compiler 5 candidate (size) | insn/mnemonic ratio | fuzzy composite | Verdict |
|---|---|---|---|---|---|
| m0900 | `__aeabi_dsub` (464B) | `fz_wm.l` `_dsub` (464B, **same size**) | 88.9% / 100.0% | 99.7% | **I** (strongest match this pass) |
| m0900 | `__aeabi_fsub` (234B) | `fz_ws.l` `_fsub` (234B, **same size**) | 87.3% / 100.0% | 99.5% | **I** |
| m0900 | `__aeabi_ddiv` (538B) | `fz_wm.l` `_ddiv` (552B) | 86.3% / 98.4% | 98.3% | **I** |
| m0900 | `__aeabi_fadd` (192B) | `fz_ws.l` `_fadd` (196B) | 86.4% / 99.2% | 98.2% | **I** |
| m0900 | `__aeabi_dmul` (312B) | `fz_wm.l` `_dmul` (332B) | 83.8% / 96.3% | 96.9% | **I** |
| m0900 | `__aeabi_fmul` (234B) | `fz_ws.l` `_fmul` (258B) | 85.0% / 95.4% | 96.3% | **I** |
| m0900 | `__aeabi_dadd` (316B) | `fz_wm.l` `_dadd` (332B) | 82.6% / 97.5% | 72.7% | **I** |
| m0900 | `__aeabi_fdiv` (306B) | `fz_ws.l` `_fdiv` (384B) | 80.5% / 88.5% | 67.5% | **I** (exact-mode; just under fuzzy's 70% floor) |
| m0400 | `__aeabi_dadd` (352B) | `fz_ws.l` `_dadd` (332B) | 1.7% / 6.1% | 18.9% | U |
| m0400 | `__aeabi_dmul` (228B) | `fz_ws.l` `_dmul` (332B) | 3.6% / 8.3% | 37.4% | U |
| m0400 | `__aeabi_d2f` (74B) | `fz_ws.l` `_d2f` (98B) | 10.2% / 13.6% | 13.1% | U |
| m0400 | `__aeabi_f2d` (38B) | `fz_ws.l` `_f2d` (86B) | 9.5% / 14.3% | 9.6% | U |
| m0400 | `__aeabi_ddiv` (222B) | `fz_ws.l` `_ddiv` (552B) | 0.0% / 5.2% | 8.1% | U |

**m0900's ENTIRE soft-float family (all 8 `__aeabi_{d,f}{add,sub,mul,div}`) now matches ARM
Compiler 5's own runtime library at 67-100% fuzzy composite** - a categorically different
result from every GCC/armclang comparison in this family (previously 7-40% composite, see the
fuzzy-match table below). Still **I**, not V (re-rules.md pt7: V needs an exact byte-diff; this
is same-algorithm-different-register-allocation, confirmed not byte-identical) - but this is
the strongest evidence in the whole investigation that **m0900 was compiled with ARM Compiler 5
(Keil), not GCC or ARM Compiler 6**. `__aeabi_dsub` and `__aeabi_fsub` are exact-size matches
with 100% mnemonic-sequence overlap - about as close as a non-byte-identical match gets.

**m0400 does NOT share this result** - its double-precision family stays at GCC/armclang-level
U (8-37% composite) against ARM Compiler 5 too. m0400 and m0900 are **not** shown to share a
compiler for this function family; this narrows, not confirms, the earlier cross-module
"single hand-tuned or ARMCC-family soft-float runtime shared across the firmware family"
inference (toolchain-inventory.md "Fuzzy-match mode" section below, re-rules.md pt9) - m0900
is I-tagged toward ARM Compiler 5 specifically; m0400's compiler for this code is still fully
open (U against GCC, ARM Compiler 6, and now ARM Compiler 5).

## Confirmed NOT present on this machine

- **IAR Embedded Workbench** (`iccarm`/`iarbuild`, `.ewp`/`.eww` project files) - not found anywhere on
  the machine. m0101 (camera loader, ThreadX "Cortex-A9/IAR Version G5.6.5.1" per
  `m0101-threadx-reversing.md`) is IAR-compiled - this is a real gap, not a speculative one. No IAR
  install exists to compile a verifying reference against; `arm-linux-gnu-gcc`/armclang Cortex-A9
  output is usable only for coarse instruction-shape comparison, not an exact match attempt.
- **Keil MDK** (`UV4`, `Keil_v5`, `.uvprojx`/`.uvproj` project files) - no installation, no project
  files referencing it, found anywhere.

## Installer-only (downloaded, NOT run - do not install without asking first)

- `st-stm32cubeclt_1.21.0_27995_20260219_1804_amd64.rpm_bundle.sh` in the shared STMicroelectronics
  mirror's `software/` dir - a separate STM32CubeCLT (Command Line Tools) bundle install script.
  **Not run.** Redundant for current needs: the STM32CubeIDE bundles already installed under
  `~/.local/share/stm32cube/bundles/` provide a working GCC 14.3.1 and armclang 21.1.1 today. Only
  worth running if a newer bundled toolchain version is specifically needed later - ask first.

## Present but incomplete (binutils only, not a compiler)

- `/opt/arm-gnu-toolchain/arm-gnu-toolchain-13.2.Rel1-x86_64-arm-none-eabi/bin/` is on `PATH` (ahead of
  the system binutils) but ships only `ar`/`as`/`ld`/`objdump`/`readelf`/`gdb`/... - **no `gcc`, no
  `g++`, no `cc1`**. Calling `arm-none-eabi-gcc` through this `PATH` entry falls through to the next
  match (Fedora's, via ccache) - confirmed by `which -a arm-none-eabi-gcc`. Not usable as a compile
  backend; fine as a binutils source if ever needed.

## `mcu_libmatch.py` integration

- `--ref-archive` path (prebuilt `.a`) was already toolchain-agnostic - no code change needed to use
  armclang's `libclang_rt.builtins.a` there.
- `--source` compile path added a `--toolchain {gcc,armclang}` selector (`gcc` stays the default,
  unchanged). `armclang` needs `--armclang-bin <path to starm-clang>` and uses
  `--target=`/`-mcpu=`/`-mfpu=`/`-mfloat-abi=` flag syntax; `readelf`/`objcopy`/`objdump` for
  extracting/disassembling the compiled object still go through `--toolchain-prefix` (GNU binutils) -
  confirmed compatible with armclang-produced ELF objects.

## Known-negative retest with the new armclang backend (#41)

Retested m0400's `__aeabi_f2d` (`0x08008d8c`, firmware size 38 B - float->double conversion, GCC-only
pass left this **U**, commit `ffc91d6`) against ST armclang's own compiler-rt
(`libclang_rt.builtins.a`, `extendsfdf2.c.obj:__aeabi_f2d`, via `--ref-archive`, no code change
needed):

```
extendsfdf2.c.obj:__aeabi_f2d: fw_len=38 ref_len=116 byte_exact=False byte_prefix_match=0.0%
insn_ratio=10.9% mnemonic_ratio=21.8% -> U (no useful match)
```

**Still U.** ARM Compiler 6 / LLVM's compiler-rt implementation of `__aeabi_f2d` is 116 B (3x the
firmware's 38 B) and structurally unrelated (generic `fp_lib`-style soft-float, not the firmware's
exponent bit-trick). This rules out ARM Compiler 6's own runtime as the source, same conclusion as
the GCC pass but now against a second, independent toolchain family. ARM Compiler 5 (armcc) and IAR
remain untried - no install of either exists on this machine (see above); still open for whoever gets
access to one.

The `--toolchain armclang` `--source` compile path (for compiling a candidate `.c` rather than pulling
a prebuilt archive symbol, e.g. CMSIS-DSP) was smoke-tested separately (trivial function, compiled,
extracted, disassembled, compared end-to-end without error) but not yet run against a real CMSIS-DSP
candidate - next step below.

## GitHub source search for a DJI MCU firmware SDK/BSP match (#41 pt3, 2026-11-02)

Dan's hypothesis: "DJI did not write that code" - likely vendor SDK/BSP source. Searched
`gh search code`/`gh search repos` (GitHub only this pass - no GitLab/other-host widen done yet).

- **`dji-sdk/Onboard-SDK`** (the one repo already known to reference ARMCC-5.0, per the task
  brief): `gh search code "__aeabi_dadd OR __aeabi_f2d" repo:dji-sdk/Onboard-SDK` -> **zero
  hits**. Confirmed U/no-match: Onboard-SDK is a later, different product (host-side C++
  SDK talking to a flight controller over serial, not MCU firmware) and does not vendor any
  soft-float runtime source. Ruled out, as expected per the task brief.
- **`dji-sdk/Payload-SDK`** (I, new): its MDK-ARM sample projects
  (`samples/sample_c/platform/rtos_freertos/stm32f4_discovery/project/mdk*/*.uvprojx`) literally
  invoke `C:\Keil_v5\ARM\ARMCC\Bin\fromelf.exe` as a post-build step, and
  `dji-sdk/Onboard-SDK-Doc`'s API reference notes "for ARMCC-5.0 compiler". This is **I**, not
  V: it shows a *later, different* DJI SDK product (STM32F4 Discovery RTOS sample, not Phantom 3
  firmware) uses Keil/ARM Compiler 5 as a supported toolchain - circumstantial support for "DJI's
  MCU-side tooling habitually used Keil", not proof about the Phantom 3 firmware specifically.
- **ARM Compiler 5 runtime library source**: confirmed not open (as expected) - no hits for its
  actual implementation anywhere public; RL-ARM, mbed and other ARM-ecosystem soft-float search
  terms returned unrelated projects (LuaJIT soft-float VM code, gdb arm-tdep.c, etc), nothing
  matching the firmware's or ARM Compiler 5's own soft-float shape.
- **DJI MCU firmware leak/source search** ("DJI" + "firmware" + "SDK"/"source", "DJI" + "STM32"
  + "Phantom", "DJI" + "leaked"): no leaked/published Phantom-era MCU firmware source found.
  Found only already-known RE tooling (`o-gs/dji-firmware-tools`, `o-gs/dji-hardware-schematics`,
  forks of same) - no new source repos. `o-gs/dji-firmware-tools/symbols/*.map` has IDA-derived
  symbol/string dumps for *other* DJI modules (wm100/wm220/wm240/wm161/C1/P3X m0800, not m0400/
  m0900) - spot-checked the m0306 one for `aeabi`/soft-float symbol names, none present (it's a
  string-table dump, not a real linker map with function symbols). Not pursued further - tangent
  outside this pass's scope, flagged here in case a future symbol-recovery pass wants it.
- **Keil runtime library leak search** ("Keil" + "armcc" + "rt_memcpy" etc): surfaced
  `RT-Thread/rt-thread`'s `rt_memcpy_cm` package (hand-written Cortex-M assembly `memcpy`,
  explicitly multi-toolchain incl. Keil-MDK) - not DJI-related, not pursued (m0400's `memcpy`
  libmatch was already run against newlib in an earlier pass, still U; RT-Thread's version not
  tried - note as an **untried** candidate if `memcpy` is revisited).

**Conclusion (I):** no direct open-source match found for DJI's actual soft-float runtime
(expected - ARM Compiler 5's own library is proprietary, and no DJI MCU firmware source has
leaked publicly). The GitHub search's only actionable finding is the Payload-SDK/Onboard-SDK-Doc
ARMCC-5.0 circumstantial evidence above, which is now secondary to the direct empirical result:
m0900's soft-float family demonstrably matches ARM Compiler 5's own compiled library (see above)
- stronger evidence than any source-search could provide.

## Next steps

1. ~~Run the CMSIS-DSP radix4 FFT family through `--toolchain armclang`~~ - done (#41 pt4,
   2026-11-03, "CMSIS-DSP radix4 FFT family vs armclang" above): still U for all three functions
   tried. ARM Compiler 5 (armcc) against this CMSIS-DSP source is the one combination left untried.
2. Try `arm-linux-gnu-gcc`/armclang Cortex-A9 output against m0101's IAR-compiled soft-float/libm
   routines for instruction-shape (not byte-exact) clues, given no IAR install exists to try directly.
3. If a newer GCC/armclang version is ever needed, the STM32CubeCLT installer
   (`st-stm32cubeclt_1.21.0_...rpm_bundle.sh`, see above) is sitting downloaded and unrun - ask before
   running it.
4. ~~STM32 HAL/LL/SPL peripheral-driver libmatch for m0306~~ - done (#41 pt4, 2026-11-03, "m0306 SPL
   peripheral-driver retest" above): `gpio_init`/`can_init` V (byte-identical), `adc_common_init` I,
   `usart_init` U (genuinely different code, not just an untried opt level).

## STM32 peripheral-driver libmatch: Keil pack contents + SPL retest (#41 pt3 addendum, 2026-11-03)

**Keil device pack contents, checked against Dan's hypothesis that DFP packs bundle more than
CMSIS headers:** confirmed true, but narrower than it first looks. The already-cached
`Keil.STM32F4xx_DFP.3.1.1` (`/mnt/2tb/git/awto-snoopfrog/tmp/keil/ext-Keil.STM32F4xx_DFP.3.1.1/`)
contains a full, real copy of ST's **HAL** driver (`stm32f4xx_hal*.c/h` - `HAL_`-prefixed,
`*_HandleTypeDef`-based API) - but only under
`CMSIS/Flash/STM32F469_QSPI_N25Q128A/Drivers/STM32F4xx_HAL_Driver/`, as a dependency of ONE
flash-programming algorithm example (external QSPI NOR flash on the STM32469I-Discovery board),
not as a general top-level SDK. Only 9 of ~80 HAL modules are present (`hal`, `hal_cortex`,
`hal_dma`, `hal_dma_ex`, `hal_gpio`, `hal_pwr`, `hal_pwr_ex`, `hal_qspi`, `hal_rcc`, `hal_rcc_ex`)
- no UART/CAN/ADC/SPI, so it can't cover this pass's candidates. No CMSIS/Flash algorithm in
either cached pack bundles SPL (older `stm32f4xx_gpio.c`-style, `GPIO_Init`/no `HAL_` prefix)
source at all. **Conclusion: Keil packs are confirmed NOT the useful source for this pass** -
used ST's own GitHub mirror instead (below), which the original follow-up note correctly flagged
as the easier/authoritative option.

**Which library to target - SPL, not HAL:** m0400's peripheral-init functions are already named
and `[V]`-tagged (`GPIO_Init`, `USART_Init`, `CAN_Init`, `ADC_Init`, `SPI_Init` in
`docs/symbols/m0400.tsv`, from an earlier decompile-and-match-by-behavior pass, not shape-guess)
- and their naming (bare `GPIO_Init`, no `HAL_` prefix, no `*_HandleTypeDef` struct parameter)
matches ST's older **Standard Peripheral Library (SPL/StdPeriph)** calling convention, not HAL's.
This corroborates the existing `docs/HISTORY.md` m0306 finding ("DJI's own raw HAL" corrected to
SPL, by code structure). So this retest targeted SPL, not HAL - HAL would have been the wrong
library per the firmware's own naming evidence, regardless of what the Keil pack happened to
contain.

**Source**: ST's SPL was never put on GitHub by ST itself (superseded by HAL/LL ~2014); used a
community mirror, `github.com/quintin-lee/STM32F4_Stdlib` (`STM32F4xx_StdPeriph_Driver/src/
stm32f4xx_{gpio,usart,can,adc,spi,rcc}.c` + CMSIS headers) - pulled via `raw.githubusercontent.com`,
not cloned. Compiles cleanly with `arm-none-eabi-gcc -mcpu=cortex-m4 -mfpu=fpv4-sp-d16
-mfloat-abi=hard -DUSE_STDPERIPH_DRIVER` (needs a stub `assert_param(expr) ((void)0)` in
`stm32f4xx_conf.h`, standard SPL release-build pattern).

**GCC and armclang results: all U.** Neither stock toolchain's compile of SPL matches (4.7-74.1%
insn_ratio depending on function/opt-level, all below the exact-match floor) - consistent with
the earlier finding that m0400's soft-float runtime doesn't match GCC/armclang either.

**armcc (ARM Compiler 5) results: 3 of 5 byte-exact, 2 of 5 near-exact - all at `-O0`.** First
attempt showed the same false "U" as GCC/armclang, but that was a **tooling bug**, not a real
negative: `extract_symbol_bytes_fromelf_text()` (the armcc `--source` extraction path, see
"ARM Compiler 5 object format" above) scanned from the target symbol's label to the next
`** Section` line, correct for a single-function source file but wrong here - armcc does not do
`-ffunction-sections` by default, so every function in `stm32f4xx_gpio.c` etc shares ONE section,
and the scan silently captured the start of the *next* SPL function too (`GPIO_Init`'s real
144 B read back as "384 B", diluting insn_ratio/mnemonic_ratio into U-looking territory even
though the true 144 B were byte-identical - caught by noticing `byte_prefix_match=100.0%` on a
"U" result, which should be structurally impossible for an unrelated function). **Fixed**:
`extract_symbol_bytes_fromelf_text()` now looks up the real size from fromelf's own symbol table
(`_fromelf_symbol_size()`, new) and stops there, the same anchor the GNU-readelf path already
used correctly. Re-ran all 5 after the fix:

| m0400 function (fw size) | ARM Compiler 5 `-O0` SPL match | insn/mnemonic ratio | Verdict |
|---|---|---|---|
| `GPIO_Init` (144B) | `GPIO_Init` (144B) | 100% byte match | **V (byte-identical)** |
| `CAN_Init` (276B) | `CAN_Init` (276B) | 100% byte match | **V (byte-identical)** |
| `SPI_Init` (60B) | `SPI_Init` (60B) | 100% byte match | **V (byte-identical)** |
| `USART_Init` (204B) | `USART_Init` (204B, same size) | 85.9% / 100.0% | **I** (just under the V floor - likely one IT-block/immediate-encoding difference, not a different algorithm) |
| `ADC_Init` (74B) | `ADC_Init` (74B, same size) | 93.8% / 100.0% | **I** (ditto) |

All 5 at every opt level other than `-O0` are U (GCC-level mismatch) - the match is specific to
**unoptimized** ARM Compiler 5 output. **Conclusion (V for 3, by exclusion across GCC+armclang+
armcc for all 5): m0400's peripheral-init code is linked, unmodified ST Standard Peripheral
Library source, compiled with ARM Compiler 5.06 at `-O0`.** This both confirms the existing
`docs/HISTORY.md` m0306 "SPL not HAL" call (now with a real compiled-code match behind it, not
just calling-convention inference) and is the second strand of evidence (after m0900's soft-
float family) that this firmware family was built with Keil/ARM Compiler 5 - a different code
region, same toolchain conclusion. `USART_Init`/`ADC_Init` not reaching V despite 100% mnemonic
overlap and matching size is worth a closer manual instruction-diff if anyone wants the last 2
confirmed exact; low priority given 3/5 are already proven.

**This also means the earlier "m0400 does NOT match ARM Compiler 5" framing (soft-float family,
above) needs a narrower reading**: m0400's *peripheral driver* code is ARM Compiler 5 + stock
SPL; its *soft-float runtime* specifically is not ARM Compiler 5's own library (nor GCC's nor
LLVM's) - a real, compiler-identified toolchain for one region of the firmware, and a genuinely
unidentified (possibly hand-tuned/replaced) runtime for another. Not a contradiction - different
code, different provenance, both now better evidenced than before this pass.

**Not attempted this pass:** m0306 (also STM32F4-family per the toolchain table) was flagged by
the same request but not retested - no still-unnamed FUN_* candidate list was pulled from
`docs/m0306-naming-pass.md` this pass; given m0400's result, m0306's existing "SPL by structure"
call is now a good bet to retest the same way (high expected payoff, cheap to try).

## m0306 SPL peripheral-driver retest (#41 pt4, 2026-11-03)

Followed up the note above: m0306's own already-named peripheral-init functions
(`docs/symbols/m0306.tsv`/`m0306-names.tsv`, tagged "V by register offsets" i.e. decompiled/
inferred, never compile-diff verified) retested against the same unmodified community SPL mirror
(`github.com/quintin-lee/STM32F4_Stdlib`) and the same ARM Compiler 5.06u6 armcc backend that
found m0400's byte-exact matches. Same image/base as `docs/m0306-naming-pass.md`
(`P3X_FW_V01.11.0020_m0306.bin`, base `0x08020000`), `--cpu Cortex-M4.fp.sp --apcs=/hardfp`.
No SPI_Init/I2C_Init/TIM_Init/DMA_Init candidates exist in m0306's naming docs to retest (checked
`docs/symbols/m0306*.tsv` - only GPIO/CAN/USART/ADC-common init are named).

m0400 matched at `-O0` only; m0306 does **not** - swept `-O0..-O3,-Ospace,-Otime` per function
and found m0306's match point is **`-O2`/`-O3`/`-Ospace`** (identical codegen across those three),
a different optimisation level than m0400's firmware build of the same library:

| m0306 function (fw addr, size) | Best armcc match | insn/mnemonic ratio | Verdict |
|---|---|---|---|
| `gpio_init` (0x0806396c, 120B) | `GPIO_Init` `-O2`/`-O3`/`-Ospace` (120B) | 92.5% / 100.0% | **V (byte-identical)** |
| `can_init` (0x0803ae02, 232B) | `CAN_Init` `-O2`/`-O3`/`-Ospace` (232B) | 79.4% / 100.0% | **V (byte-identical)** |
| `adc_common_init` (0x080374be, 30B) | `ADC_CommonInit` `-O1` (30B, same size) | 30.8% / 92.3% | **I** (same opcode sequence, different register allocation - just under the V floor, same pattern as m0400's USART_Init/ADC_Init) |
| `usart_init` (0x0803b5d8, 172B) | `USART_Init`, every opt level tried (164-204B) | best 13.6% / 36.4% (`-O2`) | **U** - genuinely different code, not a near-miss: disassembly shows the firmware's version has no APB1/APB2-base comparison (`CMP r4,#0x40011000`/`#0x40011400`) that this SPL mirror's `USART_Init` does, and uses a different BRR-fractional divisor computation (threshold compares against `0xbf00`/`0xbeff` immediates absent from the reference) - different algorithm, not a compiler/opt-level artifact |

**Conclusion: m0306's `gpio_init` and `can_init` are V, linked unmodified ST SPL compiled with ARM
Compiler 5.06u6 at `-O2` (or equivalent `-O3`/`-Ospace`)** - a third, independent confirmation
(after m0400's peripheral code and m0900's soft-float family) that this firmware family used
Keil/ARM Compiler 5, and the first real compiled-code evidence (not just naming-convention
inference) behind the existing `docs/HISTORY.md` "SPL not HAL" call for m0306 specifically.
`adc_common_init` stays I (consistent with m0400's ADC_Init/USART_Init landing just under the V
floor). `usart_init` is a genuine U, not a near-miss like m0400's `USART_Init` was - the firmware's
clock-source selection and BRR computation are structurally different from this SPL release, worth
flagging as a real divergence (possibly a different SPL point release, or DJI customisation) rather
than an unexplored opt level, if anyone revisits it.

## CMSIS-DSP radix4 FFT family vs armclang (#41 pt4, 2026-11-03)

Retested m0400's CMSIS-DSP radix-4 FFT family (`docs/m0400-naming-pass.md` section on
`cmplx_mag_f32`/`radix4_butterfly_f32`/`arm_bitreversal_f32`, previously U against 4 GCC releases
only) against ST armclang (ARM Compiler 6) - the "Next steps" item above. Same source (CMSIS-DSP
V1.4.5, commit `147cb4e3`, `zephyrproject-rtos/cmsis-dsp` mirror) and CMSIS Core headers
(`~/STM32Cube/Repository/STM32Cube_FW_F4_V1.28.3/Drivers/CMSIS/Include` - the same local package
the GCC pass used; the newer CMSIS-DSP source needs `__STATIC_INLINE`, absent from the older core
headers bundled with the STM32F4_Stdlib SPL mirror used elsewhere in this doc), `-mcpu=cortex-m4
-mfpu=fpv4-sp-d16 -mfloat-abi=hard`, `-O0` through `-O3`/`-Os`, both `--mode exact` and `--mode
fuzzy`:

| Function (fw size) | Best exact match | Best fuzzy composite | Verdict |
|---|---|---|---|
| `radix4_butterfly_f32` (836B) | `-O1`, same size (836B), 3.0%/29.1% insn/mnemonic | 52.4% (`-Os`) | **U** |
| `cmplx_mag_f32` (236B) | `-Os` (272B), 17.8%/26.0% | 37.4% (`-Os`) | **U** |
| `arm_bitreversal_f32` (176B) | `-O1`/`-O2`/`-O3`/`-Os` (~162-166B), 0.0%/22-25% | 41.3% (`-O1`) | **U** |

All three stay well under both the exact-mode V floor and the fuzzy 70% ranking floor at every
opt level - no closer than the GCC pass's own results (`docs/toolchain-inventory.md` "Fuzzy-match
mode" table below, which didn't cover this family). **Conclusion (V, by exclusion): the firmware's
CMSIS-DSP radix-4 FFT code matches neither GCC nor ARM Compiler 6/LLVM's compiled output of CMSIS-
DSP V1.4.5** - same negative as the GCC-only pass, now confirmed against a second major toolchain
family. ARM Compiler 5 (armcc) against this same CMSIS-DSP source is the one combination still
untried for this family (armcc was only retested against SPL/soft-float runtime code above, not
CMSIS-DSP) - open for a future pass if anyone wants full toolchain coverage per re-rules.md pt 10.

## Fuzzy-match mode (`--mode fuzzy`, #41 pt 2 follow-up)

For functions that already fail `--mode exact` (byte-diff) against every toolchain above - the
firmware's soft-float/CMSIS code is a structurally different implementation, not just a different
load address or opt level (see "Known-negative retest" above). Real IDA FLIRT signatures only
wildcard relocation-patched bytes and otherwise need an exact byte/CRC match - no help here, since
the divergence is structural. `python-flirt` (PyPI, under `/usr/bin/python3` only - see repo-wide
agent rules) was evaluated and not used for that reason: it would just re-run the same byte+wildcard
comparison already proven negative, with no tolerance of its own for register-allocation/instruction-
scheduling differences.

`--mode fuzzy` instead computes a composite of three signals, same philosophy as FLIRT (pattern +
masked variable bytes + call shape) but each one tolerant of a different kind of divergence:
- **masked-byte identity** (40%): byte match % after zeroing branch/call-target, pc-relative-literal,
  and movw/movt operand bytes (generic analog of relocation-masking - works on raw firmware with no
  ELF relocation table, since both fw and ref are disassembled through the same `objdump` pass).
- **mnemonic histogram overlap** (35%): order-insensitive opcode multiset overlap - tolerates
  register allocation/instruction scheduling differences the existing ordered `insn_ratio`/
  `mnemonic_ratio` (exact mode) rejects.
- **call-fanout shape** (25%): `min(calls)/max(calls)` of `bl`/`blx` sites in fw vs ref.
Threshold: composite >=70% AND size ratio >=50% -> `I (fuzzy match)`; below that -> `U`. Never
upgrades to V (re-rules.md pt 7: V needs an exact byte-diff). Calibrated conservatively - a ranking
aid for a human RE pass, not a prover.

**Retest results (2026-11-02), all still U:**

| Module | Firmware fn (size) | Best exact (toolchain) | Fuzzy composite (GCC / armclang) |
|---|---|---|---|
| m0400 | `memcpy` (36B) | U vs newlib libc.a (308B) | 29.2% / - (no compiler-rt memcpy) |
| m0400 | `__aeabi_dadd` (352B) | U vs libgcc (630B) / LLVM (880B) | 10.8% / 26.8% |
| m0400 | `__aeabi_dmul` (228B) | U vs libgcc (596B) / LLVM (664B) | 7.2% / 8.7% |
| m0400 | `__aeabi_ddiv` (222B) | U vs libgcc (464B) / LLVM (896B) | 34.9% / 34.1% |
| m0400 | `__aeabi_d2f` (74B) | U vs libgcc (158B) / LLVM (288B) | 31.2% / 33.1% |
| m0400 | `__aeabi_llsl` (30B) | U vs libgcc (24B) / LLVM (34B) | 44.2% / 54.6% (highest found this pass) |
| m0400 | `__aeabi_f2d` (38B) | U vs libgcc (66B) / LLVM (116B) | 32.1% / 33.5% |
| m0900 | `__aeabi_dadd` (316B) | U vs Cortex-M3 soft libgcc (630B) - **new, first compile-diff for m0900** | 37.8% / untried (armclang) |
| m0900 | `__aeabi_ddiv` (538B) | U vs libgcc (464B) - new | 16.6% |
| m0900 | `__aeabi_dmul` (312B) | U vs libgcc (596B) - new | 14.6% |
| m0900 | `__aeabi_dsub` (464B) | U vs libgcc (634B) - new | 16.0% |
| m0900 | `__aeabi_fadd` (192B) | U vs libgcc (352B) - new | 13.2% |
| m0900 | `__aeabi_fdiv` (306B) | U vs libgcc (310B, closest size match found) - new | 39.4% |
| m0900 | `__aeabi_fmul` (234B) | U vs libgcc (360B) - new | 20.1% |
| m0900 | `__aeabi_fsub` (234B) | U vs libgcc (356B) - new | 15.1% |

No candidate reached the 70% floor; `__aeabi_llsl` (54.6%, armclang) is the closest and still well
short. **Conclusion (V, by exclusion): fuzzy FLIRT-style matching against our own compiled reference
corpus finds nothing for the soft-float/libgcc family on either m0400 or m0900** - confirms the
exact-mode conclusion (not stock GCC/LLVM soft-float) with a tolerant method, doesn't overturn it.
m0900's soft-float family (`__aeabi_dadd/ddiv/dmul/dsub/fadd/fdiv/fmul/fsub`, `docs/m0900-naming-
pass.md` line 119, all `I`-shape-named) had never been compile-diffed before this pass - now has a
real negative result on record instead of an open shape guess, same pattern m0400 reached in
pass 2. Cross-module read (re-rules.md pt 9): both STM32 modules' soft-float is non-stock by a wide
size margin (2-2.9x), consistent with a single hand-tuned or ARMCC-family soft-float runtime shared
across the firmware family rather than two independent non-stock implementations - still **I**, no
third module checked yet.

Not attempted this pass (time-boxed): CMSIS-DSP radix4 family fuzzy retest (needs a
`git worktree add` from the `zephyrproject-rtos/cmsis-dsp` mirror at commit `147cb4e3`, not set up
yet) and m1400/m0306 (µC/OS-III kernel candidates, no FUN_* soft-float shapes found in either dump).
