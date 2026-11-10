//! DJI Cloud API wire format: MQTT topics, message envelopes and command payloads.
//!
//! Field names follow the DJI Cloud API 1.x documentation
//! (<https://developer.dji.com/doc/cloud-api-tutorial/en/>). Check them against the
//! docs for the Cloud API version and aircraft you deploy against.

use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::time::{SystemTime, UNIX_EPOCH};

/// MQTT topics for one gateway (a DJI Dock or an RC running DJI Pilot 2).
#[derive(Debug, Clone)]
pub struct Topics {
    pub gateway_sn: String,
}

impl Topics {
    pub fn new(gateway_sn: impl Into<String>) -> Self {
        Self { gateway_sn: gateway_sn.into() }
    }

    fn thing(&self, suffix: &str) -> String {
        format!("thing/product/{}/{}", self.gateway_sn, suffix)
    }

    pub fn osd(&self) -> String { self.thing("osd") }
    pub fn state(&self) -> String { self.thing("state") }
    pub fn services(&self) -> String { self.thing("services") }
    pub fn services_reply(&self) -> String { self.thing("services_reply") }
    pub fn events(&self) -> String { self.thing("events") }
    pub fn events_reply(&self) -> String { self.thing("events_reply") }
    pub fn requests(&self) -> String { self.thing("requests") }
    pub fn requests_reply(&self) -> String { self.thing("requests_reply") }
    pub fn property_set(&self) -> String { self.thing("property/set") }
    pub fn property_set_reply(&self) -> String { self.thing("property/set_reply") }
    pub fn drc_up(&self) -> String { self.thing("drc/up") }
    pub fn drc_down(&self) -> String { self.thing("drc/down") }
    pub fn status(&self) -> String { format!("sys/product/{}/status", self.gateway_sn) }
    pub fn status_reply(&self) -> String { format!("sys/product/{}/status_reply", self.gateway_sn) }

    /// Topics the cloud side subscribes to (device -> cloud).
    pub fn uplink(&self) -> Vec<String> {
        vec![
            self.osd(),
            self.state(),
            self.services_reply(),
            self.events(),
            self.requests(),
            self.property_set_reply(),
            self.drc_up(),
            self.status(),
        ]
    }

    /// Classifies an incoming topic for this gateway.
    pub fn kind_of(&self, topic: &str) -> Option<TopicKind> {
        let kind = match topic {
            t if t == self.osd() => TopicKind::Osd,
            t if t == self.state() => TopicKind::State,
            t if t == self.services_reply() => TopicKind::ServicesReply,
            t if t == self.events() => TopicKind::Events,
            t if t == self.requests() => TopicKind::Requests,
            t if t == self.property_set_reply() => TopicKind::PropertySetReply,
            t if t == self.drc_up() => TopicKind::DrcUp,
            t if t == self.status() => TopicKind::Status,
            _ => return None,
        };
        Some(kind)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum TopicKind {
    Osd,
    State,
    ServicesReply,
    Events,
    Requests,
    PropertySetReply,
    DrcUp,
    Status,
}

pub fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
}

pub fn new_id() -> String {
    uuid::Uuid::new_v4().to_string()
}

/// Standard Cloud API message envelope.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Envelope {
    #[serde(default)]
    pub tid: String,
    #[serde(default)]
    pub bid: String,
    #[serde(default)]
    pub timestamp: u64,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub gateway: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub method: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub need_reply: Option<u8>,
    #[serde(default)]
    pub data: Value,
}

impl Envelope {
    pub fn request(method: &str, data: Value) -> Self {
        Self {
            tid: new_id(),
            bid: new_id(),
            timestamp: now_ms(),
            gateway: None,
            method: Some(method.to_owned()),
            need_reply: None,
            data,
        }
    }

    /// A reply to `incoming` carrying `data`, keeping its tid/bid/method.
    pub fn reply_to(incoming: &Envelope, data: Value) -> Self {
        Self {
            tid: incoming.tid.clone(),
            bid: incoming.bid.clone(),
            timestamp: now_ms(),
            gateway: None,
            method: incoming.method.clone(),
            need_reply: None,
            data,
        }
    }

    /// `result` code of a `*_reply` message; 0 means success.
    pub fn result(&self) -> Option<i64> {
        self.data.get("result").and_then(Value::as_i64)
    }
}

/// MQTT broker the aircraft connects to for Drone Remote Control (DRC).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DrcBroker {
    /// `host:port`
    pub address: String,
    pub client_id: String,
    pub username: String,
    pub password: String,
    /// Unix seconds after which the credentials expire.
    pub expire_time: u64,
    pub enable_tls: bool,
}

/// One DRC stick frame.
///
/// * `x` forward(+)/backward(-) speed, m/s
/// * `y` right(+)/left(-) speed, m/s
/// * `h` up(+)/down(-) speed, m/s
/// * `w` yaw rate, deg/s, clockwise positive
#[derive(Debug, Clone, Copy, Default, PartialEq, Serialize, Deserialize)]
pub struct Sticks {
    pub x: f64,
    pub y: f64,
    pub h: f64,
    pub w: f64,
}

/// Per-axis limits applied before a stick frame is sent.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct StickLimits {
    pub horizontal_mps: f64,
    pub vertical_mps: f64,
    pub yaw_dps: f64,
}

impl StickLimits {
    /// Protocol maximums from the DRC docs.
    pub const PROTOCOL_MAX: StickLimits = StickLimits { horizontal_mps: 17.0, vertical_mps: 5.0, yaw_dps: 90.0 };
    /// Conservative default for manual testing.
    pub const CAUTIOUS: StickLimits = StickLimits { horizontal_mps: 5.0, vertical_mps: 2.0, yaw_dps: 45.0 };
}

