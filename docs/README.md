# Documentation index

Analysis and planning docs for the awto-dji project (talking to a DJI Phantom 3 Professional
directly, for a device the operator owns). Grouped by topic; start with `../HANDOVER.md` for
the current state and next steps, and `../CLAUDE.md` for agent onboarding.

## Protocol & control plane (the practical path)
- `protocol-verification.md` — DUML wire format verified byte-exact against a real packet.
- `control-plane-re.md` — reverse the MCU control plane, not the FPGA; external corroboration.
- `cpu-reversing-proof.md` — **the proofs in MCU code** (binding-ID handler, role machine,
  ATSHA204=auth, WiMAX telemetry); status table of each claim.
- `id-entry-point.md` — where/how the Master-ID enters the FPGA (MCU GPIO control, UART data).
- `link-security.md` — pairing by ID, scrambler≠cipher, the "nothing hidden" principle.
- `what-is-actually-secret.md` — 3-tier secrecy inventory; **LAYER CAVEAT** (MCU-layer
  cleartext is not over-the-air proof).

## Telemetry & video
- `video-and-link.md` — what talks to the phone; OSD is client-rendered, not burned at the
  aircraft; video/telemetry mux; data-vs-burned-OSD tests.

## Firmware & hardware
- `firmware-overview.md`, `binary-analysis.md`, `kernel-analysis.md`, `code-provenance.md`,
  `license-compliance.md`.
- `fpga-images.md`, `fpga-interfaces.md`, `fpga-emulation-plan.md`, `bitstream-to-verilog.md`,
  `m2001-decomp-findings.md` — FPGA bitstream RE (Mistral); the decode gaps.

## RF / SDR / recovery strategy
- `minimal-recovery.md` — eliminate the complex FPGA; recover only the small DJI-specific bits.
- `alternative-approaches.md` — cheapest routes to the ID + whitening.
- `known-plaintext-plan.md` — all-0s / repetitive-telemetry known-plaintext for the scrambler.
- `rf-sdr-and-repair.md` — SDR tooling and RF notes.
- `safety-geofence.md` — public-airspace geofence gate (safety, not defeat).

## Safety / scope
See `../CLAUDE.md` → "Scope & safety constraints". This is interoperability for an owned
aircraft: no geofence defeat, no extraction of secret key values, structural analysis only.
