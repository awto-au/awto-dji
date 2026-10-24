# Session 2026-10-23: AOA relay, gimbal sweep, DJI Assistant under Wine

Live hardware sessions only (owner's RC + aircraft). Static/regenerable analysis logs
(Renode, disassembly, firmware unpack) stay in `tmp/logs/` - see root CLAUDE.md.

## AOA relay (`scripts/re/aoa_relay_server.py`)
- `aoa_relay_server.log` - raw hex, every chunk relayed between the phone accessory and the
  dev-machine TCP listener.
- `aoa_relay_frames.log` - decoded DUML frames pulled out of the same stream.
- `aoa_relay_stdout.log` - the server process's own stdout/stderr for the run.
- Phone: Samsung S9 (LineageOS) as USB accessory of the RC's USB-A port; `awto_dji_app`
  pumping bytes to this relay. See `docs/aoa-live-test-2026-10-23.md`.

## Gimbal sweep (`scripts/re/gimbal_sweep.py`)
- `gimbal_sweep.log` - yaw +-15 deg, two cycles, sent over the AOA proxy above. No reply
  confirmed in-band; visual confirmation was inconclusive this session.

## DJI Assistant 2 under Wine (`attempt2_*.log`)
- Wine trace logs (`WINEDEBUG`) from running DJI Assistant 2 For Phantom against the real RC
  bridged into the VM. `attempt2_djiservice.log` (DJIService), `attempt2_winsock.log`
  (network calls, incl. `mydjiflight.dji.com`), `attempt2_simulatorui.log`,
  `attempt2_loaddll.log` (module load trace, large/mostly noise).
- Outcome: Assistant 2 reports the Phantom 3 controller as unsupported (expected - see
  `docs/fc-usb-port.md` "Why Assistant 2 says device not supported").
