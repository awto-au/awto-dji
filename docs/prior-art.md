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

## Cross-check done: upstream's m0306 symbol map (vendored)

Pulled upstream's `P3X_FW_V01.07.0060_m0306.map` (vendored at
`docs/symbols/upstream/`, GPL-3.0, attributed). It is a genuine **IAR linker symbol table** —
3483 *original DJI build symbols*, not RE guesses. Outcome:

- **Validation:** the control-authority handler names we derived independently
  (`api_ctrl_mode_status_request_handler`, `..._serial_open_nav_handler`,
  `..._emergency_brake_handler`, `api_init_dji_api_protocol`) appear **verbatim** in the map (our
  TSV carries them with an `fc_` prefix). DJI's own symbols confirm our control-path analysis.
  `flyc_params`, `g_config__api_entry_cfg`, `wp_setting.action_on_rc_lost`, `local_simulator`,
  `g_debug.sim_flag` likewise match our findings.
- **New facts it settled:** compiler is **IAR** (`__iar_program_start`); RTOS **µC/OS-III**
  confirmed (`OS_*`); `system_init`/`SystemInit` located (the clock bring-up we couldn't pin).
- **Confirms our additive scope:** the map has **no SPL function names** — our StdPeriph
  identification and `GPIO_Init`/`CAN_Init`/`RCC_*ClockCmd` naming are not in it.
- **Adoption candidates** (real DJI names we hadn't assigned): `kctrl_init_*` (takeoff, landing,
  gps_atti, waypoint, go_home), `ctrl_navi_waypoint_mission`, `ctrl_navi_go_home`, `ctrl_gps_atti`,
  `cmd_mission_waypoint_*_rcv`, `api_mission_planner_wp_*_handler`, `api_mission_hp_*_handler`,
  `get_gohome_stage`/`get_go_home_state`. Locate each in our V01.11.0020 image by its string refs
  (addresses differ by revision), then add to `m0306.tsv` with `source=upstream-map`.

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

## DJI runs one shared FC platform (measured across products)

DJI reuses a large common codebase across its drone line. Measured directly from upstream's IAR
symbol maps by counting identical symbol names between the **P3 FC** (`P3X…m0306`, 1227 publics)
and the **Phantom 4 FC** (`wm220_0306`, 3133 publics): **202 names are byte-identical**. That is a
floor — static/inlined functions never reach a publics map, and names drift slightly across
versions. The shared set is the platform core, not incidental:

- **RTOS:** 66 `OS_*` — the entire Micrium µC/OS-III port (scheduler, pend lists, task management).
- **DUML stack:** `crc8_table`, `crc16_table` — the same protocol engine seen in every module.
- **SDK / activation:** `dji_sdk_set_key`, `check_activation_authority`.
- **Control-mode framework:** `kctrl_init_API`.
- **Platform:** `Reset_Handler`/`HardFault_Handler`/…, `SystemInit`, `CPU_CntLeadZeros`, version/HAL
  infrastructure (`hal_push_mc_version`, `log_version_info`).

The P4 map (3133) is ~2.5x the P3 map (1227): the newer aircraft *grew* code (vision positioning,
obstacle avoidance) on the same base rather than being rewritten. Same story the module IDs tell
(every FC is `0306`, every air radio `0900`, across P3/P4/Spark/Mavic). Practical use: a function
named in the richer P4 map but absent from the sparse P3 map is a naming candidate for the same
function in our image, matched by structure/string refs.

Reproduce: `awk '/Publics by Value/{p=1;next} p&&/^ [0-9]{4}:/{print $2}' <map> | sort -u`, then
`comm -12` the two name lists (maps under `docs/symbols/upstream/`, from o-gs/dji-firmware-tools).