impl Default for StickLimits {
    fn default() -> Self {
        Self::CAUTIOUS
    }
}

impl Sticks {
    pub const ZERO: Sticks = Sticks { x: 0.0, y: 0.0, h: 0.0, w: 0.0 };

    /// Clamps every axis to `limits` (never above the protocol maximum) and maps NaN to 0.
    pub fn clamped(self, limits: StickLimits) -> Sticks {
        fn clamp(v: f64, lim: f64, max: f64) -> f64 {
            let lim = lim.abs().min(max);
            if v.is_nan() { 0.0 } else { v.clamp(-lim, lim) }
        }
        let max = StickLimits::PROTOCOL_MAX;
        Sticks {
            x: clamp(self.x, limits.horizontal_mps, max.horizontal_mps),
            y: clamp(self.y, limits.horizontal_mps, max.horizontal_mps),
            h: clamp(self.h, limits.vertical_mps, max.vertical_mps),
            w: clamp(self.w, limits.yaw_dps, max.yaw_dps),
        }
    }
}

/// Parameters for the `takeoff_to_point` service ("one-key takeoff").
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TakeoffToPoint {
    pub target_latitude: f64,
    pub target_longitude: f64,
    /// Target height, ellipsoid height in metres.
    pub target_height: f64,
    /// Height to climb to before flying to the target, metres.
    pub security_takeoff_height: f64,
    /// Return-to-home altitude, metres.
    pub rth_altitude: f64,
    /// 0 hover, 1 land, 2 return home.
    pub rc_lost_action: u8,
    pub max_speed: f64,
    #[serde(default = "new_id")]
    pub flight_id: String,
}

/// A point for `fly_to_point`.
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct Waypoint {
    pub latitude: f64,
    pub longitude: f64,
    /// Ellipsoid height, metres.
    pub height: f64,
}

/// `services` method names and payloads.
pub mod services {
    use super::*;

    pub const FLIGHT_AUTHORITY_GRAB: &str = "flight_authority_grab";
    pub const PAYLOAD_AUTHORITY_GRAB: &str = "payload_authority_grab";
    pub const DRC_MODE_ENTER: &str = "drc_mode_enter";
    pub const DRC_MODE_EXIT: &str = "drc_mode_exit";
    pub const TAKEOFF_TO_POINT: &str = "takeoff_to_point";
    pub const FLY_TO_POINT: &str = "fly_to_point";
    pub const FLY_TO_POINT_STOP: &str = "fly_to_point_stop";
    pub const RETURN_HOME: &str = "return_home";
    pub const RETURN_HOME_CANCEL: &str = "return_home_cancel";
    pub const CAMERA_PHOTO_TAKE: &str = "camera_photo_take";

    pub fn drc_mode_enter(broker: &DrcBroker, osd_frequency: u32, hsi_frequency: u32) -> Value {
        json!({ "mqtt_broker": broker, "osd_frequency": osd_frequency, "hsi_frequency": hsi_frequency })
    }

    pub fn fly_to_point(points: &[Waypoint], max_speed: f64) -> Value {
        json!({ "fly_to_id": new_id(), "max_speed": max_speed, "points": points })
    }

    /// `payload_index` looks like `"39-0-7"` (type-subtype-gimbal index).
    pub fn payload(payload_index: &str) -> Value {
        json!({ "payload_index": payload_index })
    }
}

/// `drc/down` method names and payloads.
pub mod drc {
    use super::*;

    pub const DRONE_CONTROL: &str = "drone_control";
    pub const HEART_BEAT: &str = "heart_beat";
    pub const DRONE_EMERGENCY_STOP: &str = "drone_emergency_stop";

    pub fn drone_control(seq: u64, s: Sticks) -> Value {
        json!({ "method": DRONE_CONTROL, "data": { "seq": seq, "x": s.x, "y": s.y, "h": s.h, "w": s.w } })
    }

    pub fn heart_beat(seq: u64) -> Value {
        json!({ "method": HEART_BEAT, "data": { "timestamp": now_ms() }, "seq": seq })
    }

    pub fn emergency_stop() -> Value {
        json!({ "method": DRONE_EMERGENCY_STOP, "data": {} })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn topics_match_cloud_api_layout() {
        let t = Topics::new("SN1");
        assert_eq!(t.services(), "thing/product/SN1/services");
        assert_eq!(t.drc_down(), "thing/product/SN1/drc/down");
        assert_eq!(t.status_reply(), "sys/product/SN1/status_reply");
        assert_eq!(t.kind_of("thing/product/SN1/osd"), Some(TopicKind::Osd));
        assert_eq!(t.kind_of("thing/product/OTHER/osd"), None);
    }

    #[test]
    fn sticks_are_clamped_and_nan_safe() {
        let s = Sticks { x: 100.0, y: -100.0, h: f64::NAN, w: 1000.0 }.clamped(StickLimits::CAUTIOUS);
        assert_eq!(s, Sticks { x: 5.0, y: -5.0, h: 0.0, w: 45.0 });
        let huge = StickLimits { horizontal_mps: 99.0, vertical_mps: 99.0, yaw_dps: 999.0 };
        let s = Sticks { x: 50.0, y: 0.0, h: 50.0, w: -500.0 }.clamped(huge);
        assert_eq!(s, Sticks { x: 17.0, y: 0.0, h: 5.0, w: -90.0 });
    }

    #[test]
    fn reply_keeps_ids() {
        let req = Envelope::request("update_topo", json!({}));
        let rep = Envelope::reply_to(&req, json!({ "result": 0 }));
        assert_eq!((&rep.tid, &rep.bid), (&req.tid, &req.bid));
        assert_eq!(rep.result(), Some(0));
    }
}
