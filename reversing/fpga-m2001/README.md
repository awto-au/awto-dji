# m2001 (ground FPGA, Cyclone IV GX EP4CGX150): lifted Verilog

Generated from the pluribus repo's structural lift of this image's bitstream. See `docs/bitstream-to-verilog.md` and `docs/fpga-images.md` for scope/methodology; see pluribus `docs/lightbridge-fpga.md` for the running findings summary (clocks, SPI, scramblers, M9K, the AF3 authentication engine, etc.).

Regenerate with: `python3.15t scripts/cycloneiv_clean_image_build.py <image> --out <dir>` in the pluribus repo (`lifters/cycloneiv_clean/`, vendor-derived decoders only, no bitstream bytes hand-edited).

- `flat.v` — flat structural netlist (LUTs/FFs/M9K/MAC by physical ID; `// UNDECODED:` lines mark what the decoders don't yet cover).
- `rtl.v` — readable lift: named adders/counters/FSMs/shift-registers/LFSRs/CRC where recognised; structure-derived names only (nothing in the bitstream names anything).

Counts at generation time (from the run's own `build.json`): 89,282 LUTs, 35,873 FFs, 85 IO pads, 2 PLLs, 542 M9K tiles, 87 MACs; package F672 (exact match). 18 undecoded items remain (FF sync-load source on 131 FFs, IO standard/termination on some pads, 2 PLL input-clock-source pips, 1 pad direction). These are first-pass structural lifts, not vendor-equivalent netlists — see the pluribus repo for gate/coverage numbers and open items (tracked on `awtoau/pluribus` issues #165, #169, #176, #177, #178).
