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

## Shared patterns across the other chips (measured from upstream maps)

Does the FC's design recur in the other MCUs? Checked the upstream symbol maps for the camera
(A9), ground radio (NXP LPC1765), air radio (STM32F103) and gimbal (STM32). Yes — two patterns are
company-wide, over heterogeneous silicon:

- **DUML protocol engine** — `crc8_table`/`crc16_table` appear in the **gimbal** (m0400) and the
  **ground LPC radio** (m1400, NXP); the **camera** (m0100, A9) carries the `DjiMsg*` router
  strings; the FC has both tables. Same 0x55 / CRC8-0x77 / CRC16-0x3692 stack on STM32, NXP LPC and
  Ambarella alike.
- **Parameter system (named params + defaults + range validation + get/set/restore over DUML)** —
  the *concept* recurs, instantiated per subsystem rather than one shared table:
  - FC: `flyc_params` (FlycExportParam) + `cfg write index`/`max write allow` validation.
  - Gimbal: `gimb_user_param_*`, `gimb_user_param_restore_default`,
    `gimb_user_param_all_restore_defaults`, `packet_exec_gimb_resume_default_param`.
  - Ground LPC radio: `param_buf`, `cmd_param`, and a `Wrong Parameter` validation string.
  So "parameter validation for a config message" is a DJI house pattern, not FC-only.

RTOS, by contrast, is chosen per silicon (and the choice is visible in the symbols):
- **Micrium µC/OS** on the STM32 FC **and** the NXP LPC ground radio (`OS_CPU_*`, `OS_IdleTask`,
  `OS_TS_GET` in m1400) — DJI standardised µC/OS across its MCU subsystems.
- **ThreadX** on the Ambarella A9 camera (`_tx_thread_*`), where the vendor BSP dictates it.

## Handling this correctly in Ghidra (multi-program project + Version Tracking)

The right structure is **one Ghidra project holding each module as its own program** (our
V01.11.0020 m0306, plus reference builds), not separate projects. Two ways to pull in upstream's
names:

1. **Version Tracking (VT)** — Ghidra's built-in version-diff. It correlates two *binaries*
   (exact-function, symbol-name, data-flow matchers) and ports names/comments/types across a
   version gap. To use it we need the *binary* of a symbol-bearing build (e.g. P3 FC V01.07.0060,
   or P4 `wm220_0306`), load it, apply upstream's `.map`/`.idc`, then VT-correlate to our image.
   VT handles same-component pairs well (P3 FC ↔ P4 FC); cross-arch modules (A9 vs LPC) live in the
   same project but as separate programs with their own language spec — VT does not cross arch.
2. **String-anchored name port** (no VT, no reference binary needed) — parse the upstream `.map`,
   and for each named function match it into our image by the debug strings it references
   (version-robust, since addresses move but string refs don't). Cheaper for our one target.

P4 FC (`wm220_0306`) is the same **STM32F4 family** as the P3 (shared `Reset_Handler`,
`SystemInit`, IAR, µC/OS); the exact part needs the P4 vector table from its binary. Its map is the
richer naming source (3133 vs 1227 publics), so it is the better VT/port reference for the control
and nav layers.

## String-anchored name port: result

Implemented the no-VT port (`scripts/re/port_symbols.py` + `scripts/re/ghidra/fc_port_names.py`),
leaning on DJI's convention that a function logs its own name ("call <fn>"). Against the P3
V01.07.0060 map (same product line → same log strings): 50 names anchored to a string in our
V01.11.0020 image, of which **13 resolved to a function with high/med confidence** (output:
`docs/symbols/m0306-ported.tsv`).

- **Mutual validation:** 11 of the 13 land on addresses we had *independently* derived
  (`api_ctrl_mode_serial_open_nav_handler` @ 0x08055b9c, `..._cmd_status_request` @ 0x08055cb8, the
  `api_mission_*` hotpoint/follow-me set, `app_mission_hp_start_handler` @ 0x08055e2e). The port and
  our own analysis confirm each other, and we gain DJI's canonical names (dropping our `fc_` prefix).
- **Limitations (honest):** the method only catches functions that log their own name; two false
  positives where a caller's log string names a callee (`hal_compass_add`, `app_pre_malloc_ack`)
  were dropped by hand. The **flight-mode controllers** (`ctrl_navi_*`, `kctrl_init_*`) did **not**
  resolve — their names live in a state-name *table* with no direct code xref in a `-noanalysis`
  pass; locating them needs the {fn_ptr,name_ptr} table walk or a full analysis run (future work).

So string-anchoring is good for validation and for handler functions, but the full control-mode
map is the case that actually wants Version Tracking against the P4 binary.

## P3 vs P4 flight controller (same platform, bigger device + new sensing)

From the two FC maps (addresses/sizes are facts from the maps; the exact MCU part is bounded, not
pinned — that needs the P4 binary's vector table or a PCB teardown):

- **Code/RAM size:** P4 `.text` = 0x1265D4 (~1.2 MB) vs P3 ~0x85D34 (~548 KB) — P4 FC is ~2.3x the
  code (needs ≥2 MB flash). P4 data/bss symbols sit around a **0x2040_0000 RAM base** reaching
  ~0x2045D870 (~400 KB), far beyond the P3 F427's ~196 KB at 0x2000_0000. So the **P4 FC is a
  larger-memory part than the P3's STM32F427** (or F427 + external RAM) — same STM32F4-family
  platform code (shared `Reset_Handler`/`SystemInit`/IAR/µC/OS), a bigger device. Exact part: **U**.
- **Sensors — same parts, more of them + redundancy:** both use **MPU-6500** (`mpu6500_driver_init`),
  **IST8303** and **HMC5883** compasses. P4 adds `imu_groups`, `init_all_gyro_acc` and **three**
  high-freq gyro channels (`rec_high_freq_gyro_data_0/1/2`), **dual barometers**
  (`get_ex_baro1/2_raw`), IMU **temperature control** (`gyro_acc_tmp_ctl_init`) and vibration
  detection — i.e. redundant, heated IMUs vs the P3's single set.
- **New FC features in P4 (absent in P3):** obstacle avoidance and vision — `rec_svo_avoid_run`
  (stereo visual odometry), `link_vo_msg_callback`, `rec_vision_tof_run`, `hal_add_tof`,
  `hal_add_ultrasonic`, front/back radar (`rec_radar_avoid_front/back_run`),
  `sdk_ctrl_set_avoid_obstacle_enable`, `avoid_cfg`/`avoid_obstacle_limit_cfg`; **RTK**
  (`handle_app_to_rtk_pack`, `rec_gs_rtk_data_run`, `miss_rtk`); nav-system residual fusion
  (`rec_ns_data_residuals_run`). This is what the extra ~700 KB of code is.

### Why the DJI names are consistent ("standardised") across products

The upstream maps carry DJI's *own* symbol names, and they line up across P3/P4 because it is **one
shared codebase** (202 identical symbols, same functions). They reached the RE community two ways:
DJI firmware **logs its own function names** in debug strings (the convention our string-anchored
port exploits), from which names are recoverable; and at least one **symbol-bearing artefact** (the
IAR linker map — note `__iar_program_start`) was obtained. So "standardised" = one source tree +
DJI's consistent internal naming, captured from the binaries' own strings and a leaked/shipped map.
