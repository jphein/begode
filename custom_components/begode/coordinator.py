"""BLE connection coordinator for Begode EUCs.

Maintains an active GATT connection to the wheel (routed through ESPHome
bluetooth proxies by HA's bluetooth stack), feeds the notification stream
into the protocol decoder, and pushes throttled state updates.

A Begode wheel accepts only ONE BLE client at a time — while this
coordinator is connected, the phone app cannot connect. The `enabled` flag
(exposed as a switch entity) releases the wheel for app use.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    BleakError,
    establish_connection,
)

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth.match import BluetoothCallbackMatcher
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, PUSH_INTERVAL
from .protocol import CHAR_UUID, BegodeDecoder, WheelState

_LOGGER = logging.getLogger(__name__)

RECONNECT_DELAY = 10.0

type BegodeConfigEntry = ConfigEntry[BegodeCoordinator]


class BegodeCoordinator(DataUpdateCoordinator[WheelState]):
    """Push-based coordinator holding the wheel's BLE connection."""

    config_entry: BegodeConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: BegodeConfigEntry,
        address: str,
        voltage_scale: float,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{address}",
            update_interval=None,
        )
        self.address = address
        self.decoder = BegodeDecoder(voltage_scale)
        self.enabled = True
        self.connected = False
        self._client: BleakClient | None = None
        self._connect_lock = asyncio.Lock()
        self._last_push = 0.0
        self._flush_handle: asyncio.TimerHandle | None = None
        self._reconnect_handle: asyncio.TimerHandle | None = None
        self._identify_task: asyncio.Task | None = None
        self._stopped = False
        self._unsub_bluetooth: Callable[[], None] | None = None
        # Battery-rise tracking: charging detection can't rely on the current
        # sign alone (the Mten Mini's reported current fluctuates around zero
        # while charging).
        self.last_charge_rise: float = 0.0
        self._last_battery: int | None = None
        self.async_set_updated_data(self.decoder.state)

    @property
    def state(self) -> WheelState:
        return self.decoder.state

    async def async_start(self) -> None:
        """Register for advertisements and try an initial connection."""
        self._unsub_bluetooth = bluetooth.async_register_callback(
            self.hass,
            self._advertisement_seen,
            BluetoothCallbackMatcher(address=self.address, connectable=True),
            bluetooth.BluetoothScanningMode.ACTIVE,
        )
        self.config_entry.async_on_unload(self._unsub_bluetooth)
        if bluetooth.async_ble_device_from_address(self.hass, self.address, True):
            self.config_entry.async_create_background_task(
                self.hass, self._connect(), f"begode_connect_{self.address}"
            )

    async def async_stop(self) -> None:
        self._stopped = True
        self._cancel_timers()
        await self._disconnect()

    def set_enabled(self, enabled: bool) -> None:
        """Switch entity hook: allow/forbid holding the BLE connection."""
        self.enabled = enabled
        if not enabled:
            self.config_entry.async_create_background_task(
                self.hass, self._disconnect(), f"begode_disconnect_{self.address}"
            )
        elif bluetooth.async_ble_device_from_address(self.hass, self.address, True):
            self.config_entry.async_create_background_task(
                self.hass, self._connect(), f"begode_connect_{self.address}"
            )
        self._push(force=True)

    @callback
    def _advertisement_seen(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        if self.enabled and not self.connected and not self._connect_lock.locked():
            self.config_entry.async_create_background_task(
                self.hass, self._connect(), f"begode_connect_{self.address}"
            )

    async def _connect(self) -> None:
        if self._stopped or not self.enabled or self.connected:
            return
        async with self._connect_lock:
            if self._stopped or not self.enabled or self.connected:
                return
            ble_device = bluetooth.async_ble_device_from_address(
                self.hass, self.address, True
            )
            if ble_device is None:
                return
            _LOGGER.debug("Connecting to %s", self.address)
            try:
                client = await establish_connection(
                    BleakClientWithServiceCache,
                    ble_device,
                    self.address,
                    self._disconnected_callback,
                )
                await client.start_notify(CHAR_UUID, self._notification_handler)
            except (BleakError, TimeoutError) as err:
                _LOGGER.debug("Connection to %s failed: %s", self.address, err)
                self._schedule_reconnect()
                return
            self._client = client
            self.connected = True
            _LOGGER.info("Connected to Begode wheel %s", self.address)
            self._push(force=True)
            if self.state.model is None or self.state.firmware is None:
                self._identify_task = self.config_entry.async_create_background_task(
                    self.hass, self._request_identity(), f"begode_ident_{self.address}"
                )

    async def _request_identity(self) -> None:
        """Ask the wheel for firmware ("V") and model name ("N")."""
        for _ in range(5):
            if not self.connected or self._client is None:
                return
            try:
                if self.state.firmware is None:
                    await self._client.write_gatt_char(CHAR_UUID, b"V", response=False)
                    await asyncio.sleep(0.3)
                if self.state.model is None:
                    await self._client.write_gatt_char(CHAR_UUID, b"N", response=False)
            except (BleakError, TimeoutError):
                return
            await asyncio.sleep(1.0)
            if self.state.model is not None and self.state.firmware is not None:
                break
        if self.state.model or self.state.firmware:
            self._update_device_registry()
            self._push(force=True)

    def _update_device_registry(self) -> None:
        registry = dr.async_get(self.hass)
        device = registry.async_get_device(identifiers={(DOMAIN, self.address)})
        if device:
            registry.async_update_device(
                device.id,
                model=self.state.model or device.model,
                sw_version=self.state.firmware or device.sw_version,
            )

    def _notification_handler(
        self, _char: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        if self.decoder.handle_notification(bytes(data)):
            self._push()

    def _push(self, force: bool = False) -> None:
        now = self.hass.loop.time()
        st = self.decoder.state
        if (
            st.battery is not None
            and self._last_battery is not None
            and st.battery > self._last_battery
            and (st.speed or 0.0) < 1.0
        ):
            self.last_charge_rise = now
        if st.battery is not None:
            self._last_battery = st.battery
        if not force and now - self._last_push < PUSH_INTERVAL:
            if self._flush_handle is None:
                self._flush_handle = self.hass.loop.call_later(
                    PUSH_INTERVAL - (now - self._last_push), self._flush
                )
            return
        self._last_push = now
        if self._flush_handle:
            self._flush_handle.cancel()
            self._flush_handle = None
        self.async_set_updated_data(self.decoder.state)

    def _flush(self) -> None:
        self._flush_handle = None
        self._last_push = self.hass.loop.time()
        self.async_set_updated_data(self.decoder.state)

    def _disconnected_callback(self, _client: BleakClient) -> None:
        """Called by bleak when the wheel drops the connection (e.g. power off)."""
        self.connected = False
        self._client = None
        _LOGGER.info("Begode wheel %s disconnected", self.address)
        self.state.zero_live()
        if not self._stopped:
            self.hass.loop.call_soon_threadsafe(self._handle_disconnect)

    def _handle_disconnect(self) -> None:
        self._push(force=True)
        self._schedule_reconnect()

    def _schedule_reconnect(self) -> None:
        if self._stopped or not self.enabled:
            return
        if self._reconnect_handle:
            self._reconnect_handle.cancel()
        self._reconnect_handle = self.hass.loop.call_later(
            RECONNECT_DELAY, self._retry_connect
        )

    def _retry_connect(self) -> None:
        self._reconnect_handle = None
        if self.enabled and not self.connected and not self._stopped:
            self.config_entry.async_create_background_task(
                self.hass, self._connect(), f"begode_connect_{self.address}"
            )

    def _cancel_timers(self) -> None:
        if self._flush_handle:
            self._flush_handle.cancel()
            self._flush_handle = None
        if self._reconnect_handle:
            self._reconnect_handle.cancel()
            self._reconnect_handle = None

    async def _disconnect(self) -> None:
        client = self._client
        self._client = None
        self.connected = False
        if client is not None:
            try:
                await client.disconnect()
            except (BleakError, TimeoutError):
                pass
