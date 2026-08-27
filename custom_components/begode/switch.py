"""Connection-control switch for Begode EUC.

A Begode wheel accepts a single BLE client. Turn this switch OFF to release
the wheel so the phone app can connect (e.g. before a ride).
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_OFF, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .coordinator import BegodeConfigEntry, BegodeCoordinator
from .entity import BegodeEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BegodeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([BegodeConnectionSwitch(entry.runtime_data)])


class BegodeConnectionSwitch(BegodeEntity, SwitchEntity, RestoreEntity):
    """Allow/forbid HA holding the wheel's BLE connection."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_name = "Maintain connection"
    _attr_icon = "mdi:bluetooth-connect"

    def __init__(self, coordinator: BegodeCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_maintain_connection"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state == STATE_OFF:
            self.coordinator.set_enabled(False)
            self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        return self.coordinator.enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.coordinator.set_enabled(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.coordinator.set_enabled(False)
        self.async_write_ha_state()
