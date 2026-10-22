//! Ground-station client for the awto-dji Android bridge, over the `mavlink` crate.
//!
//! The Android app (DJI Mobile SDK v4) is the vehicle; this is the GCS. They exchange
//! MAVLink v2 `common` messages over UDP. The message subset matches the Python client
//! and the Kotlin bridge (see `ground/python/awto_dji_ground/protocol.py`).

use mavlink::dialects::common::{
    MavAutopilot, MavCmd, MavFrame, MavMessage, MavModeFlag, MavState, MavType, COMMAND_LONG_DATA,
    HEARTBEAT_DATA, SET_POSITION_TARGET_LOCAL_NED_DATA,
};
use mavlink::error::MessageReadError;
use mavlink::{Connection, MavConnection, MavHeader};
use std::sync::Mutex;
use std::thread::sleep;
use std::time::{Duration, Instant};

pub const VEHICLE_SYSTEM_ID: u8 = 1;
pub const VEHICLE_COMPONENT_ID: u8 = 1;
pub const GCS_SYSTEM_ID: u8 = 255;
pub const GCS_COMPONENT_ID: u8 = 190;

pub const MAX_HORIZONTAL_MPS: f32 = 5.0;
pub const MAX_VERTICAL_MPS: f32 = 3.0;
pub const MAX_YAW_DPS: f32 = 90.0;

/// Velocity-and-yaw-rate `type_mask`: keep vel x/y/z and yaw_rate, ignore the rest.
const VELOCITY_YAWRATE_TYPE_MASK: u16 = 0b0000_0100_1100_0111;

const POLL_SLEEP: Duration = Duration::from_millis(2);

/// Custom flight modes reported in `HEARTBEAT.custom_mode`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FlightMode {
    Unknown,
    Manual,
    Hold,
    Guided,
    Takeoff,
    Landing,
    Rtl,
    Other(u32),
}

impl From<u32> for FlightMode {
    fn from(v: u32) -> Self {
        match v {
            0 => FlightMode::Unknown,
            1 => FlightMode::Manual,
            2 => FlightMode::Hold,
            3 => FlightMode::Guided,
            4 => FlightMode::Takeoff,
            5 => FlightMode::Landing,
            6 => FlightMode::Rtl,
            other => FlightMode::Other(other),
        }
    }
}

#[derive(Debug, Clone, Copy, Default)]
pub struct Telemetry {
    pub lat: f64,
    pub lon: f64,
    pub relative_alt_m: f32,
    pub vx: f32,
    pub vy: f32,
    pub vz: f32,
    pub heading_deg: f32,
    pub battery_pct: i8,
    pub satellites: u8,
    pub armed: bool,
    pub in_air: bool,
    pub custom_mode: u32,
    pub has_heartbeat: bool,
}

impl Telemetry {
    pub fn mode(&self) -> FlightMode {
        FlightMode::from(self.custom_mode)
    }
}

#[derive(Debug)]
pub enum Error {
    Io(std::io::Error),
    Mavlink(String),
    Rejected { command: u32, result: u32 },
    Timeout(&'static str),
}

impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Error::Io(e) => write!(f, "io: {e}"),
            Error::Mavlink(e) => write!(f, "mavlink: {e}"),
            Error::Rejected { command, result } => {
                write!(f, "command {command} rejected: MAV_RESULT={result}")
            }
            Error::Timeout(what) => write!(f, "timed out waiting for {what}"),
        }
    }
}

impl std::error::Error for Error {}
pub type Result<T> = std::result::Result<T, Error>;

fn clamp(v: f32, limit: f32) -> f32 {
    if v.is_nan() {
        0.0
    } else {
        v.clamp(-limit, limit)
    }
}

pub struct Vehicle {
    conn: Connection<MavMessage>,
    seq: Mutex<u8>,
    pub telemetry: Telemetry,
    last_gcs_hb: Instant,
}

impl Vehicle {
    /// Connect with any `mavlink` address, e.g. `"udpout:HOST:14550"` to reach the
    /// bridge or `"udpin:0.0.0.0:14550"` to listen for it.
    pub fn connect(address: &str) -> Result<Self> {
        let conn = mavlink::connect::<MavMessage>(address).map_err(Error::Io)?;
        Ok(Self {
            conn,
            seq: Mutex::new(0),
            telemetry: Telemetry::default(),
            last_gcs_hb: Instant::now() - Duration::from_secs(10),
        })
    }

    fn header(&self) -> MavHeader {
        let mut seq = self.seq.lock().unwrap();
        let header = MavHeader {
            system_id: GCS_SYSTEM_ID,
            component_id: GCS_COMPONENT_ID,
            sequence: *seq,
        };
        *seq = seq.wrapping_add(1);
        header
    }

