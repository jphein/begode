"""Config flow for the Begode EUC integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import CONF_VOLTAGE, DEFAULT_VOLTAGE, DOMAIN
from .protocol import SERVICE_UUID, VOLTAGE_SCALES

VOLTAGE_SELECTOR = SelectSelector(
    SelectSelectorConfig(
        options=[f"{v}" for v in VOLTAGE_SCALES],
        mode=SelectSelectorMode.DROPDOWN,
    )
)


class BegodeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Begode EUC."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovery_info: BluetoothServiceInfoBleak | None = None

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle bluetooth discovery (only fires for name-matched wheels)."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovery_info = discovery_info
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._discovery_info is not None
        if user_input is not None:
            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data={
                    CONF_ADDRESS: self._discovery_info.address,
                    CONF_VOLTAGE: user_input[CONF_VOLTAGE],
                },
            )
        name = self._discovery_info.name or self._discovery_info.address
        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=name): str,
                    vol.Required(CONF_VOLTAGE, default=DEFAULT_VOLTAGE): VOLTAGE_SELECTOR,
                }
            ),
            description_placeholders={"address": self._discovery_info.address},
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manual setup: pick a connectable device advertising the UART service."""
        errors: dict[str, str] = {}
        current = self._async_current_ids(include_ignore=False)
        candidates: dict[str, str] = {}
        for info in bluetooth.async_discovered_service_info(self.hass, connectable=True):
            if info.address in current:
                continue
            if SERVICE_UUID in info.service_uuids:
                label = f"{info.name} ({info.address})" if info.name != info.address else info.address
                candidates[info.address] = label

        if user_input is not None:
            address = user_input[CONF_ADDRESS].strip().upper()
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data={
                    CONF_ADDRESS: address,
                    CONF_VOLTAGE: user_input[CONF_VOLTAGE],
                },
            )

        if not candidates:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(candidates),
                    vol.Required(CONF_NAME, default="Begode EUC"): str,
                    vol.Required(CONF_VOLTAGE, default=DEFAULT_VOLTAGE): VOLTAGE_SELECTOR,
                }
            ),
            errors=errors,
        )
