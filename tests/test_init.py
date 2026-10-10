"""Tests for HAVRV config-entry setup."""

from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.havrv import HavrvRuntimeData
from custom_components.havrv.const import (
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
    DOMAIN,
    UNIT_SYSTEM_METRIC,
    UNIT_SYSTEM_US_CUSTOMARY,
)


async def test_setup_and_unload_legacy_name_only_entry(hass: HomeAssistant) -> None:
    """An existing name-only RV entry remains set-up and unloadable."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Adventure RV",
        data={CONF_NAME: "Adventure RV"},
        unique_id="adventure rv",
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    assert entry.runtime_data == HavrvRuntimeData(
        name="Adventure RV",
        measurement_system=(
            UNIT_SYSTEM_US_CUSTOMARY
            if hass.config.units == US_CUSTOMARY_SYSTEM
            else UNIT_SYSTEM_METRIC
        ),
    )

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_setup_uses_home_assistant_units_for_legacy_entry(
    hass: HomeAssistant,
) -> None:
    """Default legacy profile units to Home Assistant's unit system."""
    hass.config.units = US_CUSTOMARY_SYSTEM
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Adventure RV",
        data={CONF_NAME: "Adventure RV"},
        unique_id="adventure rv",
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    assert entry.runtime_data.measurement_system == UNIT_SYSTEM_US_CUSTOMARY


async def test_setup_populates_typed_runtime_profile(hass: HomeAssistant) -> None:
    """Expose saved RV profile values as typed runtime data."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Liberty",
        unique_id="liberty",
        data={
            CONF_NAME: "Liberty",
            CONF_COACH_YEAR: 2003,
            CONF_MANUFACTURER: "Prevost",
            CONF_COACH_BUILDER: "Liberty",
            CONF_MAKE: "H3-45",
            CONF_MODEL: "Elegant Lady",
            CONF_COACH_IDENTIFIER: "1234",
            CONF_MEASUREMENT_SYSTEM: UNIT_SYSTEM_US_CUSTOMARY,
            CONF_STORAGE_ZONE_ID: "zone.rv_storage",
            CONF_OVERALL_HEIGHT: 12.5,
            CONF_OVERALL_LENGTH: 45.0,
            CONF_OVERALL_WIDTH: 8.5,
            CONF_FUEL_TANK_CAPACITY: 250.0,
            CONF_FRESH_WATER_TANK_CAPACITY: 160.0,
            CONF_GRAY_WATER_TANK_CAPACITY: 100.0,
            CONF_BLACK_WATER_TANK_CAPACITY: 80.0,
            CONF_REAR_AXLE_COUNT: 2,
            CONF_MAIN_REAR_WHEEL_CONFIGURATION: "dual",
            CONF_TAG_AXLE_PRESENT: True,
            CONF_TAG_AXLE_WHEEL_CONFIGURATION: "single",
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    assert entry.runtime_data == HavrvRuntimeData(
        name="Liberty",
        coach_year=2003,
        manufacturer="Prevost",
        coach_builder="Liberty",
        make="H3-45",
        model="Elegant Lady",
        coach_identifier="1234",
        storage_zone_id="zone.rv_storage",
        measurement_system=UNIT_SYSTEM_US_CUSTOMARY,
        overall_height=12.5,
        overall_length=45.0,
        overall_width=8.5,
        fuel_tank_capacity=250.0,
        fresh_water_tank_capacity=160.0,
        gray_water_tank_capacity=100.0,
        black_water_tank_capacity=80.0,
        rear_axle_count=2,
        main_rear_wheel_configuration="dual",
        tag_axle_present=True,
        tag_axle_wheel_configuration="single",
    )
