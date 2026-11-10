//! Cloud-side MQTT client for one DJI gateway (Dock or Pilot 2 RC).

use crate::protocol::{Envelope, TopicKind, Topics};
use rumqttc::{AsyncClient, Event as MqttEvent, MqttOptions, Packet, QoS, Transport};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use std::time::Duration;
use tokio::sync::{mpsc, oneshot};
use tokio::task::JoinHandle;

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("mqtt: {0}")]
    Mqtt(#[from] rumqttc::ClientError),
    #[error("json: {0}")]
    Json(#[from] serde_json::Error),
    #[error("no reply to `{0}` within the timeout")]
    Timeout(String),
    #[error("`{method}` rejected by device with result {result}")]
    Rejected { method: String, result: i64 },
    #[error("client is shut down")]
    Closed,
    #[error("{0}")]
    Invalid(String),
}

pub type Result<T> = std::result::Result<T, Error>;

fn default_port() -> u16 { 1883 }
fn default_timeout_ms() -> u64 { 10_000 }
fn default_true() -> bool { true }

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ClientConfig {
    pub host: String,
    #[serde(default = "default_port")]
    pub port: u16,
    #[serde(default)]
    pub client_id: Option<String>,
    #[serde(default)]
    pub username: Option<String>,
    #[serde(default)]
    pub password: Option<String>,
    #[serde(default)]
    pub tls: bool,
    /// Serial number of the gateway: the Dock SN, or the RC SN for Pilot 2.
    pub gateway_sn: String,
    #[serde(default = "default_timeout_ms")]
    pub service_timeout_ms: u64,
    /// Answer `update_topo` status messages and `need_reply` events with result 0.
    /// Devices stall without these replies, so only turn it off if your own code answers them.
    #[serde(default = "default_true")]
    pub auto_reply: bool,
}

/// Something that happened on the connection.
#[derive(Debug, Clone, Serialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum Event {
    Connected,
    Disconnected { reason: String },
    /// A message from the device on one of the uplink topics.
    Message {
        kind: TopicKind,
        method: Option<String>,
        tid: String,
        bid: String,
        data: Value,
    },
    /// Outcome of a request started through the FFI layer.
    ServiceResult {
        request_id: u64,
        method: String,
        ok: bool,
        #[serde(skip_serializing_if = "Option::is_none")]
        result: Option<i64>,
        #[serde(skip_serializing_if = "Option::is_none")]
        output: Option<Value>,
        #[serde(skip_serializing_if = "Option::is_none")]
        error: Option<String>,
    },
}

type Pending = Arc<Mutex<HashMap<String, oneshot::Sender<Envelope>>>>;

pub struct CloudClient {
    mqtt: AsyncClient,
    topics: Topics,
    pending: Pending,
    timeout: Duration,
    task: JoinHandle<()>,
}

