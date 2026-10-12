"""Editable RV specifications and monitoring limits."""

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import Entity

from . import HavrvConfigEntry, _entry_entity_mappings
from .config_flow import _normalize_options
from .const import (
    CONF_BLACK_WATER_TANK_CAPACITY,
    CONF_FRESH_WATER_TANK_CAPACITY,
    CONF_FUEL_TANK_CAPACITY,
    CONF_GRAY_WATER_TANK_CAPACITY,
    CONF_OVERALL_HEIGHT,
    CONF_OVERALL_LENGTH,
    CONF_OVERALL_WIDTH,
    CONF_TANK_THRESHOLDS,
    CONF_TIRE_BATTERY_LOW,
    CONF_TIRE_PRESSURE_THRESHOLDS,
    CONF_TIRE_TEMPERATURE_HIGH,
    DEFAULT_TANK_THRESHOLDS,
    DEFAULT_TIRE_BATTERY_LOW,
    DEFAULT_TIRE_PRESSURE,
    DEFAULT_TIRE_TEMPERATURE_HIGH,
    DOMAIN,
    TANK_PROBLEM,
    TANK_TYPES,
    TANK_WARNING,
    TIRE_AXLE,
    TIRE_FRONT,
    TIRE_PRESSURE_HIGH,
    TIRE_PRESSURE_LOW,
    TIRE_TAG,
    UNIT_SYSTEM_METRIC,
)
from .tire import tire_positions

PARALLEL_UPDATES = 0

PROFILE_NUMBER_KEYS = (
    CONF_OVERALL_HEIGHT,
    CONF_OVERALL_LENGTH,
    CONF_OVERALL_WIDTH,
    CONF_FUEL_TANK_CAPACITY,
    CONF_FRESH_WATER_TANK_CAPACITY,
    CONF_GRAY_WATER_TANK_CAPACITY,
    CONF_BLACK_WATER_TANK_CAPACITY,
)


@dataclass(frozen=True, kw_only=True)
class HavrvNumberDescription(NumberEntityDescription):
    """Describe a numeric setting's location in the saved configuration."""

    path: tuple[str, ...]
    profile: bool = False
    default: float | None = None
    suggested_default: float | None = None


def _descriptions(entry: HavrvConfigEntry) -> list[HavrvNumberDescription]:
    """Create controls for quantities and supported monitoring limits."""
    metric = entry.runtime_data.measurement_system == UNIT_SYSTEM_METRIC
    descriptions = [
        HavrvNumberDescription(
            key=key,
            translation_key=key,
            path=(key,),
            profile=True,
            device_class=(
                NumberDeviceClass.DISTANCE
                if key in PROFILE_NUMBER_KEYS[:3]
                else NumberDeviceClass.VOLUME_STORAGE
            ),
            native_unit_of_measurement=(
                ("m" if metric else "ft")
                if key in PROFILE_NUMBER_KEYS[:3]
                else ("L" if metric else "gal")
            ),
        )
        for key in PROFILE_NUMBER_KEYS
    ]
    for tank in TANK_TYPES:
        for index, level in enumerate((TANK_WARNING, TANK_PROBLEM)):
            descriptions.append(
                HavrvNumberDescription(
                    key=f"{tank}_tank_{level}",
                    translation_key=f"{tank}_tank_{level}",
                    path=(CONF_TANK_THRESHOLDS, tank, level),
                    default=DEFAULT_TANK_THRESHOLDS[tank][index],
                    native_max_value=100,
                    native_step=1,
                    native_unit_of_measurement="%",
                )
            )

    groups = {position.group for position in tire_positions(entry.data)}
    for group in (TIRE_FRONT, TIRE_AXLE, TIRE_TAG):
        if group not in groups:
            continue
        for index, limit in enumerate((TIRE_PRESSURE_LOW, TIRE_PRESSURE_HIGH)):
            descriptions.append(
                HavrvNumberDescription(
                    key=f"tire_{group}_pressure_{limit}",
                    translation_key=f"tire_{group}_pressure_{limit}",
                    path=(CONF_TIRE_PRESSURE_THRESHOLDS, group, limit),
                    suggested_default=DEFAULT_TIRE_PRESSURE[
                        entry.runtime_data.measurement_system
                    ][index],
                    device_class=NumberDeviceClass.PRESSURE,
                    native_unit_of_measurement="kPa" if metric else "psi",
                )
            )
    if groups:
        descriptions.extend(
            (
                HavrvNumberDescription(
                    key=CONF_TIRE_TEMPERATURE_HIGH,
                    translation_key=CONF_TIRE_TEMPERATURE_HIGH,
                    path=(CONF_TIRE_TEMPERATURE_HIGH,),
                    suggested_default=DEFAULT_TIRE_TEMPERATURE_HIGH[
                        entry.runtime_data.measurement_system
                    ],
                    device_class=NumberDeviceClass.TEMPERATURE,
                    native_unit_of_measurement="°C" if metric else "°F",
                ),
                HavrvNumberDescription(
                    key=CONF_TIRE_BATTERY_LOW,
                    translation_key=CONF_TIRE_BATTERY_LOW,
                    path=(CONF_TIRE_BATTERY_LOW,),
                    default=DEFAULT_TIRE_BATTERY_LOW,
                    device_class=NumberDeviceClass.BATTERY,
                    native_max_value=100,
                    native_step=1,
                    native_unit_of_measurement="%",
                ),
            )
        )
    return descriptions


