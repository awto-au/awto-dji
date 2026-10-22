//! End-to-end tests against a local `mosquitto` broker and a simulated gateway.
//! Skipped when `mosquitto` is not installed.

use awto_dji_core::protocol::{Envelope, Topics};
use awto_dji_core::{ClientConfig, CloudClient, DrcBroker, DrcOptions, DrcSession, Event, Sticks};
use rumqttc::{AsyncClient, Event as MqttEvent, MqttOptions, Packet, QoS};
use serde_json::{Value, json};
use std::net::TcpListener;
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::time::Duration;

struct Broker {
    child: Child,
    port: u16,
}

impl Drop for Broker {
    fn drop(&mut self) {
        let _ = self.child.kill();
    }
}

fn start_broker() -> Option<Broker> {
    let port = TcpListener::bind("127.0.0.1:0").ok()?.local_addr().ok()?.port();
    let child = Command::new("mosquitto")
        .args(["-p", &port.to_string()])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .ok()?;
    std::thread::sleep(Duration::from_millis(300));
    Some(Broker { child, port })
}

/// Simulated gateway: answers every service with `result`, records DRC frames.
async fn fake_gateway(port: u16, sn: &str, result: i64) -> Arc<Mutex<Vec<Value>>> {
    let topics = Topics::new(sn);
    let mut opts = MqttOptions::new(format!("gw-{sn}"), "127.0.0.1", port);
    opts.set_keep_alive(Duration::from_secs(5));
    let (client, mut el) = AsyncClient::new(opts, 64);
    client.subscribe(topics.services(), QoS::AtLeastOnce).await.unwrap();
    client.subscribe(topics.drc_down(), QoS::AtLeastOnce).await.unwrap();
    client.subscribe(topics.status_reply(), QoS::AtLeastOnce).await.unwrap();
    let frames = Arc::new(Mutex::new(Vec::new()));
    let seen = frames.clone();
    tokio::spawn(async move {
        loop {
            let Ok(MqttEvent::Incoming(Packet::Publish(p))) = el.poll().await else { continue };
            let v: Value = serde_json::from_slice(&p.payload).unwrap();
            if p.topic == topics.services() {
                let env: Envelope = serde_json::from_value(v).unwrap();
                let reply = Envelope::reply_to(&env, json!({ "result": result, "output": { "ok": true } }));
                let _ = client.try_publish(topics.services_reply(), QoS::AtLeastOnce, false, serde_json::to_vec(&reply).unwrap());
            } else {
                seen.lock().unwrap().push(json!({ "topic": p.topic, "msg": v }));
            }
        }
    });
    tokio::time::sleep(Duration::from_millis(200)).await;
    frames
}

fn config(port: u16, sn: &str) -> ClientConfig {
    serde_json::from_value(json!({ "host": "127.0.0.1", "port": port, "gateway_sn": sn, "service_timeout_ms": 2000 })).unwrap()
}

async fn wait_connected(rx: &mut tokio::sync::mpsc::UnboundedReceiver<Event>) {
    loop {
        if let Some(Event::Connected) = rx.recv().await {
            tokio::time::sleep(Duration::from_millis(100)).await;
            return;
        }
    }
}

fn drone_control_frames(frames: &Mutex<Vec<Value>>) -> Vec<Value> {
    frames
        .lock()
        .unwrap()
        .iter()
        .filter(|f| f["msg"]["method"] == "drone_control")
        .map(|f| f["msg"]["data"].clone())
        .collect()
}

#[tokio::test]
async fn services_and_drc_round_trip() {
    let Some(broker) = start_broker() else {
        eprintln!("mosquitto not installed; skipping");
        return;
    };
    let frames = fake_gateway(broker.port, "DOCK1", 0).await;
    let (client, mut rx) = CloudClient::connect(config(broker.port, "DOCK1")).unwrap();
    wait_connected(&mut rx).await;

    let reply = client.call_service("return_home", json!({})).await.unwrap();
    assert_eq!(reply.data["output"]["ok"], true);

    let opts: DrcOptions = serde_json::from_value(json!({
        "broker": DrcBroker { address: format!("127.0.0.1:{}", broker.port), client_id: "drc".into(),
                              username: "".into(), password: "".into(), expire_time: 0, enable_tls: false },
        "rate_hz": 20.0,
        "deadman_ms": 300
    }))
    .unwrap();
    let drc = DrcSession::enter(client.clone(), opts).await.unwrap();
    for _ in 0..6 {
        drc.set_sticks(Sticks { x: 100.0, y: 0.0, h: 1.0, w: 0.0 });
        tokio::time::sleep(Duration::from_millis(50)).await;
    }
    let sent = drone_control_frames(&frames);
    assert!(sent.iter().any(|d| d["x"] == 5.0), "clamped forward frame expected: {sent:?}");

    // Stop updating: the dead-man timer must zero the sticks.
    frames.lock().unwrap().clear();
    tokio::time::sleep(Duration::from_millis(700)).await;
    let late = drone_control_frames(&frames);
    let last = late.last().expect("frames keep streaming");
    assert_eq!((last["x"].as_f64(), last["h"].as_f64()), (Some(0.0), Some(0.0)));

    drc.exit().await.unwrap();
}

#[tokio::test]
async fn rejected_service_is_an_error_and_topo_is_answered() {
    let Some(broker) = start_broker() else { return };
    let frames = fake_gateway(broker.port, "RC1", 314000).await;
    let (client, mut rx) = CloudClient::connect(config(broker.port, "RC1")).unwrap();
    wait_connected(&mut rx).await;

    let err = client.call_service("takeoff_to_point", json!({})).await.unwrap_err();
    assert!(matches!(err, awto_dji_core::Error::Rejected { result: 314000, .. }), "{err}");

    // Device announces its topology; the client must answer on status_reply.
    let mut opts = MqttOptions::new("gw-status", "127.0.0.1", broker.port);
    opts.set_keep_alive(Duration::from_secs(5));
    let (dev, mut el) = AsyncClient::new(opts, 8);
    tokio::spawn(async move { while el.poll().await.is_ok() {} });
    let topo = Envelope::request("update_topo", json!({ "sub_devices": [] }));
    dev.publish(Topics::new("RC1").status(), QoS::AtLeastOnce, false, serde_json::to_vec(&topo).unwrap()).await.unwrap();
    tokio::time::sleep(Duration::from_millis(400)).await;
    let replied = frames.lock().unwrap().iter().any(|f| f["topic"] == "sys/product/RC1/status_reply" && f["msg"]["tid"] == topo.tid);
    assert!(replied, "update_topo must be answered");
}
