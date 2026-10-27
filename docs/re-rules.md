# Firmware RE rules (this repo)

Canonical rules: `awto-dan/docs/embedded/embedded-rules.md` section "Firmware reverse-engineering (Ghidra)". This page = how they apply here. Tags: **V** verified, **I** inferred, **U** unknown.

## Process
1. Prior art first: `docs/symbols/upstream/PROVENANCE.md`, `docs/symbols/*.tsv`, `grep -ri <thing> docs/`.
2. Per-chip checklist: `stm32-reversing-process.md` (STM32), `lpc-reversing-process.md` (LPC); module names `naming-map.md`.
3. Full depth in one pass: every GPIO/peripheral, bus chips, every table entry.
4. Record: symbol TSV + struct header (`docs/symbols/`), doc with offsets and repro command, fact changes in `HISTORY.md`.

## Rules
- Subsystem prefixes (`gfx_`, `io_`, `usb_`, `fpga_`, `adc_`, `key_`); name by function, not counter. Prefix only after call-graph isolation check; mixed callers are handlers, no prefix. Precedent: `fpga_link_*` rename (#85).
- Confidence tag on every name; fix on contradiction.
- Constants verified by usage, not bit pattern.
- Mirror findings into Ghidra one at a time (name + plate comment + equate).
- No single-path assumption: check RX filters and independent send paths. "Excluded" needs each alternative checked (see XOR-key case, #84).
- Trace from the real UI call site, not plausible names.
- Over-the-air encryption is not ruled out by MCU-layer cleartext (`what-is-actually-secret.md`).
- Scope: interoperability on the owner's aircraft; no key extraction, geofence defeat or control override.
- Old chats mined for RE findings: `chat-mining.md`.
