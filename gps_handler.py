from __future__ import annotations
import os
import json
import logging
import threading
from typing import Callable, Optional

log = logging.getLogger(__name__)

ODO_PATH = '/data/odo.json'
HACC_MAX_M = 10.0
SAVE_INTERVAL_MI = 1.0  # Save every 1 mile (roughly every 60s at highway speed)


class OdometerAccumulator:
    """Pure ODO/trip accumulation logic. No I/O except optional save_callback."""

    def __init__(
        self,
        initial_odo_mi: float = 0.0,
        save_callback: Optional[Callable[[float, float], None]] = None,
    ):
        self.odo_mi: float = initial_odo_mi
        self.trip_mi: float = 0.0
        self._last_save_odo: float = initial_odo_mi
        self._save_cb = save_callback

    def update(self, speed_mph: float, dt_s: float, hacc_m: float) -> bool:
        if hacc_m >= HACC_MAX_M:
            return False
        delta_mi = speed_mph * (dt_s / 3600.0)
        self.odo_mi += delta_mi
        self.trip_mi += delta_mi
        if self._save_cb and (self.odo_mi - self._last_save_odo) >= SAVE_INTERVAL_MI:
            self._save_cb((self.odo_mi, self.trip_mi))
            self._last_save_odo = self.odo_mi
        return True


import time
from vehicle_state import VehicleState

GPS_TIMEOUT_S = 5.0


def _load_odo() -> float:
    try:
        with open(ODO_PATH) as f:
            return float(json.load(f).get('odo_mi', 0.0))
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return 0.0


def _atomic_save(odo_data) -> None:
    """Write ODO atomically. Power-safe via os.replace().

    Accepts either a (odo_mi, trip_mi) tuple (from OdometerAccumulator callback)
    or two positional floats for direct calls.
    """
    if isinstance(odo_data, tuple):
        odo_mi, trip_mi = odo_data
    else:
        odo_mi = odo_data
        trip_mi = 0.0
    tmp = ODO_PATH + '.tmp'
    try:
        with open(tmp, 'w') as f:
            json.dump({'odo_mi': odo_mi, 'trip_mi': trip_mi}, f)
        os.replace(tmp, ODO_PATH)
    except OSError as e:
        log.warning("ODO save failed: %s", e)


class GPSListener(threading.Thread):
    """Daemon thread: reads gpsd, accumulates ODO, writes to VehicleState."""

    def __init__(self, state: VehicleState):
        super().__init__(daemon=True, name='GPSListener')
        self._state = state
        self._running = False
        self._acc = OdometerAccumulator(
            initial_odo_mi=_load_odo(),
            save_callback=_atomic_save,
        )
        self._last_fix_time = 0.0

    def run(self) -> None:
        import gps as _gps  # noqa: PLC0415 — lazy import; not available on dev machines
        self._running = True
        session = _gps.gps(mode=_gps.WATCH_ENABLE | _gps.WATCH_NEWSTYLE)
        last_time = time.monotonic()
        log.info("GPS listener started")

        while self._running:
            try:
                report = session.next()
            except StopIteration:
                break
            except Exception as e:
                log.warning("GPS read error: %s", e)
                continue

            now = time.monotonic()
            dt_s = now - last_time
            last_time = now

            if report['class'] != 'TPV':
                continue

            speed_ms = getattr(report, 'speed', 0.0) or 0.0
            hacc_m = getattr(report, 'epx', 999.0) or 999.0
            speed_mph = speed_ms * 2.23694

            fix_valid = self._acc.update(speed_mph, dt_s, hacc_m)
            if fix_valid:
                self._last_fix_time = now

            gps_ok = (now - self._last_fix_time) < GPS_TIMEOUT_S

            with self._state.lock:
                if fix_valid:
                    self._state.speed_mph = speed_mph
                self._state.odo_mi = self._acc.odo_mi
                self._state.trip_mi = self._acc.trip_mi
                self._state.gps_fix = gps_ok

    def stop(self) -> None:
        self._running = False
        _atomic_save((self._acc.odo_mi, self._acc.trip_mi))
        log.info("GPS listener stopped, ODO saved")
