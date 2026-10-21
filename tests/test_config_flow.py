"""Tests for the HAVRV config flow."""

from datetime import date
from types import SimpleNamespace

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.havrv.config_flow import (
    HavrvConfigFlow,
    _normalize_entity_mappings,
    _normalize_options,
    _normalize_power_source,
    _normalize_profile,
    _options_schema,
    _power_source_schema,
)
from custom_components.havrv.config_flow import (
    _default_measurement_system as get_default_measurement_system,
)
from custom_components.havrv.const import (
    CONF_BLACK_WATER_TANK_CAPACITY,
    CONF_CHASSIS_BATTERY_BANK_COUNT,
    CONF_COACH_BUILDER,
    CONF_COACH_IDENTIFIER,
    CONF_COACH_YEAR,
    CONF_CONFIGURE_POWER_SOURCES,
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
    CONF_OVERALL_HEIGHT,
    CONF_OVERALL_LENGTH,
    CONF_OVERALL_WIDTH,
    CONF_POWER_SOURCES,
    CONF_REAR_AXLE_COUNT,
    CONF_STORAGE_ZONE_ID,
    CONF_TAG_AXLE_PRESENT,
    CONF_TAG_AXLE_WHEEL_CONFIGURATION,
    CONF_TANK_ENTITY_MAPPINGS,
    CONF_TIRE_BATTERY_LOW,
    CONF_TIRE_ENTITY_MAPPINGS,
    CONF_TIRE_PRESSURE_THRESHOLDS,
    CONF_TIRE_TEMPERATURE_HIGH,
    DOMAIN,
    UNIT_SYSTEM_METRIC,
    UNIT_SYSTEM_US_CUSTOMARY,
)
from custom_components.havrv.power import PowerSource
from custom_components.havrv.tire import tire_positions


async def _init_user_flow(hass: HomeAssistant) -> dict:
    """Initialize the user config flow."""
    return await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )


async def test_initial_form_is_short_and_defensively_validated(
    hass: HomeAssistant,
) -> None:
    """Only name and units are offered; invalid direct submissions still fail."""
    form = await _init_user_flow(hass)
    assert {str(key) for key in form["data_schema"].schema} == {
        CONF_NAME,
        CONF_MEASUREMENT_SYSTEM,
    }
    flow = HavrvConfigFlow()
    flow.hass = hass
    result = await flow.async_step_user(
        {
            CONF_NAME: "Adventure RV",
            CONF_MEASUREMENT_SYSTEM: "invalid",
        }
    )
    assert result["errors"] == {"base": "invalid_measurement"}


async def _finish_power_flow(
    hass: HomeAssistant, result: dict, *, options: bool = False
) -> dict:
    """Accept empty optional mappings in the default power-source setup."""
    while result.get("step_id") == "power_source":
        manager = hass.config_entries.options if options else hass.config_entries.flow
        result = await manager.async_configure(result["flow_id"], user_input={})
        assert not result.get("errors"), result
    return result


def _default_measurement_system(hass: HomeAssistant) -> str:
    """Return the unit system used by Home Assistant."""
    if hass.config.units == US_CUSTOMARY_SYSTEM:
        return UNIT_SYSTEM_US_CUSTOMARY
    return UNIT_SYSTEM_METRIC


def test_default_measurement_system_falls_back_to_metric() -> None:
    """Use metric units when Home Assistant has an unsupported unit system."""
    hass = SimpleNamespace(config=SimpleNamespace(units=None))

    assert get_default_measurement_system(hass) == UNIT_SYSTEM_METRIC


def test_entity_mapping_normalization_rejects_invalid_input() -> None:
    """Reject a mapping field that is not a list of entity IDs."""
    mappings, error = _normalize_entity_mappings(
        {"power_entities": "sensor.house_battery_voltage"}
    )

    assert mappings == {}
    assert error == "invalid_entity_mapping"


