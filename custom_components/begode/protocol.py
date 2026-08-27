"""Begode/Gotway BLE protocol decoder.

SPDX-License-Identifier: GPL-3.0-or-later

Ported from WheelLog's GotwayAdapter (reverse-engineered protocol):
https://github.com/Wheellog/Wheellog.Android (GPL-3.0).

The wheel streams 24-byte frames over a serial-to-BLE bridge (HM-10 style,
service FFE0 / characteristic FFE1). Frames: header 55 AA, footer 5A 5A 5A 5A,
byte 18 is the frame type. No checksums; frames arrive fragmented across BLE
notifications, so bytes are reassembled from the stream.

The voltage field is calibrated for a 67.2V (16s) pack regardless of the
wheel's real pack voltage — higher-voltage wheels need a fixed multiplier.
Battery percent is derived from the *raw* (67.2-base) value, so it is
independent of the multiplier.
"""
from __future__ import annotations

from dataclasses import dataclass, field

SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
CHAR_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"

FRAME_LEN = 24

# Pack voltage -> multiplier for the 67.2V-base raw voltage field.
VOLTAGE_SCALES: dict[str, float] = {
    "42": 42.0 / 67.2,  # Mten Mini (10s) — verified against its BMS-reported voltage
    "67.2": 1.0,
    "84": 1.25,
    "100.8": 1.5,
    "116.8": 116.8 / 67.2,
    "134.4": 2.0,
    "151.2": 2.25,
    "168": 2.5,
}

ALERT_BITS = (
    (0x01, "high_power"),
    (0x02, "speed_alarm_2"),
    (0x04, "speed_alarm_1"),
    (0x08, "low_voltage"),
    (0x10, "over_voltage"),
    (0x20, "over_temperature"),
    (0x40, "hall_sensor_error"),
    (0x80, "transport_mode"),
)


def _u16(buf: bytes, off: int) -> int:
    return (buf[off] << 8) | buf[off + 1]


def _s16(buf: bytes, off: int) -> int:
    val = _u16(buf, off)
    return val - 0x10000 if val >= 0x8000 else val


def _u32(buf: bytes, off: int) -> int:
    return (buf[off] << 24) | (buf[off + 1] << 16) | (buf[off + 2] << 8) | buf[off + 3]


def battery_percent(raw_voltage: int) -> int:
    """WheelLog 'better percents' SoC curve from the raw 67.2-base centivolts."""
    if raw_voltage > 6680:
        return 100
    if raw_voltage > 5440:
        return min(100, round((raw_voltage - 5320) / 13.6))
    if raw_voltage > 5120:
        return (raw_voltage - 5120) // 36
    return 0


class FrameUnpacker:
    """Reassemble 24-byte frames from the fragmented BLE byte stream."""

    def __init__(self) -> None:
        self._buf = bytearray()
        self._collecting = False
        self._prev = -1

    def add_byte(self, c: int) -> bytes | None:
        """Feed one byte; return a complete frame when one is assembled."""
        if self._collecting:
            self._buf.append(c)
            self._prev = c
            size = len(self._buf)
            if size > 20 and size <= FRAME_LEN and c != 0x5A:
                self._collecting = False
                return None
            if size == FRAME_LEN:
                self._collecting = False
                return bytes(self._buf)
            # Resync on the garbage patterns WheelLog handles: a stray
            # 55 AA 5A [5A] immediately followed by a real 55 AA header.
            if size == 5 and self._buf[2] == 0x5A and self._buf[3] == 0x55 and self._buf[4] == 0xAA:
                self._buf = bytearray(b"\x55\xaa")
            elif (
                size == 6
                and self._buf[2] == 0x5A
                and self._buf[3] == 0x5A
                and self._buf[4] == 0x55
                and self._buf[5] == 0xAA
            ):
                self._buf = bytearray(b"\x55\xaa")
        else:
            if c == 0xAA and self._prev == 0x55:
                self._buf = bytearray(b"\x55\xaa")
                self._collecting = True
            self._prev = c
        return None


