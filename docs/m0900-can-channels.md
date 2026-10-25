# m0900 DUML channels: CAN 0x412-0x415 and USART1 (where traffic is sent)

Static trace of `P3X_FW_V01.11.0020_m0900.bin` (SHA-256 `72156b4b...13fe6d`, app base
`0x08008000`). Closes `dataflow.md` §5 items 1 and 10. Tags: **V** = read from code (address
cited), **I** = inferred, **U** = unknown.

Reproduce: `python3 scripts/re/m0900_can_channels.py`. It asserts every V claim below against
the image. Getting the image: download the official `P3P_FW_V01.11.0020.bin.zip` (URL in
`scripts/fetch_dji_tools.ps1`), check the container hash in `data-manifest.md`, then extract
module `m0900` with `python3 scripts/re/xv4_extract.py`. That script is a minimal xV4 reader
written here and does not depend on dji-firmware-tools.

## Answer in one table

| Channel | Dir | Queue / ring | Size | Carries (receiver type = `pkt[5] & 0x1f`) | Board codes | Tag |
|---|---|---|---|---|---|---|
| CAN StdId **0x412** | TX | obj `0x20002330` | 512 B ring | types 1, 4, 8, 15 | 2/4/5/6 | V |
| CAN StdId **0x413** | RX | obj `0x2000234c` | 512 B ring, 320 B frame | anything, then dispatched | 2/4/5/6 | V |
| CAN StdId **0x414** | TX | obj **`0x20002538`** | 64 B ring | **type 30 only** | 2/4/5/6 | V |
| CAN StdId **0x415** | RX | obj `0x20002554` | 64 B ring, **64 B max frame** | anything, then dispatched | 2/4/5/6 (queue registered on all boards) | V |
| **USART1** 256000 8N1 | TX | `uart_send(1)` | 256 B DMA | **types 3, 5, 10, 11, 12, 18, 21, 23** (and 17) | **all** | V |
| USART1 | RX | ring `0x2000002b` | 512 B DMA, 320 B frame | anything, then dispatched | all | V |
| USART3 257143 8N1 | TX/RX | `uart_send(3)`, ring `0x2000007b` | | types 2, 6, 13, 14, 16, 20, 22 | all | V |

**Correction to earlier docs.** `dataflow.md` and `m0900-buses.tsv` said that on boards
2/4/5/6, types 3, 5, 10, 11, 12, ... (FC, center board, battery, ESC) were sent to "CAN queue
`0x20002538`". That is wrong. Those types are sent out **USART1**, on every board code (§3).
`0x20002538` is the **0x414** queue, and only type 30 is routed to it.

## 1. Queue initialisation: 0x20002538 is StdId 0x414 (V)

`can_queue_init 0x0800b3ec (obj, std_id, is_tx, ring_size, [sp]=ring_buf)` writes
`obj[0]=std_id`, `obj[0x18]=is_tx`, and the ring descriptor at `obj+4` (size at `+0xc`, mask at
`+0x10`, buf at `+0x14`). Then:

- `is_tx=1`: the object is appended to the TX table `0x200015d0+0x34` (count at
  `0x20000094`, 13 slots). The TX-empty IRQ `0x0800b299` drains this table.
- `is_tx=0`: a bxCAN filter is installed (`CAN_FilterInit 0x0800872e`). The filter bank is
  the RX count, FilterIdHigh is `std_id<<5`, the mask is `0xffff/0xffff` in 32-bit mask mode
  (an exact match on a standard data frame), and it goes to FIFO0. The object is appended to
  the RX table `0x200015d0` (count at `0x20000098`).

There are exactly four call sites, from two functions:

| Caller | Site | obj | StdId | Dir | Ring |
|---|---|---|---|---|---|
| `0x080113a8` | `0x080113de` | `0x20002330` | `0x412` | TX | 512 B @ `0x20001f30` |
| `0x080113a8` | `0x080113f2` | `0x2000234c` | `0x413` | RX (filter bank 0) | 512 B @ `0x20002130` |
| `0x08011828` | `0x08011838` | **`0x20002538`** | **`0x414`** | TX | 64 B @ `0x200024b8` |
| `0x08011828` | `0x0801184c` | `0x20002554` | `0x415` | RX (filter bank 1) | 64 B @ `0x200024f8` |