def _tire_profile_entry(*, options: dict | None = None) -> MockConfigEntry:
    """Create an RV entry with single and dual tire positions."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Adventure RV",
        data={
            CONF_NAME: "Adventure RV",
            CONF_REAR_AXLE_COUNT: 2,
            CONF_MAIN_REAR_WHEEL_CONFIGURATION: "dual",
            CONF_TAG_AXLE_PRESENT: True,
            CONF_TAG_AXLE_WHEEL_CONFIGURATION: "single",
        },
        options=options or {},
        unique_id="adventure rv",
    )


def test_tire_positions_include_tag_in_rear_axle_count() -> None:
    """Create stable names for front, drive, dual, and tag tire positions."""
    positions = tire_positions(_tire_profile_entry().data)

    assert len(positions) == 8
    assert [position.name for position in positions] == [
        "Front Left Tire",
        "Front Right Tire",
        "Rear Axle 1 Left Inner Tire",
        "Rear Axle 1 Left Outer Tire",
        "Rear Axle 1 Right Inner Tire",
        "Rear Axle 1 Right Outer Tire",
        "Tag Axle Left Tire",
        "Tag Axle Right Tire",
    ]


def test_tire_positions_support_two_main_axles_and_tag() -> None:
    """Include each configured main rear axle before the tag axle."""
    profile = dict(_tire_profile_entry().data)
    profile[CONF_REAR_AXLE_COUNT] = 3
    positions = tire_positions(profile)

    assert len(positions) == 12
    assert any(position.key == "rear_axle_2_left_inner" for position in positions)
    assert any(position.key == "rear_axle_2_right_outer" for position in positions)
    assert any(position.key == "tag_axle_left" for position in positions)


def test_options_normalization_stores_tire_sources_and_thresholds() -> None:
    """Store tire source selections and optional alert thresholds."""
    entry = _tire_profile_entry()
    options, error = _normalize_options(
        {
            "tire_front_left_pressure": "sensor.front_left_pressure",
            "tire_front_left_temperature": "sensor.front_left_temperature",
            "tire_front_left_battery": "sensor.front_left_battery",
            "tire_front_pressure_low": 450,
            "tire_front_pressure_high": 800,
            "tire_axle_pressure_low": 500,
            "tire_axle_pressure_high": 850,
            "tire_tag_pressure_low": 400,
            "tire_tag_pressure_high": 750,
            CONF_TIRE_TEMPERATURE_HIGH: 80,
            CONF_TIRE_BATTERY_LOW: 20,
        },
        entry,
    )

    assert error is None
    assert options[CONF_TIRE_ENTITY_MAPPINGS] == {
        "front_left_pressure": "sensor.front_left_pressure",
        "front_left_temperature": "sensor.front_left_temperature",
        "front_left_battery": "sensor.front_left_battery",
    }
    assert options[CONF_TIRE_PRESSURE_THRESHOLDS] == {
        "front": {"low": 450.0, "high": 800.0},
        "axle": {"low": 500.0, "high": 850.0},
        "tag": {"low": 400.0, "high": 750.0},
    }
    assert options[CONF_TIRE_TEMPERATURE_HIGH] == 80
    assert options[CONF_TIRE_BATTERY_LOW] == 20


def test_options_normalization_defaults_tire_battery_threshold() -> None:
    """Store the default low-battery limit when no override is submitted."""
    options, error = _normalize_options({}, _tire_profile_entry())

    assert error is None
    assert options[CONF_TIRE_BATTERY_LOW] == 20


def test_tank_options_store_individual_level_sources() -> None:
    """Store optional level sensors by explicitly selected tank type."""
    options, error = _normalize_options(
        {
            "fresh_water_tank_level": "sensor.fresh_level",
            "black_water_tank_level": "sensor.black_level",
        },
        _tire_profile_entry(),
    )

    assert error is None
    assert options[CONF_TANK_ENTITY_MAPPINGS] == {
        "fresh_water": "sensor.fresh_level",
        "black_water": "sensor.black_level",
    }


def test_tank_options_accept_number_and_input_number_sources() -> None:
    """Allow numeric helper entities as tank level sources."""
    options, error = _normalize_options(
        {
            "fresh_water_tank_level": "number.fresh_level",
            "gray_water_tank_level": "input_number.gray_level",
        },
        _tire_profile_entry(),
    )

    assert error is None
    assert options[CONF_TANK_ENTITY_MAPPINGS] == {
        "fresh_water": "number.fresh_level",
        "gray_water": "input_number.gray_level",
    }


def test_tank_options_accept_template_sensor_sources() -> None:
    """Allow template sensors as tank level sources."""
    options, error = _normalize_options(
        {"fresh_water_tank_level": "sensor.template_fresh_level"},
        _tire_profile_entry(),
    )

    assert error is None
    assert options[CONF_TANK_ENTITY_MAPPINGS] == {
        "fresh_water": "sensor.template_fresh_level",
    }


def test_all_tank_level_selectors_accept_numeric_entity_domains() -> None:
    """Offer sensor and numeric helper domains for each tank level."""
    schema = _options_schema(_tire_profile_entry())
    selectors = {marker.schema: selector for marker, selector in schema.schema.items()}

    for tank in ("fresh_water", "gray_water", "black_water"):
        assert selectors[f"{tank}_tank_level"].config["domain"] == [
            "sensor",
            "number",
            "input_number",
        ]


@pytest.mark.parametrize(
    ("user_input", "expected_error"),
    [
        (
            {"fresh_water_tank_level": "binary_sensor.fresh_level"},
            "invalid_tank_entity_mapping",
        ),
        (
            {
                "fresh_water_tank_level": "sensor.shared_level",
                "gray_water_tank_level": "sensor.shared_level",
            },
            "duplicate_tank_entity_mapping",
        ),
        (
            {"fresh_water_tank_level": 123},
            "invalid_tank_entity_mapping",
        ),
    ],
)
def test_tank_options_reject_invalid_level_mappings(
    user_input: dict, expected_error: str
) -> None:
    """Reject invalid or conflicting tank level sources."""
    options, error = _normalize_options(user_input, _tire_profile_entry())

    assert options == {}
    assert error == expected_error


def test_tank_thresholds_are_stored_per_tank() -> None:
    """Store warning and problem levels with the direction-aware tank type."""
    options, error = _normalize_options(
        {
            "fresh_water_tank_warning": 30,
            "fresh_water_tank_problem": 10,
            "gray_water_tank_warning": 70,
            "gray_water_tank_problem": 90,
        },
        _tire_profile_entry(),
    )

    assert error is None
    assert options["tank_thresholds"] == {
        "fresh_water": {"warning": 30.0, "problem": 10.0},
        "gray_water": {"warning": 70.0, "problem": 90.0},
    }


@pytest.mark.parametrize(
    ("user_input", "expected_error"),
    [
        ({"fresh_water_tank_warning": 30}, "incomplete_tank_threshold"),
        (
            {"fresh_water_tank_warning": 10, "fresh_water_tank_problem": 30},
            "invalid_tank_threshold",
        ),
        (
            {"black_water_tank_warning": 90, "black_water_tank_problem": 70},
            "invalid_tank_threshold",
        ),
        (
            {"gray_water_tank_warning": "x", "gray_water_tank_problem": 90},
            "invalid_tank_threshold",
        ),
    ],
)
def test_tank_thresholds_reject_invalid_values(
    user_input: dict, expected_error: str
) -> None:
    """Reject incomplete, wrong-direction, or non-numeric tank thresholds."""
    options, error = _normalize_options(user_input, _tire_profile_entry())

    assert options == {}
    assert error == expected_error


@pytest.mark.parametrize(
    "entity_id",
    [
        "sensor.template_pressure",
        "number.tire_pressure",
        "input_number.tire_pressure",
    ],
)
def test_tire_options_accept_numeric_entity_domains(entity_id: str) -> None:
    """Allow sensor, template sensor, number, and input-number sources."""
    options, error = _normalize_options(
        {"tire_front_left_pressure": entity_id},
        _tire_profile_entry(),
    )

    assert error is None
    assert options[CONF_TIRE_ENTITY_MAPPINGS] == {
        "front_left_pressure": entity_id,
    }


@pytest.mark.parametrize(
    ("user_input", "expected_error"),
    [
        (
            {
                "tire_front_left_pressure": "sensor.shared",
                "tire_front_right_pressure": "sensor.shared",
            },
            "duplicate_tire_entity_mapping",
        ),
        (
            {"tire_front_left_pressure": "climate.front_tire"},
            "invalid_tire_entity_mapping",
        ),
        (
            {"tire_front_left_pressure": "sensor"},
            "invalid_tire_entity_mapping",
        ),
        (
            {"tire_front_left_pressure": 123},
            "invalid_tire_entity_mapping",
        ),
        (
            {"tire_front_pressure_low": 400},
            "incomplete_tire_pressure_threshold",
        ),
        (
            {"tire_front_pressure_low": 900, "tire_front_pressure_high": 800},
            "invalid_tire_pressure_threshold",
        ),
        (
            {CONF_TIRE_BATTERY_LOW: 101},
            "invalid_tire_battery_threshold",
        ),
        (
            {CONF_TIRE_TEMPERATURE_HIGH: -1},
            "invalid_tire_temperature_threshold",
        ),
    ],
)
def test_options_normalization_rejects_invalid_tire_settings(
    user_input: dict, expected_error: str
) -> None:
    """Reject duplicate source sensors and invalid tire alert limits."""
    options, error = _normalize_options(user_input, _tire_profile_entry())

    assert options == {}
    assert error == expected_error


async def test_user_flow_creates_profile_with_optional_fields_blank(
    hass: HomeAssistant,
) -> None:
    """Only the RV profile name is required."""
    form = await _init_user_flow(hass)
    assert form["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        form["flow_id"],
        user_input={CONF_NAME: "Adventure RV"},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Adventure RV"
    assert result["data"] == {
        CONF_NAME: "Adventure RV",
        CONF_HOUSE_BATTERY_BANK_COUNT: 1,
        CONF_CHASSIS_BATTERY_BANK_COUNT: 1,
        CONF_ENTITY_MAPPINGS: {},
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
    result = await _finish_power_flow(hass, result)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_MEASUREMENT_SYSTEM] == UNIT_SYSTEM_US_CUSTOMARY


def test_profile_normalization_stores_coach_details() -> None:
    """Store optional coach identity, zone, capacities, and axle settings."""
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
        CONF_TAG_AXLE_WHEEL_CONFIGURATION: "single",
    }

    data, error = _normalize_profile(
        input_data, default_measurement_system=UNIT_SYSTEM_METRIC
    )
    assert error is None
    assert data == {
        CONF_NAME: "Liberty",
        CONF_HOUSE_BATTERY_BANK_COUNT: 1,
        CONF_CHASSIS_BATTERY_BANK_COUNT: 1,
        CONF_ENTITY_MAPPINGS: {},
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


def test_profile_accepts_three_rear_axles_including_tag() -> None:
    """Allow two main rear axles plus a tag axle in the inclusive count."""
    data, error = _normalize_profile(
        {
            CONF_NAME: "Adventure RV",
            CONF_REAR_AXLE_COUNT: "three",
            CONF_MAIN_REAR_WHEEL_CONFIGURATION: "dual",
            CONF_TAG_AXLE_WHEEL_CONFIGURATION: "single",
        },
        default_measurement_system=UNIT_SYSTEM_METRIC,
    )

    assert error is None
    assert data[CONF_REAR_AXLE_COUNT] == 3
    assert data[CONF_TAG_AXLE_PRESENT] is True
    positions = tire_positions(data)
    assert any(position.key == "rear_axle_2_left_inner" for position in positions)
    assert any(position.key == "tag_axle_left" for position in positions)


def test_profile_derives_no_tag_for_one_rear_axle() -> None:
    """A single configured rear axle creates no tag-axle positions."""
    data, error = _normalize_profile(
        {
            CONF_NAME: "Adventure RV",
            CONF_REAR_AXLE_COUNT: "one",
            CONF_MAIN_REAR_WHEEL_CONFIGURATION: "dual",
        },
        default_measurement_system=UNIT_SYSTEM_METRIC,
    )

    assert error is None
    assert data[CONF_TAG_AXLE_PRESENT] is False
    assert CONF_TAG_AXLE_WHEEL_CONFIGURATION not in data
    assert all(position.group != "tag" for position in tire_positions(data))


def test_profile_stores_grouped_source_entity_mappings() -> None:
    """Store mapped source entities by RV system."""
    data, error = _normalize_profile(
        {
            CONF_NAME: "Adventure RV",
            "power_entities": ["sensor.house_battery_voltage"],
            "water_entities": ["binary_sensor.fresh_water_low"],
        },
        default_measurement_system=UNIT_SYSTEM_METRIC,
    )

    assert error is None
    assert data[CONF_ENTITY_MAPPINGS] == {
        "power": ["sensor.house_battery_voltage"],
        "water": ["binary_sensor.fresh_water_low"],
    }


def test_profile_rejects_source_entity_in_multiple_groups() -> None:
    """Require each source entity to be assigned to one system."""
    _, error = _normalize_profile(
        {
            CONF_NAME: "Adventure RV",
            "power_entities": ["sensor.house_battery_voltage"],
            "water_entities": ["sensor.house_battery_voltage"],
        },
        default_measurement_system=UNIT_SYSTEM_METRIC,
    )

    assert error == "duplicate_entity_mapping"


async def test_options_flow_updates_source_entity_mappings(
    hass: HomeAssistant,
) -> None:
    """Add source mappings to an existing profile."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Adventure RV",
        data={
            CONF_NAME: "Adventure RV",
            CONF_ENTITY_MAPPINGS: {"water": ["sensor.fresh_water_level"]},
        },
        options={
            CONF_TANK_ENTITY_MAPPINGS: {
                "fresh_water": "sensor.fresh_water_level",
            },
        },
        unique_id="adventure rv",
    )
    entry.add_to_hass(hass)

    form = await hass.config_entries.options.async_init(entry.entry_id)
    assert form["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        form["flow_id"],
        user_input={"power_entities": ["sensor.house_battery_voltage"]},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_ENTITY_MAPPINGS] == {
        "power": ["sensor.house_battery_voltage"],
        "water": ["sensor.fresh_water_level"],
    }
    assert entry.options[CONF_TANK_ENTITY_MAPPINGS] == {
        "fresh_water": "sensor.fresh_water_level",
    }


