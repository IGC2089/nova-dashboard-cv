from __future__ import annotations
import struct
import logging
from typing import Optional

log = logging.getLogger(__name__)

CAN_ID_0 = 0x320
CAN_ID_1 = 0x321


class SpeeduinoDecoder:
    """Pure decode logic — no hardware dependency, fully unit-testable."""

    def decode_0x320(self, data: bytes) -> Optional[dict]:
        if len(data) < 8:
            return None
        rpm = struct.unpack_from('<H', data, 0)[0]
        map_kpa = data[2]
        tps_pct = data[3]
        iat_c = data[4] - 40
        clt_c = data[5] - 40
        clt_f = clt_c * 1.8 + 32
        afr = data[6] * 0.0068 * 14.7
        batt_v = data[7] * 0.1
        return {
            'rpm':     float(rpm),
            'map_kpa': float(map_kpa),
            'tps_pct': float(tps_pct),
            'iat_c':   float(iat_c),
            'clt_f':   clt_f,
            'afr':     afr,
            'batt_v':  batt_v,
        }

    def decode_0x321(self, data: bytes) -> Optional[dict]:
        if len(data) < 4:
            return None
        pw1_us = struct.unpack_from('<H', data, 0)[0]
        inj_duty = data[2] * 0.5
        ign_advance = data[3] - 40
        return {
            'pw1_us':      float(pw1_us),
            'inj_duty':    inj_duty,
            'ign_advance': float(ign_advance),
        }


import threading
import can
from vehicle_state import VehicleState


class CANListener(threading.Thread):
    """Daemon thread: reads SocketCAN frames, decodes, writes to VehicleState."""

    def __init__(self, state: VehicleState, channel: str = 'can0'):
        super().__init__(daemon=True, name='CANListener')
        self._state = state
        self._channel = channel
        self._decoder = SpeeduinoDecoder()
        self._running = False

    def run(self) -> None:
        import time
        self._running = True
        while self._running:
            try:
                bus = can.interface.Bus(channel=self._channel, bustype='socketcan')
                log.info("CAN listener started on %s", self._channel)
                try:
                    while self._running:
                        msg = bus.recv(timeout=0.1)
                        if msg is None:
                            continue
                        if msg.arbitration_id == CAN_ID_0:
                            result = self._decoder.decode_0x320(bytes(msg.data))
                            if result:
                                self._apply(result)
                        elif msg.arbitration_id == CAN_ID_1:
                            result = self._decoder.decode_0x321(bytes(msg.data))
                            if result:
                                self._apply(result)
                finally:
                    bus.shutdown()
                    log.info("CAN listener stopped")
            except OSError as e:
                log.warning("CAN unavailable (%s) — retrying in 5s", e)
                time.sleep(5)

    def stop(self) -> None:
        self._running = False

    def _apply(self, values: dict) -> None:
        with self._state.lock:
            for key, val in values.items():
                if hasattr(self._state, key):
                    setattr(self._state, key, val)
