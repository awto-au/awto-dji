//! C ABI. All calls are non-blocking: anything that waits on the device returns a
//! request id, and its outcome arrives later from [`awto_dji_poll_event`] as a
//! `service_result` event. Strings are UTF-8 JSON; strings returned by this library
//! must be released with [`awto_dji_string_free`]. See `include/awto_dji.h`.
//!
//! Safety contract for every function: pointer arguments are null or valid
//! NUL-terminated strings / handles from `awto_dji_client_new` that have not been freed.

#![allow(clippy::missing_safety_doc)]

use crate::client::{ClientConfig, CloudClient, Error, Event};
use crate::drc::{DrcOptions, DrcSession};
use crate::protocol::Sticks;
use serde_json::Value;
use std::cell::RefCell;
use std::ffi::{CStr, CString, c_char};
use std::future::Future;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex, OnceLock};
use tokio::runtime::Runtime;
use tokio::sync::mpsc;

thread_local! {
    static LAST_ERROR: RefCell<Option<String>> = const { RefCell::new(None) };
}

fn set_error(msg: impl Into<String>) {
    LAST_ERROR.with(|e| *e.borrow_mut() = Some(msg.into()));
}

fn runtime() -> &'static Runtime {
    static RT: OnceLock<Runtime> = OnceLock::new();
    RT.get_or_init(|| {
        tokio::runtime::Builder::new_multi_thread()
            .worker_threads(2)
            .thread_name("awto-dji")
            .enable_all()
            .build()
            .expect("tokio runtime")
    })
}

pub struct Handle {
    client: Arc<CloudClient>,
    events_rx: Mutex<mpsc::UnboundedReceiver<Event>>,
    events_tx: mpsc::UnboundedSender<Event>,
    drc: Arc<tokio::sync::Mutex<Option<DrcSession>>>,
    next_request: AtomicU64,
}

impl Handle {
    /// Runs `fut` in the background and reports its outcome as a `service_result` event.
    fn spawn_request<F>(&self, method: String, fut: F) -> u64
    where
        F: Future<Output = Result<Option<Value>, Error>> + Send + 'static,
    {
        let request_id = self.next_request.fetch_add(1, Ordering::Relaxed);
        let tx = self.events_tx.clone();
        runtime().spawn(async move {
            let event = match fut.await {
                Ok(output) => Event::ServiceResult { request_id, method, ok: true, result: Some(0), output, error: None },
                Err(e) => {
                    let result = match &e {
                        Error::Rejected { result, .. } => Some(*result),
                        _ => None,
                    };
                    Event::ServiceResult { request_id, method, ok: false, result, output: None, error: Some(e.to_string()) }
                }
            };
            let _ = tx.send(event);
        });
        request_id
    }
}

unsafe fn str_arg<'a>(p: *const c_char, name: &str) -> Option<&'a str> {
    if p.is_null() {
        set_error(format!("{name} is null"));
        return None;
    }
    match unsafe { CStr::from_ptr(p) }.to_str() {
        Ok(s) => Some(s),
        Err(_) => {
            set_error(format!("{name} is not UTF-8"));
            None
        }
    }
}

unsafe fn json_arg(p: *const c_char, name: &str) -> Option<Value> {
    let s = unsafe { str_arg(p, name) }?;
    if s.trim().is_empty() {
        return Some(Value::Object(Default::default()));
    }
    serde_json::from_str(s).map_err(|e| set_error(format!("{name}: {e}"))).ok()
}

unsafe fn handle<'a>(h: *mut Handle) -> Option<&'a Handle> {
    if h.is_null() {
        set_error("handle is null");
    }
    unsafe { h.as_ref() }
}

fn into_c(s: String) -> *mut c_char {
    CString::new(s).map(CString::into_raw).unwrap_or(std::ptr::null_mut())
}

/// Connects to the broker. `config_json` is a `ClientConfig`. Returns null on error.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn awto_dji_client_new(config_json: *const c_char) -> *mut Handle {
    let Some(cfg) = (unsafe { json_arg(config_json, "config_json") }) else { return std::ptr::null_mut() };
    let cfg: ClientConfig = match serde_json::from_value(cfg) {
        Ok(c) => c,
        Err(e) => {
            set_error(format!("config_json: {e}"));
            return std::ptr::null_mut();
        }
    };
    let connected = {
        let _guard = runtime().enter();
        CloudClient::connect(cfg)
    };
    match connected {
        Ok((client, events_rx)) => {
            let (events_tx, mut internal_rx) = mpsc::unbounded_channel();
            // Merge internal results into the client's event stream so the host polls one queue.
            let (merged_tx, merged_rx) = mpsc::unbounded_channel();
            let mut events_rx = events_rx;
            runtime().spawn(async move {
                loop {
                    let ev = tokio::select! {
                        Some(ev) = events_rx.recv() => ev,
                        Some(ev) = internal_rx.recv() => ev,
                        else => return,
                    };
                    if merged_tx.send(ev).is_err() {
                        return;
                    }
                }
            });
            Box::into_raw(Box::new(Handle {
                client,
                events_rx: Mutex::new(merged_rx),
                events_tx,
                drc: Arc::default(),
                next_request: AtomicU64::new(1),
            }))
        }
        Err(e) => {
            set_error(e.to_string());
            std::ptr::null_mut()
        }
    }
}

