# DUML command/field schema (awto-dji#33)

Canonical, language-agnostic source for DUML command/push payload layouts. Generates
the Python and Dart code (+ tests + docs) instead of hand-maintaining each in both
languages - the OSD General dual-cmdset/cmdid fix had to be done twice (once per
language) the night this started; that's the bug class this stops.

**Status:** 12 of ~723 known commands (`scripts/re/duml_catalog.py`) migrated.
Migrate incrementally as each command actually gets traced/needed - see
`commands.yaml`'s header comment for the current count and known gaps (chiefly:
`Get*`/`Set*` pairs that share one id for both an empty outgoing request and a
payload-bearing reply - this schema supports only one `direction` per id, so those
stay partly hand-written; see `commands.yaml`'s `0x00/0x01` entry).

## Files

- `docs/schema/duml/commands.yaml` - the single schema file, a YAML map keyed by DUML
  code (`"0xSS/0xII"`, the primary cmdset/cmdid as a hex string). One entry per
  command/push. A struct registered under more than one (cmdset,cmdid) pair lists every
  alias in its own `ids:`; the map key is just the first (primary) one.
- `scripts/re/gen_duml_schema.py` - reads the YAML, writes per entry (file name =
  snake_case of the entry's `name`):
  - `scripts/re/duml_generated/<name>.py`
  - `app/packages/duml/lib/src/generated/<name>.dart`
  - `scripts/re/duml_generated/test_<name>.py` + `app/packages/duml/test/generated/<name>_test.dart`
    (only if the entry has a `tests:` list)
  - `docs/schema/duml/generated/<name>.md` (always - the human-readable doc page,
    also what the pretty printer/call sites should link to instead of restating
    field layouts in prose elsewhere)
- Regenerate: `python3 -I scripts/re/gen_duml_schema.py`. **Never hand-edit any
  generated file** - edit `commands.yaml` and regenerate.

## Two directions

- `direction: push` - decode-only (an incoming telemetry push or a Get-reply we
  decode but never construct ourselves). `OsdGeneral` was the proof of concept.
- `direction: command` - encode-only (an outgoing command we build and send).
  `RestartDevice` was the first. `receiverType` is always a required call-site
  parameter on the generated class's `.encode()` - never baked into the schema/class,
  even for a command that in practice only ever targets one device type.

A command's generated class also gets a module-level `decode(payload)` (Python) /
is itself read-back-able (Dart) purely for display (the pretty printer showing a
captured outgoing frame) - it is not a second direction, and never validates/extends
what gets encoded.

## Field kinds

Push (decode):
- `f64_rad_to_deg` - little-endian double at `offset`, radians -> degrees.
- `i16_scaled` - little-endian int16 at `offset`, divided by `scale`.
- `u8` / `i8` - raw (un)signed byte at `offset`.
- `bitfield_u32` - one bit of a little-endian uint32 at `offset`.
- `bitfield_u8` - one bit of a single byte at `offset` (param: `bit`).
- `bits_u8` - a multi-bit unsigned sub-value of a single byte at `offset` (params:
  `shift`, `width`).
- `ascii_nul` - NUL-terminated ASCII string, `offset`/`length` bytes, trimmed at the
  first NUL.
- `version_quad` - 4 bytes at `offset..offset+3`, formatted `"NN.NN.NN.NN"` in
  **descending** byte order (matches the real getters' `get(hi)..get(lo)` convention -
  see `commands.yaml`'s `0x00/0x01` entry).
- `enum_u8` - byte at `offset` looked up via `enum_ref`'s `.find()` (the enum itself
  stays hand-written in `motor_status.dart`, not regenerated - one Dart target today,
  no reason to templatize ~100-value enums).
- `motor_failed_cause_p3` - escape hatch for one genuinely branchy field, see below.

Command (encode):
- `u8` / `u16` / `u32` / `i16` - plain fixed-width field.
- `i16_scaled` - little-endian int16, `value * scale` rounded on encode.
- `packed_u8` - one byte built from named sub-`bits:` (each `{name, dart_name, shift,
  width, default, type: bool|omit, valid}`).
- `role: const` - fixed `value`, not a constructor parameter.
- `role: param` - constructor parameter with a `default`, optional `valid` list
  (rejected at construction, not sent).

Common to both: `offset`, `confidence` (V/I/U, same convention as
`docs/known-telemetry-and-commands.md`), `doc` (terse, per-field), `targets` -
`[python]`, `[dart]`, or both (a field only gets generated for a language it lists;
Python currently has no concept of an *optional* field - every Python-targeted push
field must be decodable unconditionally at the entry's own `min_length`).

Per-entry (not per-field): `name`, `direction`, `class_doc`, `confidence`,
`provenance` (citation: decompile class/file:line, real capture + log path, or
external dissector cross-check - same style as the rest of this repo's docs), `ids`,
`min_length` (push) or `payload_length` (command), `fields`, optional `tests:`.

### Escape hatch: `motor_failed_cause_p3`

One field (`OsdGeneral.motorFailedCause`) decodes via a 4-way branch depending on
`flycVersion` and payload length (ported byte-for-byte from the real
`DataOsdGetPushCommon.getMotorFailedCause()`). Rather than build a general
conditional/expression DSL for one field, this kind is special-cased in
`gen_duml_schema.py` (`dart_motor_failed_cause_block`), parameterized by the schema's
`byte_offset`/`alt_byte_offset`/`flyc_version_field`/`enum_ref` - so the offsets and
provenance stay in the YAML, only the branch shape is hardcoded. Add a new such kind
only when the next genuinely branchy field shows up - don't reach for one to avoid a
two-line hand derivation outside the schema (see `GimbalPushParams.status`'s doc for
the cheaper alternative when a sub-field is used in exactly one place).

## Tests

Only **behavioral** tests belong in a `tests:` list (e.g. "this input must be
rejected"). Never a hand-calculated `expect_payload_hex`/byte-equality assertion -
that value is computed from the exact same offset/scale arithmetic the generator
itself encodes from, so it's circular, and it has been hand-derived wrong twice in
this repo's own history. If a real captured bench value exists, cite it as prose
(exact bytes + capture log path) in a `doc:` field instead - never as a hand-derived
hex assertion.

## Adding a field to an existing entry

1. Edit `commands.yaml`.
2. `python3 -I scripts/re/gen_duml_schema.py`.
3. `cd app/packages/duml && dart analyze && dart test` /
   `cd scripts/re && python3 -I test_duml_telemetry.py`.

## Adding a new command/push

1. Add an entry to `commands.yaml`, keyed by its primary `(cmdset,cmdid)`. Trace the
   real wire shape from an actual decoder/encoder/decompile/capture - never guess
   fields from `duml_catalog.py`'s name alone.
2. Regenerate (above).
3. Wire the generated module in: replace the hand-written decoder/encoder with an
   import of the generated module (`scripts/re/duml_telemetry.py`'s `PUSH_DECODERS`
   entries and `scripts/re/duml_commands.py`'s `REGISTRY` entries are the two places
   Python call sites plug in). Leave existing hand-written Dart call sites alone
   unless you're the one doing that specific migration pass - the generator always
   emits the new Dart file regardless, ready for that later pass.
