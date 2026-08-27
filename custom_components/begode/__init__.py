"""Begode EUC BLE integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant

from .const import CONF_VOLTAGE, DEFAULT_VOLTAGE
from .coordinator import BegodeConfigEntry, BegodeCoordinator
from .protocol import VOLTAGE_SCALES

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR, Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: BegodeConfigEntry) -> bool:
    address = entry.data[CONF_ADDRESS]
    voltage = entry.data.get(CONF_VOLTAGE, DEFAULT_VOLTAGE)
    scale = VOLTAGE_SCALES.get(voltage, 1.0)

    coordinator = BegodeCoordinator(hass, entry, address, scale)
    entry.runtime_data = coordinator
    await coordinator.async_start()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BegodeConfigEntry) -> bool:
    await entry.runtime_data.async_stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
