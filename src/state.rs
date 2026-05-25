use parking_lot::Mutex;
use std::sync::Arc;

/// All live vehicle data. Must be `Clone` so main thread can snapshot without holding the lock.
#[derive(Clone, Default)]
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
        assert_eq!(s.afr, 0.0);
        assert!(!s.bt_pairing_pending);
        assert!(s.bt_pairing_accepted.is_none());
    }

    #[test]
    fn shared_state_can_be_written_and_cloned() {
        let shared = new_shared();

        // Write from one "thread"
        shared.lock().rpm = 3500.0;
        shared.lock().speed_kph = 120.0;

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
