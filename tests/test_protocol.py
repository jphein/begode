"""Tests for the Begode protocol decoder (pure Python, no HA imports)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "custom_components" / "begode"))

import protocol  # noqa: E402
from protocol import BegodeDecoder, FrameUnpacker, battery_percent  # noqa: E402

# Sample frames from WheelLog's reverse-engineering notes (GotwayAdapter).
FRAME_A = bytes.fromhex("55AA19F0000000000000012CFDCA0001FFF800185A5A5A5A")
FRAME_B = bytes.fromhex("55AA000A4A1248001C20002A00030007000804185A5A5A5A")


def test_unpacker_reassembles_fragments():
    unpacker = FrameUnpacker()
    frames = []
    # Feed frame A split across odd-size chunks, twice, with leading garbage.
    stream = b"\x00\x13" + FRAME_A + b"\x99" + FRAME_A
    for byte in stream:
        frame = unpacker.add_byte(byte)
        if frame:
            frames.append(frame)
    assert frames == [FRAME_A, FRAME_A]


def test_unpacker_rejects_bad_footer():
    bad = FRAME_A[:22] + b"\x00\x00"
    unpacker = FrameUnpacker()
    assert all(unpacker.add_byte(b) is None for b in bad)
    # And it recovers on the next good frame.
    for byte in FRAME_A[:-1]:
        assert unpacker.add_byte(byte) is None
    assert unpacker.add_byte(FRAME_A[-1]) == FRAME_A


def test_frame_a_decoding_67v():
    dec = BegodeDecoder(voltage_scale=1.0)
    assert dec.handle_notification(FRAME_A)
    st = dec.state
    assert st.raw_voltage == 0x19F0  # 6640
    assert st.voltage == 66.40
    assert st.battery == 97  # round((6640-5320)/13.6)
    assert st.speed == 0.0
    assert st.trip_distance == 0.0
    assert st.phase_current == 3.0  # 0x012C = 300
    assert round(st.temperature, 1) == 34.9  # -566/340 + 36.53
    assert st.power == 199.2


def test_frame_a_trip_distance_is_u16_at_8():
    frame = bytearray(FRAME_A)
    frame[6:8] = (61).to_bytes(2, "big")  # non-distance counter, must be ignored
    frame[8:10] = (12345).to_bytes(2, "big")
    dec = BegodeDecoder()
    dec.handle_notification(bytes(frame))
    assert dec.state.trip_distance == 12.345


def test_frame_a_pwm_not_taken_from_frame_a():
    frame = bytearray(FRAME_A)
    frame[14:16] = (3080).to_bytes(2, "big")  # junk on stock firmware
    dec = BegodeDecoder()
    dec.handle_notification(bytes(frame))
    assert dec.state.pwm is None


def test_frame_a_voltage_scaling_134v():
    dec = BegodeDecoder(voltage_scale=2.0)
    dec.handle_notification(FRAME_A)
    assert dec.state.voltage == 132.80
    # SoC comes from the raw 67.2-base value — unchanged by scaling.
    assert dec.state.battery == 97


def test_frame_b_total_distance():
    dec = BegodeDecoder()
    assert dec.handle_notification(FRAME_B)
    assert dec.state.total_distance == 674.322  # 0x000A4A12 m
    assert dec.state.alerts == []


def test_frame_b_alerts():
    frame = bytearray(FRAME_B)
    frame[14] = 0x28  # over_temperature | low_voltage
    dec = BegodeDecoder()
    dec.handle_notification(bytes(frame))
    assert sorted(dec.state.alerts) == ["low_voltage", "over_temperature"]


def test_frame_07_battery_current_and_motor_temp():
    frame = bytearray(24)
    frame[0:2] = b"\x55\xaa"
    frame[2:4] = (500).to_bytes(2, "big")  # battery current 5.00 A (discharge)
    frame[6:8] = (42).to_bytes(2, "big")  # motor temp 42 C
    frame[8:10] = (30).to_bytes(2, "big")  # hw PWM 30%
    frame[18] = 0x07
    frame[19] = 0x18
    frame[20:24] = b"\x5a\x5a\x5a\x5a"
    dec = BegodeDecoder()
    dec.handle_notification(bytes(frame))
    st = dec.state
    assert st.battery_current == -5.0  # WheelLog negates: positive raw = discharge
    assert st.motor_temperature == 42.0
    assert st.pwm == 30.0


def test_frame_01_bms_voltage():
    frame = bytearray(24)
    frame[0:2] = b"\x55\xaa"
    frame[6:8] = (1332).to_bytes(2, "big")  # 133.2 V true pack voltage
    frame[18] = 0x01
    frame[20:24] = b"\x5a\x5a\x5a\x5a"
    dec = BegodeDecoder()
    dec.handle_notification(bytes(frame))
    assert dec.state.bms_voltage == 133.2


def test_cell_frames():
    def cell_frame(ftype, page, mv_values):
        frame = bytearray(24)
        frame[0:2] = b"\x55\xaa"
        for i, mv in enumerate(mv_values):
            frame[(i + 1) * 2 : (i + 1) * 2 + 2] = mv.to_bytes(2, "big")
        frame[18] = ftype
        frame[19] = page
        frame[20:24] = b"\x5a\x5a\x5a\x5a"
        return bytes(frame)

    dec = BegodeDecoder()
    dec.handle_notification(cell_frame(0x02, 0, [4100, 4110, 4095, 4102, 4100, 4100, 4100, 4100]))
    dec.handle_notification(cell_frame(0x02, 1, [4150, 4100, 4100, 4100, 0, 0, 0, 0]))
    st = dec.state
    assert st.cell_min == 4.095
    assert st.cell_max == 4.150
    assert st.cell_diff == 0.055


def test_ascii_model_and_firmware():
    dec = BegodeDecoder()
    assert dec.handle_notification(b"NAMEFalcon")
    assert dec.state.model == "Falcon"
    assert dec.handle_notification(b"GW2.03")
    assert dec.state.firmware == "2.03"


def test_battery_percent_curve():
    assert battery_percent(6700) == 100
    assert battery_percent(6680 + 1) == 100
    assert battery_percent(5320 + 680) == 50  # midpoint of linear zone
    assert battery_percent(5100) == 0
    assert battery_percent(5150) == 0  # (5150-5120)//36 = 0
    assert 0 <= battery_percent(5445) <= 10


def test_zero_live():
    dec = BegodeDecoder()
    dec.handle_notification(FRAME_A)
    dec.state.zero_live()
    assert dec.state.speed == 0.0
    assert dec.state.phase_current == 0.0
    assert dec.state.battery == 97  # sticky values untouched
    assert dec.state.voltage == 66.40


def test_voltage_scale_table():
    assert protocol.VOLTAGE_SCALES["67.2"] == 1.0
    assert protocol.VOLTAGE_SCALES["84"] == 1.25
    assert protocol.VOLTAGE_SCALES["100.8"] == 1.5
    assert protocol.VOLTAGE_SCALES["134.4"] == 2.0
