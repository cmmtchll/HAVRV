"""Tests for the HAVRV config flow."""

from datetime import date

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
from pytest_homeassistant_custom_component.common import MockConfigEntry

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


async def _init_user_flow(hass: HomeAssistant) -> dict:
    """Initialize the user config flow."""
    return await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )


def _default_measurement_system(hass: HomeAssistant) -> str:
    """Return the unit system used by Home Assistant."""
    if hass.config.units == US_CUSTOMARY_SYSTEM:
        return UNIT_SYSTEM_US_CUSTOMARY
    return UNIT_SYSTEM_METRIC


async def test_user_flow_creates_profile_with_optional_fields_blank(
    hass: HomeAssistant,
) -> None:
    """Only the RV profile name is required."""
    form = await _init_user_flow(hass)
    assert form["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        form["flow_id"], user_input={CONF_NAME: "Adventure RV"}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Adventure RV"
    assert result["data"] == {
        CONF_NAME: "Adventure RV",
        CONF_MEASUREMENT_SYSTEM: _default_measurement_system(hass),
        CONF_TAG_AXLE_PRESENT: False,
    }
    assert result["result"].unique_id == "adventure rv"


async def test_user_flow_defaults_to_home_assistant_us_customary_units(
    hass: HomeAssistant,
) -> None:
    """Default the profile units to Home Assistant's US customary setting."""
    hass.config.units = US_CUSTOMARY_SYSTEM
    form = await _init_user_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        form["flow_id"], user_input={CONF_NAME: "Adventure RV"}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_MEASUREMENT_SYSTEM] == UNIT_SYSTEM_US_CUSTOMARY


async def test_user_flow_stores_coach_profile_and_specifications(
    hass: HomeAssistant,
) -> None:
    """Store optional coach identity, zone, capacities, and axle settings."""
    form = await _init_user_flow(hass)
    input_data = {
        CONF_NAME: " Liberty ",
        CONF_COACH_YEAR: 2003,
        CONF_MANUFACTURER: " Prevost ",
        CONF_COACH_BUILDER: " Liberty ",
        CONF_MAKE: " H3-45 ",
        CONF_MODEL: " Elegant Lady ",
        CONF_COACH_IDENTIFIER: " 1234 ",
        CONF_MEASUREMENT_SYSTEM: UNIT_SYSTEM_US_CUSTOMARY,
        CONF_STORAGE_ZONE_ID: "zone.rv_storage",
        CONF_OVERALL_HEIGHT: 12.5,
        CONF_OVERALL_LENGTH: 45,
        CONF_OVERALL_WIDTH: 8.5,
        CONF_FUEL_TANK_CAPACITY: 250,
        CONF_FRESH_WATER_TANK_CAPACITY: 160,
        CONF_GRAY_WATER_TANK_CAPACITY: 100,
        CONF_BLACK_WATER_TANK_CAPACITY: 80,
        CONF_REAR_AXLE_COUNT: "two",
        CONF_MAIN_REAR_WHEEL_CONFIGURATION: "dual",
        CONF_TAG_AXLE_PRESENT: True,
        CONF_TAG_AXLE_WHEEL_CONFIGURATION: "single",
    }

    result = await hass.config_entries.flow.async_configure(
        form["flow_id"], user_input=input_data
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Liberty"
    assert result["data"] == {
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
    }


async def test_user_flow_rejects_duplicate_name(hass: HomeAssistant) -> None:
    """Reject duplicate RV profile names."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Adventure RV",
        data={CONF_NAME: "Adventure RV"},
        unique_id="adventure rv",
    )
    entry.add_to_hass(hass)

    form = await _init_user_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        form["flow_id"], user_input={CONF_NAME: "Adventure RV"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_flow_rejects_whitespace_name(hass: HomeAssistant) -> None:
    """Reject whitespace-only RV profile names."""
    form = await _init_user_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        form["flow_id"], user_input={CONF_NAME: "   "}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "name_required"}


async def test_user_flow_rejects_invalid_coach_year(hass: HomeAssistant) -> None:
    """Reject years outside the supported range."""
    form = await _init_user_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        form["flow_id"],
        user_input={CONF_NAME: "Adventure RV", CONF_COACH_YEAR: date.today().year + 2},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_coach_year"}


async def test_user_flow_rejects_non_positive_measurement(
    hass: HomeAssistant,
) -> None:
    """Reject dimensions and tank capacities that are not positive."""
    form = await _init_user_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        form["flow_id"],
        user_input={CONF_NAME: "Adventure RV", CONF_FUEL_TANK_CAPACITY: 0},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_measurement"}


async def test_user_flow_requires_tag_wheel_configuration(
    hass: HomeAssistant,
) -> None:
    """Require a wheel layout when the profile has a tag axle."""
    form = await _init_user_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        form["flow_id"],
        user_input={CONF_NAME: "Adventure RV", CONF_TAG_AXLE_PRESENT: True},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "tag_axle_wheel_configuration_required"}


async def test_user_flow_rejects_tag_wheels_when_no_tag_axle(
    hass: HomeAssistant,
) -> None:
    """Reject a tag axle wheel layout when no tag axle is selected."""
    form = await _init_user_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        form["flow_id"],
        user_input={
            CONF_NAME: "Adventure RV",
            CONF_TAG_AXLE_PRESENT: False,
            CONF_TAG_AXLE_WHEEL_CONFIGURATION: "dual",
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "tag_wheel_configuration_without_tag_axle"}


async def test_user_flow_accepts_tag_axle_with_wheel_configuration(
    hass: HomeAssistant,
) -> None:
    """Accept a tag axle when its wheel configuration is provided."""
    form = await _init_user_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        form["flow_id"],
        user_input={
            CONF_NAME: "Adventure RV",
            CONF_TAG_AXLE_PRESENT: True,
            CONF_TAG_AXLE_WHEEL_CONFIGURATION: "dual",
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_TAG_AXLE_PRESENT] is True
    assert result["data"][CONF_TAG_AXLE_WHEEL_CONFIGURATION] == "dual"
