import struct
from can_handler import SpeeduinoDecoder


def _make_0x320(rpm=0, map_kpa=101, tps=0, iat_c=25, clt_c=90,
                o2_raw=147, batt_raw=138):
    data = bytearray(8)
    struct.pack_into('<H', data, 0, rpm)
    data[2] = map_kpa
    data[3] = tps
    data[4] = iat_c + 40
    data[5] = clt_c + 40
    data[6] = o2_raw
    data[7] = batt_raw
    return bytes(data)


def _make_0x321(pw1=1200, inj_duty=25, ign_advance=10):
    data = bytearray(8)
    struct.pack_into('<H', data, 0, pw1)
    data[2] = inj_duty * 2
    data[3] = ign_advance + 40
    return bytes(data)


def test_decode_rpm():
    d = SpeeduinoDecoder()
    result = d.decode_0x320(_make_0x320(rpm=3400))
    assert result['rpm'] == 3400.0


def test_decode_clt_celsius():
    d = SpeeduinoDecoder()
    result = d.decode_0x320(_make_0x320(clt_c=90))
    assert abs(result['clt_c'] - 90.0) < 0.01


def test_decode_afr_stoich():
    d = SpeeduinoDecoder()
    result = d.decode_0x320(_make_0x320(o2_raw=147))
    assert abs(result['afr'] - 14.7) < 0.1


def test_decode_map():
    d = SpeeduinoDecoder()
    result = d.decode_0x320(_make_0x320(map_kpa=98))
    assert result['map_kpa'] == 98.0


def test_decode_battery():
    d = SpeeduinoDecoder()
    result = d.decode_0x320(_make_0x320(batt_raw=138))
    assert abs(result['batt_v'] - 13.8) < 0.01


def test_short_frame_returns_none():
    d = SpeeduinoDecoder()
    assert d.decode_0x320(b'\x00\x01\x02') is None


def test_decode_0x321_ignition_advance():
    d = SpeeduinoDecoder()
    result = d.decode_0x321(_make_0x321(ign_advance=10))
    assert result['ign_advance'] == 10.0


def test_decode_0x321_short_frame_returns_none():
    d = SpeeduinoDecoder()
    assert d.decode_0x321(b'\x00') is None