def _setting_value(
    entry: HavrvConfigEntry, description: HavrvNumberDescription
) -> float | None:
    """Read a saved setting or its effective runtime default."""
    value: Any = entry.data if description.profile else entry.options
    for key in description.path:
        value = value.get(key) if isinstance(value, Mapping) else None
    return description.default if value is None else float(value)


class HavrvConfigurationNumber(NumberEntity):
    """Persist an editable numeric setting on the main RV device."""

    entity_description: HavrvNumberDescription
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    # Leave headroom for HA's unit-conversion and capability rounding.
    _attr_native_max_value = 1e100
    _attr_native_step = 0.1

    def __init__(
        self, entry: HavrvConfigEntry, description: HavrvNumberDescription
    ) -> None:
        """Initialize a configuration control with a stable identity."""
        self._entry = entry
        self.entity_description = description
        prefix = "profile" if description.profile else "configuration"
        self._attr_unique_id = f"{entry.entry_id}_{prefix}_{description.key}"
        self._attr_device_info = {"identifiers": {(DOMAIN, entry.entry_id)}}
        if description.native_max_value is not None:
            self._attr_native_max_value = description.native_max_value
        if description.native_step is not None:
            self._attr_native_step = description.native_step

    async def async_added_to_hass(self) -> None:
        """Default temperature display to profile units, retaining user overrides."""
        await super().async_added_to_hass()
        if self.device_class != NumberDeviceClass.TEMPERATURE:
            return
        assert self.registry_entry is not None
        options: Mapping[str, Any] = self.registry_entry.options.get("number", {})
        current_unit = options.get("unit_of_measurement")
        if current_unit is None or current_unit == options.get("havrv_profile_unit"):
            unit = self.native_unit_of_measurement
            er.async_get(self.hass).async_update_entity_options(
                self.entity_id,
                "number",
                {
                    **options,
                    "unit_of_measurement": unit,
                    "havrv_profile_unit": unit,
                },
            )
            self.async_registry_entry_updated()

    @property
    def native_value(self) -> float | None:
        """Read the saved value without inventing unknown specifications."""
        return _setting_value(self._entry, self.entity_description)

    @property
    def extra_state_attributes(self) -> dict[str, float] | None:
        """Distinguish a form suggestion from an active, saved tire limit."""
        default = self.entity_description.suggested_default
        if self.native_value is None and default is not None:
            return {"suggested_default": default}
        return None

    async def async_set_native_value(self, value: float) -> None:
        """Validate and save a setting, retaining all unrelated configuration."""
        description = self.entity_description
        error: str | None = None
        if not math.isfinite(value):
            error = "invalid_numeric_setting"
        elif description.profile:
            if value <= 0:
                error = "invalid_measurement"
            else:
                self.hass.config_entries.async_update_entry(
                    self._entry, data={**self._entry.data, description.key: value}
                )
        else:
            submitted: dict[str, Any] = {
                f"{category}_entities": entities
                for category, entities in _entry_entity_mappings(self._entry).items()
            }
            for setting in _descriptions(self._entry):
                if setting.profile:
                    continue
                current = _setting_value(self._entry, setting)
                if current is not None:
                    submitted[setting.key] = current
                elif setting.path[0] == CONF_TIRE_PRESSURE_THRESHOLDS and (
                    description.path[:2] == setting.path[:2]
                ):
                    submitted[setting.key] = setting.suggested_default
            submitted[description.key] = value
            options, error = _normalize_options(submitted, self._entry)
            if error is None:
                self.hass.config_entries.async_update_entry(
                    self._entry, options={**self._entry.options, **options}
                )
        if error is not None:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key=error
            )
        self.async_write_ha_state()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HavrvConfigEntry,
    async_add_entities: Callable[[list[Entity]], None],
) -> None:
    """Expose numeric configuration on the RV device."""
    async_add_entities(
        [
            HavrvConfigurationNumber(entry, description)
            for description in _descriptions(entry)
        ]
    )
