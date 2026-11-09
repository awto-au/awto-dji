# docs/data — derived DUML/protocol data

Source-attributed tables and the canonical catalog generated from them. Downloaded inputs
(firmware, APK) are NOT here — see `../data-manifest.md`. Workflow to add/change a command:
`../duml-catalog-workflow.md`.

## DUML command catalog

| File | Role | Edit? |
|---|---|---|
| `duml-catalog.json` | **CANONICAL** — one entry per (cmdset, cmdid), merged, with per-source evidence + firmware-version provenance. The bindings generate from this. | ❌ generated (`scripts/duml_catalog_build.py`) |
| `apk-duml-commands.tsv` | SOURCE — commands from the DJI GO 4 APK (`evidence` col) | ✅ hand-edited |
| `dll-duml-commands.tsv` | SOURCE — commands from the DJI Windows DLLs (`source` col = literal strings) | ✅ hand-edited |
| `apk-cmdset-devicetype.tsv` | SOURCE — CmdSet / DeviceType enums (runtime-unpacked) | ✅ hand-edited |
| `cmdset-gap-report.tsv` | analysis — coverage gaps | — |
| `duml-table-matches-*.json` | provenance — the APK command table located across firmware versions (sha256) | — generated |
| `apk-dynamic-cmdset-ids.tsv`, `dll-duml-commands.tsv`, … | further source extractions | ✅ |

To add/change a command: edit the relevant **source** table, then `python3 scripts/duml_catalog_build.py && python3 scripts/duml_catalog_gen_dart.py && (cd app/packages/duml && dart test)`. Never hand-edit `duml-catalog.json` or the generated bindings. Full process: `../duml-catalog-workflow.md`.

## Other tables

Firmware symbol/handler tables under `../symbols/` (per-MCU). This dir holds the app/protocol-level extractions.