@dataclass
class WheelState:
    """Decoded wheel telemetry."""

    voltage_scale: float = 1.0

    # Frame A (0x00)
    raw_voltage: int | None = None  # centivolts, 67.2V base
    voltage: float | None = None  # V, scaled
    battery: int | None = None  # %
    speed: float | None = None  # km/h
    trip_distance: float | None = None  # km
    phase_current: float | None = None  # A
    temperature: float | None = None  # °C (controller / MPU6050)
    pwm: float | None = None  # %

    # Frame B (0x04)
    total_distance: float | None = None  # km
    alerts: list[str] = field(default_factory=list)

    # Frame 0x07 (extended live data, newer firmwares)
    battery_current: float | None = None  # A (negative = charging)
    motor_temperature: float | None = None  # °C
    _true_pwm: bool = False

    # Frame 0x01 (smart BMS summary, newer wheels)
    bms_voltage: float | None = None  # V, reported directly by BMS

    # Frames 0x02/0x03 (smart BMS cell voltages)
    cells: dict[int, float] = field(default_factory=dict)

    # ASCII responses to "N"/"V" commands
    model: str | None = None
    firmware: str | None = None

    @property
    def power(self) -> float | None:
        """W — prefers true battery current when the wheel reports it."""
        if self.voltage is None:
            return None
        current = self.battery_current if self.battery_current is not None else self.phase_current
        if current is None:
            return None
        return round(self.voltage * current, 1)

    @property
    def cell_min(self) -> float | None:
        vals = [v for v in self.cells.values() if v > 0]
        return min(vals) if vals else None

    @property
    def cell_max(self) -> float | None:
        vals = [v for v in self.cells.values() if v > 0]
        return max(vals) if vals else None

    @property
    def cell_diff(self) -> float | None:
        if self.cell_min is None or self.cell_max is None:
            return None
        return round(self.cell_max - self.cell_min, 3)

    def zero_live(self) -> None:
        """Zero out instantaneous values (used when the wheel disconnects)."""
        if self.speed is not None:
            self.speed = 0.0
        if self.phase_current is not None:
            self.phase_current = 0.0
        if self.battery_current is not None:
            self.battery_current = 0.0
        if self.pwm is not None:
            self.pwm = 0.0


class BegodeDecoder:
    """Feed BLE notification chunks, maintain a WheelState."""

    def __init__(self, voltage_scale: float = 1.0) -> None:
        self.state = WheelState(voltage_scale=voltage_scale)
        self._unpacker = FrameUnpacker()

    def handle_notification(self, data: bytes) -> bool:
        """Process one BLE notification chunk. Returns True if state changed."""
        changed = self._try_ascii(data)
        for byte in data:
            frame = self._unpacker.add_byte(byte)
            if frame is not None:
                changed = self._decode_frame(frame) or changed
        return changed

    def _try_ascii(self, data: bytes) -> bool:
        """Model/firmware arrive as bare ASCII chunks in the same stream."""
        if self.state.model is not None and self.state.firmware is not None:
            return False
        try:
            text = data.decode("ascii").strip()
        except UnicodeDecodeError:
            return False
        if text.startswith("NAME") and self.state.model is None:
            self.state.model = text[4:].lstrip(":").strip()
            return True
        if text.startswith("GW") and self.state.firmware is None and len(text) > 2:
            self.state.firmware = text[2:].strip()
            return True
        return False

    def _decode_frame(self, buf: bytes) -> bool:
        st = self.state
        ftype = buf[18]
        if ftype == 0x00:  # Frame A: live data
            st.raw_voltage = _u16(buf, 2)
            st.voltage = round(st.raw_voltage * st.voltage_scale / 100.0, 2)
            st.battery = battery_percent(st.raw_voltage)
            st.speed = round(abs(_s16(buf, 4)) * 3.6 / 100.0, 1)
            # Trip is the 16-bit word at 8 (bytes 6-7 are NOT distance high
            # bits on current firmwares — verified live on Falcon/A2/Mten Mini).
            st.trip_distance = round(_u16(buf, 8) / 1000.0, 3)
            st.phase_current = round(abs(_s16(buf, 10)) / 100.0, 2)
            st.temperature = round(_s16(buf, 12) / 340.0 + 36.53, 1)
            # Bytes 14-15 are only PWM on certain custom firmwares; stock
            # Begode fw streams junk there (~300%), so PWM comes solely from
            # frame 0x07.
            return True
        if ftype == 0x04:  # Frame B: odometer + settings/alerts
            st.total_distance = round(_u32(buf, 2) / 1000.0, 3)
            alert = buf[14]
            st.alerts = [name for bit, name in ALERT_BITS if alert & bit]
            return True
        if ftype == 0x07:  # Extended live data
            st.battery_current = round(-_s16(buf, 2) / 100.0, 2)
            st.motor_temperature = float(_s16(buf, 6))
            hw_pwm = _s16(buf, 8)
            if hw_pwm != 0:
                st._true_pwm = True
            if st._true_pwm:
                st.pwm = float(abs(hw_pwm))
            return True
        if ftype == 0x01:  # Smart BMS summary: true pack voltage
            bms_voltage = _u16(buf, 6)
            if bms_voltage:
                st.bms_voltage = round(bms_voltage / 10.0, 1)
            return True
        if ftype in (0x02, 0x03):  # Smart BMS cell voltages, 8 cells per frame
            bms_num = ftype - 0x02  # 0 or 1
            page = buf[19]
            for i in range(8):
                val = _u16(buf, (i + 1) * 2) / 1000.0
                if val > 0:
                    st.cells[bms_num * 1000 + page * 8 + i] = val
            return True
        return False
