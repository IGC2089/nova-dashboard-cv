use parking_lot::Mutex;
use std::sync::Arc;

/// All live vehicle data. Must be `Clone` so main thread can snapshot without holding the lock.
#[derive(Clone, Debug, PartialEq)]
pub struct VehicleState {
    // ECU (from CAN)
    pub rpm:         f32,
    pub map_kpa:     f32,
    pub clt_c:       f32,
    pub afr:         f32,
    pub tps_pct:     f32,
    pub iat_c:       f32,
    pub batt_v:      f32,
    pub ign_advance: f32,
    // GPS
    pub speed_kph:   f32,
    pub odo_km:      f64,
    pub trip_km:     f64,
    pub gps_fix:     bool,
    // Fuel
    pub fuel_pct:    f32,
    // Bluetooth pairing
    pub bt_pairing_pending:  bool,
    pub bt_pairing_device:   String,
    pub bt_pairing_passkey:  u32,
    /// None = waiting for user, Some(true) = accepted, Some(false) = rejected
    pub bt_pairing_accepted: Option<bool>,
}

impl Default for VehicleState {
    fn default() -> Self {
        Self {
            rpm:         0.0,
            map_kpa:     101.3,   // atmospheric pressure at rest
            clt_c:       0.0,
            afr:         14.7,    // stoichiometric — valid before first CAN frame
            tps_pct:     0.0,
            iat_c:       20.0,    // room temperature default
            batt_v:      12.0,    // nominal resting voltage
            ign_advance: 0.0,
            speed_kph:   0.0,
            odo_km:      0.0,
            trip_km:     0.0,
            gps_fix:     false,
            fuel_pct:    0.5,     // half tank — better than empty
            bt_pairing_pending:  false,
            bt_pairing_device:   String::new(),
            bt_pairing_passkey:  0,
            bt_pairing_accepted: None,
        }
    }
}

/// Thread-safe shared state handle. Clone this Arc to give each thread access.
pub type SharedState = Arc<Mutex<VehicleState>>;

/// Create a new shared state.
pub fn new_shared() -> SharedState {
    Arc::new(Mutex::new(VehicleState::default()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_values_are_sane() {
        let s = VehicleState::default();
        assert_eq!(s.rpm, 0.0);
        assert_eq!(s.speed_kph, 0.0);
        assert_eq!(s.afr, 14.7);          // stoichiometric, not 0.0
        assert_eq!(s.batt_v, 12.0);       // nominal resting voltage
        assert!(!s.bt_pairing_pending);
        assert!(s.bt_pairing_accepted.is_none());
    }

    #[test]
    fn shared_state_can_be_written_and_cloned() {
        let shared = new_shared();

        // Write both fields atomically under a single lock
        {
            let mut s = shared.lock();
            s.rpm = 3500.0;
            s.speed_kph = 120.0;
        }

        // Read snapshot — lock held briefly, then released
        let snap = shared.lock().clone();
        assert_eq!(snap.rpm, 3500.0);
        assert_eq!(snap.speed_kph, 120.0);
    }

    #[test]
    fn two_clones_see_same_data() {
        let shared = new_shared();
        let clone_a = Arc::clone(&shared);
        let clone_b = Arc::clone(&shared);

        clone_a.lock().clt_c = 92.0;
        assert_eq!(clone_b.lock().clt_c, 92.0);
    }
}
