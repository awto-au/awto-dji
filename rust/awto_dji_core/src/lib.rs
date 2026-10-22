//! Cloud-side control of DJI Enterprise aircraft through the DJI Cloud API.
//!
//! * [`protocol`]: topics, envelopes and command payloads
//! * [`client`]: MQTT client for one gateway (Dock or Pilot 2 RC)
//! * [`drc`]: live stick control with a dead-man timer
//! * [`ffi`]: C ABI used by the Flutter app (Linux and Android) and other hosts

pub mod client;
pub mod drc;
pub mod ffi;
pub mod protocol;

pub use client::{ClientConfig, CloudClient, Error, Event, Result};
pub use drc::{DrcOptions, DrcSession};
pub use protocol::{DrcBroker, StickLimits, Sticks, TakeoffToPoint, Topics, Waypoint};
