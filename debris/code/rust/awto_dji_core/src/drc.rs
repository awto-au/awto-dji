//! Drone Remote Control (DRC): live stick control over MQTT.
//!
//! The session streams `drone_control` frames at a fixed rate. If the caller stops
//! updating the sticks for longer than `deadman_ms` (UI froze, network to the
//! operator dropped), the session sends zero sticks so the aircraft brakes and hovers.

use crate::client::{CloudClient, Result};
use crate::protocol::{DrcBroker, StickLimits, Sticks, drc, services};
use serde::{Deserialize, Serialize};
use serde_json::json;
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::watch;
use tokio::task::JoinHandle;

fn default_rate_hz() -> f64 { 10.0 }
fn default_deadman_ms() -> u64 { 500 }
fn default_osd_hz() -> u32 { 10 }
fn default_hsi_hz() -> u32 { 1 }

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DrcOptions {
    pub broker: DrcBroker,
    /// DJI documents 5-10 Hz for `drone_control`.
    #[serde(default = "default_rate_hz")]
    pub rate_hz: f64,
    #[serde(default = "default_deadman_ms")]
    pub deadman_ms: u64,
    #[serde(default)]
    pub limits: StickLimits,
    #[serde(default = "default_osd_hz")]
    pub osd_frequency: u32,
    #[serde(default = "default_hsi_hz")]
    pub hsi_frequency: u32,
}

pub struct DrcSession {
    client: Arc<CloudClient>,
    sticks: watch::Sender<(Sticks, Instant)>,
    task: JoinHandle<()>,
}

impl DrcSession {
    /// Takes flight authority, enters DRC mode and starts streaming zero sticks.
    pub async fn enter(client: Arc<CloudClient>, opts: DrcOptions) -> Result<DrcSession> {
        client.call_service(services::FLIGHT_AUTHORITY_GRAB, json!({})).await?;
        client
            .call_service(
                services::DRC_MODE_ENTER,
                services::drc_mode_enter(&opts.broker, opts.osd_frequency, opts.hsi_frequency),
            )
            .await?;

        let (sticks, rx) = watch::channel((Sticks::ZERO, Instant::now()));
        let task = tokio::spawn(stream_sticks(client.clone(), rx, opts));
        Ok(DrcSession { client, sticks, task })
    }

    /// Sets the stick values to stream. Call this at least every `deadman_ms`.
    pub fn set_sticks(&self, s: Sticks) {
        self.sticks.send_replace((s, Instant::now()));
    }

    /// Commands an immediate stop. The aircraft brakes and hovers.
    pub async fn emergency_stop(&self) -> Result<()> {
        self.set_sticks(Sticks::ZERO);
        let topic = self.client.topics().drc_down();
        self.client.publish(topic, &drc::emergency_stop()).await
    }

    /// Stops streaming and leaves DRC mode. The aircraft hovers once frames stop.
    pub async fn exit(self) -> Result<()> {
        self.task.abort();
        self.client.call_service(services::DRC_MODE_EXIT, json!({})).await?;
        Ok(())
    }
}

impl Drop for DrcSession {
    fn drop(&mut self) {
        self.task.abort();
    }
}

async fn stream_sticks(client: Arc<CloudClient>, rx: watch::Receiver<(Sticks, Instant)>, opts: DrcOptions) {
    let period = Duration::from_secs_f64(1.0 / opts.rate_hz.clamp(1.0, 20.0));
    let deadman = Duration::from_millis(opts.deadman_ms);
    let topic = client.topics().drc_down();
    let mut tick = tokio::time::interval(period);
    tick.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
    let mut last_heartbeat = Instant::now();
    let mut seq: u64 = 0;
    loop {
        tick.tick().await;
        let frame = sticks_for_frame(*rx.borrow(), Instant::now(), deadman, opts.limits);
        let _ = client.publish_fast(topic.clone(), &drc::drone_control(seq, frame)).await;
        if last_heartbeat.elapsed() >= Duration::from_secs(1) {
            let _ = client.publish_fast(topic.clone(), &drc::heart_beat(seq)).await;
            last_heartbeat = Instant::now();
        }
        seq = seq.wrapping_add(1);
    }
}

/// The stick values to send now: zero if the last update is older than `deadman`.
fn sticks_for_frame(latest: (Sticks, Instant), now: Instant, deadman: Duration, limits: StickLimits) -> Sticks {
    let (sticks, updated) = latest;
    if now.saturating_duration_since(updated) > deadman {
        Sticks::ZERO
    } else {
        sticks.clamped(limits)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn deadman_zeroes_stale_sticks() {
        let t0 = Instant::now();
        let s = Sticks { x: 3.0, y: 0.0, h: 0.0, w: 0.0 };
        let deadman = Duration::from_millis(500);
        let lim = StickLimits::CAUTIOUS;
        assert_eq!(sticks_for_frame((s, t0), t0 + Duration::from_millis(100), deadman, lim), s);
        assert_eq!(sticks_for_frame((s, t0), t0 + Duration::from_millis(600), deadman, lim), Sticks::ZERO);
    }

    #[test]
    fn options_have_safe_defaults() {
        let o: DrcOptions = serde_json::from_value(json!({
            "broker": { "address": "10.0.0.2:1883", "client_id": "drc", "username": "u",
                        "password": "p", "expire_time": 1, "enable_tls": false }
        }))
        .unwrap();
        assert_eq!(o.rate_hz, 10.0);
        assert_eq!(o.deadman_ms, 500);
        assert_eq!(o.limits, StickLimits::CAUTIOUS);
    }
}
