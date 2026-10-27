"""Diagnostics support for HAVRV."""

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant

from . import HavrvConfigEntry
from .const import (
    CONF_BLACK_WATER_TANK_CAPACITY,
    CONF_CHASSIS_BATTERY_BANK_COUNT,
    CONF_COACH_BUILDER,
    CONF_COACH_IDENTIFIER,
    CONF_COACH_YEAR,
    CONF_ENTITY_MAPPINGS,
    CONF_FRESH_WATER_TANK_CAPACITY,
    CONF_FUEL_TANK_CAPACITY,
    CONF_GRAY_WATER_TANK_CAPACITY,
    CONF_HOUSE_BATTERY_BANK_COUNT,
    CONF_MAIN_REAR_WHEEL_CONFIGURATION,
    CONF_MAKE,
    CONF_MANUFACTURER,
    CONF_MEASUREMENT_SYSTEM,
    CONF_MODEL,
    CONF_OPERATIONS_SOURCES,
    CONF_OVERALL_HEIGHT,
    CONF_OVERALL_LENGTH,
    CONF_OVERALL_WIDTH,
    CONF_POWER_SOURCES,
    CONF_REAR_AXLE_COUNT,
    CONF_STORAGE_ZONE_ID,
    CONF_TAG_AXLE_PRESENT,
    CONF_TAG_AXLE_WHEEL_CONFIGURATION,
    CONF_TIRE_BATTERY_LOW,
    CONF_TIRE_ENTITY_MAPPINGS,
    CONF_TIRE_PRESSURE_THRESHOLDS,
    CONF_TIRE_TEMPERATURE_HIGH,
)

TO_REDACT = {
    CONF_OPERATIONS_SOURCES,
    CONF_HOUSE_BATTERY_BANK_COUNT,
    CONF_CHASSIS_BATTERY_BANK_COUNT,
    CONF_POWER_SOURCES,
    CONF_NAME,
    CONF_COACH_YEAR,
    CONF_MANUFACTURER,
    CONF_COACH_BUILDER,
    CONF_MAKE,
    CONF_MODEL,
    CONF_COACH_IDENTIFIER,
    CONF_STORAGE_ZONE_ID,
    CONF_MEASUREMENT_SYSTEM,
    CONF_OVERALL_HEIGHT,
    CONF_OVERALL_LENGTH,
    CONF_OVERALL_WIDTH,
    CONF_FUEL_TANK_CAPACITY,
    CONF_FRESH_WATER_TANK_CAPACITY,
    CONF_GRAY_WATER_TANK_CAPACITY,
    CONF_BLACK_WATER_TANK_CAPACITY,
    CONF_REAR_AXLE_COUNT,
    CONF_MAIN_REAR_WHEEL_CONFIGURATION,
    CONF_TAG_AXLE_PRESENT,
    CONF_TAG_AXLE_WHEEL_CONFIGURATION,
    CONF_ENTITY_MAPPINGS,
    CONF_TIRE_ENTITY_MAPPINGS,
    CONF_TIRE_PRESSURE_THRESHOLDS,
    CONF_TIRE_TEMPERATURE_HIGH,
    CONF_TIRE_BATTERY_LOW,
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: HavrvConfigEntry
) -> dict[str, Any]:
    """Return redacted profile configuration and active platform names."""
    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "entry_options": async_redact_data(dict(entry.options), TO_REDACT),
        "platforms": [platform.value for platform in entry.runtime_data.platforms],
    }