Both callers are called from boot init `0x0800dac4`, at `0x0800db98` and `0x0800db9c`.
`0x080113a8` checks `get_board_version` ∈ {4,5,6,2} itself. **`0x08011828` has no board
check**, so the 0x414/0x415 objects and filter are created on every board. The CAN peripheral
itself (`can_init 0x0800b31c`, called from `0x0800dbe0`) is only brought up for boards
{4,5,6,2}. So on board 7 the 0x414/0x415 queues exist but are dead.

## 2. Receive: 0x413 and 0x415 reach the same DUML processing (V)

- **IRQ** `can_rx0 0x0800b23c` is not specific to any ID. It reads FIFO0, walks the 13-slot
  RX table, and for the object whose `obj[0]` equals the frame's StdId (with IDE=0) it pushes
  the DLC bytes into `obj+4`. Nothing in it branches on 0x413 or 0x415.
- **Pumps**, all run from the main loop at `0x0800dc6c..0x0800dc82` with no board check:

  | Pump | Ring | Parser obj | Then |
  |---|---|---|---|
  | `0x0801148c` | `0x20002350` (CAN 0x413), or `0x20000053` (USART2) on board 7 | `0x20002368`, buf 320 B | `duml_dispatch 0x0801198a` |
  | `0x08011882` | `0x20002558` (CAN 0x415) | `0x20002570`, buf **64 B** | `duml_dispatch 0x0801198a` |
  | `0x08012626` | `0x2000002b` (USART1, filled by IRQ `0x0800ab86`) | `0x20002620`, buf 320 B | `duml_dispatch 0x0801198a` |

- **Parsers.** All three are created with `parser_init 0x08011a7e(parser, buf, cb, size)` and
  the **same** frame callback `0x08011be7`. They are fed by the same byte-wise state machine,
  `0x08011a8e`.
- **Differences** (V for the code, I for the meaning):
  - The 0x415 channel accepts at most **64-byte** DUML frames. A longer header length makes
    the parser resync at `0x08011ad8`.
  - The 0x415 pump has **no link-alive watchdog**. The 0x413 pump counts to 0x96 and the
    USART1 pump counts to 0x258, then each calls `0x0800c320` (status bits 8 and 4). The
    0x415 pump has neither.
  - I: so 0x414/0x415 is a small auxiliary channel, not a monitored main link.
- **Origin is lost.** `duml_dispatch` (table `0x0801a120`) keys only on the receiver type and
  index plus the command set and id. It has no port field, so a frame that arrives on 0x415
  is handled exactly like one on 0x413 or USART1. When nothing matches, it is forwarded by
  `packet_send`.

## 3. Routing: which receiver types select each queue (V)

`packet_send 0x080118d0` uses `tbb` on `pkt[5] & 0x1f`. The table is at `0x080118e4`, and each
target is `0x080118e4 + 2*byte`. Every target was followed to its final branch:

| Types | tbb target | Resolves to |
|---|---|---|
| 2, 6, 13, 14, 16, 20, 22 | `0x0801194e` | `uart_send(3, ...)` USART3 |
| 1, 4, 8, 15 | `0x08011904` | `0x0801141c`: on boards 2/4/5/6, `can_enqueue_and_tx(0x20002330)` (**0x412**); on board 7, a UART chosen by type/index |
| **3, 5, 10, 11, 12, 18, 21, 23** | **`0x08011938`** | **`0x0801261c` = `movs r0,#1; b uart_send` → USART1, with no board check** |
| 17 | `0x0801195c` | boards 2/4/5/6: `0x08011936` → USART1; board 7: `0x0801141c` |
| **30** | `0x0801190e` | boards 2/4/5/6: `0x08011942` → `0x08011876` → `can_enqueue_and_tx(0x20002538)` (**0x414**); board 7: USART1 |
| 0, 7, 9, 19, 24-29 | `0x08011988` | dropped |

How the earlier misreading happened: `0x08011938` is the second instruction of the board-7
fall-through at `0x08011936`. The `tbb` jumps there directly, so it skips the board check.
`uart_send` port 1 is DMA1 channel 4 (`0x40020044`), which is USART1_TX on STM32F1.