    fn send(&self, msg: &MavMessage) -> Result<()> {
        self.conn
            .send(&self.header(), msg)
            .map_err(|e| Error::Mavlink(e.to_string()))?;
        Ok(())
    }

    /// Emit a GCS heartbeat, and tell a `udpin` bridge our address.
    pub fn send_gcs_heartbeat(&mut self) -> Result<()> {
        let hb = HEARTBEAT_DATA {
            custom_mode: 0,
            mavtype: MavType::MAV_TYPE_GCS,
            autopilot: MavAutopilot::MAV_AUTOPILOT_INVALID,
            base_mode: MavModeFlag::empty(),
            system_status: MavState::MAV_STATE_ACTIVE,
            mavlink_version: 3,
        };
        self.send(&MavMessage::HEARTBEAT(hb))?;
        self.last_gcs_hb = Instant::now();
        Ok(())
    }

    fn heartbeat_if_due(&mut self) -> Result<()> {
        if self.last_gcs_hb.elapsed() >= Duration::from_secs(1) {
            self.send_gcs_heartbeat()?;
        }
        Ok(())
    }

    /// Poll for messages for up to `budget`, applying each to telemetry. Returns how
    /// many were read.
    pub fn pump(&mut self, budget: Duration) -> Result<usize> {
        self.heartbeat_if_due()?;
        let deadline = Instant::now() + budget;
        let mut count = 0;
        loop {
            match self.conn.try_recv() {
                Ok((_h, msg)) => {
                    self.ingest(&msg);
                    count += 1;
                }
                Err(MessageReadError::Io(e))
                    if e.kind() == std::io::ErrorKind::WouldBlock
                        || e.kind() == std::io::ErrorKind::TimedOut =>
                {
                    if Instant::now() >= deadline {
                        return Ok(count);
                    }
                    sleep(POLL_SLEEP);
                }
                // A parse error on one datagram: skip it and keep going.
                Err(_) => {
                    if Instant::now() >= deadline {
                        return Ok(count);
                    }
                }
            }
        }
    }

    fn ingest(&mut self, msg: &MavMessage) {
        let t = &mut self.telemetry;
        match msg {
            MavMessage::HEARTBEAT(hb) => {
                t.has_heartbeat = true;
                t.custom_mode = hb.custom_mode;
                t.armed = hb.base_mode.intersects(MavModeFlag::MAV_MODE_FLAG_SAFETY_ARMED);
            }
            MavMessage::GLOBAL_POSITION_INT(p) => {
                t.lat = p.lat as f64 / 1e7;
                t.lon = p.lon as f64 / 1e7;
                t.relative_alt_m = p.relative_alt as f32 / 1000.0;
                t.vx = p.vx as f32 / 100.0;
                t.vy = p.vy as f32 / 100.0;
                t.vz = p.vz as f32 / 100.0;
                if p.hdg != u16::MAX {
                    t.heading_deg = p.hdg as f32 / 100.0;
                }
            }
            MavMessage::GPS_RAW_INT(g) => t.satellites = g.satellites_visible,
            MavMessage::BATTERY_STATUS(b) => t.battery_pct = b.battery_remaining,
            MavMessage::EXTENDED_SYS_STATE(s) => {
                t.in_air = matches!(s.landed_state as u8, 2 | 3 | 4);
            }
            _ => {}
        }
    }

    /// Pump until a fresh heartbeat is seen, or time out.
    pub fn wait_ready(&mut self, timeout: Duration) -> Result<()> {
        self.send_gcs_heartbeat()?;
        let deadline = Instant::now() + timeout;
        while Instant::now() < deadline {
            self.pump(Duration::from_millis(200))?;
            if self.telemetry.has_heartbeat {
                return Ok(());
            }
        }
        Err(Error::Timeout("bridge heartbeat"))
    }

    fn command_long(&self, command: MavCmd, params: [f32; 7]) -> Result<()> {
        let data = COMMAND_LONG_DATA {
            param1: params[0],
            param2: params[1],
            param3: params[2],
            param4: params[3],
            param5: params[4],
            param6: params[5],
            param7: params[6],
            command,
            target_system: VEHICLE_SYSTEM_ID,
            target_component: VEHICLE_COMPONENT_ID,
            confirmation: 0,
        };
        self.send(&MavMessage::COMMAND_LONG(data))
    }

    fn await_ack(&mut self, command: MavCmd, timeout: Duration) -> Result<()> {
        let deadline = Instant::now() + timeout;
        while Instant::now() < deadline {
            match self.conn.try_recv() {
                Ok((_h, MavMessage::COMMAND_ACK(ack))) if ack.command == command => {
                    // MAV_RESULT_ACCEPTED = 0, MAV_RESULT_IN_PROGRESS = 5
                    return match ack.result as u32 {
                        0 | 5 => Ok(()),
                        other => Err(Error::Rejected {
                            command: command as u32,
                            result: other,
                        }),
                    };
                }
                Ok((_h, msg)) => self.ingest(&msg),
                Err(MessageReadError::Io(e))
                    if e.kind() == std::io::ErrorKind::WouldBlock
                        || e.kind() == std::io::ErrorKind::TimedOut =>
                {
                    sleep(POLL_SLEEP);
                }
                Err(_) => {}
            }
        }
        Err(Error::Timeout("COMMAND_ACK"))
    }

