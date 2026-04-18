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
