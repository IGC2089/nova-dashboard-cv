from gps_handler import OdometerAccumulator


def test_initial_odo_preserved():
    acc = OdometerAccumulator(initial_odo_km=77654.0)
    assert acc.odo_km == 77654.0


def test_trip_always_starts_at_zero():
    acc = OdometerAccumulator(initial_odo_km=77654.0)
    assert acc.trip_km == 0.0


def test_accumulate_distance_good_fix():
    acc = OdometerAccumulator(initial_odo_km=0.0)
    acc.update(speed_kph=100.0, dt_s=3600.0, hacc_m=5.0)
    assert abs(acc.odo_km - 100.0) < 0.001
    assert abs(acc.trip_km - 100.0) < 0.001


def test_no_accumulation_when_hacc_too_high():
    acc = OdometerAccumulator(initial_odo_km=0.0)
    acc.update(speed_kph=100.0, dt_s=3600.0, hacc_m=50.0)
    assert acc.odo_km == 0.0
    assert acc.trip_km == 0.0


def test_save_triggered_after_threshold():
    saves = []
    acc = OdometerAccumulator(initial_odo_km=0.0, save_callback=saves.append)
    # accumulate 0.8 km — below 1.6 km threshold, no save
    acc.update(speed_kph=100.0, dt_s=28.8, hacc_m=5.0)
    assert len(saves) == 0
    # accumulate 1.0 km more — crosses 1.6 km threshold, one save
    acc.update(speed_kph=100.0, dt_s=36.0, hacc_m=5.0)
    assert len(saves) == 1


def test_update_returns_fix_status():
    acc = OdometerAccumulator(initial_odo_km=0.0)
    valid = acc.update(speed_kph=50.0, dt_s=1.0, hacc_m=3.0)
    assert valid is True
    invalid = acc.update(speed_kph=50.0, dt_s=1.0, hacc_m=99.0)
    assert invalid is False
