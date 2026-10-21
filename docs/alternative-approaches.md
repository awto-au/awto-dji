# Alternative routes to the ID + whitening (lower-effort than reversing)

Ranked cheapest-first. The theme: because the link is WiMAX/LTE-family with no cipher,
you can often **recognise** the unknowns rather than reverse them.

## A. Recognise the whitening (it is likely the WiMAX standard scrambler)

WiMAX/802.16 uses a **published data scrambler** — a known PRBS (`x^15 + x^14 + 1`) with
the seed derived from frame/ID per the spec. Given the link is "based on WiMAX" with
`mcs`/`harq` (firmware-confirmed), DJI plausibly used it. If so the **polynomial is
already known** and only the **seed** is DJI-specific (small search/derivation). So:
test the handful of standard PRBS polynomials against a capture and solve the seed,
instead of extracting an LFSR from the netlist. May eliminate the whitening RE entirely.

## B. Normal telemetry as free known-plaintext (no patching)

The DUML OSD telemetry repeats the same fields every frame, so ordinary traffic is
highly repetitive near-known plaintext. Capture a few seconds of normal standby/flight
and the repetition exposes the scrambler by correlation (XOR frames of identical content
-> payload cancels). No all-black patch, no firmware/FPGA work.

## C. Read the ID (do not reverse for its value)

The Master-ID / SN appears in **cleartext in the DUML stream** (and on the device label /
in the app). Get the value from a DUML capture directly. Its **bit position in the frame**
falls out of the known-plaintext capture (constant header bytes to one aircraft). The MCU
disassembly becomes optional, not required.

## D. Ciphertext-only LFSR recovery

An additive LFSR leaves linear structure. From a recovered sequence (via B), run
**Berlekamp-Massey** to get polynomial + seed. Standard and mechanical.

## E. SDR tooling as scaffolding

`gr-inspector` for blind OFDM parameter estimation; adapt the `proto17/dji_droneid`
sync/descramble pipeline (same OFDM primitives) rather than building from scratch.

## Honest catch (applies to all SDR routes)

You still need a working **demod to the descrambler input** (sync -> FFT -> demap) — the
standard WiMAX receiver chain, which is **re-implemented from spec, not reversed**. So
these routes remove the FPGA/MCU reverse-engineering, but not the OFDM-receiver build.

## Recommendation

Lowest-effort path is **A + B + C**: capture normal traffic with a wideband SDR, read the
ID from cleartext DUML, and test the standard WiMAX scrambler polynomials + solve the
seed. If it is the standard scrambler, the FPGA and MCU never need to be reversed at all.
