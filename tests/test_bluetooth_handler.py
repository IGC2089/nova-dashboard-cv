# tests/test_bluetooth_handler.py
"""Tests for AVRCPPoller — pure logic, no D-Bus hardware required."""
from bluetooth_handler import AVRCPPoller


def test_parse_properties_connected_playing():
    props = {
        "Status": "playing",
        "Track": {
            "Title": "Bohemian Rhapsody",
            "Artist": "Queen",
            "Album": "A Night at the Opera",
        },
    }
    result = AVRCPPoller.parse_properties(props)
    assert result["bt_connected"] is True
    assert result["bt_playing"] is True
    assert result["bt_title"] == "Bohemian Rhapsody"
    assert result["bt_artist"] == "Queen"
    assert result["bt_album"] == "A Night at the Opera"


def test_parse_properties_paused():
    props = {
        "Status": "paused",
        "Track": {"Title": "Yesterday", "Artist": "Beatles", "Album": "Help!"},
    }
    result = AVRCPPoller.parse_properties(props)
    assert result["bt_connected"] is True
    assert result["bt_playing"] is False


def test_parse_properties_empty_track():
    props = {"Status": "playing", "Track": {}}
    result = AVRCPPoller.parse_properties(props)
    assert result["bt_title"] == ""
    assert result["bt_artist"] == ""
    assert result["bt_album"] == ""


def test_parse_properties_missing_track_key():
    props = {"Status": "stopped"}
    result = AVRCPPoller.parse_properties(props)
    assert result["bt_connected"] is True
    assert result["bt_playing"] is False
    assert result["bt_title"] == ""


def test_parse_empty_gives_disconnected():
    result = AVRCPPoller.parse_properties({})
    assert result["bt_connected"] is False
    assert result["bt_playing"] is False