impl CloudClient {
    /// Starts the connection. Must be called inside a Tokio runtime.
    ///
    /// Returns immediately; [`Event::Connected`] arrives once the broker accepts us.
    /// Requests issued before that are queued.
    pub fn connect(cfg: ClientConfig) -> Result<(Arc<CloudClient>, mpsc::UnboundedReceiver<Event>)> {
        if cfg.gateway_sn.is_empty() {
            return Err(Error::Invalid("gateway_sn is required".into()));
        }
        let client_id = cfg
            .client_id
            .clone()
            .unwrap_or_else(|| format!("awto-dji-{}", &uuid::Uuid::new_v4().simple().to_string()[..8]));
        let mut opts = MqttOptions::new(client_id, cfg.host.clone(), cfg.port);
        opts.set_keep_alive(Duration::from_secs(30));
        opts.set_max_packet_size(1 << 20, 1 << 20);
        if let Some(user) = &cfg.username {
            opts.set_credentials(user.clone(), cfg.password.clone().unwrap_or_default());
        }
        if cfg.tls {
            opts.set_transport(Transport::tls_with_default_config());
        }

        let (mqtt, mut eventloop) = AsyncClient::new(opts, 256);
        let topics = Topics::new(cfg.gateway_sn.clone());
        let pending: Pending = Arc::default();
        let (tx, rx) = mpsc::unbounded_channel();

        let task = {
            let mqtt = mqtt.clone();
            let topics = topics.clone();
            let pending = pending.clone();
            let auto_reply = cfg.auto_reply;
            tokio::spawn(async move {
                loop {
                    match eventloop.poll().await {
                        Ok(MqttEvent::Incoming(Packet::ConnAck(_))) => {
                            for t in topics.uplink() {
                                // try_* because awaiting the request queue from inside the
                                // event loop task would deadlock once the queue is full.
                                let _ = mqtt.try_subscribe(t, QoS::AtLeastOnce);
                            }
                            let _ = tx.send(Event::Connected);
                        }
                        Ok(MqttEvent::Incoming(Packet::Publish(p))) => {
                            let Some(kind) = topics.kind_of(&p.topic) else { continue };
                            let Ok(env) = serde_json::from_slice::<Envelope>(&p.payload) else { continue };
                            if kind == TopicKind::ServicesReply
                                && let Some(waiter) = pending.lock().unwrap().remove(&env.tid)
                            {
                                let _ = waiter.send(env.clone());
                            }
                            if auto_reply {
                                auto_answer(&mqtt, &topics, kind, &env);
                            }
                            let _ = tx.send(Event::Message {
                                kind,
                                method: env.method,
                                tid: env.tid,
                                bid: env.bid,
                                data: env.data,
                            });
                        }
                        Ok(_) => {}
                        Err(e) => {
                            let _ = tx.send(Event::Disconnected { reason: e.to_string() });
                            if tx.is_closed() {
                                return;
                            }
                            tokio::time::sleep(Duration::from_secs(1)).await;
                        }
                    }
                }
            })
        };

        let client = CloudClient {
            mqtt,
            topics,
            pending,
            timeout: Duration::from_millis(cfg.service_timeout_ms),
            task,
        };
        Ok((Arc::new(client), rx))
    }

    pub fn topics(&self) -> &Topics {
        &self.topics
    }

    /// Publishes `payload` as JSON on `topic`.
    pub async fn publish(&self, topic: String, payload: &Value) -> Result<()> {
        let bytes = serde_json::to_vec(payload)?;
        self.mqtt.publish(topic, QoS::AtLeastOnce, false, bytes).await?;
        Ok(())
    }

    /// Publishes with QoS 0. Used for high-rate DRC frames where a late frame is worse than a lost one.
    pub async fn publish_fast(&self, topic: String, payload: &Value) -> Result<()> {
        let bytes = serde_json::to_vec(payload)?;
        self.mqtt.publish(topic, QoS::AtMostOnce, false, bytes).await?;
        Ok(())
    }

    /// Calls a `services` method and waits for its `services_reply`. A non-zero `result` is an error.
    pub async fn call_service(&self, method: &str, data: Value) -> Result<Envelope> {
        let req = Envelope::request(method, data);
        let (tx, rx) = oneshot::channel();
        self.pending.lock().unwrap().insert(req.tid.clone(), tx);
        if let Err(e) = self.publish(self.topics.services(), &serde_json::to_value(&req)?).await {
            self.pending.lock().unwrap().remove(&req.tid);
            return Err(e);
        }
        let reply = match tokio::time::timeout(self.timeout, rx).await {
            Ok(Ok(reply)) => reply,
            Ok(Err(_)) => return Err(Error::Closed),
            Err(_) => {
                self.pending.lock().unwrap().remove(&req.tid);
                return Err(Error::Timeout(method.to_owned()));
            }
        };
        match reply.result() {
            Some(0) | None => Ok(reply),
            Some(result) => Err(Error::Rejected { method: method.to_owned(), result }),
        }
    }

    pub async fn disconnect(&self) {
        let _ = self.mqtt.disconnect().await;
        self.task.abort();
    }
}

impl Drop for CloudClient {
    fn drop(&mut self) {
        self.task.abort();
    }
}

fn auto_answer(mqtt: &AsyncClient, topics: &Topics, kind: TopicKind, env: &Envelope) {
    let topic = match kind {
        TopicKind::Status if env.method.as_deref() == Some("update_topo") => topics.status_reply(),
        TopicKind::Events if env.need_reply == Some(1) => topics.events_reply(),
        _ => return,
    };
    let reply = Envelope::reply_to(env, json!({ "result": 0 }));
    if let Ok(bytes) = serde_json::to_vec(&reply) {
        let _ = mqtt.try_publish(topic, QoS::AtLeastOnce, false, bytes);
    }
}
