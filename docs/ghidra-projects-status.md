# Ghidra project status (all DJI modules)

Canonical home: `re/ghidra-projects/<module>/proj/` — native extracted directories, not
archives. 11 modules, all headless-verified working 2026-10-31.

## The `.gpr` = 0 bytes thing (read this before re-investigating it)

Every project here shows a 0-byte `.gpr` file. **This is not corruption or data loss.**
Confirmed directly: this installed Ghidra (12.2 DEV) writes a 0-byte `.gpr` for ANY project
created or touched via `analyzeHeadless` — including a brand-new throwaway project created
fresh for this check. The `.gpr` is a small GUI-only project-descriptor/lock file; Ghidra's
GUI writes it properly on first interactive open+save, but headless mode never does, and
doesn't need to — `analyzeHeadless <path>/proj <ProjectName> -process "<program>"` opens
and processes these projects' real data (`.rep/idata/.../db.*.gbf`) successfully regardless.

**To get a normal `.gpr` back**: open the project in the Ghidra GUI once (File > Open
Project, point at the `proj/` folder) and save. Purely cosmetic; nothing to fix before then.

## Status table

| Module | Program file | `.gbf` size | Headless-verified | Dump text |
|---|---|---|---|---|
| `cam_server_m0100` | `cam_server` | 2.1 MB | PASS | `cam_server_dump.txt` |
| `m0101_threadx_loader` | `P3X_FW_V01.01.0006_m0101.bin` | 6.5 MB | PASS | `m0101_dump.txt` |
| `m0306_flight_controller` | `P3X_FW_V01.11.0020_m0306.bin` | 10.5 MB | PASS | `m0306_dump.txt` |
| `m0400_gimbal` | `P3X_FW_V01.11.0020_m0400.bin` | 3.2 MB | PASS | `m0400_dump.txt`, `m0400_full_dump.txt` (two separate passes, both kept) |
| `m0900_radio` | `P3X_FW_V01.11.0020_m0900.bin` | 2.1 MB | PASS | `m0900_dump.txt`, `m0900_can_dump.txt` (separate CAN-focused pass, content differs, both kept) |
| `m1400_radio` | `C1_FW_V01.06.0000_m1400.bin` | 4.2 MB | PASS | `m1400_dump.txt` |
| `m1500_fx2lp` | `m1500_code.bin` | 868 KB | PASS | `m1500_dump.txt` |
| `m1600_fx2` | `m1600_code.bin` | 868 KB | PASS | `m1600_dump.txt` |
| `m1601_fx3` | `dummy_bootstrap.bin` | 3.7 MB | PASS | `m1601_dump.txt` |
| `rpc_trans_m0100` | `rpc_trans` | 1.3 MB | PASS | `rpc_trans_dump.txt` |
| `viz_tracking_m0100` | `viz_tracking` | 2.2 MB | PASS | `viz_tracking_dump.txt` |

All 11/11 pass. No archive had a genuinely incomplete/corrupted `.rep` — the 0-byte-`.gpr`
pattern was identical and harmless across every one.

## Verify command (reusable)

```
analyzeHeadless re/ghidra-projects/<module>/proj <ProjectName> -process "<program file>" -noanalysis
```

`<ProjectName>` and `<program file>` per the table above (program file is the exact string
from `<ProjectName>.rep/idata/00/00000000.prp`'s `NAME` field if this table ever goes stale).
"Save succeeded" in the output = pass.

## What changed 2026-10-31

- Retired `.tar.gz` archive storage for all 11 modules — native `proj/` directories only now
  (Dan's explicit instruction: no archives going forward).
- Moved 13 dump-text files out of `tmp/` (disposable, would have been lost on next cleanup)
  into their matching `re/ghidra-projects/<module>/` directories.
- Scrubbed every `.gbf`/dump file for personal paths before committing — none found; all
  embedded paths are in-repo (`firmware/...`, `tmp/air/...` source references), same pattern
  already accepted elsewhere in this repo.
