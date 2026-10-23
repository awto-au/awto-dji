# captures/

Raw USB captures (USBPcap via tshark) of vendor tools talking to the aircraft/controller.

## 2026-10-23_assistant2-phantom_p3-controller.pcapng
- Host: Windows VM, USBPcap1 (root hub), Wireshark 4.6.9. 604 packets, 427 s.
- Tool: DJI Assistant 2 For Phantom 2.0.10.4, launched with a Phantom 3 controller attached.
  The tool reported "device not supported" (it targets the Phantom 4 family).
- Devices: `2CA3:0008` (USB 1.1, "DJI CONTROLLER", COM3) and `FFF0:0008` (USB 2.0, COM4).
- Decoded: `*.decoded.txt` (`scripts/duml_pcap_decode.ps1`).
- Observed: host asks the controller set 00 id 0c (ping), 01 (version -> `GL300C`) and ff
  (build string -> `WM320 A7_LPC1 20170828/00`). The FFF0 port gets a ~2 Hz host ping (00/0c)
  that is never answered, and emits ~1 Hz ASCII debug lines (`gimbal pitch/roll/yaw`, `sending limit areas`).
- Reading of "WM320" vs the Phantom 4's "WM330" is an inference, not confirmed in the tool.
