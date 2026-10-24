# Session 2026-10-24: RC identity queries, live AOA link

## RC identity (`scripts/re/get_identity.py`)
- `get_identity.log` - read-only identity/serial/version queries sent to the RC
  (`/dev/ttyACM4`, receiver 0x0e and others). See `docs/identity-queries.md` for the per-query
  table and verification. Summary: RC answers GetVersion/GetDeviceInfo/GetDeviceState; no
  reply to GetSerialNum or the RC master-id queries at any receiver tried.

## App live link (`app_live_link.log`)
- `adb logcat` capture from the test phone (192.168.25.120) while `awto_dji_app` was
  connected over the real AOA link (RC on the phone's USB-A port, bird powered). Shows the
  app's own `[link]` rx/packet lines plus platform USB-accessory events.
- Link health in-app at capture time: DUML + video both flowing (video ~570-595 KB/s,
  DUML ~3 KB/s), high CRC-error count consistent with the known resync-on-video-bytes
  behaviour documented in `docs/aoa-live-test-2026-10-23.md`.
- OSD-derived position/attitude values in this capture are implausible (e.g. altitude in the
  thousands of m/s range, lat/lon out of range) - not yet explained; worth checking the OSD
  field offsets/scale against a known-good capture before trusting this screen's numbers.
