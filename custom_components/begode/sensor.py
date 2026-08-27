"""Sensors for Begode EUC telemetry."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfLength,
    UnitOfPower,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import BegodeConfigEntry, BegodeCoordinator
from .entity import BegodeEntity
from .protocol import WheelState


@dataclass(frozen=True, kw_only=True)
class BegodeSensorDescription(SensorEntityDescription):
    """Describes a Begode sensor."""

    value_fn: Callable[[WheelState], float | int | str | None]
    restore: bool = False
    restore_fn: Callable[[WheelState, float | int | str], None] | None = None


def _seed(attr: str) -> Callable[[WheelState, float | int | str], None]:
    def seed(state: WheelState, value: float | int | str) -> None:
        if getattr(state, attr) is None:
            setattr(state, attr, value)

    return seed


SENSORS: tuple[BegodeSensorDescription, ...] = (
    BegodeSensorDescription(
        key="battery",
        name="Battery",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda s: s.battery,
        restore=True,
        restore_fn=_seed("battery"),
    ),
    BegodeSensorDescription(
        key="voltage",
        name="Voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=1,
        value_fn=lambda s: s.voltage,
        restore=True,
        restore_fn=_seed("voltage"),
    ),
    BegodeSensorDescription(
        key="speed",
        name="Speed",
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        suggested_display_precision=1,
        value_fn=lambda s: s.speed,
    ),
    BegodeSensorDescription(
        key="trip_distance",
        name="Trip distance",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        suggested_display_precision=2,
        value_fn=lambda s: s.trip_distance,
        restore=True,
        restore_fn=_seed("trip_distance"),
    ),
    BegodeSensorDescription(
        key="total_distance",
        name="Total distance",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        suggested_display_precision=1,
        value_fn=lambda s: s.total_distance,
        restore=True,
        restore_fn=_seed("total_distance"),
    ),
    BegodeSensorDescription(
        key="phase_current",
        name="Phase current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=1,
        value_fn=lambda s: s.phase_current,
    ),
    BegodeSensorDescription(
        key="battery_current",
        name="Battery current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=1,
        value_fn=lambda s: s.battery_current,
    ),
    BegodeSensorDescription(
        key="power",
        name="Power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda s: s.power,
    ),
    BegodeSensorDescription(
        key="temperature",
        name="Controller temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=lambda s: s.temperature,
        restore=True,
        restore_fn=_seed("temperature"),
    ),
    BegodeSensorDescription(
        key="motor_temperature",
        name="Motor temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=0,
        value_fn=lambda s: s.motor_temperature,
    ),
    BegodeSensorDescription(
        key="pwm",
        name="PWM",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        icon="mdi:sine-wave",
        value_fn=lambda s: s.pwm,
    ),
    BegodeSensorDescription(
        key="bms_voltage",
        name="BMS voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.bms_voltage,
        restore=True,
        restore_fn=_seed("bms_voltage"),
    ),
    BegodeSensorDescription(
        key="cell_min",
        name="Cell voltage min",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=3,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.cell_min,
    ),
    BegodeSensorDescription(
        key="cell_max",
        name="Cell voltage max",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=3,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.cell_max,
    ),
    BegodeSensorDescription(
        key="cell_diff",
        name="Cell voltage spread",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=3,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.cell_diff,
    ),
    BegodeSensorDescription(
        key="model",
        name="Model",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:unicycle",
        value_fn=lambda s: s.model,
        restore=True,
        restore_fn=_seed("model"),
    ),
    BegodeSensorDescription(
        key="firmware",
        name="Firmware",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:chip",
        value_fn=lambda s: s.firmware,
        restore=True,
        restore_fn=_seed("firmware"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BegodeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(BegodeSensor(coordinator, desc) for desc in SENSORS)


class BegodeSensor(BegodeEntity, RestoreSensor):
    """A telemetry sensor; sticky values survive HA restarts via restore."""

    entity_description: BegodeSensorDescription

    def __init__(
        self, coordinator: BegodeCoordinator, description: BegodeSensorDescription
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}_{description.key}"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if not self.entity_description.restore or self.entity_description.restore_fn is None:
            return
        if self.entity_description.value_fn(self.coordinator.state) is not None:
            return
        last = await self.async_get_last_sensor_data()
        if last is not None and last.native_value is not None:
            self.entity_description.restore_fn(
                self.coordinator.state, last.native_value
            )
            self.async_write_ha_state()

    @property
    def native_value(self) -> float | int | str | None:
        return self.entity_description.value_fn(self.coordinator.state)