async def test_options_flow_updates_tire_source_and_preserves_other_limits(
    hass: HomeAssistant,
) -> None:
    """Render tire mappings and retain existing settings when partially edited."""
    entry = _tire_profile_entry(
        options={
            CONF_TIRE_ENTITY_MAPPINGS: {
                "front_left_pressure": "sensor.old_pressure",
                "front_left_temperature": "sensor.old_temperature",
            },
            CONF_TIRE_PRESSURE_THRESHOLDS: {"front": {"low": 400, "high": 800}},
            CONF_TIRE_TEMPERATURE_HIGH: 75,
            CONF_TIRE_BATTERY_LOW: 25,
        }
    )
    entry.add_to_hass(hass)

    form = await hass.config_entries.options.async_init(entry.entry_id)
    assert form["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        form["flow_id"],
        user_input={
            "tire_front_left_pressure": "sensor.new_pressure",
            "tire_front_pressure_low": 450,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_TIRE_ENTITY_MAPPINGS] == {
        "front_left_pressure": "sensor.new_pressure",
        "front_left_temperature": "sensor.old_temperature",
    }
    assert entry.options[CONF_TIRE_PRESSURE_THRESHOLDS]["front"] == {
        "low": 450,
        "high": 800,
    }
    assert entry.options[CONF_TIRE_TEMPERATURE_HIGH] == 75
    assert entry.options[CONF_TIRE_BATTERY_LOW] == 25


async def test_options_flow_rejects_duplicate_source_entities(
    hass: HomeAssistant,
) -> None:
    """Reject source entities assigned to multiple RV systems in options."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Adventure RV",
        data={CONF_NAME: "Adventure RV"},
        unique_id="adventure rv",
    )
    entry.add_to_hass(hass)

    form = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        form["flow_id"],
        user_input={
            "power_entities": ["sensor.house_battery_voltage"],
            "water_entities": ["sensor.house_battery_voltage"],
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "duplicate_entity_mapping"}


async def test_reconfigure_flow_updates_profile_and_preserves_mappings(
    hass: HomeAssistant,
) -> None:
    """Edit vehicle details without changing profile identity or mappings."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Adventure RV",
        unique_id="adventure rv",
        data={
            CONF_NAME: "Adventure RV",
            CONF_ENTITY_MAPPINGS: {"power": ["sensor.house_voltage"]},
            CONF_MEASUREMENT_SYSTEM: UNIT_SYSTEM_METRIC,
            CONF_REAR_AXLE_COUNT: 1,
            CONF_MAIN_REAR_WHEEL_CONFIGURATION: "single",
        },
        options={CONF_ENTITY_MAPPINGS: {"water": ["binary_sensor.tank_low"]}},
        version=3,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)

    form = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )
    assert form["step_id"] == "reconfigure"

    invalid = await hass.config_entries.flow.async_configure(
        form["flow_id"],
        user_input={CONF_REAR_AXLE_COUNT: "two"},
    )
    assert invalid["type"] is FlowResultType.FORM
    assert invalid["errors"]["base"] == "tag_axle_wheel_configuration_required"

    result = await hass.config_entries.flow.async_configure(
        form["flow_id"],
        user_input={
            CONF_MEASUREMENT_SYSTEM: UNIT_SYSTEM_US_CUSTOMARY,
            CONF_OVERALL_HEIGHT: 12.5,
            CONF_REAR_AXLE_COUNT: "two",
            CONF_MAIN_REAR_WHEEL_CONFIGURATION: "dual",
            CONF_TAG_AXLE_WHEEL_CONFIGURATION: "single",
        },
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.title == "Adventure RV"
    assert entry.unique_id == "adventure rv"
    assert entry.data[CONF_ENTITY_MAPPINGS] == {"power": ["sensor.house_voltage"]}
    assert entry.options[CONF_ENTITY_MAPPINGS] == {"water": ["binary_sensor.tank_low"]}
    assert entry.data[CONF_OVERALL_HEIGHT] == 12.5
    assert entry.data[CONF_TAG_AXLE_PRESENT] is True
    assert entry.runtime_data.overall_height == 12.5
    assert entry.runtime_data.tag_axle_present is True
    assert await hass.config_entries.async_unload(entry.entry_id)


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


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({CONF_COACH_YEAR: date.today().year + 2}, "invalid_coach_year"),
        ({CONF_FUEL_TANK_CAPACITY: 0}, "invalid_measurement"),
        ({CONF_MANUFACTURER: {}}, "invalid_measurement"),
        ({CONF_REAR_AXLE_COUNT: "one"}, "main_rear_wheel_configuration_required"),
        ({CONF_REAR_AXLE_COUNT: "two"}, "tag_axle_wheel_configuration_required"),
        (
            {
                CONF_REAR_AXLE_COUNT: "one",
                CONF_MAIN_REAR_WHEEL_CONFIGURATION: "dual",
                CONF_TAG_AXLE_WHEEL_CONFIGURATION: "dual",
            },
            "tag_wheel_configuration_without_tag_axle",
        ),
    ],
)
def test_profile_rejects_invalid_reference_fields(fields, expected) -> None:
    """Shared detailed forms reject invalid specifications and incomplete layouts."""
    _, error = _normalize_profile(
        {CONF_NAME: "Adventure RV", **fields},
        default_measurement_system=UNIT_SYSTEM_METRIC,
    )
    assert error == expected


