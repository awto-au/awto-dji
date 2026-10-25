# dev.py: commands, logging, exceptions

- Entry point: `./dev.py` (repo root). `./dev.py describe` = JSON list; `./dev.py --help` = human list.
- Commands: `describe doctor clean gate ci selftest fmt-check fmt lint test build run`
  plus `duml-probe probe-fc-usb pcap-decode fetch-firmware duml-pretty duml-watch duml-cli
  verify fw-check gimbal gimbal-sweep aoa-relay aoa-send get-identity usb-inventory`.
- `ci` = fmt-check, lint, test, build. Dart only (`app/packages/duml`, `app/packages/geofence`).
- `build` and `run` have no argv: they SKIP (125) and `ci` reports GO with a skip listed.
- Python tests (`scripts/re/test_*.py`) are NOT run by `./dev.py test`. Run them directly:
  `python3 -I scripts/re/test_duml_telemetry.py`, `test_duml_pretty.py`, `test_aoa_mux.py`,
  `test_relay_records.py`. Open: add a STEPS entry.

## Logging rule and exceptions

Rule: every `__main__` script in `scripts/` and `scripts/re/` logs via `scripts/_log.py`
to `tmp/logs/<name>.log`, or is listed here.

Exceptions with reason:

- **Session-log tools (8)** write `captures/sessions/<date>/` via `duml_proto.session_log_dir()`.
  Tracked hardware evidence, not regenerable, so not `tmp/logs/`:
  `scripts/duml_probe.py`, `scripts/probe_fc_usb.py`, `scripts/re/aoa_relay_server.py`,
  `scripts/re/get_identity.py`, `scripts/re/duml_watch.py`, `scripts/re/phone_kprobe_sniff.py`,
  `scripts/re/gimbal_sweep.py`, `scripts/re/verify.py`.
- **Stdout tools (5)**: output on stdout is the product (viewer, sender, or pass/fail runner):
  `scripts/re/duml_pretty.py` (viewer; reads session log), `scripts/re/duml_cli.py`,
  `scripts/re/aoa_send.py`, `scripts/re/test_aoa_mux.py`, `scripts/re/test_relay_records.py`.
- **Migration backlog (26)**: write their own `tmp/logs/<name>.log` (or `logs/`/`logdir`) with a
  private writer, predating `_log.py`. Compliant in location, not in mechanism. Move each to
  `from _log import log` when next edited:
  `scripts/app_icon.py`, `scripts/fetch_firmware.py`, `scripts/fpga_corpus_scan.py`,
  `scripts/re/air_survey.py`, `scripts/re/apk_dynamic_unpack.py`, `scripts/re/apk_extract.py`,
  `scripts/re/apk_memscan.py`, `scripts/re/capture_fc_boot.py`, `scripts/re/cmdset_fuzz.py`,
  `scripts/re/compare_cmdset_gaps.py`, `scripts/re/decode_ad9363.py`,
  `scripts/re/export_phy_params.py`, `scripts/re/extract_apk_cmdset.py`,
  `scripts/re/fc_usb_xrefs.py`, `scripts/re/fpga_regmap.py`, `scripts/re/fpga_write_path.py`,
  `scripts/re/full_command_probe.py`, `scripts/re/lpc17xx_periph_scan.py`,
  `scripts/re/m0306_probe.py`, `scripts/re/m0900_ad_script.py`, `scripts/re/m0900_capture.py`,
  `scripts/re/m0900_trace.py`, `scripts/re/mcu_trace.py`, `scripts/re/rfs_full_extract.py`,
  `scripts/re/usb_switch_trace.py`, `scripts/re/wine_serial_proxy.py`.

## Formatting

- `dart format` output for `lib/src/generated/` comes from `scripts/re/gen_duml_schema.py`,
  which runs `dart format` on each file it writes. Hand edits there are overwritten.