/// Disconnects and frees the handle. Any DRC session is dropped (streaming stops).
#[unsafe(no_mangle)]
pub unsafe extern "C" fn awto_dji_client_free(h: *mut Handle) {
    if h.is_null() {
        return;
    }
    let h = unsafe { Box::from_raw(h) };
    let client = h.client.clone();
    runtime().block_on(async move {
        h.drc.lock().await.take();
        client.disconnect().await;
    });
}

/// Next event as JSON, or null when the queue is empty.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn awto_dji_poll_event(h: *mut Handle) -> *mut c_char {
    let Some(h) = (unsafe { handle(h) }) else { return std::ptr::null_mut() };
    match h.events_rx.lock().unwrap().try_recv() {
        Ok(ev) => serde_json::to_string(&ev).map(into_c).unwrap_or(std::ptr::null_mut()),
        Err(_) => std::ptr::null_mut(),
    }
}

/// Calls a `services` method. Returns a request id, or 0 on a bad argument.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn awto_dji_call_service(h: *mut Handle, method: *const c_char, data_json: *const c_char) -> u64 {
    let Some(h) = (unsafe { handle(h) }) else { return 0 };
    let Some(method) = (unsafe { str_arg(method, "method") }) else { return 0 };
    let Some(data) = (unsafe { json_arg(data_json, "data_json") }) else { return 0 };
    let client = h.client.clone();
    let m = method.to_owned();
    h.spawn_request(method.to_owned(), async move {
        let reply = client.call_service(&m, data).await?;
        Ok(reply.data.get("output").cloned())
    })
}

/// Publishes raw JSON on any topic, e.g. a `requests_reply`. Returns 0 on success.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn awto_dji_publish(h: *mut Handle, topic: *const c_char, payload_json: *const c_char) -> i32 {
    let Some(h) = (unsafe { handle(h) }) else { return -1 };
    let Some(topic) = (unsafe { str_arg(topic, "topic") }) else { return -1 };
    let Some(payload) = (unsafe { json_arg(payload_json, "payload_json") }) else { return -1 };
    let client = h.client.clone();
    let topic = topic.to_owned();
    runtime().spawn(async move {
        let _ = client.publish(topic, &payload).await;
    });
    0
}

/// Takes flight authority and enters DRC. `options_json` is a `DrcOptions`. Returns a request id or 0.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn awto_dji_drc_enter(h: *mut Handle, options_json: *const c_char) -> u64 {
    let Some(h) = (unsafe { handle(h) }) else { return 0 };
    let Some(opts) = (unsafe { json_arg(options_json, "options_json") }) else { return 0 };
    let opts: DrcOptions = match serde_json::from_value(opts) {
        Ok(o) => o,
        Err(e) => {
            set_error(format!("options_json: {e}"));
            return 0;
        }
    };
    let client = h.client.clone();
    let slot = h.drc.clone();
    h.spawn_request("drc_mode_enter".into(), async move {
        let mut slot = slot.lock().await;
        if let Some(old) = slot.take() {
            let _ = old.exit().await;
        }
        *slot = Some(DrcSession::enter(client, opts).await?);
        Ok(None)
    })
}

/// Updates the streamed sticks. Returns 0, or -1 when DRC is not active.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn awto_dji_drc_set_sticks(h: *mut Handle, x: f64, y: f64, height: f64, w: f64) -> i32 {
    let Some(h) = (unsafe { handle(h) }) else { return -1 };
    match h.drc.try_lock() {
        Ok(guard) => match guard.as_ref() {
            Some(s) => {
                s.set_sticks(Sticks { x, y, h: height, w });
                0
            }
            None => {
                set_error("DRC is not active");
                -1
            }
        },
        // Enter or exit is in progress; the next call will land.
        Err(_) => -1,
    }
}

/// Sends `drone_emergency_stop`. Returns a request id or 0.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn awto_dji_drc_emergency_stop(h: *mut Handle) -> u64 {
    let Some(h) = (unsafe { handle(h) }) else { return 0 };
    let slot = h.drc.clone();
    h.spawn_request("drone_emergency_stop".into(), async move {
        match slot.lock().await.as_ref() {
            Some(s) => s.emergency_stop().await.map(|_| None),
            None => Err(Error::Invalid("DRC is not active".into())),
        }
    })
}

/// Leaves DRC mode. Returns a request id or 0.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn awto_dji_drc_exit(h: *mut Handle) -> u64 {
    let Some(h) = (unsafe { handle(h) }) else { return 0 };
    let slot = h.drc.clone();
    h.spawn_request("drc_mode_exit".into(), async move {
        match slot.lock().await.take() {
            Some(s) => s.exit().await.map(|_| None),
            None => Ok(None),
        }
    })
}

/// Last error on this thread, or null. Free with `awto_dji_string_free`.
#[unsafe(no_mangle)]
pub extern "C" fn awto_dji_last_error() -> *mut c_char {
    LAST_ERROR.with(|e| e.borrow_mut().take()).map(into_c).unwrap_or(std::ptr::null_mut())
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn awto_dji_string_free(s: *mut c_char) {
    if !s.is_null() {
        drop(unsafe { CString::from_raw(s) });
    }
}
