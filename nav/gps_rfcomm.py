"""GPS listener thread — reads NMEA sentences from /dev/rfcomm0.

Reconnects automatically every 5 s if the Bluetooth link drops.
Thread-safe: call get_position() from any thread.
"""
from __future__ import annotations
import logging
import threading
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

RECONNECT_INTERVAL = 5.0
DEFAULT_PORT = '/dev/rfcomm0'
DEFAULT_BAUD = 9600


@dataclass
class GpsPosition:
    lat: float = 0.0
    lon: float = 0.0
    heading: float = 0.0       # degrees, 0 = North
    speed_kmh: float = 0.0
    fix: bool = False


class GpsRfcomm(threading.Thread):
    """Daemon thread: reads NMEA from a rfcomm serial port, reconnects on drop."""

    def __init__(self, port: str = DEFAULT_PORT, baud: int = DEFAULT_BAUD):
        super().__init__(daemon=True, name='GpsRfcomm')
        self._port = port
        self._baud = baud
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
                # Preserve last known position but mark fix lost
                with self._lock:
                    self._pos = GpsPosition(
                        lat=self._pos.lat,
                        lon=self._pos.lon,
                        fix=False,
                    )
            self._stop_event.wait(RECONNECT_INTERVAL)

    def _read_loop(self) -> None:
        import serial
        import pynmea2

        log.info("Opening %s @ %d baud", self._port, self._baud)
        with serial.Serial(self._port, self._baud, timeout=2.0) as ser:
            log.info("GPS port open")
            last = GpsPosition()

            while not self._stop_event.is_set():
                try:
                    raw = ser.readline().decode('ascii', errors='replace').strip()
                except serial.SerialException as exc:
                    raise  # bubble up to reconnect loop

                if not raw.startswith('$'):
                    continue

                try:
                    msg = pynmea2.parse(raw)
                except pynmea2.ParseError:
                    continue

                if isinstance(msg, pynmea2.types.talker.RMC):
                    if msg.status == 'A':   # Active = valid fix
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
                        # GGA supplements RMC with altitude; update lat/lon if we have it
                        last = GpsPosition(
                            lat=msg.latitude,
                            lon=msg.longitude,
                            heading=last.heading,
                            speed_kmh=last.speed_kmh,
                            fix=True,
                        )
                        self._set(last)
