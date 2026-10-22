"""Restorable runtime controls for the always-present Tow device."""

import math
from typing import TYPE_CHECKING

from homeassistant.components.number import NumberDeviceClass, NumberMode, RestoreNumber
from homeassistant.components.select import SelectEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_ON, UnitOfMass
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util.unit_conversion import MassConverter

from .const import DOMAIN, UNIT_SYSTEM_METRIC

if TYPE_CHECKING:
    from . import HavrvConfigEntry

TOW_TYPES = ("car", "trailer")


def tow_device_info(entry: HavrvConfigEntry) -> DeviceInfo:
    """Return a stable child device independent of profile configuration."""
    parent_device_id = entry.runtime_data.device_id
    if parent_device_id is None:
        raise RuntimeError("RV device must be registered before platform setup")
    return {
        "identifiers": {(DOMAIN, f"{entry.entry_id}_tow")},
        "name": "Tow",
        "via_device_id": parent_device_id,
    }


class HavrvTowingSwitch(SwitchEntity, RestoreEntity):
    """Record whether the user is currently towing, without controlling hardware."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "towing"
    _attr_is_on = False

    def __init__(self, entry: HavrvConfigEntry) -> None:
        """Initialize the runtime switch."""
        self._attr_unique_id = f"{entry.entry_id}_tow_towing"
        self._attr_device_info = tow_device_info(entry)

    async def async_added_to_hass(self) -> None:
        """Restore towing status, defaulting to off for a new profile."""
        await super().async_added_to_hass()
        if (state := await self.async_get_last_state()) is not None:
            self._attr_is_on = state.state == STATE_ON

    async def async_turn_on(self, **kwargs: object) -> None:
        """Record that the RV is towing."""
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: object) -> None:
        """Record that the RV is not towing."""
        self._attr_is_on = False
        self.async_write_ha_state()


class HavrvTowTypeSelect(SelectEntity, RestoreEntity):
    """Choose the type of towed vehicle at runtime."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "tow_type"
    _attr_options = list(TOW_TYPES)
    _attr_current_option = "car"

    def __init__(self, entry: HavrvConfigEntry) -> None:
        """Initialize the type selector."""
        self._attr_unique_id = f"{entry.entry_id}_tow_type"
        self._attr_device_info = tow_device_info(entry)

    async def async_added_to_hass(self) -> None:
        """Restore the last supported type."""
        await super().async_added_to_hass()
        if (
            state := await self.async_get_last_state()
        ) is not None and state.state in TOW_TYPES:
            self._attr_current_option = state.state

    async def async_select_option(self, option: str) -> None:
        """Record the selected tow type."""
        if option not in TOW_TYPES:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="invalid_tow_type"
            )
        self._attr_current_option = option
        self.async_write_ha_state()


class HavrvTowWeightNumber(RestoreNumber):
    """Record tow weight independently of configuration and towing status."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "tow_weight"
    _attr_device_class = NumberDeviceClass.WEIGHT
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = 1e100
    _attr_native_step = 0.1

    def __init__(self, entry: HavrvConfigEntry) -> None:
        """Initialize a weight in the profile's units without guessing a load."""
        self._attr_unique_id = f"{entry.entry_id}_tow_weight"
        self._attr_device_info = tow_device_info(entry)
        self._attr_native_unit_of_measurement = (
            UnitOfMass.KILOGRAMS
            if entry.runtime_data.measurement_system == UNIT_SYSTEM_METRIC
            else UnitOfMass.POUNDS
        )

    async def async_added_to_hass(self) -> None:
        """Restore native weight, converting when the profile's units change."""
        await super().async_added_to_hass()
        data = await self.async_get_last_number_data()
        if (
            data is not None
            and data.native_value is not None
            and data.native_unit_of_measurement in MassConverter.VALID_UNITS
            and math.isfinite(data.native_value)
            and data.native_value >= 0
        ):
            value = MassConverter.convert(
                data.native_value,
                data.native_unit_of_measurement,
                self.native_unit_of_measurement,
            )
            if math.isfinite(value) and value <= self.native_max_value:
                self._attr_native_value = value

    async def async_set_native_value(self, value: float) -> None:
        """Record a finite non-negative weight without reloading the profile."""
        if not math.isfinite(value) or not 0 <= value <= self.native_max_value:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="invalid_tow_weight"
            )
        self._attr_native_value = value
        self.async_write_ha_state()