def test_profile_accepts_tag_axle_with_wheel_configuration() -> None:
    """Accept a tag axle when its wheel configuration is provided."""
    data, error = _normalize_profile(
        {
            CONF_NAME: "Adventure RV",
            CONF_REAR_AXLE_COUNT: "two",
            CONF_MAIN_REAR_WHEEL_CONFIGURATION: "dual",
            CONF_TAG_AXLE_WHEEL_CONFIGURATION: "dual",
        },
        default_measurement_system=UNIT_SYSTEM_METRIC,
    )

    assert error is None
    assert data[CONF_TAG_AXLE_PRESENT] is True
    assert data[CONF_REAR_AXLE_COUNT] == 2
    assert data[CONF_TAG_AXLE_WHEEL_CONFIGURATION] == "dual"
    positions = tire_positions(data)
    assert any(position.key == "rear_axle_1_left_inner" for position in positions)
    assert any(position.key == "tag_axle_left_inner" for position in positions)
    assert not any(position.key.startswith("rear_axle_2_") for position in positions)


@pytest.mark.parametrize("count", [-1, 1.5, True, float("nan"), float("inf"), "2"])
def test_invalid_battery_bank_count(count: object) -> None:
    """Bank counts must be finite, non-negative integers."""
    _, error = _normalize_profile(
        {CONF_NAME: "RV", CONF_HOUSE_BATTERY_BANK_COUNT: count},
        default_measurement_system=UNIT_SYSTEM_METRIC,
    )
    assert error == "invalid_battery_bank_count"


