# captures/

Tracked artifacts from real hardware (owner's aircraft/RC), kept because they can't be
regenerated from firmware/code alone. Regenerable analysis output (Renode, disassembly,
firmware unpack) stays in `tmp/` - see root CLAUDE.md.

- `sessions/<date>/` - per-session logs from live-hardware scripts (AOA relay, identity
  queries, gimbal sends, app logcat captures), one README per session.
- Top-level `*.pcapng`/`*.txt` below - USB captures of vendor tools (Assistant 2, tshark).
- `../capture_local/` (repo root, gitignored) - oversized captures from the same sessions
  (multi-GB relay logs, raw video) that stay on disk for agents to read but never get
  committed; git history can't shrink back down once something that big is in it.

Raw USB captures (USBPcap via tshark) of vendor tools talking to the aircraft/controller.

## 2026-10-23_assistant2-phantom_p3-controller.pcapng
- Host: Windows VM, USBPcap1 (root hub), Wireshark 4.6.9. 604 packets, 427 s.
- Tool: DJI Assistant 2 For Phantom 2.0.10.4, launched with a Phantom 3 controller attached.
  The tool reported "device not supported" (it targets the Phantom 4 family).
- Devices: `2CA3:0008` (USB 1.1, "DJI CONTROLLER", COM3) and `FFF0:0008` (USB 2.0, COM4).
- Decoded: `*.duml.txt` and `*.cdc-ctrl.txt` (`scripts/pcap_decode.py duml|cdc`; 90 DUML frames, all CRCs valid).
- Observed: host asks the controller set 00 id 0c (ping), 01 (version -> `GL300C`) and ff
  (build string -> `WM320 A7_LPC1 20170828/00`). The FFF0 port gets a ~2 Hz host ping (00/0c)
  that is never answered, and emits ~1 Hz ASCII debug lines (`gimbal pitch/roll/yaw`, `sending limit areas`).
- Reading of "WM320" vs the Phantom 4's "WM330" is an inference, not confirmed in the tool.

## 2026-10-23_assistant2-both-connected.pcapng
- Same host/tool as above, aircraft + controller both connected, Assistant 2 left running across several
  physical replugs. 760 packets, 248 s, USBPcap1. Files: `.duml.txt` (`scripts/pcap_decode.py duml`,
  167 DUML frames, all CRCs valid) and `.cdc-ctrl.txt` (`scripts/pcap_decode.py cdc`: baud, data format, DTR/RTS).
- Replugs at 23.6 s, 190.9 s, 216 s (controller) and 223 s (aircraft). USB device addresses swap
  between replugs (1.1/1.2), so read the `dev` column per time, not per address.
- Serial settings (both ports, Windows `usbser`): enumerates at 9600 8N1, the Assistant then
  sets **115200 8N1** on open. Port-open pattern is `SET_CONTROL_LINE_STATE`: **RTS=1, DTR=0**;
  closing/reset sends 0/0. **DTR is never asserted.** No SEND_BREAK. Some `GET_LINE_CODING`
  answers decode as "0 baud 0N1": probably empty completion packets, not real values.
- DUML: controller (2CA3) answers ping/version/build string; aircraft port (FFF0) is pinged every
  ~0.5 s and never answers, only emitting ~1 Hz ASCII debug lines (gimbal angles, "gps init", "compass
  stuck", "Eeprom write offset"). Nothing in the capture is a serial number or personal identifier
  (checked ASCII and UTF-16 strings).
