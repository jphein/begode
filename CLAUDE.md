# CLAUDE.md — begode

Custom Home Assistant integration for JP's three Begode EUCs (Mten Mini,
Falcon, A2) over BLE via the ESPHome bluetooth proxies. See README.md for
protocol details and entity list.

## Key facts

- **Protocol**: WheelLog `GotwayAdapter` port — 24-byte frames `55 AA … 5A 5A 5A 5A`,
  byte 18 = frame type, big-endian, no checksums. Reference source saved
  during development; canonical upstream is `Wheellog/Wheellog.Android`.
- **BLE**: service `FFE0`, char `FFE1` (notify + write w/o response).
  Wheels advertise **no local name** — discovery by name won't fire; use the
  manual config flow (lists connectable FFE0 advertisers).
- **Wheel MAC↔model map**: in the session memory (`begode-euc-integration`),
  not in this public repo. Model is read from the wheel via the `N` command
  after connect, so the config flow doesn't need it.
- **Pack voltages**: Falcon = 100.8V (×1.5), A2 = 84V (×1.25),
  Mten Mini = 42V charger / 180Wh — non-standard, scaling determined
  empirically (see README voltage table).
- **One BLE client per wheel**: HA connection blocks the phone app. The
  per-wheel "Maintain connection" switch releases it.

## Workflow

- Edit under `custom_components/begode/`, run `python3 -m pytest tests/`
  (pure-Python protocol tests, no HA needed).
- Deploy: `tar cz -C custom_components begode | ssh <user>@<ha-host> "sudo tar xz -C /config/custom_components/"`
  (HA host details live in the `ha` skill), then restart HA — new Python
  requires a restart; see the `ha` skill for gotchas (HTTP 200 ≠ ready).
- Config entries: one per wheel; data = `address`, `voltage` (pack preset).
  Changing voltage = delete + re-add the entry (no options flow yet).
