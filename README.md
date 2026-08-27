# begode — Home Assistant integration for Begode/Gotway EUCs

Custom HA integration that connects to Begode electric unicycles over BLE
(via ESPHome bluetooth proxies with `active: true`) and exposes their
telemetry as sensors.

## How it works

Begode/Gotway wheels bridge their controller UART over BLE (HM-10 style:
service `FFE0`, characteristic `FFE1`, notify + write-without-response).
Once connected, the wheel streams 24-byte telemetry frames continuously —
no polling. The protocol was reverse-engineered by the WheelLog project;
`protocol.py` is a Python port of WheelLog's `GotwayAdapter`.

Frame types decoded:

| Type | Content |
|------|---------|
| `0x00` | live data: voltage, speed, trip distance, phase current, controller temp, PWM |
| `0x04` | odometer (total distance), settings, alert flags |
| `0x07` | battery current, motor temperature, hardware PWM (newer firmwares) |
| `0x01` | smart-BMS summary: true pack voltage (newer wheels) |
| `0x02`/`0x03` | smart-BMS per-cell voltages |

Model and firmware are ASCII responses to the `N` / `V` commands, sent once
after connecting.

## Voltage scaling & SoC

The protocol's voltage field is calibrated for a 67.2V (16s) pack no matter
the wheel's real pack — higher-voltage wheels need a fixed multiplier,
chosen at setup ("Pack voltage"):

| Pack | Multiplier | Wheels |
|------|-----------|--------|
| 67.2V (16s) | 1.0 | older/small wheels |
| 84V (20s) | 1.25 | **A2**, Mten4 |
| 100.8V (24s) | 1.5 | **Falcon**, RS/Nikola 100V |
| 134.4V (32s) | 2.0 | Master, EX |
| 151.2/168V | 2.25/2.5 | Master Pro, EX30 |

Battery SoC is computed from the *raw* (67.2-base) voltage with WheelLog's
"better percents" curve, so it is correct regardless of the multiplier.

## Entities per wheel

Sensors: battery, voltage, speed, trip distance, total distance (odometer,
`total_increasing` — usable in long-term statistics), phase current, battery
current, power, controller temperature, motor temperature, PWM, BMS voltage +
cell min/max/spread (smart-BMS wheels only), model, firmware.
Binary sensors: connected, charging (negative battery current at standstill).
Switch: **maintain connection**.

Sticky values (battery, voltage, odometer, …) are restored across HA
restarts and retained while the wheel is powered off; instantaneous values
(speed, currents, power, PWM) zero out on disconnect.

## ⚠️ One BLE client at a time

A Begode wheel accepts a single BLE connection. While HA holds it, the
Begode app / EUC World / WheelLog **cannot connect** (and vice versa). Turn
the wheel's "Maintain connection" switch off to release it before a ride,
or automate it.

## Deploying

```bash
tar cz -C custom_components begode | ssh <user>@<ha-host> "sudo tar xz -C /config/custom_components/"
# restart HA, then add via Settings → Devices & Services → Add → Begode EUC
```

## License

**GPL-3.0** (see LICENSE). `protocol.py` is a port of WheelLog's
`GotwayAdapter` ([Wheellog/Wheellog.Android](https://github.com/Wheellog/Wheellog.Android),
GPL-3.0) — this project inherits that license as a derivative work.
Credit and thanks to the WheelLog contributors for the protocol
reverse-engineering.

## Tests

```bash
python3 -m pytest tests/
```

Protocol decoding is covered by unit tests using WheelLog's documented
sample frames; no HA install needed.
