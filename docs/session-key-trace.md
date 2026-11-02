# Session-key / link XOR key trace (issue #84)

Tags: **V** verified in disassembly/decompile, **I** inferred, **U** unknown. Addresses: m0900 base 0x08008000, m1400 base 0xA000 (flash = offset + 0xA000), m0306 base 0x08020000.
Scripts (all log to `./tmp/logs/<name>.log`): `scripts/re/session_key_scan.py` (constants over `firmware/`), `session_key_xrefs.py` (m0900 literal-pool xrefs), `session_key_prng.py` (rand/srand model), `session_key_crypto_scan.py` (crypto constants + m0306 dispatch table).

## Summary
- Both ends implement the same scheme (V):
  - **Air (m0900):** `radio_session_key_init` 0x0800ea34 draws 24 bytes, 3DES-encrypts the constant `78 65 54 87 62 23 36 47` into `link_xor_key` (0x20001b18).
  - **Ground (m1400):** `duml_set9_cmd00_session_key_rx` 0xce94 receives the 24 bytes in a cmdset 9 / cmd 0 DUML frame, runs the same 3DES over the same constant into `radio_link_state+0x64` (0x1000423c).
- The key is carried in cleartext inside that DUML message (V layout below). No asymmetric crypto or key exchange exists in m0900 (V, negative).
- The 24-byte key is a function of one SysTick VAL sample: at most 72000 distinct keys (I, model; ~16.1 bits).
- Over-the-air protection of the message is **U** (air FPGA unidentified).

## Q1 USART3 on m0900
- V: receiver type 14 (OSD) goes to `uart_send(3)` unconditionally (`packet_send_route_tbb` 0x080118e4; `dataflow.md` sec. 7). USART3 = 257143 baud 8N1, DMA, IDLE framing.
- I: USART3 wire goes to the air FPGA (by elimination, `dataflow.md` edge 10/17); needs schematic or probe. m1900 air FPGA contents: **U**, not guessed.
- V: nothing on m0900 consumes cmdset 9 cmd 0 from USART3; the message is outbound only.
- V: consumer exists on the ground MCU (m1400, Q3/Q7). Consumer on the FPGA end: **U**.

## Q2 Flight controller (m0306)
- V: DUML dispatch is the flat (funcptr, key=(cmd<<8)|cmdset) table 0x080ab440..0x080ab644 (`fc-usb-duml.md`): 65 entries, cmdsets 0x01:1, 0x02:1, 0x03:58, 0x04:3, 0x06:1, 0x07:1. **No cmdset 9 entry** (`session_key_crypto_scan.py`).
- V: no DES S-box, no 3DES constant, no DES IP/PC-1 pattern in the m0306 image (`session_key_scan.py`).
- V: m0306 does contain AES S-box/inverse (0x080ef1b9, 0x080ef2b9, 0x080f0224, 0x080f0324, 0x080f0cdc), SHA-1/SHA-256/MD5 constants and the P-256 prime (0x080b6b84) - FC auth/crypto library, no link to this key (I).
- U: other receive paths that bypass the table (e.g. raw-frame handlers) were not exhaustively checked; no 8/24-byte key store was found by constants, but absence of a store is not proven by constants alone.

## Q3 Ground side and constant search
Searched: all 242 non-text files (excluding .txt .ini .csv .zip .md .json .tsv .py) under `firmware/` recursively: top-level full containers and module bins, `unpacked/` (P3X, C1, P3S, P3X_m1900, `corpus_scan/` for 13 products), `raw/` (all product containers). Patterns: constant (both byte orders), DES S1 row 0 (nibble and packed), two SP-table layouts (LE/BE), IP and PC-1 byte tables. 83 hits listed; full list in the log.
- Constant `78 65 54 87 62 23 36 47` hits in **MCU images** (V):
  - m0900 (P3X V01.11.0020): 0x0800eaa4 in `radio_session_key_init`.
  - m1400 (C1 V01.06.0000 RC MCU): 0xd254 (literal pool of `duml_set9_cmd00_session_key_rx` 0xce94).
  - m1401 (C1 V01.06.0000): file offset 0xb1e0, S1 table at 0x19be4. Not in a Ghidra project, function unmapped (I: sibling image of m1400, same layout; the string "tick" follows the constant as in m1400).
  - Same constant + S-box also in `corpus_scan` images: GL300E RC m1400 (0x12980), MATRICE100 m0900 (0x221c), raw MG1S RC. Same scheme in other DJI products (I).
  - Full containers (`P3X_FW_V01.11.0020.bin` 0x3f1e838, every `raw/C1/*` container) hit at the offsets of the above modules (m0900 container offset 0x3f17d94 + 0x6aa4 = 0x3f1e838).