    pub fn takeoff(&mut self, altitude_m: f32) -> Result<()> {
        self.command_long(
            MavCmd::MAV_CMD_NAV_TAKEOFF,
            [0.0, 0.0, 0.0, f32::NAN, 0.0, 0.0, altitude_m],
        )?;
        self.await_ack(MavCmd::MAV_CMD_NAV_TAKEOFF, Duration::from_secs(10))
    }

    pub fn land(&mut self) -> Result<()> {
        self.command_long(MavCmd::MAV_CMD_NAV_LAND, [0.0; 7])?;
        self.await_ack(MavCmd::MAV_CMD_NAV_LAND, Duration::from_secs(10))
    }

    pub fn return_to_home(&mut self) -> Result<()> {
        self.command_long(MavCmd::MAV_CMD_NAV_RETURN_TO_LAUNCH, [0.0; 7])?;
        self.await_ack(MavCmd::MAV_CMD_NAV_RETURN_TO_LAUNCH, Duration::from_secs(10))
    }

    pub fn arm(&mut self, arm: bool) -> Result<()> {
        let p1 = if arm { 1.0 } else { 0.0 };
        self.command_long(
            MavCmd::MAV_CMD_COMPONENT_ARM_DISARM,
            [p1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        )?;
        self.await_ack(MavCmd::MAV_CMD_COMPONENT_ARM_DISARM, Duration::from_secs(5))
    }

    /// Send one body-frame velocity frame (m/s) and yaw rate (deg/s). Clamped to the
    /// protocol envelope. Resend at ~10 Hz; the bridge zeroes the sticks if frames stop.
    pub fn set_velocity(&self, forward: f32, right: f32, down: f32, yaw_rate_dps: f32) -> Result<()> {
        let data = SET_POSITION_TARGET_LOCAL_NED_DATA {
            time_boot_ms: 0,
            target_system: VEHICLE_SYSTEM_ID,
            target_component: VEHICLE_COMPONENT_ID,
            coordinate_frame: MavFrame::MAV_FRAME_BODY_NED,
            type_mask: VELOCITY_YAWRATE_TYPE_MASK,
            x: 0.0,
            y: 0.0,
            z: 0.0,
            vx: clamp(forward, MAX_HORIZONTAL_MPS),
            vy: clamp(right, MAX_HORIZONTAL_MPS),
            vz: clamp(down, MAX_VERTICAL_MPS),
            afx: 0.0,
            afy: 0.0,
            afz: 0.0,
            yaw: 0.0,
            yaw_rate: clamp(yaw_rate_dps, MAX_YAW_DPS).to_radians(),
        };
        self.send(&MavMessage::SET_POSITION_TARGET_LOCAL_NED(data))
    }

    /// Stream `forward/right/down/yaw_rate` for `duration` at `rate_hz`, then hover.
    pub fn fly_velocity(
        &mut self,
        forward: f32,
        right: f32,
        down: f32,
        yaw_rate_dps: f32,
        duration: Duration,
        rate_hz: f32,
    ) -> Result<()> {
        let period = Duration::from_secs_f32(1.0 / rate_hz.max(1.0));
        let end = Instant::now() + duration;
        while Instant::now() < end {
            self.set_velocity(forward, right, down, yaw_rate_dps)?;
            self.pump(period)?;
        }
        self.set_velocity(0.0, 0.0, 0.0, 0.0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn clamp_handles_nan_and_limits() {
        assert_eq!(clamp(f32::NAN, 5.0), 0.0);
        assert_eq!(clamp(9.0, 5.0), 5.0);
        assert_eq!(clamp(-9.0, 5.0), -5.0);
    }

    #[test]
    fn flight_mode_mapping() {
        assert_eq!(FlightMode::from(3), FlightMode::Guided);
        assert_eq!(FlightMode::from(99), FlightMode::Other(99));
    }

    #[test]
    fn type_mask_keeps_velocity_and_yawrate() {
        // Ignore bits: pos x/y/z (0-2), acc x/y/z (6-8), yaw (10). Keep vel (3-5), yaw_rate (11).
        let m = VELOCITY_YAWRATE_TYPE_MASK;
        for bit in [0, 1, 2, 6, 7, 8, 10] {
            assert_eq!(m >> bit & 1, 1, "bit {bit} should be ignored");
        }
        for bit in [3, 4, 5, 11] {
            assert_eq!(m >> bit & 1, 0, "bit {bit} should be kept");
        }
    }
}
