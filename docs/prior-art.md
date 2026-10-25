# Prior art: existing DJI FC reverse-engineering, and where this repo stands

Honest positioning of this project's m0306 (Phantom 3 flight controller) work against the public
DJI RE ecosystem, so we don't re-derive what already exists and we know what is genuinely new.

## The existing projects

- **[o-gs/dji-firmware-tools](https://github.com/o-gs/dji-firmware-tools)** — the canonical effort.
  GPL-3.0, actively maintained. Provides firmware container/crypto tools, an FC parameter editor,
  bin→ELF wrappers, "hardcoder" value patchers, and a Wireshark DUML dissector. **Ships IDA/Ghidra
  symbol files (`.map` + `.idc`) for many modules, including `P3X_FW_V01.07.0060_m0306`** — i.e. the
  P3 FC, one firmware revision below the `V01.11.0020` we analyse.
- **[MrBurnsAT/phantom-firmware-tools](https://github.com/MrBurnsAT/phantom-firmware-tools)** — a
  Phantom-3-focused fork; container extract/merge. Format docs trace back to phantom-licensecheck.

## Where this repo overlaps (reuse, not new ground)

| Our artefact | Existing equivalent | Note |
|---|---|---|
| `scripts/re/xv4_extract.py` | `dji_xv4_fwcon.py` | xV4 container parse — re-implemented; cite upstream |
| `scripts/re/xv4_decrypt.py` | upstream's documented module-AES key/scheme | we do the crypto ourselves but the scheme is theirs |
| `scripts/re/fc_param_table.py` (incl. `--defaults`, the 834-param dump) | `dji_flyc_param_ed.py` | **substantial duplication** — their tool already extracts the FlycExportParam array to JSON *with min/max/default*. Our value-add is only that it runs on the decrypted image directly and cross-links to our RAM-address symbol TSVs. |
| Ghidra raw-bin load (`fc_setup.py`) | `arm_bin2elf.py` | same purpose (wrap raw image for a disassembler) |

## Where this repo appears to be new (no public equivalent found)

Searched upstream's tool list, README and symbols; none of these are covered there:

- **STM32 register-library identification** — that m0306 uses ST StdPeriph (SPL), not HAL/LL, shown
  by code structure across RCC/GPIO/USART/CAN (`fc-io-inventory.md`). Upstream patches hardcoded
  values; it does not characterise the library.
- **I/O pin map derived from the SPL callers** — CAN1=PD0/PD1, CAN2=PB12/PB13, SDIO=PC8-12/PD2,
  USB OTG_FS=PA11/PA12, with AF numbers (`fc-io-inventory.md`).
- **Control-authority / agency** model (priority mutex, the API enable chain, mode-gate byte==2),
  simulator cmdset, RC-loss behaviour (`fc-message-path.md`). Upstream is packet-level
  (`comm_dissector`), not handler-semantic.
- **Linux→FC path** (rpmsg/DjiMsg router) and the **FPGA pinout model**.

## Recommended course (avoid duplicating; spend effort on the new layers)

1. **Cross-check our function names against upstream's `P3X_FW_V01.07.0060_m0306.map`** rather than
   re-deriving them. Most of our `docs/symbols/m0306.tsv` naming could be confirmed (or corrected)
   against it cheaply; addresses shift between 01.07.0060 and 01.11.0020 but names/structure carry.
2. **Licence:** dji-firmware-tools is **GPL-3.0** and this repo is **GPL-3.0-only** too, so the
   licences are compatible — we *may* import/adapt their `m0306.map` names with attribution (note
   the upstream file + commit in the TSV `source` column). No conflict; just attribute.
3. **Concentrate original work** on the semantic layers above (control authority, I/O map,
   sim/RC-loss, Linux→FC, FPGA) — that is where this repo adds beyond the existing ecosystem.

Sources: [o-gs/dji-firmware-tools](https://github.com/o-gs/dji-firmware-tools),
[MrBurnsAT/phantom-firmware-tools](https://github.com/MrBurnsAT/phantom-firmware-tools).