- No constant hit in: m0306, m0400, m0800, m1500, m1600, m1601, m1100/1101/1200-1203, m1300, m1700/1701, m1900 (P3X and P3S), m2000-2002, Linux m0100 (V, byte search; a movw/movt-built constant would not match, U).
- DES S1 (nibble layout): m0900 0x08015e5c, m1400 0x2ead4, m1401 0x19be4 (+ products above). SP-table/IP/PC-1 hits only in Linux m0100 (libcrypto, unrelated).
- V: m1400 `duml_dispatch` 0xf3c8 (frame[9] cmdset, frame[10] cmd; one caller 0xfce4): case 9 / cmd 0 -> `bl 0xf72c` -> 0xce94.
- m1400 also contains SHA-256 K constants at 0x2fd38 and a DES S-box region 0x2e000-0x30000 (V constants; use not traced, U).

## Q4 rand / srand / seed space
- V: `srand` 0x080127d8: ring of 55 words at 0x20002770 (`rand_ring`), `s = seed; for i=54..0: ring[i] = s + (s>>16); s = s*0x10dcd + 0x66d619e1` (pools 0x08012810, 0x0801280c). `rand` 0x080081cc: additive lagged Fibonacci, taps A (start idx 31) and B (start idx 0), `x = ring[B]+ring[A]; ring[B] = x; return x & 0x7fffffff`. Key byte = low 8 bits of x.
- V: all state derives from the 32-bit `srand` argument; `srand(1)` runs at C init (0x08012802).
- V: seed = SysTick VAL read at 0x0800ea50, `srand` call at 0x0800ea52. SysTick LOAD = 0x1193f (71999) written once, `systick_tim1_init` 0x0800c1a2 (only store to 0xE000E014); CLKSOURCE = HCLK. VAL range 0..71999.
- I (model reimplemented in `session_key_prng.py`, not run on firmware): 72000 seeds give 72000 distinct 24-byte keys. Max distinct session keys = 72000 (~2^16.14). `link_xor_key` is a deterministic function of the key, so also <= 72000 values.
- I: effective entropy may be lower - the call is made at a polled event (FPGA reg 0xE9 bits[1:0]==3 seen by `fpga_link_rx_poll`) that may be phase-locked to the 1 ms tick; not measured.
- U: 72 MHz SYSCLK assumed from the 1 ms tick comment; PLL setup not re-checked here.

## Q5 References to link_xor_key / radio_session_key in m0900
Literal-pool scan of the whole image (words in 0x20001ab4..0x20001ad0 and 0x20001b00..0x20001b3f): pools at 0x0800ea8c, 0x0800eeac, 0x0800f7bc, 0x0800fbe0, 0x08010044, 0x08010458, 0x080108c8, 0x08010af4 (`session_key_xrefs.py`). Key-relevant users (V):
- Write key: `radio_session_key_init` 0x0800ea34 (`strb [S+0x4c+i]` at 0x0800ea68; 3DES output to 0x20001b18 via pool 0x0800eeac at 0x0800eab2). Guard byte 0x2000015f.
- Read key (S+0x4c): `radio_status_push` 0x0801029e (memcpy 0x18 B at S+0x4c to message buffer S+0x217).
- Read xor key: `fpga_link_rx_poll` 0x0800f978 passes `0x0800fbe0 pool (S+0x14) + 0x50` = 0x20001b18 as arg 2 of `fpga_link_payload_descramble` 0x0800e008 (decomp; callsite near 0x0800fa76). That function receives the key only by pointer.
- Other users of the 0x20001b18 pool (0x0800eac2, `fpga_regs_2_9e_9f_set`, `fpga_channel_write`, 0x0800ec82) use it as a base with negative offsets to S+5.. (not key accesses) (I).
- No other store to S+0x4c..0x6b with a `[rN,#imm]` form (checked in all functions loading these pools); hits at +0x50/+0x54/+0x60 belong to other bases (I).
- S+0..4 (5 bytes, hop-seed ID in `radio_hop_seed_update`) are inserted into the key message (below).

## Q6 Asymmetric / key-exchange crypto in m0900
- V (negative, constants): no AES S-box/Te0, SHA-1/256/512 K, MD5 T, secp256r1 prime/b, secp256k1 prime, CRC32 table, RSA SPKI/ASN.1 header, TEA delta in m0900. One byte-pattern hit `ed ff ff ff ff ff ff ff` at 0x08019ff8 is the middle of a table of small negative ints (errno-style values), not curve25519 (I).
- V (negative, routines): the only crypto routines are DES: `des_feistel` 0x0800c8e8, `des_key_schedule` 0x0800cc08, `des_crypt_block` 0x0800cd4c, `des3_key_schedule` 0x0800cd92, `des3_crypt_block` 0x0800cde2. Their only external call sites are in `radio_session_key_init` (0x0800eaac, 0x0800eab6). No bignum/modexp routine named or located; no DH/ECC/RSA/HMAC code seen (I - absence of a routine is not proven by constants and call graph alone, but no 32-bit multi-word loops were found by name).
- V: no key is derived from a peer-provided value in m0900: the only inputs are SysTick VAL and rand.
- m1400 side: DES + SHA-256 constants present (V constants); a RSA/ECC use there is U.

