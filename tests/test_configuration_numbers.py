"""Tests for editable configuration and read-only profile diagnostics."""

import pytest
from homeassistant.const import CONF_NAME, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.translation import async_get_translations
from homeassistant.util.unit_system import METRIC_SYSTEM, US_CUSTOMARY_SYSTEM
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.havrv.const import (
    CONF_ENTITY_MAPPINGS,
    CONF_FRESH_WATER_TANK_CAPACITY,
    CONF_MAIN_REAR_WHEEL_CONFIGURATION,
    CONF_MEASUREMENT_SYSTEM,
    CONF_OVERALL_HEIGHT,
    CONF_REAR_AXLE_COUNT,
    CONF_TAG_AXLE_PRESENT,
    CONF_TAG_AXLE_WHEEL_CONFIGURATION,
    CONF_TANK_ENTITY_MAPPINGS,
    CONF_TANK_THRESHOLDS,
    CONF_TIRE_BATTERY_LOW,
    CONF_TIRE_ENTITY_MAPPINGS,
    CONF_TIRE_PRESSURE_THRESHOLDS,
    CONF_TIRE_TEMPERATURE_HIGH,
    DOMAIN,
    UNIT_SYSTEM_METRIC,
    UNIT_SYSTEM_US_CUSTOMARY,
)
from custom_components.havrv.number import (
    PROFILE_NUMBER_KEYS,
    HavrvConfigurationNumber,
    _descriptions,
)


def _entry(
    system: str = UNIT_SYSTEM_METRIC, *, configured: bool = True
) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="RV",
        unique_id="rv",
        data={
            CONF_NAME: "RV",
            CONF_MEASUREMENT_SYSTEM: system,
            CONF_OVERALL_HEIGHT: 3.8,
            CONF_FRESH_WATER_TANK_CAPACITY: 400.0,
            CONF_REAR_AXLE_COUNT: 2,
            CONF_MAIN_REAR_WHEEL_CONFIGURATION: "dual",
            CONF_TAG_AXLE_PRESENT: True,
            CONF_TAG_AXLE_WHEEL_CONFIGURATION: "single",
        },
        options={
            CONF_ENTITY_MAPPINGS: {"power": ["sensor.voltage"]},
            CONF_TANK_ENTITY_MAPPINGS: {"fresh_water": "number.fresh"},
            CONF_TIRE_ENTITY_MAPPINGS: {
                "front_left_pressure": "input_number.pressure",
                "front_left_temperature": "sensor.template_temperature",
            },
            CONF_TIRE_PRESSURE_THRESHOLDS: {"front": {"low": 600.0, "high": 1100.0}},
            CONF_TIRE_TEMPERATURE_HIGH: 80.0,
            "future_option": "preserved",
        }
        if configured
        else {},
        version=3,
    )


def _entity(
    hass: HomeAssistant, entry: MockConfigEntry, suffix: str, domain: str | None = None
) -> str:
    return next(
        ent.entity_id
        for ent in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        if ent.unique_id == f"{entry.entry_id}_{suffix}"
        and (domain is None or ent.domain == domain)
    )


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    hass.states.async_set("number.fresh", "40", {"unit_of_measurement": "%"})
    hass.states.async_set(
        "input_number.pressure", "100", {"unit_of_measurement": "psi"}
    )
    hass.states.async_set(
        "sensor.template_temperature", "170", {"unit_of_measurement": "°F"}
    )
    if hass.config_entries.async_get_entry(entry.entry_id) is None:
        entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _set(
    hass: HomeAssistant, entry: MockConfigEntry, suffix: str, value: float
) -> None:
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": _entity(hass, entry, suffix), "value": value},
        blocking=True,
    )
    await hass.async_block_till_done()


