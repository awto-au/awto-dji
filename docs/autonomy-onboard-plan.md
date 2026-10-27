# Onboard autonomous operation: architecture plan

Goal: an **autonomy agent running on the aircraft's own Linux** (camera A9, m0100) that flies
pre-planned/offboard missions on the owner's own P3P, driving the stock flight controller
(m0306) with high-level setpoints — without a ground link. Keep the FC: it owns sensor fusion,
stabilization, motor mixing and its own failsafes. We supply *where to go*, not *how to fly*.

Tags: **V** verified, **I** inferred, **U** unknown.

## Why drive the stock FC, not replace it

Replacing m0306 means reproducing IMU/GPS fusion, attitude control, ESC protocol and battery
failsafes on an STM32F427 with no airframe tuning data — months of work before a stable hover,
with brick/flyaway risk. Every mature autonomy stack (PX4 offboard, ArduPilot guided, DJI MSDK
missions) instead keeps the FC and sends setpoints. We do the same.

## The hard constraint: control semantics must be verified, never guessed

`protocol-verification.md` and the m0306 scan (2026-10-25) establish:
- **V:** m0306 is heavily stripped — no control strings, no CRC tables, no plain set/id dispatch
  records. The joystick command ID is itself unresolved (dissector `0x29` vs app enum `0x8E`/142,
  `apk-vs-dissector-gap-report`).
- **V:** the app's real control + geofence logic is in native libs (`libmain.so`,
  `libSDKRelativeJNI.so`, `libFlyForbid.so`) this project does not RE.
- **Consequence:** the virtual-stick **payload**, the **authority/mode handshake**, and the
  **watchdog period** cannot be recovered reliably from the stock FC binary. Guessing any of
  them and then flying is the classic flyaway path.

**Principle:** the exact control frame, authority sequence and timeout come from a **verified
source on the owner's own aircraft** — a DJI Mobile SDK v4 session (MSDK officially supports the
P3) or a capture of the real GO app driving the bird — captured with `aoa_relay_server.py` /
`aoa_chunk_decode.py`. The firmware RE tells us the *transport and routing*; the *control
semantics* are ground-truthed, then replicated onboard.

## Components

```
                      +------------------- camera A9 Linux (m0100) -------------------+
   mission file  -->  | autonomy agent (new)                                         |
   (waypoints,        |   - mission sequencer        - geofence gate (ports          |
    offboard loop)    |   - setpoint generator          packages/geofence logic)     |
                      |   - HARD WATCHDOG            - telemetry ingest (OSD 0x03/43) |
                      |          |                                   ^                |
                      |          v  control frame (verified)         | telemetry      |
                      |   DUML-over-IPC  --netlink--> rpmsg_trans.ko -+                |
                      +---------------------------|----------------------------------+
                                                  v  (camera RTOS DjiMsg router)
                                 FC setpoints --> ch0 --> ... --> m0900 USART1 --> m0306 (FC)
```

- **Autonomy agent** — new process. Portable core (mission, geofence, watchdog, setpoint math)
  with a thin platform layer for the onboard transport. Cross-compiled for the camera's Linux
  (ARM, `arm-none-linux-gnueabi`, glibc 2013.05, kernel 3.8 — static link to avoid its old libc).
- **Transport** — `linux-to-fc-path.md`: netlink → `rpmsg_trans.ko` (`dji_app`/`dji_sock`) →
  RTOS `DjiMsg` router. DUML-over-IPC framing on that channel is **U** (only the fw-update
  framing is decoded) — a work item below.
- **Telemetry** — the FC's OSD push (set 0x03 id 0x43) already flows; the agent ingests it for
  position/attitude/battery to close the loop. Decoders exist in `packages/duml`.
- **Geofence** — `packages/geofence` already gates by zone/altitude/velocity; every setpoint is
  checked **before** it is sent.

## Safety model

Safety model: see `SAFETY.md` ("Autonomy ... safety model").

## Work order (safety items gate flight)

| Step | What | Source | State |
|---|---|---|---|
| A | Control-command surface: virtual-stick id + payload, authority/mode handshake | **verified capture** (MSDK v4 / GO app on owner's bird), not the stripped binary | TODO — needs owner hardware |
| B | FC command-timeout / failsafe behaviour (stop setpoints → what, how fast; bad-mode handling) | **bench measurement**, props off | TODO — needs owner hardware |
| C | Onboard injection framing: DUML-over-IPC on the camera channel; does the FC accept an onboard sender | m0100 RTOS `DjiIpc*` trace + bench | partial (route V, framing U) |
| D | Autonomy agent: geofence-gated setpoint loop + hard watchdog; mission sequencer; telemetry ingest | this repo | buildable now (safe-by-construction, control frame as a verified-capture slot) |
| E | Bench bring-up: props off → motors disabled → tethered → open-field, failsafe+override proven at each gate | — | after A–D |

## What can be built now, before any hardware

- The **agent skeleton**: mission/geofence/watchdog/telemetry state machine, with the control
  frame behind an interface whose only implementation is "fill from verified capture" (refuses to
  emit until populated). This makes the safety scaffolding real and testable with replay/sim
  (the app already has simulated + replay transports).
- The **capture tooling** to get step A: scripted MSDK-v4 / GO-app session capture + a decoder
  that extracts the virtual-stick frames, authority sequence and inter-frame timing.
- Unit tests for the geofence gate and watchdog against recorded telemetry.

Scope & safety: see `SAFETY.md`.