@pytest.mark.parametrize(
    ("settings", "error"),
    [
        ({"voltage": 12}, "invalid_power_entity_mapping"),
        ({"voltage": "sensor"}, "invalid_power_entity_mapping"),
        ({"voltage": "sensor."}, "invalid_power_entity_mapping"),
        ({"voltage": "switch.voltage"}, "invalid_power_entity_mapping"),
        ({"enabled": "sensor.enabled"}, "invalid_power_entity_mapping"),
        ({"charging": "number.charging"}, "invalid_power_entity_mapping"),
        ({"warning": "sensor.warning"}, "invalid_power_entity_mapping"),
        ({"problem": "number.problem"}, "invalid_power_entity_mapping"),
        (
            {"warning": "binary_sensor.shared", "problem": "binary_sensor.shared"},
            "duplicate_power_entity_mapping",
        ),
        (
            {"current": "sensor.shared", "voltage": "sensor.shared"},
            "duplicate_power_entity_mapping",
        ),
        ({"location": "front"}, "invalid_power_location"),
        ({"nominal_voltage": 36}, "invalid_nominal_voltage"),
        ({"nominal_capacity": 0}, "invalid_nominal_capacity"),
        ({"nominal_capacity": float("nan")}, "invalid_nominal_capacity"),
    ],
)
def test_power_source_validation(settings: dict, error: str) -> None:
    """Reject incompatible domains, invalid specifications and duplicate roles."""
    result, actual_error = _normalize_power_source(
        settings, PowerSource("house_bank_1", "House", True)
    )
    assert result == {}
    assert actual_error == error