@pytest.mark.parametrize(
    ("system", "ha_units", "distance", "volume", "pressure", "temperature"),
    [
        (UNIT_SYSTEM_METRIC, US_CUSTOMARY_SYSTEM, "m", "L", "kPa", "°C"),
        (UNIT_SYSTEM_US_CUSTOMARY, METRIC_SYSTEM, "ft", "gal", "psi", "°F"),
    ],
)
async def test_device_categories_and_profile_units(
    hass: HomeAssistant, system, ha_units, distance, volume, pressure, temperature
) -> None:
    """Numbers use profile units even when HA is configured differently."""
    hass.config.units = ha_units
    entry = _entry(system)
    await _setup(hass, entry)
    rv = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, entry.entry_id), entry.entry_id
    )
    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    controls = [
        ent for ent in entities if ent.domain == "number" and ent.device_id == rv.id
    ]
    assert len(controls) == 21
    assert all(ent.entity_category is EntityCategory.CONFIG for ent in controls)
    assert all(ent.device_id == rv.id for ent in controls)
    units = {
        "profile_overall_height": distance,
        "profile_fresh_water_tank_capacity": volume,
        "configuration_tire_front_pressure_low": pressure,
        "configuration_tire_temperature_high": temperature,
        "configuration_fresh_water_tank_warning": "%",
        "configuration_tire_battery_low": "%",
    }
    for suffix, unit in units.items():
        state = hass.states.get(_entity(hass, entry, suffix))
        assert state.attributes["unit_of_measurement"] == unit
        assert state.attributes["mode"] == "box"
    profiles = [
        ent
        for ent in entities
        if ent.domain == "sensor" and "_profile_" in ent.unique_id
    ]
    assert profiles
    assert all(ent.entity_category is EntityCategory.DIAGNOSTIC for ent in profiles)
    assert not any(
        ent.domain == "sensor" and ent.unique_id == f"{entry.entry_id}_profile_{key}"
        for ent in entities
        for key in PROFILE_NUMBER_KEYS
    )


async def test_unknown_specifications_and_legacy_limits(hass: HomeAssistant) -> None:
    """Unknown quantities and optional limits are not invented or activated."""
    entry = _entry(configured=False)
    await _setup(hass, entry)
    assert (
        hass.states.get(_entity(hass, entry, "profile_overall_width")).state
        == "unknown"
    )
    low = hass.states.get(_entity(hass, entry, "configuration_tire_front_pressure_low"))
    assert low.state == "unknown"
    assert low.attributes["suggested_default"] == 689.5
    temperature = hass.states.get(
        _entity(hass, entry, "configuration_tire_temperature_high")
    )
    assert temperature.state == "unknown"
    assert temperature.attributes["suggested_default"] == 65.6
    assert (
        hass.states.get(_entity(hass, entry, "configuration_tire_battery_low")).state
        == "20.0"
    )
    assert (
        hass.states.get(
            _entity(hass, entry, "configuration_fresh_water_tank_warning")
        ).state
        == "50.0"
    )
    assert CONF_TIRE_PRESSURE_THRESHOLDS not in entry.options
    assert CONF_TIRE_TEMPERATURE_HIGH not in entry.options


async def test_profile_write_persists_and_updates_tank(hass: HomeAssistant) -> None:
    """Capacity controls and reconfiguration share the same persisted field."""
    entry = _entry()
    await _setup(hass, entry)
    original_options = dict(entry.options)
    capacity = _entity(hass, entry, "profile_fresh_water_tank_capacity")
    await _set(hass, entry, "profile_fresh_water_tank_capacity", 500)
    assert entry.data[CONF_FRESH_WATER_TANK_CAPACITY] == 500
    assert entry.runtime_data.fresh_water_tank_capacity == 500
    assert entry.options == original_options
    assert _entity(hass, entry, "profile_fresh_water_tank_capacity") == capacity
    assert hass.states.get(capacity).state == "500.0"
    assert (
        hass.states.get(_entity(hass, entry, "tank_fresh_water_capacity")).state
        == "500.0"
    )

    form = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "reconfigure", "entry_id": entry.entry_id},
    )
    defaults = {
        key.schema: key.default()
        for key in form["data_schema"].schema
        if callable(key.default)
    }
    assert defaults[CONF_FRESH_WATER_TANK_CAPACITY] == 500
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_FRESH_WATER_TANK_CAPACITY: 600}
    )
    await hass.async_block_till_done()
    assert hass.states.get(capacity).state == "600.0"
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert hass.states.get(capacity).state == "unavailable"
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(capacity).state == "600.0"


