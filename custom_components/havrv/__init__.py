"""Set up the HAVRV integration."""

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM

from .const import (
    CONF_BLACK_WATER_TANK_CAPACITY,
    CONF_COACH_BUILDER,
    CONF_COACH_IDENTIFIER,
    CONF_COACH_YEAR,
    CONF_FRESH_WATER_TANK_CAPACITY,
    CONF_FUEL_TANK_CAPACITY,
    CONF_GRAY_WATER_TANK_CAPACITY,
    CONF_MAIN_REAR_WHEEL_CONFIGURATION,
    CONF_MAKE,
    CONF_MANUFACTURER,
    CONF_MEASUREMENT_SYSTEM,
    CONF_MODEL,
    CONF_OVERALL_HEIGHT,
    CONF_OVERALL_LENGTH,
    CONF_OVERALL_WIDTH,
    CONF_REAR_AXLE_COUNT,
    CONF_STORAGE_ZONE_ID,
    CONF_TAG_AXLE_PRESENT,
    CONF_TAG_AXLE_WHEEL_CONFIGURATION,
    UNIT_SYSTEM_METRIC,
    UNIT_SYSTEM_US_CUSTOMARY,
)


@dataclass
class HavrvRuntimeData:
    """Runtime data for an RV profile."""

    name: str
    coach_year: int | None = None
    manufacturer: str | None = None
    coach_builder: str | None = None
    make: str | None = None
    model: str | None = None
    coach_identifier: str | None = None
    storage_zone_id: str | None = None
    measurement_system: str = UNIT_SYSTEM_METRIC
    overall_height: float | None = None
    overall_length: float | None = None
    overall_width: float | None = None
    fuel_tank_capacity: float | None = None
    fresh_water_tank_capacity: float | None = None
    gray_water_tank_capacity: float | None = None
    black_water_tank_capacity: float | None = None
    rear_axle_count: int | None = None
    main_rear_wheel_configuration: str | None = None
    tag_axle_present: bool = False
    tag_axle_wheel_configuration: str | None = None


type HavrvConfigEntry = ConfigEntry[HavrvRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: HavrvConfigEntry) -> bool:
    """Set up an RV profile from a config entry."""
    data = entry.data
    if hass.config.units == US_CUSTOMARY_SYSTEM:
        configured_measurement_system = UNIT_SYSTEM_US_CUSTOMARY
    else:
        configured_measurement_system = UNIT_SYSTEM_METRIC

    entry.runtime_data = HavrvRuntimeData(
        name=data[CONF_NAME],
        coach_year=data.get(CONF_COACH_YEAR),
        manufacturer=data.get(CONF_MANUFACTURER),
        coach_builder=data.get(CONF_COACH_BUILDER),
        make=data.get(CONF_MAKE),
        model=data.get(CONF_MODEL),
        coach_identifier=data.get(CONF_COACH_IDENTIFIER),
        storage_zone_id=data.get(CONF_STORAGE_ZONE_ID),
        measurement_system=data.get(
            CONF_MEASUREMENT_SYSTEM, configured_measurement_system
        ),
        overall_height=data.get(CONF_OVERALL_HEIGHT),
        overall_length=data.get(CONF_OVERALL_LENGTH),
        overall_width=data.get(CONF_OVERALL_WIDTH),
        fuel_tank_capacity=data.get(CONF_FUEL_TANK_CAPACITY),
        fresh_water_tank_capacity=data.get(CONF_FRESH_WATER_TANK_CAPACITY),
        gray_water_tank_capacity=data.get(CONF_GRAY_WATER_TANK_CAPACITY),
        black_water_tank_capacity=data.get(CONF_BLACK_WATER_TANK_CAPACITY),
        rear_axle_count=data.get(CONF_REAR_AXLE_COUNT),
        main_rear_wheel_configuration=data.get(CONF_MAIN_REAR_WHEEL_CONFIGURATION),
        tag_axle_present=data.get(CONF_TAG_AXLE_PRESENT, False),
        tag_axle_wheel_configuration=data.get(CONF_TAG_AXLE_WHEEL_CONFIGURATION),
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HavrvConfigEntry) -> bool:
    """Unload an RV profile."""
    return True
