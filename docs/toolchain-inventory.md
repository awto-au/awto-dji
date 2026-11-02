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

## Confirmed NOT present on this machine

- **ARM Compiler 5** (`armcc`/`armasm`/`armlink`/`fromelf`) - not on `PATH`, not under `/opt`,
  `~/.local`, or anywhere else searched (incl. wastebasket dirs, read-only).
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

## Next steps

1. Run the CMSIS-DSP radix4 FFT family (`cfft_radix4_f32` etc, still U against 4 GCC releases per the
   m0400 pass) through `--toolchain armclang` - ARM's own toolchain is a more likely original compiler
   for ARM-authored CMSIS-DSP source than GCC.
2. Try `arm-linux-gnu-gcc`/armclang Cortex-A9 output against m0101's IAR-compiled soft-float/libm
   routines for instruction-shape (not byte-exact) clues, given no IAR install exists to try directly.
3. If a newer GCC/armclang version is ever needed, the STM32CubeCLT installer
   (`st-stm32cubeclt_1.21.0_...rpm_bundle.sh`, see above) is sitting downloaded and unrun - ask before
   running it.

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