@pytest.mark.parametrize("domain", ["sensor", "number", "input_number"])
def test_power_numeric_selector_and_validation_match(domain: str) -> None:
    """Sensor, helper and template-result numeric domains work in every form."""
    bank = PowerSource("house_bank_1", "House", True)
    schema = _power_source_schema(bank, {})
    fields = {key.schema: value for key, value in schema.schema.items()}
    assert fields["voltage"].config["domain"] == ["sensor", "number", "input_number"]
    assert fields["enabled"].config["domain"] == [
        "binary_sensor",
        "switch",
        "input_boolean",
    ]
    settings, error = _normalize_power_source(
        {"voltage": f"{domain}.template_voltage", "current": f"{domain}.current"},
        bank,
    )
    assert error is None
    assert settings["voltage"] == f"{domain}.template_voltage"
    assert settings["nominal_voltage"] == 24
    assert settings["location"] == "not_shown"
    assert "nominal_capacity" not in settings


async def test_options_configure_independent_banks_and_readonly_sources(
    hass: HomeAssistant,
) -> None:
    """Complete the native recovery wizard with banks and explicit charging."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=3,
        data={
            CONF_NAME: "Power RV",
            CONF_HOUSE_BATTERY_BANK_COUNT: 2,
            CONF_CHASSIS_BATTERY_BANK_COUNT: 0,
        },
    )
    entry.add_to_hass(hass)
    form = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        form["flow_id"],
        user_input={
            CONF_CONFIGURE_POWER_SOURCES: True,
        },
    )
    assert result["step_id"] == "power_source"
    assert result["description_placeholders"] == {"source": "House Batteries Bank 1"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "voltage": "input_number.house_voltage",
            "current": "number.house_current",
            "enabled": "switch.house_enabled",
            "charging": "input_boolean.house_charging",
            "warning": "binary_sensor.house_warning",
            "problem": "switch.house_problem",
            "nominal_voltage": "48",
            "nominal_capacity": 400,
            "location": "left_rear",
        },
    )
    assert result["description_placeholders"] == {"source": "House Batteries Bank 2"}
    result = await _finish_power_flow(hass, result, options=True)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    settings = entry.options[CONF_POWER_SOURCES]
    assert list(settings) == [
        "house_bank_1",
        "house_bank_2",
        "inverter",
        "generator",
        "shore_power",
    ]
    assert settings["house_bank_1"]["nominal_voltage"] == 48
    assert settings["house_bank_1"]["nominal_capacity"] == 400
    assert settings["house_bank_1"]["charging"] == "input_boolean.house_charging"
    assert settings["house_bank_1"]["warning"] == "binary_sensor.house_warning"
    assert settings["house_bank_1"]["problem"] == "switch.house_problem"
    assert settings["house_bank_2"] == {"nominal_voltage": 24, "location": "not_shown"}
    assert settings["shore_power"] == {"line_count": 2, "location": "not_shown"}


async def test_power_options_invalid_capacity_preserves_input(
    hass: HomeAssistant,
) -> None:
    """Invalid capacity stays on the same bank and retains valid submitted fields."""
    entry = MockConfigEntry(domain=DOMAIN, version=3, data={CONF_NAME: "Power RV"})
    entry.add_to_hass(hass)
    form = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        form["flow_id"], user_input={CONF_CONFIGURE_POWER_SOURCES: True}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"voltage": "sensor.voltage", "nominal_capacity": 0},
    )
    assert result["errors"] == {"base": "invalid_nominal_capacity"}
    assert result["description_placeholders"]["source"] == "House Batteries Bank 1"
    fields = {key.schema: key for key in result["data_schema"].schema}
    assert fields["voltage"].description["suggested_value"] == "sensor.voltage"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"nominal_capacity": 200}
    )
    await _finish_power_flow(hass, result, options=True)


async def test_options_edit_power_settings_and_preserve_other_options(
    hass: HomeAssistant,
) -> None:
    """Edit defaults and remove mappings without saving any partial wizard state."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Power RV",
        version=3,
        data={CONF_NAME: "Power RV"},
        options={
            CONF_POWER_SOURCES: {
                "house_bank_1": {
                    "voltage": "sensor.old",
                    "charging": "binary_sensor.charging",
                    "warning": "binary_sensor.warning",
                    "problem": "input_boolean.problem",
                    "nominal_voltage": 12,
                    "nominal_capacity": 200,
                    "location": "left_mid",
                }
            }
        },
    )
    entry.add_to_hass(hass)
    form = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        form["flow_id"],
        user_input={
            CONF_CONFIGURE_POWER_SOURCES: True,
            "power_entities": ["sensor.generic"],
        },
    )
    assert result["step_id"] == "power_source"
    defaults = result["data_schema"]({})
    assert defaults["nominal_voltage"] == "12"
    fields = {key.schema: key for key in result["data_schema"].schema}
    assert fields["nominal_capacity"].description["suggested_value"] == 200
    assert fields["charging"].description["suggested_value"] == "binary_sensor.charging"
    assert fields["warning"].description["suggested_value"] == "binary_sensor.warning"
    assert fields["problem"].description["suggested_value"] == "input_boolean.problem"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"nominal_capacity": 0}
    )
    assert result["errors"] == {"base": "invalid_nominal_capacity"}
    assert entry.options[CONF_POWER_SOURCES]["house_bank_1"]["voltage"] == "sensor.old"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "nominal_voltage": "24",
            "location": "not_shown",
        },
    )
    while result.get("step_id") == "power_source":
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], user_input={}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_ENTITY_MAPPINGS] == {"power": ["sensor.generic"]}
    assert entry.options[CONF_POWER_SOURCES]["house_bank_1"] == {
        "nominal_voltage": 24,
        "location": "not_shown",
    }
    assert (
        _normalize_options({}, entry)[0][CONF_POWER_SOURCES]
        == (entry.options[CONF_POWER_SOURCES])
    )


