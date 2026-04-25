from vehicle_state import VehicleState

def test_media_fields_exist_with_defaults():
    s = VehicleState()
    assert s.bt_connected is False
    assert s.bt_playing is False
    assert s.bt_title == ""
    assert s.bt_artist == ""
    assert s.bt_album == ""

def test_snapshot_copies_media_fields():
    s = VehicleState()
    with s.lock:
        s.bt_connected = True
        s.bt_playing = True
        s.bt_title = "Bohemian Rhapsody"
        s.bt_artist = "Queen"
        s.bt_album = "A Night at the Opera"
    snap = s.snapshot()
    assert snap.bt_connected is True
    assert snap.bt_playing is True
    assert snap.bt_title == "Bohemian Rhapsody"
    assert snap.bt_artist == "Queen"
    assert snap.bt_album == "A Night at the Opera"
    assert snap.lock is None