## Q7 Path of the 24 key bytes
1. V: `radio_status_push` 0x0801029e (every 50 ticks; counter `% 0x32`) builds a 0x43-byte payload at S+0x1f1 and calls `duml_build_send(..., receiver 0xe, cmdset 9, cmd 0, buf, 0x43)`. Payload layout (V from decomp):
   - [0x00..0x1f] copy of S+0x1b0 (32 B, meaning U)
   - [0x22..0x25] word at S+0x9c (meaning U)
   - [0x26..0x3d] `radio_session_key` (24 B), with key indices 0, 7, 9, 13, 21 overwritten by link-ID bytes S[0..4]
   - [0x3e..0x42] the five original key bytes from those indices
2. V: so the message is **not** a plain copy: five key bytes are moved to the tail and replaced by the 5 ID bytes; every key byte is still present (tail). The rest is cleartext (no cipher call in `radio_status_push`).
3. V: receiver type 14 -> `packet_send` -> `uart_send(3)` -> USART3 DMA TX (0x200007d0). No modification between `duml_build_send` and the UART (route table is unconditional).
4. U: air FPGA, OFDM link, ground FPGA/UART. Whether the frame is transmitted as-is or wrapped/encrypted: **U**; not visible from MCU code.
5. V: m1400 `duml_dispatch` case 9 / cmd 0 -> `duml_set9_cmd00_session_key_rx` 0xce94:
   - copies 0x43 B from frame+0xb to 0x10004442;
   - requires bytes [0x26, 0x2d, 0x2f, 0x33, 0x3b] == `radio_link_state[0..4]` (0x100041d8) - same five positions m0900 overwrites (0x26+{0,7,9,13,21});
   - restores those five bytes from [0x3e..0x42];
   - if the 24 B differ from `session_key_last` (0x10002838): stores them at `radio_link_state+0x4c`, runs 3DES key schedule (0x1a8b8) and encrypt (0x1a908) of the constant at 0xd254 into `radio_link_state+0x64`, sets +0x70 = tick+100, copies the key words to `rc_state+0x7a` and (tick+0x3d090) to `rc_state+0x82`, hex-logs the 8 B key ("tick %u" log).
6. I: the derived 8-byte key = m0900 `link_xor_key`; same constant, same 3DES shape. Equality of the two derived values is not computed (needs a key sample).
7. I: the 5 ID bytes act as a pairing check: a frame is accepted only if the ground already holds the same link ID. Source of the ground ID (stored at 0x100041d8): not traced, U.
8. U: where m1400 applies the 8-byte key (the copy at `rc_state+0x7a` is read at 0x000176ac into a struct at r9+0x6c/0x70 during an init path 0x00017576); the XOR on the ground may be in the RC FPGA. U.
- Parsers of cmdset 9 cmd 0: m1400 yes (V); m0900 no (no handler, no receiver); m0306 no (V, table); other modules: no constant or DES hits, so none expected (I); m1401 U.
- Does the FC store the bytes: no cmdset 9 handling in the dispatch table (V), no key-sized store found (I).

## Open
- U: transport of the cs9/cmd0 frame through the FPGAs (cleartext or wrapped). Needs probe on USART3 TX / RC-side UART plus an SDR capture.
- U: m1401 role and its copy of the receiver.
- U: where m1400 applies the derived key.
- Capture check: a cs9/cmd0 frame (0x43 B payload, bytes [0x26+{0,7,9,13,21}] equal) on m0900 USART3 TX would confirm Q7 step 1-3 on hardware.

## Names added (rename-first)
- m0900 (`docs/symbols/m0900_V01.11.0020.tsv`): 1 new row (`link_key_plaintext_const` 0x0800eaa4), 2 notes rewritten (`srand`, `radio_status_push` now V with payload layout). Re-applied with `scripts/re/m0900_ghidra_names.py`; dump regenerated.
- m1400 (`docs/symbols/c1_m1400.tsv`): 11 rows: funcs `duml_set9_cmd00_session_key_rx` 0xce94, `duml_dispatch` 0xf3c8, `des3_key_schedule` 0x1a8b8, `des3_crypt_block` 0x1a908, `memcmp` 0x217a8, `memcpy` 0x218d4; tables `link_key_plaintext_const` 0xd254, `des_sbox` 0x2ead4; ram `radio_link_state` 0x100041d8, `session_key_last` 0x10002838, `session_key_msg_buf` 0x10004442. New driver `scripts/re/m1400_ghidra_names.py` (base gate + `M1400Names.java` + `DumpLPC17xx.java`); project and dump regenerated. The Ghidra project has no SRAM block, so the 3 ram rows (and other 0x1000xxxx rows) are labelled in the TSV only (U: add an SRAM block to the driver).
- m0306 (`docs/symbols/m0306.tsv`): 1 row `duml_dispatch_tbl` 0x080ab440. No m0306 driver exists yet; not re-applied.
- No struct header added for m1400 `radio_link_state` (layout known only for +0..4, +0x4c, +0x64, +0x70).
