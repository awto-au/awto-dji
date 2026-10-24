# DUML command/field schema (awto-dji#33)

Canonical, language-agnostic source for DUML payload field layouts. Generates the
Python and Dart decoders instead of hand-maintaining both - the OSD General
dual-cmdset/cmdid fix had to be done twice (once per language) the night this started;
that's the bug class this stops.

**Status: proof of concept.** Only `osd_general.yaml` is schema-driven. Still
hand-maintained, unchanged by this pass:
- `scripts/re/duml_catalog.py` (723-name catalog) - generated from the TSV, not this
  schema; no payload layout to migrate.
- `scripts/re/duml_commands.py` REGISTRY (gimbal commands, camera, RC permission) -
  send-side payloads, not yet expressed here.
- `app/packages/duml/lib/src/rc_signal.dart`, `version.dart`,
  `app/awto_dji_app/lib/link/gimbal_commands.dart`, `diagnostics_commands.dart` - not
  yet ported.
- `scripts/re/duml_telemetry.py`'s `_gimbal_push`, `_rc_signal_push` - not yet ported.

## Files

- `docs/schema/duml/*.yaml` - one file per command/push struct.
- `scripts/re/gen_duml_schema.py` - reads the YAML, writes:
  - `scripts/re/duml_generated/<name>.py`
  - `app/packages/duml/lib/src/generated/<name>.dart`
- Regenerate: `python3 -I scripts/re/gen_duml_schema.py`. **Never hand-edit the
  generated files** - edit the YAML and regenerate.
- `telemetry.dart` and `duml_telemetry.py`'s `osd` entry are now thin wrappers around
  the generated code (import/re-export only).

## Schema format

Top level (per file):
- `name` - struct/class name (e.g. `OsdGeneral`).
- `class_doc`, `confidence` (V/I/U, same convention as
  `docs/known-telemetry-and-commands.md`), `provenance` - citation, file:line or
  decompile-class style, same as the rest of this repo's docs.
- `ids` - list of `{cmdset, cmdid, catalog_name}` this struct answers under (more than
  one when the real app registers one class under multiple ids - see `osd_general.yaml`
  for why that's a real case, not speculative).
- `min_length` - payload length gate; shorter payloads are not this push at all
  (`matches()`/`decode() -> None`).
- `fields` - ordered list, each:
  - `name` (snake_case, used as the Python dict key), `dart_name` (optional override;
    default is camelCase of `name`).
  - `kind` - one of:
    - `f64_rad_to_deg` - little-endian double at `offset`, radians -> degrees.
    - `i16_scaled` - little-endian int16 at `offset`, divided by `scale`.
    - `u8` - raw byte at `offset`.
    - `bitfield_u32` - one bit of a little-endian uint32 at `offset` (shared `offset`
      -> one flags read, generated once even if several fields reference it).
    - `enum_u8` - byte at `offset` looked up via `enum_ref`'s `.find()` (the enum
      itself stays hand-written in `motor_status.dart` - not regenerated; this schema
      only has one Dart target today and no reason yet to templatize ~100-value enums).
    - `motor_failed_cause_p3` - escape hatch for one genuinely branchy field (decode
      path depends on `flyc_version` and payload length) - see below.
  - `offset`, `scale`, `bit`, `enum_ref` as the kind requires.
  - `min_length` - per-field gate; omit to inherit the struct's `min_length` (field is
    then non-optional/non-nullable in the generated Dart class). Python does not
    support per-field min_length yet (every Python-targeted field must be
    unconditionally decodable at the struct's own `min_length`).
  - `targets` - `[python]`, `[dart]`, or both. Python only gets a field when asked;
    today that's the 9 geometric fields `duml_telemetry.py` already had - the
    motor/IMU/compass/version fields stay Dart-only until someone needs them in Python.
  - `confidence`, `doc` - per-field, same V/I/U convention.

### Escape hatch: `motor_failed_cause_p3`

One field (`OsdGeneral.motorFailedCause`) decodes via a 4-way branch depending on
`flycVersion` and payload length (ported byte-for-byte from the real
`DataOsdGetPushCommon.getMotorFailedCause()`). Rather than build a general
conditional/expression DSL for one field, this kind is special-cased in
`gen_duml_schema.py` (`dart_motor_failed_cause_block`), parameterized by the schema's
`byte_offset`/`alt_byte_offset`/`flyc_version_field`/`enum_ref` - so the offsets and
provenance stay in the YAML (and in provenance-tracking), only the branch shape is
hardcoded. Add a new such field to a new `*_p3`-style kind in the generator rather than
reinventing the DSL question when the next branchy field shows up.

## Adding a field to an existing schema

1. Edit the `.yaml` file.
2. `python3 -I scripts/re/gen_duml_schema.py`.
3. `cd app/packages/duml && dart test` / `cd scripts/re && python3 -I test_duml_telemetry.py`.

## Adding a new command/push

1. New `docs/schema/duml/<name>.yaml`, same shape as `osd_general.yaml`.
2. Regenerate (above) - `gen_duml_schema.py` processes every `*.yaml` in the directory.
3. Wire the generated module in: replace the hand-written decoder with an
   import/re-export, the way `telemetry.dart` and `duml_telemetry.py`'s `osd` entry
   were done this pass.