async def test_threshold_write_preserves_sources_and_updates_detection(
    hass: HomeAssistant,
) -> None:
    """Limits are saved in options, reflected in forms, and applied on reload."""
    entry = _entry()
    await _setup(hass, entry)
    original_data = dict(entry.data)
    problem = _entity(hass, entry, "tire_front_left_pressure", "binary_sensor")
    assert hass.states.get(problem).state == "off"
    await _set(hass, entry, "configuration_tire_front_pressure_low", 700)
    assert entry.options[CONF_TIRE_PRESSURE_THRESHOLDS]["front"] == {
        "low": 700,
        "high": 1100,
    }
    assert hass.states.get(problem).state == "on"
    assert entry.data == original_data
    assert entry.options[CONF_ENTITY_MAPPINGS] == {"power": ["sensor.voltage"]}
    assert entry.options[CONF_TANK_ENTITY_MAPPINGS] == {"fresh_water": "number.fresh"}
    assert (
        entry.options[CONF_TIRE_ENTITY_MAPPINGS]
        == _entry().options[CONF_TIRE_ENTITY_MAPPINGS]
    )
    assert entry.options["future_option"] == "preserved"
    await _set(hass, entry, "configuration_tire_temperature_high", 70)
    assert (
        hass.states.get(
            _entity(hass, entry, "tire_front_left_temperature", "binary_sensor")
        ).state
        == "on"
    )
    await _set(hass, entry, "configuration_tire_battery_low", 30)
    assert entry.options[CONF_TIRE_BATTERY_LOW] == 30
    await _set(hass, entry, "configuration_fresh_water_tank_problem", 45)
    assert (
        hass.states.get(_entity(hass, entry, "tank_fresh_water_status")).state
        == "problem"
    )
    assert entry.options[CONF_TANK_THRESHOLDS]["fresh_water"] == {
        "warning": 50,
        "problem": 45,
    }
    form = await hass.config_entries.options.async_init(entry.entry_id)
    defaults = {
        key.schema: key.default()
        for key in form["data_schema"].schema
        if callable(key.default)
    }
    assert defaults["fresh_water_tank_problem"] == 45
    assert defaults["tire_front_pressure_low"] == 700
    result = await hass.config_entries.options.async_configure(
        form["flow_id"], user_input={"tire_front_pressure_low": 650}
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    assert (
        hass.states.get(
            _entity(hass, entry, "configuration_tire_front_pressure_low")
        ).state
        == "650.0"
    )


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("profile_overall_height", 0),
        ("profile_fresh_water_tank_capacity", -1),
        ("configuration_fresh_water_tank_warning", 20),
        ("configuration_gray_water_tank_warning", 80),
        ("configuration_black_water_tank_problem", 40),
        ("configuration_tire_front_pressure_low", 1100),
        ("configuration_tire_front_pressure_high", 600),
        ("configuration_tire_temperature_high", -1),
        ("configuration_tire_battery_low", 101),
    ],
)
async def test_invalid_writes_leave_configuration_unchanged(
    hass: HomeAssistant, key: str, value: float
) -> None:
    """Invalid ranges and crossing limits fail without changing the entry."""
    entry = _entry()
    await _setup(hass, entry)
    before_data, before_options = dict(entry.data), dict(entry.options)
    with pytest.raises(ServiceValidationError):
        await _set(hass, entry, key, value)
    assert entry.data == before_data
    assert entry.options == before_options


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
async def test_nonfinite_write_is_translated(hass: HomeAssistant, value: float) -> None:
    """Reject nonfinite native values, including service validation bypasses."""
    entry = _entry()
    await _setup(hass, entry)
    control = HavrvConfigurationNumber(entry, _descriptions(entry)[0])
    control.hass = hass
    with pytest.raises(ServiceValidationError) as exc:
        await control.async_set_native_value(value)
    assert exc.value.translation_key == "invalid_numeric_setting"
    assert entry.data[CONF_OVERALL_HEIGHT] == 3.8


