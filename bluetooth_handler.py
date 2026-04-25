# bluetooth_handler.py
"""Daemon thread that polls BlueZ AVRCP for media metadata and controls."""
from __future__ import annotations
import logging
import threading
import time
from typing import Optional

from vehicle_state import VehicleState

log = logging.getLogger(__name__)

POLL_INTERVAL = 1.0  # seconds between D-Bus polls
ALLOWED_COMMANDS = frozenset({"Play", "Pause", "Next", "Previous", "Stop"})


class AVRCPPoller:
    """Pure parse logic — no D-Bus dependency, fully unit-testable."""

    @staticmethod
    def parse_properties(props: dict) -> dict:
        """Convert raw MediaPlayer1 properties dict to media state dict."""
        if not props:
            return {
                "bt_connected": False,
                "bt_playing": False,
                "bt_title": "",
                "bt_artist": "",
                "bt_album": "",
            }
        status = str(props.get("Status", "")).lower()
        track = props.get("Track", {}) or {}
        return {
            "bt_connected": True,
            "bt_playing": status == "playing",
            "bt_title": str(track.get("Title", "")),
            "bt_artist": str(track.get("Artist", "")),
            "bt_album": str(track.get("Album", "")),
        }


class BluetoothHandler(threading.Thread):
    """Daemon thread: polls BlueZ MediaPlayer1 every second, updates VehicleState."""

    def __init__(self, state: VehicleState):
        super().__init__(daemon=True, name="BluetoothHandler")
        self._state = state
        self._stop_event = threading.Event()
        self._cmd_lock = threading.Lock()
        self._pending_cmd: Optional[str] = None

    def send_command(self, cmd: str) -> None:
        """Thread-safe: queue a playback command."""
        if cmd not in ALLOWED_COMMANDS:
            log.warning("Rejected unknown BT command: %r", cmd)
            return
        with self._cmd_lock:
            self._pending_cmd = cmd

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        try:
            import dbus
        except ImportError:
            log.warning("dbus-python not available — Bluetooth media disabled")
            return

        bus = dbus.SystemBus()
        poller = AVRCPPoller()
        consecutive_failures = 0

        while not self._stop_event.is_set():
            try:
                self._poll_once(bus, poller, dbus)
                consecutive_failures = 0
            except Exception:
                consecutive_failures += 1
                level = logging.WARNING if consecutive_failures >= 3 else logging.DEBUG
                log.log(level, "BT poll error (failure #%d)", consecutive_failures, exc_info=True)
                self._write_disconnected()

            self._stop_event.wait(POLL_INTERVAL)

    def _poll_once(self, bus, poller: AVRCPPoller, dbus) -> None:
        """Find first MediaPlayer1 object and read its properties."""
        manager = dbus.Interface(
            bus.get_object("org.bluez", "/"),
            "org.freedesktop.DBus.ObjectManager",
        )
        objects = manager.GetManagedObjects()

        player_path = None
        ctrl_path = None
        for path, ifaces in objects.items():
            if "org.bluez.MediaPlayer1" in ifaces:
                player_path = path
            if "org.bluez.MediaControl1" in ifaces:
                ctrl_path = path

        if player_path is None:
            self._write_disconnected()
            return

        # Send any pending command before reading state
        with self._cmd_lock:
            cmd = self._pending_cmd
            self._pending_cmd = None

        if cmd:
            if ctrl_path:
                try:
                    ctrl = dbus.Interface(
                        bus.get_object("org.bluez", ctrl_path),
                        "org.bluez.MediaControl1",
                    )
                    getattr(ctrl, cmd)()
                    log.debug("BT command sent: %s", cmd)
                except Exception:
                    log.warning("BT command failed: %s", cmd, exc_info=True)
            else:
                log.warning("No MediaControl1 path found, cannot send command: %s", cmd)

        props_iface = dbus.Interface(
            bus.get_object("org.bluez", player_path),
            "org.freedesktop.DBus.Properties",
        )
        raw = props_iface.GetAll("org.bluez.MediaPlayer1")
        media = poller.parse_properties(dict(raw))
        self._write(media)

    def _write(self, media: dict) -> None:
        with self._state.lock:
            self._state.bt_connected = media["bt_connected"]
            self._state.bt_playing = media["bt_playing"]
            self._state.bt_title = media["bt_title"]
            self._state.bt_artist = media["bt_artist"]
            self._state.bt_album = media["bt_album"]

    def _write_disconnected(self) -> None:
        with self._state.lock:
            self._state.bt_connected = False
            self._state.bt_playing = False
            self._state.bt_title = ""
            self._state.bt_artist = ""
            self._state.bt_album = ""