def test_shore_placement_is_external_and_ignores_battery_fields() -> None:
    """Shore has side placement only and no Charging or nominal bank settings."""
    shore = PowerSource("shore_power", "Shore Power")
    schema = _power_source_schema(shore, {})
    assert "charging" not in {key.schema for key in schema.schema}
    assert _normalize_power_source({"location": "left_front"}, shore)[1] == (
        "invalid_power_location"
    )
    assert _normalize_power_source(
        {"location": "right", "charging": "binary_sensor.unused"}, shore
    ) == ({"line_count": 2, "location": "right"}, None)


@pytest.mark.parametrize("count", [0, 3, 1.5, True, "2", None, float("nan")])
def test_invalid_shore_line_counts(count: object) -> None:
    """Reject invalid counts rather than truncating them or enabling extra lines."""
    assert _normalize_power_source(
        {"line_count": count}, PowerSource("shore_power", "Shore")
    ) == ({}, "invalid_shore_line_count")


@pytest.mark.parametrize("count", [1, 2])
@pytest.mark.parametrize("domain", ["sensor", "number", "input_number"])
def test_shore_line_schema_and_numeric_validation(count: int, domain: str) -> None:
    """All shore numeric roles use the same source domains and active-line rules."""
    shore = PowerSource("shore_power", "Shore")
    fields = {
        marker.schema: validator
        for marker, validator in _power_source_schema(
            shore, {"line_count": count}
        ).schema.items()
    }
    settings = {"line_count": count}
    metrics = ["voltage", "current", "frequency", "power", "energy"]
    if count == 2:
        metrics += [f"line_2_{metric}" for metric in metrics[:4]]
    for metric in metrics:
        assert fields[metric].config["domain"] == ["sensor", "number", "input_number"]
        settings[metric] = f"{domain}.template_{metric}"
    normalized, error = _normalize_power_source(settings, shore)
    assert error is None
    assert all(normalized[metric] == settings[metric] for metric in metrics)
    assert ("line_2_voltage" in fields) == (count == 2)
    settings["frequency"] = "switch.invalid"
    assert _normalize_power_source(settings, shore)[1] == "invalid_power_entity_mapping"
    settings["frequency"] = settings["energy"]
    assert (
        _normalize_power_source(settings, shore)[1] == "duplicate_power_entity_mapping"
    )