@pytest.mark.parametrize("system", [UNIT_SYSTEM_METRIC, UNIT_SYSTEM_US_CUSTOMARY])
async def test_unset_pressure_pair_uses_form_default(
    hass: HomeAssistant, system: str
) -> None:
    """Setting one pressure limit initializes its companion in profile units."""
    entry = _entry(system, configured=False)
    await _setup(hass, entry)
    value, companion = (700, 1034.2) if system == UNIT_SYSTEM_METRIC else (110, 150)
    await _set(hass, entry, "configuration_tire_front_pressure_low", value)
    assert entry.options[CONF_TIRE_PRESSURE_THRESHOLDS]["front"] == {
        "low": value,
        "high": companion,
    }
    assert CONF_TIRE_TEMPERATURE_HIGH not in entry.options
    assert "axle" not in entry.options[CONF_TIRE_PRESSURE_THRESHOLDS]


async def test_registry_upgrade_and_layout_cleanup(hass: HomeAssistant) -> None:
    """Replace old specification sensors and remove only obsolete tire limits."""
    entry = _entry()
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_profile_overall_height",
        config_entry=entry,
    )
    await _setup(hass, entry)
    assert registry.async_get(old.entity_id) is None
    front = _entity(hass, entry, "configuration_tire_front_pressure_low")
    tag = _entity(hass, entry, "configuration_tire_tag_pressure_low")
    height = _entity(hass, entry, "profile_overall_height")
    hass.config_entries.async_update_entry(
        entry,
        data={
            **entry.data,
            CONF_REAR_AXLE_COUNT: 1,
            CONF_TAG_AXLE_PRESENT: False,
        },
    )
    await hass.async_block_till_done()
    assert registry.async_get(tag) is None
    assert registry.async_get(front) is not None
    assert _entity(hass, entry, "profile_overall_height") == height
    data = dict(entry.data)
    data.pop(CONF_REAR_AXLE_COUNT)
    hass.config_entries.async_update_entry(entry, data=data)
    await hass.async_block_till_done()
    assert registry.async_get(front) is None
    assert _entity(hass, entry, "profile_overall_height") == height


async def test_explicit_unit_overrides_and_profile_changes(hass: HomeAssistant) -> None:
    """Preserve user units and convert writes, but let default units follow profiles."""
    hass.config.units = US_CUSTOMARY_SYSTEM
    entry = _entry()
    await _setup(hass, entry)
    registry = er.async_get(hass)
    temperature = _entity(hass, entry, "configuration_tire_temperature_high")
    height = _entity(hass, entry, "profile_overall_height")
    assert hass.states.get(temperature).attributes["unit_of_measurement"] == "°C"
    registry.async_update_entity_options(
        temperature, "number", {"unit_of_measurement": "°F"}
    )
    registry.async_update_entity_options(
        height, "number", {"unit_of_measurement": "ft"}
    )
    await hass.async_block_till_done()
    assert hass.states.get(temperature).attributes["unit_of_measurement"] == "°F"
    assert hass.states.get(temperature).state == "176.0"
    await _set(hass, entry, "configuration_tire_temperature_high", 158)
    assert entry.options[CONF_TIRE_TEMPERATURE_HIGH] == pytest.approx(70)
    assert hass.states.get(temperature).attributes["unit_of_measurement"] == "°F"
    await _set(hass, entry, "profile_overall_height", 10)
    assert entry.data[CONF_OVERALL_HEIGHT] == pytest.approx(3.048)
    assert hass.states.get(height).attributes["unit_of_measurement"] == "ft"

    registry.async_update_entity_options(temperature, "number", {})
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(temperature).attributes["unit_of_measurement"] == "°C"
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_MEASUREMENT_SYSTEM: UNIT_SYSTEM_US_CUSTOMARY}
    )
    await hass.async_block_till_done()
    assert hass.states.get(temperature).attributes["unit_of_measurement"] == "°F"
    registry.async_update_entity_options(
        temperature, "number", {"unit_of_measurement": "°C"}
    )
    await hass.async_block_till_done()
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(temperature).attributes["unit_of_measurement"] == "°C"


