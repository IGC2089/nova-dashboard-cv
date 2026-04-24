from __future__ import annotations
import threading
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class VehicleState:
    # ECU signals
    rpm: float = 0.0
    map_kpa: float = 0.0
    clt_c: float = 0.0
    afr: float = 14.7
    tps_pct: float = 0.0
    iat_c: float = 0.0
    batt_v: float = 12.0
    ign_advance: float = 0.0

    # GPS signals
    speed_kph: float = 0.0
    odo_km: float = 0.0
    trip_km: float = 0.0
    gps_fix: bool = False

    # Fuel level (0.0–1.0)
    fuel_pct: float = 0.5

    # Threading (excluded from snapshot)
    lock: Optional[threading.Lock] = field(
        default_factory=threading.Lock, repr=False, compare=False
    )

    def snapshot(self) -> VehicleState:
        """Return a lock-free copy of current state for the render thread."""
        with self.lock:
            return VehicleState(
                rpm=self.rpm,
                map_kpa=self.map_kpa,
                clt_c=self.clt_c,
                afr=self.afr,
                tps_pct=self.tps_pct,
                iat_c=self.iat_c,
                batt_v=self.batt_v,
                ign_advance=self.ign_advance,
                speed_kph=self.speed_kph,
                odo_km=self.odo_km,
                trip_km=self.trip_km,
                gps_fix=self.gps_fix,
                fuel_pct=self.fuel_pct,
                lock=None,
            )
