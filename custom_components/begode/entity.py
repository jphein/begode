"""Base entity for Begode EUC."""
from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BegodeCoordinator


class BegodeEntity(CoordinatorEntity[BegodeCoordinator]):
    """Entity tied to one wheel's coordinator."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: BegodeCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            connections={(CONNECTION_BLUETOOTH, coordinator.address)},
            name=coordinator.config_entry.title,
            manufacturer="Begode",
            model=coordinator.state.model,
            sw_version=coordinator.state.firmware,
        )
