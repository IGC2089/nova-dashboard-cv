use std::io::{BufRead, BufReader, Write};
use std::net::TcpStream;
use std::time::{Duration, Instant};
use serde_json::Value;
use crate::state::SharedState;

const ODO_PATH: &str = "/data/odo.json";
const HACC_MAX_M: f32 = 10.0;
const SAVE_INTERVAL_KM: f64 = 1.6;
const GPS_TIMEOUT_S: f32 = 5.0;

// ── ODO accumulator (pure logic, testable) ───────────────────────────────────

pub struct OdometerAccumulator {
    pub odo_km:  f64,
    pub trip_km: f64,
    last_save:   f64,
}

impl OdometerAccumulator {
    pub fn new(initial_odo_km: f64) -> Self {
        Self { odo_km: initial_odo_km, trip_km: 0.0, last_save: initial_odo_km }
    }

    /// Returns true if fix was valid (hacc within threshold).
    pub fn update(&mut self, speed_kph: f32, dt_s: f32, hacc_m: f32) -> bool {
        if hacc_m >= HACC_MAX_M { return false; }
        let delta_km = speed_kph as f64 * (dt_s as f64 / 3600.0);
        self.odo_km  += delta_km;
        self.trip_km += delta_km;
        true
    }

    /// True if ODO has advanced enough to warrant a save.
    pub fn needs_save(&self) -> bool {
        (self.odo_km - self.last_save) >= SAVE_INTERVAL_KM
    }

    pub fn mark_saved(&mut self) {
        self.last_save = self.odo_km;
    }
}

// ── ODO persistence ──────────────────────────────────────────────────────────

pub fn load_odo() -> f64 {
    let text = std::fs::read_to_string(ODO_PATH).unwrap_or_default();
    serde_json::from_str::<Value>(&text)
        .ok()
        .and_then(|v| v["odo_km"].as_f64())
        .unwrap_or(0.0)
}

pub fn save_odo(odo_km: f64, trip_km: f64) {
    let tmp = format!("{ODO_PATH}.tmp");
    let json = format!("{{\"odo_km\":{odo_km:.3},\"trip_km\":{trip_km:.3}}}");
    if std::fs::write(&tmp, &json).is_ok() {
        if let Err(e) = std::fs::rename(&tmp, ODO_PATH) {
            log::warn!("Failed to rename {tmp} to {ODO_PATH}: {e}");
        }
    }
}

// ── Background thread ────────────────────────────────────────────────────────

pub fn spawn_gps_thread(state: SharedState) {
    std::thread::Builder::new()
        .name("gps".into())
        .spawn(move || {
            loop {
                match run_gps_loop(&state) {
                    Ok(()) => break,
                    Err(e) => {
                        log::warn!("GPS unavailable ({e}) — retrying in 5s");
                        std::thread::sleep(Duration::from_secs(5));
                    }
                }
            }
        })
        .expect("GPS thread spawn");
}

fn run_gps_loop(state: &SharedState) -> Result<(), Box<dyn std::error::Error>> {
    let stream = TcpStream::connect("127.0.0.1:2947")?;
    stream.set_read_timeout(Some(Duration::from_secs(10)))?;
    {
        let w: &TcpStream = &stream;
        w.write_all(b"?WATCH={\"enable\":true,\"json\":true}\r\n")?;
    }
    log::info!("GPS connected to gpsd");

    let initial_odo = load_odo();
    let mut acc = OdometerAccumulator::new(initial_odo);
    let mut last_time = Instant::now();
    let mut last_fix  = Instant::now();

    let reader = BufReader::new(&stream);
    for line in reader.lines() {
        let line = line?;
        let v: Value = match serde_json::from_str(&line) {
            Ok(v) => v,
            Err(_) => continue,
        };
        if v["class"] != "TPV" { continue; }

        let now    = Instant::now();
        let dt_s   = now.duration_since(last_time).as_secs_f32();
        let dt_s   = dt_s.min(2.0);

        let speed_ms = v["speed"].as_f64().unwrap_or(0.0) as f32;
        let hacc_m   = v["eph"].as_f64().unwrap_or(999.0) as f32;
        let mode     = v["mode"].as_i64().unwrap_or(0);
        let speed_kph = speed_ms * 3.6;

        let fix_valid = mode >= 2 && acc.update(speed_kph, dt_s, hacc_m);
        if fix_valid {
            last_time = now;
            last_fix = now;
        }

        let gps_ok = now.duration_since(last_fix).as_secs_f32() < GPS_TIMEOUT_S;

        {
            let mut s = state.lock();
            if fix_valid {
                s.speed_kph = speed_kph;
            } else {
                s.speed_kph = 0.0;
            }
            s.odo_km  = acc.odo_km;
            s.trip_km = acc.trip_km;
            s.gps_fix = gps_ok;
        }

        if acc.needs_save() {
            save_odo(acc.odo_km, acc.trip_km);
            acc.mark_saved();
        }
    }
    // gpsd closed the connection, retry
    Err("gpsd connection closed".into())
}

// ── Tests ────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn odo_accumulates_distance() {
        let mut acc = OdometerAccumulator::new(0.0);
        // 100 km/h for 1 hour = 100 km (dt_s = 3600s, hacc = 5m)
        acc.update(100.0, 3600.0, 5.0);
        assert!((acc.odo_km - 100.0).abs() < 0.001);
        assert!((acc.trip_km - 100.0).abs() < 0.001);
    }

    #[test]
    fn odo_ignores_bad_hacc() {
        let mut acc = OdometerAccumulator::new(0.0);
        let valid = acc.update(100.0, 3600.0, 15.0); // hacc > 10m
        assert!(!valid);
        assert_eq!(acc.odo_km, 0.0);
    }

    #[test]
    fn odo_loads_initial_value() {
        let acc = OdometerAccumulator::new(12345.0);
        assert_eq!(acc.odo_km, 12345.0);
        assert_eq!(acc.trip_km, 0.0);
    }

    #[test]
    fn needs_save_triggers_at_interval() {
        let mut acc = OdometerAccumulator::new(0.0);
        acc.update(100.0, 3600.0, 1.0); // +100 km >> 1.6 km threshold
        assert!(acc.needs_save());
        acc.mark_saved();
        assert!(!acc.needs_save());
    }
}
