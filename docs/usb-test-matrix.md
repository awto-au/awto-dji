# USB bench test matrix

2026-10-24. Working hypothesis: the DJI subsystems may expose useful USB service
paths. Test each physical port and state before declaring support or lack of support.
Enumeration, streaming data and command replies are separate results.

## Current evidence

| Physical connection | Enumeration | Data / command evidence | Still to test |
|---|---|---|---|
| RC micro-USB service port | V: `2ca3:0008`, CDC ACM, currently `ttyACM4` | Prior captures/probes verify version, ping and build replies | Which aircraft destinations are routed, and whether telemetry/video is available |
| Aircraft front FC micro-USB | V previously: `fff0:0008`, CDC ACM; absent from current snapshot | Earlier log streaming; no replies to the tested queries. Later listen/heartbeat logs contain a silent run | Re-enumeration/power state, boot timing, receiver selection and session setup; silence is not proof USB is unsupported |
| RC USB-A phone connection | Prior Android AOA handshake and live telemetry capture | V: real DUML frames; video-like data also observed | PC-equivalent peripheral role and alternate firmware interfaces; see `fx3-usb-modes.md` |
| Camera/gimbal USB port | Not identified in current PC enumeration | Firmware contains USB/CDC mode and routing indications; actual hardware behavior U | Identify connector, capture descriptors across power-up, determine current function |
| Newly connected board near gimbal | Physical board/port identity not confirmed | No separately identified USB device in current snapshot | Establish whether this is native USB or an adapter; correlate one cable change with a topology change |

The last two rows may refer to the same physical interface; do not count them as two
verified devices. Four USB-UART adapters are present, but their downstream boards
cannot be identified from USB descriptor strings alone.

Snapshot: [usb_inventory.jsonl](../captures/sessions/2026-10-24/usb_inventory.jsonl).
At 12:00:59 Melbourne time, exactly one device in that snapshot has VID `2ca3`
and none have VID `fff0` or `0547`. Generic Cypress adapters are not automatically DJI
devices. The RC's two USB interfaces are one physical USB device, not two connections.

## Repeatable sequence for each port

1. Label the board and physical connector, cable, hub path and power state. Record
   which USB-UART adapter, if any, is used. Change one connection at a time.
2. Start the cached-descriptor watcher, then correlate plug/unplug and aircraft/RC
   power changes with topology, VID/PID, interfaces, endpoints and serial-port names.
   A missing enumeration result is a physical/power/role observation, not a DUML verdict.
3. Once the port is positively identified, check whether another process already owns
   it. Capture passive startup traffic before starting a query test. Opening a CDC port
   can change control lines even when no payload is sent; record line settings.
4. On an identified DJI CDC/DUML port, use the existing known read-only queries
   (General ping/version/build), recording sender/receiver and exact request bytes.
   Test one reader at a time. Keep boot-window and settled-boot results distinct.
5. Correlate replies by valid CRC, sequence, addresses and command set/ID. Preserve raw
   input when no DUML is found; it could be logs, another protocol or a partial stream.
6. For vendor bulk, storage, network or AOA interfaces, first identify their protocol
   and active endpoints. A serial probe is not a universal USB test. Record USB roles
   and any firmware-supported mode selection separately from ordinary query results.

Configuration setters and firmware-upgrade commands are outside this initial
read-only test pass. A positive interface result does not imply every command routes
through it; a failed query establishes only that exact test result.

## Inventory tool

`scripts/re/usb_inventory.py` uses cached sysfs attributes only. It does not open a
device or compete with the existing serial watcher. Timestamps use Melbourne time.
Watching emits an initial snapshot and subsequent changes as JSON Lines.

```sh
python3 -I scripts/re/usb_inventory.py
python3 -I scripts/re/usb_inventory.py --watch-seconds 60 --output captures/sessions/2026-10-24/usb_inventory.jsonl
```

Related evidence: `p3-usb-observations-2026-10-23.md`, `identity-queries.md`,
`camera-linux-console-access.md`, `fx3-usb-modes.md`. The historical headline in
`fc-usb-duml.md` is contradicted by that document's own later interrupt-handler
audit and must not be used to rule out further USB testing.
