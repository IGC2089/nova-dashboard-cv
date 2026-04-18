from __future__ import annotations
import os
import json
import logging
import threading
from typing import Callable, Optional

log = logging.getLogger(__name__)

ODO_PATH = '/data/odo.json'
HACC_MAX_M = 10.0
SAVE_INTERVAL_S = 300.0  # Save at most every 5 minutes


class OdometerAccumulator:
    """Pure ODO/trip accumulation logic. No I/O except optional save_callback."""

    def __init__(
        self,
        initial_odo_mi: float = 0.0,
        save_callback: Optional[Callable[[float, float], None]] = None,
    ):
        self.odo_mi: float = initial_odo_mi
        self.trip_mi: float = 0.0
        self._elapsed_s: float = 0.0
        self._last_save_s: float = 0.0
        self._save_cb = save_callback

    def update(self, speed_mph: float, dt_s: float, hacc_m: float) -> bool:
        if hacc_m >= HACC_MAX_M:
            return False
        delta_mi = speed_mph * (dt_s / 3600.0)
        self.odo_mi += delta_mi
        self.trip_mi += delta_mi
        self._elapsed_s += dt_s
        if self._save_cb and (self._elapsed_s - self._last_save_s) >= SAVE_INTERVAL_S:
            self._save_cb((self.odo_mi, self.trip_mi))
            self._last_save_s = self._elapsed_s
        return True