async def test_native_shore_count_refreshes_before_saving(
    hass: HomeAssistant,
) -> None:
    """Changing count refreshes fields before committing the complete wizard."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=3,
        data={CONF_NAME: "Shore"},
        options={CONF_POWER_SOURCES: {"shore_power": {"voltage": "sensor.legacy"}}},
    )
    entry.add_to_hass(hass)
    form = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        form["flow_id"], user_input={CONF_CONFIGURE_POWER_SOURCES: True}
    )
    while result["description_placeholders"]["source"] != "Shore Power":
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], user_input={}
        )
    assert "line_2_voltage" not in {key.schema for key in result["data_schema"].schema}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"line_count": 1.5}
    )
    assert result["errors"] == {"base": "invalid_shore_line_count"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"line_count": 2, "voltage": "sensor.legacy"},
    )
    assert "line_2_voltage" in {key.schema for key in result["data_schema"].schema}
    assert "line_count" not in entry.options[CONF_POWER_SOURCES]["shore_power"]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "line_count": 1,
            "voltage": "sensor.legacy",
            "line_2_power": "number.watts",
        },
    )
    assert "line_2_power" not in {key.schema for key in result["data_schema"].schema}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"line_count": 2, "voltage": "sensor.legacy"}
    )
    line_2_field = next(
        key for key in result["data_schema"].schema if key.schema == "line_2_power"
    )
    assert line_2_field.description["suggested_value"] == "number.watts"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "line_count": 2,
            "voltage": "sensor.legacy",
            "line_2_power": "number.watts",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_POWER_SOURCES]["shore_power"]["line_count"] == 2


@pytest.mark.parametrize("domain", ["binary_sensor", "switch", "input_boolean"])
@pytest.mark.parametrize(
    "key", ["house_bank_1", "chassis_bank_1", "inverter", "generator", "shore_power"]
)
def test_power_alert_selectors_and_validation_match(domain: str, key: str) -> None:
    """Every bank and AC source accepts the same read-only alert domains."""
    source = PowerSource(key, key, "bank" in key)
    schema = _power_source_schema(source, {})
    fields = {field.schema: selector for field, selector in schema.schema.items()}
    for metric in ("warning", "problem"):
        assert fields[metric].config["domain"] == [
            "binary_sensor",
            "switch",
            "input_boolean",
        ]
    settings, error = _normalize_power_source(
        {"warning": f"{domain}.warning", "problem": f"{domain}.problem"}, source
    )
    assert error is None
    assert settings["warning"] == f"{domain}.warning"
    assert settings["problem"] == f"{domain}.problem"