Exhaustive search: the only branches into `can_enqueue_and_tx 0x0800b468` are `0x08011460`
(the 0x412 queue) and `0x0801187e` (the 0x414 queue). The only way into `0x08011876` is
`0x0801194a` (type 30). So **the m0900 code never sends anything on 0x414 except DUML frames
addressed to receiver type 30**.

## 4. Framing: identical on every channel (V)

All channels use the same parser, `0x08011a8e`, and the same callback, so they all use:

- sync byte `0x55`,
- `len = u16[1] & 0x3ff`, resync when `len` is larger than the buffer,
- version `b2>>2` ∈ {0,1} (`0x08011a66`),
- header CRC8 with seed `0x77` over bytes 0..2, compared with byte 3 (`0x08011e0e`),
- frame CRC16 with seed `0x3692` over `len-2`, compared with the last u16 (`0x08011be6`).

The only per-channel difference is buffer size: 320 B for 0x413 and USART1, 64 B for 0x415.

## 5. What this means for the "two logical links on one CAN bus" theory

- **V:** there are two logical DUML links on CAN1 at 1 Mbit/s, 0x412/0x413 and 0x414/0x415.
  They are full duplex, use the same framing, and feed the same router.
- **Refuted (V):** "one CAN link for the FC". m0900 **never** sends FC-type traffic (type 3)
  over CAN. Type 3 goes to USART1 on every board. This also settles the old "which USART is
  CENTER" question: **USART1 (256000 8N1) is the FC/center-board DUML link**, and it carries
  FC, center board (5), PC/MVO (10), battery (11) and ESC (12). This matches the wiki's
  "CENTER = 256000 8N1 to FC". The "RX armed, no TX route" note was the misread `tbb`.
  - I: OSD pushes from the FC (`set 0x03 id 0x43`) therefore most likely arrive on USART1, not
    CAN 0x413. They still reach the same dispatch handler `0x08011ed5`.
- **V:** 0x412/0x413 is the **camera/gimbal side**. It carries type 1 (camera), type 4
  (gimbal), type 8 (DM36x air) and type 15. The `0x43` handler re-addresses FC pushes to type 1,
  and those go out here.
- **V:** 0x414/0x415 is a **dedicated channel to receiver type 30**. Type 30 is unnamed in
  this repo (`DeviceType` in `app/packages/duml` does not list it). The camera's own router
  also gives type 30 a channel of its own (`fpga-write-path.md` §1: "ch1: type 30"). I: so
  type 30 is a real peer with a fixed, separate link. Which board it is: **U**.
- **Active or vestigial?** Registering the channel does not prove it is used, as you noted.
  What is shown is narrower:
  - V: the queues and filter exist on every board, and the RX pump runs unconditionally.
  - V: the TX side is reachable only by forwarding a frame addressed to type 30. No m0900
    code builds such a frame directly.
  - U: whether any node on a real P3P CAN bus sends StdId 0x415, or whether anything ever
    addresses type 30. The 64 B frame cap and the missing watchdog fit a small, optional
    peer.

## 6. How to close the remaining U items

1. **Is 0x414/0x415 live on the bus?** Put a passive CAN sniffer (1 Mbit/s, listen-only) on
   the m0900 CAN pair (PA11/PA12 transceiver) of the operator's own aircraft and log the
   StdIds. 0x412/0x413 should show; 0x414/0x415 either shows or does not. This needs no
   decoding: the frames are plain DUML split into 8-byte chunks.
2. **Who is type 30?** Grep the other modules (m0306 FC, m0100 camera, m1100/m1200/m1700)
   for routes that send type-30 frames, i.e. a `tbb` or table entry for index 30, or a byte
   `0x1e` stored to `pkt[5]`. The FC firmware's CAN TX setup would show whether it owns
   StdId 0x415.
3. **Board code.** `get_board_version` (RAM `0x200000d8`) decides CAN versus board-7 UART
   routing. Read it on hardware with DUML `set 0x00 id 0x01` (version) or a Renode GPIO
   strap sweep.
