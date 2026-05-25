use crate::state::SharedState;

const CAN_ID_0: u32 = 0x320;
const CAN_ID_1: u32 = 0x321;

// ── Pure decode logic (no hardware dep, fully testable) ──────────────────────

#[derive(Debug, PartialEq)]
pub struct Frame0x320 {
    pub rpm:      f32,
    pub map_kpa:  f32,
    pub tps_pct:  f32,
    pub iat_c:    f32,
    pub clt_c:    f32,
    pub afr:      f32,
    pub batt_v:   f32,
}

#[derive(Debug, PartialEq)]
pub struct Frame0x321 {
    pub ign_advance: f32,
}

pub fn decode_0x320(data: &[u8]) -> Option<Frame0x320> {
    if data.len() < 8 { return None; }
    let rpm     = u16::from_le_bytes([data[0], data[1]]) as f32;
    let map_kpa = data[2] as f32;
    let tps_pct = data[3] as f32;
    let iat_c   = data[4] as f32 - 40.0;
    let clt_c   = data[5] as f32 - 40.0;
    let afr     = data[6] as f32 * 0.0068 * 14.7;
    let batt_v  = data[7] as f32 * 0.1;
    Some(Frame0x320 { rpm, map_kpa, tps_pct, iat_c, clt_c, afr, batt_v })
}

pub fn decode_0x321(data: &[u8]) -> Option<Frame0x321> {
    if data.len() < 4 { return None; }
    let ign_advance = data[3] as f32 - 40.0;
    Some(Frame0x321 { ign_advance })
}

// ── Background thread ────────────────────────────────────────────────────────

pub fn spawn_can_thread(state: SharedState) {
    std::thread::Builder::new()
        .name("can".into())
        .spawn(move || {
            use std::time::Duration;
            loop {
                match run_can_loop(&state) {
                    Ok(()) => break,
                    Err(e) => {
                        log::warn!("CAN unavailable ({e}) — retrying in 5s");
                        std::thread::sleep(Duration::from_secs(5));
                    }
                }
            }
        })
        .expect("CAN thread spawn failed");
}

#[cfg(target_os = "linux")]
fn run_can_loop(state: &SharedState) -> Result<(), Box<dyn std::error::Error>> {
    use socketcan::{CanSocket, Socket, CanAnyFrame, EmbeddedFrame};

    let sock = CanSocket::open("can0")?;
    log::info!("CAN listener started on can0");

    loop {
        match sock.read_frame()? {
            CanAnyFrame::Normal(frame) => {
                let id   = frame.raw_id();
                let data = frame.data();

                if id == CAN_ID_0 {
                    if let Some(f) = decode_0x320(data) {
                        let mut s = state.lock();
                        s.rpm      = f.rpm;
                        s.map_kpa  = f.map_kpa;
                        s.tps_pct  = f.tps_pct;
                        s.iat_c    = f.iat_c;
                        s.clt_c    = f.clt_c;
                        s.afr      = f.afr;
                        s.batt_v   = f.batt_v;
                    }
                } else if id == CAN_ID_1 {
                    if let Some(f) = decode_0x321(data) {
                        state.lock().ign_advance = f.ign_advance;
                    }
                }
            }
            _ => {}
        }
    }
}

#[cfg(not(target_os = "linux"))]
fn run_can_loop(_state: &SharedState) -> Result<(), Box<dyn std::error::Error>> {
    Err("CAN is only supported on Linux".into())
}

// ── Tests ────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn decode_0x320_parses_known_bytes() {
        // rpm=3000 (LE: 0xB8, 0x0B), map=95, tps=20,
        // iat: 80-40=40C, clt: 125-40=85C,
        // afr: 200*0.0068*14.7≈19.999, batt: 124*0.1=12.4V
        let data = [0xB8u8, 0x0B, 95, 20, 80, 125, 200, 124, 0, 0, 0, 0];
        let f = decode_0x320(&data).unwrap();
        assert_eq!(f.rpm, 3000.0);
        assert_eq!(f.map_kpa, 95.0);
        assert_eq!(f.tps_pct, 20.0);
        assert_eq!(f.iat_c, 40.0);
        assert_eq!(f.clt_c, 85.0);
        assert!((f.afr - 19.9992).abs() < 0.01);
        assert!((f.batt_v - 12.4).abs() < 0.01);
    }

    #[test]
    fn decode_0x320_returns_none_on_short_data() {
        assert!(decode_0x320(&[0, 1, 2]).is_none());
    }

    #[test]
    fn decode_0x321_parses_ign_advance() {
        // data[3] = 58 → 58-40 = 18 degrees
        let data = [0u8, 0, 0, 58];
        let f = decode_0x321(&data).unwrap();
        assert_eq!(f.ign_advance, 18.0);
    }

    #[test]
    fn decode_0x321_returns_none_on_short_data() {
        assert!(decode_0x321(&[0, 1]).is_none());
    }
}