async def test_legacy_unit_defaults_align_with_options_form(
    hass: HomeAssistant,
) -> None:
    """Profiles without units use the same HA fallback in controls and forms."""
    hass.config.units = US_CUSTOMARY_SYSTEM
    entry = _entry(configured=False)
    entry.add_to_hass(hass)
    data = dict(entry.data)
    data.pop(CONF_MEASUREMENT_SYSTEM)
    hass.config_entries.async_update_entry(entry, data=data)
    await _setup(hass, entry)
    pressure = hass.states.get(
        _entity(hass, entry, "configuration_tire_front_pressure_low")
    )
    assert pressure.attributes["unit_of_measurement"] == "psi"
    assert pressure.attributes["suggested_default"] == 100
    form = await hass.config_entries.options.async_init(entry.entry_id)
    defaults = {
        key.schema: key.default()
        for key in form["data_schema"].schema
        if callable(key.default)
    }
    assert defaults["tire_front_pressure_low"] == 100
    assert defaults["tire_front_pressure_high"] == 150
    assert defaults[CONF_TIRE_TEMPERATURE_HIGH] == 150


async def test_adding_unknown_capacity_without_a_source(hass: HomeAssistant) -> None:
    """A new capacity creates a tank without inventing a level or percentage."""
    entry = _entry()
    await _setup(hass, entry)
    capacity = _entity(hass, entry, "profile_gray_water_tank_capacity")
    assert hass.states.get(capacity).state == "unknown"
    await _set(hass, entry, "profile_gray_water_tank_capacity", 200)
    assert hass.states.get(capacity).state == "200.0"
    assert (
        hass.states.get(_entity(hass, entry, "tank_gray_water_capacity")).state
        == "200.0"
    )
    assert (
        hass.states.get(_entity(hass, entry, "tank_gray_water_percentage")).state
        == "unavailable"
    )
    assert entry.options[CONF_TANK_ENTITY_MAPPINGS] == {"fresh_water": "number.fresh"}


@pytest.mark.parametrize(
    ("key", "value", "error"),
    [
        (CONF_TIRE_TEMPERATURE_HIGH, -1, "invalid_tire_temperature_threshold"),
        (CONF_TIRE_BATTERY_LOW, 101, "invalid_tire_battery_threshold"),
    ],
)
async def test_native_limits_use_shared_validation(
    hass: HomeAssistant, key: str, value: float, error: str
) -> None:
    """Native writes also enforce limits without relying on HA's service bounds."""
    entry = _entry()
    await _setup(hass, entry)
    control = HavrvConfigurationNumber(
        entry, next(item for item in _descriptions(entry) if item.key == key)
    )
    control.hass = hass
    before = dict(entry.options)
    with pytest.raises(ServiceValidationError) as exc:
        await control.async_set_native_value(value)
    assert exc.value.translation_key == error
    assert entry.options == before


async def test_names_and_exceptions_are_translated(hass: HomeAssistant) -> None:
    """Configuration entities and native validation messages have translations."""
    entry = _entry()
    await _setup(hass, entry)
    translations = await async_get_translations(hass, "en", "entity", {DOMAIN})
    descriptions = _descriptions(entry)
    for description in descriptions:
        assert translations[
            f"component.{DOMAIN}.entity.number.{description.translation_key}.name"
        ]
    with pytest.raises(ServiceValidationError) as exc:
        await _set(hass, entry, "configuration_fresh_water_tank_warning", 20)
    assert exc.value.translation_domain == DOMAIN
    assert exc.value.translation_key == "invalid_tank_threshold"
