"""Binary sensors for Begode EUC."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import BegodeConfigEntry, BegodeCoordinator
from .entity import BegodeEntity

# Regen while riding also shows negative battery current; require standstill.
# -0.1 A: idle wheels report ~0.00..-0.02 A, charging reads -0.1..-0.5 A
# (the Mten Mini trickles as low as -0.12 A, which a -0.3 cutoff missed).
CHARGING_CURRENT_THRESHOLD = -0.1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BegodeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [BegodeConnectedSensor(coordinator), BegodeChargingSensor(coordinator)]
    )


class BegodeConnectedSensor(BegodeEntity, BinarySensorEntity):
    """Whether HA currently holds the wheel's BLE connection."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = None
    _attr_name = "Connected"

    def __init__(self, coordinator: BegodeCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_connected"

    @property
    def is_on(self) -> bool:
        return self.coordinator.connected

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"alerts": self.coordinator.state.alerts}


class BegodeChargingSensor(BegodeEntity, BinarySensorEntity):
    """Charging heuristic: negative battery current at standstill."""

    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING
    _attr_name = "Charging"

    def __init__(self, coordinator: BegodeCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_charging"

    @property
    def is_on(self) -> bool | None:
        state = self.coordinator.state
        if not self.coordinator.connected or state.battery_current is None:
            return False
        return (
            state.battery_current < CHARGING_CURRENT_THRESHOLD
            and (state.speed or 0.0) < 1.0
        )
