//! Minimal CLI: take off, fly a short forward leg, return home.
//!
//! Run the Python sim bridge first, or point at the real Android bridge:
//!     python -m awto_dji_ground.sim_bridge --listen udpin:0.0.0.0:14550
//!     cargo run --bin fly -- udpout:127.0.0.1:14550

use awto_dji_ground::Vehicle;
use std::time::Duration;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let address = std::env::args().nth(1).unwrap_or_else(|| "udpout:127.0.0.1:14550".into());
    let mut v = Vehicle::connect(&address)?;

    println!("waiting for bridge at {address} ...");
    v.wait_ready(Duration::from_secs(15))?;
    println!("connected; mode {:?}", v.telemetry.mode());

    println!("taking off");
    v.takeoff(1.2)?;

    println!("forward 2 m/s for 2 s");
    v.fly_velocity(2.0, 0.0, 0.0, 0.0, Duration::from_secs(2), 10.0)?;

    println!("yaw 45 deg/s for 2 s");
    v.fly_velocity(0.0, 0.0, 0.0, 45.0, Duration::from_secs(2), 10.0)?;

    println!("returning home");
    v.return_to_home()?;
    println!("alt now {:.1} m, sats {}", v.telemetry.relative_alt_m, v.telemetry.satellites);
    Ok(())
}
