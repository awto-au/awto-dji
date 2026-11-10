# DUML catalog workflow — how to add or change a command

Single source of truth for DUML commands is **`docs/data/duml-catalog.json`** (generated).
Bindings for each language are generated from it — no hand-maintained copies. Part of the
integrated-system consolidation (`integrated-system-architecture.md`, #102).

## Pipeline

```
 source tables (docs/data/, hand-edited, source-attributed)
   apk-duml-commands.tsv     (DJI GO 4 APK — `evidence` col)
   dll-duml-commands.tsv     (DJI Windows DLLs — `source` col)
   apk-cmdset-devicetype.tsv (CmdSet / DeviceType enums)
        │  scripts/duml_catalog_build.py   (reconcile by cmdset/cmdid, merge evidence, fold fw-version provenance)
        ▼
 docs/data/duml-catalog.json   ← CANONICAL, generated, do not hand-edit
        │  scripts/duml_catalog_gen_dart.py   (and python/rust generators, same shape)
        ▼
 app/packages/duml/lib/src/generated/catalog_data.dart   ← generated, do not hand-edit
```

## To add or change a command

1. Edit the **source table** that attests it, with evidence (never edit the catalog or a binding):
   - APK-sourced → `docs/data/apk-duml-commands.tsv` (cmdset, cmdid, name, direction, payload, status, **evidence**).
   - DLL/firmware-string sourced → `docs/data/dll-duml-commands.tsv` (cmdset, cmdid, name, **source**, status).
   - New CmdSet/DeviceType enum → `docs/data/apk-cmdset-devicetype.tsv`.
   Use `0xNN` for a confirmed id, `?` when unknown. A command may appear in both tables; the build merges them by `(cmdset, cmdid)` and keeps every source's evidence.
2. Regenerate: `python3 scripts/duml_catalog_build.py` then `python3 scripts/duml_catalog_gen_dart.py`.
3. Test: `cd app/packages/duml && dart test test/catalog_data_test.dart`.
4. Commit the source table edit + the regenerated `duml-catalog.json` + the regenerated binding(s) **together**.

## Rules

- **Never hand-edit** `duml-catalog.json` or any `generated/` binding — they are overwritten. Change a source table and regenerate.
- Every command carries **source evidence**; unverified ids stay `?` (emit as `null` in bindings).
- CmdSet / DeviceType names are the authoritative DJI enums from `apk-cmdset-devicetype.tsv` (e.g. CmdSet 0 = `COMMON`), not the command tables' informal labels (`general`).
- **Firmware-version coverage** lives in `duml-catalog.json` → `table_provenance` (which firmware the command table is sha256-matched in, from `duml-table-matches-*.json`). Per-command versioning is future work.

## Adding a language binding

Write `scripts/duml_catalog_gen_<lang>.py` reading `duml-catalog.json`, emitting the same shape as the Dart one (a const list of entries + a cmdset map), with a `// generated — do not edit` header and a test. Then retire that language's hand-copied command list. Remaining target: **Python** (`ground/`). (Rust is parked — `debris/code/rust/`; no binding unless a Cloud-API use case returns.)
