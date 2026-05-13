"""GPS listener thread — connects to a Bluetooth GPS over RFCOMM.

Discovers the RFCOMM channel via SDP automatically (no manual rfcomm bind needed).
Reconnects every 5 s if the link drops.
Thread-safe: call get_position() from any thread.
"""
from __future__ import annotations
import logging
import socket
import subprocess
import threading
from dataclasses import dataclass

log = logging.getLogger(__name__)

RECONNECT_INTERVAL = 5.0
SPP_UUID = '00001101-0000-1000-8000-00805F9B34FB'


@dataclass
class GpsPosition:
    lat: float = 0.0
    lon: float = 0.0
    heading: float = 0.0       # degrees, 0 = North
    speed_kmh: float = 0.0
    fix: bool = False


def _find_channel(mac: str) -> int | None:
    """Run sdptool to find the RFCOMM channel of the GPS SPP service."""
    try:
        out = subprocess.check_output(
            ['sdptool', 'browse', mac],
            stderr=subprocess.DEVNULL, timeout=15,
        ).decode(errors='replace')
    except Exception as exc:
        log.warning("sdptool failed: %s", exc)
        return None

    channel = None
    in_target = False
    for line in out.splitlines():
        low = line.lower()
        if any(k in low for k in ('gps', 'nmea', 'serial port')):
            in_target = True
        if in_target and 'channel:' in low:
            try:
                channel = int(line.split()[-1])
            except ValueError:
                pass
            break
    return channel


class GpsRfcomm(threading.Thread):
    """Daemon thread: discovers RFCOMM channel via SDP and reads NMEA sentences."""

    def __init__(self, mac: str, port: str = '/dev/rfcomm0', baud: int = 9600):
        super().__init__(daemon=True, name='GpsRfcomm')
        self._mac = mac
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._pos = GpsPosition()

    def stop(self) -> None:
        self._stop_event.set()

    def get_position(self) -> GpsPosition:
        with self._lock:
            return self._pos

    def _set(self, pos: GpsPosition) -> None:
        with self._lock:
            self._pos = pos

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._read_loop()
            except Exception as exc:
                log.warning("GPS link lost: %s — retrying in %.0fs", exc, RECONNECT_INTERVAL)
                with self._lock:
                    self._pos = GpsPosition(lat=self._pos.lat, lon=self._pos.lon, fix=False)
            self._stop_event.wait(RECONNECT_INTERVAL)

    def _read_loop(self) -> None:
        import pynmea2

        log.info("Discovering RFCOMM channel for %s …", self._mac)
        channel = _find_channel(self._mac)
        if channel is None:
            raise RuntimeError("GPS service not found via SDP")
        log.info("Connecting to %s channel %d", self._mac, channel)

        sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
        sock.settimeout(10.0)
        sock.connect((self._mac, channel))
        sock.settimeout(3.0)
        log.info("GPS connected")

        last = GpsPosition()
        buf = b''
        with sock:
            while not self._stop_event.is_set():
                try:
                    chunk = sock.recv(256)
                except TimeoutError:
                    continue
                if not chunk:
                    raise ConnectionError("GPS socket closed by remote")
                buf += chunk
                while b'\n' in buf:
                    line, buf = buf.split(b'\n', 1)
                    raw = line.decode('ascii', errors='replace').strip()
                    if not raw.startswith('$'):
                        continue
                    try:
                        msg = pynmea2.parse(raw)
                    except pynmea2.ParseError:
                        continue

                    if isinstance(msg, pynmea2.types.talker.RMC):
                        if msg.status == 'A':
                            last = GpsPosition(
                                lat=msg.latitude,
                                lon=msg.longitude,
                                heading=float(msg.true_course or 0.0),
                                speed_kmh=float(msg.spd_over_grnd or 0.0) * 1.852,
                                fix=True,
                            )
                            self._set(last)
                        else:
                            self._set(GpsPosition(lat=last.lat, lon=last.lon, fix=False))

                    elif isinstance(msg, pynmea2.types.talker.GGA):
                        if msg.gps_qual and int(msg.gps_qual) > 0:
                            last = GpsPosition(
                                lat=msg.latitude,
                                lon=msg.longitude,
                                heading=last.heading,
                                speed_kmh=last.speed_kmh,
                                fix=True,
                            )
                            self._set(last)
