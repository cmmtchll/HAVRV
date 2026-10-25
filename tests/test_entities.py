"""Tests for mapped HAVRV entities."""

from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.climate import ClimateEntityFeature
from homeassistant.components.light import ColorMode
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import CONF_NAME, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util.unit_system import METRIC_SYSTEM, US_CUSTOMARY_SYSTEM
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.havrv import (
    binary_sensor,
    climate,
    light,
    number,
    select,
    sensor,
    switch,
)
from custom_components.havrv.binary_sensor import HavrvBinarySensor
from custom_components.havrv.climate import HavrvClimate
from custom_components.havrv.const import (
    CONF_TIRE_BATTERY_LOW,
    CONF_TIRE_ENTITY_MAPPINGS,
    CONF_TIRE_PRESSURE_THRESHOLDS,
    CONF_TIRE_TEMPERATURE_HIGH,
    DOMAIN,
    TIRE_BATTERY,
    TIRE_FRONT,
    TIRE_PRESSURE,
    TIRE_TEMPERATURE,
    UNIT_SYSTEM_METRIC,
    UNIT_SYSTEM_US_CUSTOMARY,
)
from custom_components.havrv.light import HavrvLight
from custom_components.havrv.sensor import HavrvSensor, HavrvTireSensor
from custom_components.havrv.switch import HavrvSwitch
from custom_components.havrv.tire import (
    TirePosition,
    _numeric_state,
    overall_tire_problem,
    pressure_in_profile_units,
    temperature_in_profile_units,
    tire_data_present,
    tire_positions,
    tire_problem,
)


@pytest.mark.parametrize(
    "platform",
    [binary_sensor, climate, light, number, select, sensor, switch],
    ids=["binary_sensor", "climate", "light", "number", "select", "sensor", "switch"],
)
def test_platforms_declare_parallel_updates(platform: ModuleType) -> None:
    """Declare no extra parallelism for event-driven proxies."""
    assert platform.PARALLEL_UPDATES == 0


def _entry(*, options: dict | None = None) -> MockConfigEntry:
    """Create a profile entry for entity tests."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Test RV",
        data={CONF_NAME: "Test RV"},
        options=options or {},
        unique_id="test rv",
    )


def _attach_to_hass(entity: object, hass: HomeAssistant) -> None:
    """Attach an entity to Home Assistant for property and action tests."""
    entity.hass = hass


async def test_sensor_mirrors_numeric_metadata_and_unavailable_state(
    hass: HomeAssistant,
) -> None:
    """Mirror sensor state, metadata, and unavailable status."""
    hass.states.async_set(
        "sensor.battery_voltage",
        "13.4",
        {
            "friendly_name": "Battery Voltage",
            "unit_of_measurement": "V",
            "icon": "mdi:car-battery",
            "device_class": "voltage",
            "state_class": "measurement",
            "suggested_display_precision": 1,
        },
    )
    entity = HavrvSensor(_entry(), "power", "sensor.battery_voltage", "parent")
    _attach_to_hass(entity, hass)

    assert entity.available
    assert entity.name == "Battery Voltage"
    assert entity.native_value == 13.4
    assert entity.native_unit_of_measurement == "V"
    assert entity.icon == "mdi:car-battery"
    assert entity.device_class is SensorDeviceClass.VOLTAGE
    assert entity.state_class is SensorStateClass.MEASUREMENT
    assert entity.suggested_display_precision == 1

    hass.states.async_set("sensor.battery_voltage", "unknown")
    assert not entity.available
    assert entity.native_value is None

    hass.states.async_remove("sensor.battery_voltage")
    assert not entity.available
    assert entity.name == "sensor.battery_voltage"


@pytest.mark.parametrize("units", [UNIT_SYSTEM_METRIC, UNIT_SYSTEM_US_CUSTOMARY])
async def test_generic_numeric_helpers_honor_profile_units_and_overrides(
    hass: HomeAssistant,
    units: str,
) -> None:
    """Helpers/templates mirror read-only readings in profile, not HA global, units."""
    metric = units == UNIT_SYSTEM_METRIC
    hass.config.units = US_CUSTOMARY_SYSTEM if metric else METRIC_SYSTEM
    readings = (
        ("sensor.template_temperature", "temperature", 100, "°F", "°C", 37.7777778),
        ("number.template_pressure", "pressure", 100, "psi", "kPa", 689.4757293),
        ("input_number.volume", None, 10, "gal", "L", 37.85411784),
        ("number.length", "distance", 10, "ft", "m", 3.048),
        ("input_number.mass", "weight", 10, "lb", "kg", 4.5359237),
        ("sensor.area", "area", 100, "ft²", "m²", 9.290304),
        ("sensor.speed", "speed", 55, "mph", "km/h", 88.51392),
    )
    for source, device_class, value, source_unit, _, _ in readings:
        attributes = {"unit_of_measurement": source_unit}
        if device_class:
            attributes["device_class"] = device_class
        hass.states.async_set(source, str(value), attributes)
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=3,
        data={
            CONF_NAME: "Units RV",
            "measurement_system": units,
            "entity_mappings": {"other": [row[0] for row in readings]},
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    registry = er.async_get(hass)
    for source, _, value, source_unit, profile_unit, expected in readings:
        entity_id = registry.async_get_entity_id(
            "sensor",
            DOMAIN,
            f"{entry.entry_id}_other_{source}",
        )
        state = hass.states.get(entity_id)
        assert float(state.state) == pytest.approx(expected if metric else value)
        assert state.attributes["unit_of_measurement"] == (
            profile_unit if metric else source_unit
        )
        assert hass.states.get(source).state == str(value)
    temperature_id = registry.async_get_entity_id(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_other_sensor.template_temperature",
    )
    registry.async_update_entity_options(
        temperature_id,
        "sensor",
        {"unit_of_measurement": "K"},
    )
    await hass.async_block_till_done()
    temperature = hass.states.get(temperature_id)
    assert temperature.attributes["unit_of_measurement"] == "K"
    assert float(temperature.state) == pytest.approx(310.9277778)
    helper_id = registry.async_get_entity_id(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_other_input_number.volume",
    )
    hass.states.async_set("input_number.volume", "unavailable")
    await hass.async_block_till_done()
    assert hass.states.get(helper_id).state == "unavailable"
    hass.states.async_set("input_number.volume", "nan", {"unit_of_measurement": "gal"})
    await hass.async_block_till_done()
    assert hass.states.get(helper_id).state == "unknown"
    hass.states.async_set("input_number.volume", "20", {"unit_of_measurement": "gal"})
    await hass.async_block_till_done()
    assert float(hass.states.get(helper_id).state) == pytest.approx(
        75.70823568 if metric else 20,
    )
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_binary_sensor_mirrors_source_state_and_class(
    hass: HomeAssistant,
) -> None:
    """Mirror a source binary sensor and its device class."""
    hass.states.async_set(
        "binary_sensor.door",
        "on",
        {"friendly_name": "Storage Door", "icon": "mdi:door", "device_class": "door"},
    )
    entity = HavrvBinarySensor(_entry(), "chassis", "binary_sensor.door", "parent")
    _attach_to_hass(entity, hass)

    assert entity.available
    assert entity.name == "Storage Door"
    assert entity.is_on is True
    assert entity.icon == "mdi:door"
    assert entity.device_class is BinarySensorDeviceClass.DOOR

    hass.states.async_set("binary_sensor.door", "off")
    assert entity.is_on is False
    hass.states.async_set("binary_sensor.door", "unavailable")
    assert entity.is_on is None
    assert not entity.available


async def test_source_entity_category_is_preserved(hass: HomeAssistant) -> None:
    """Keep the mapped source entity's registry category."""
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "sensor",
        "source_integration",
        "sensor.private_diagnostic",
        suggested_object_id="private_diagnostic",
        entity_category=EntityCategory.DIAGNOSTIC,
    )
    entity = HavrvSensor(_entry(), "power", "sensor.private_diagnostic", "parent")
    _attach_to_hass(entity, hass)

    assert entity.entity_category is EntityCategory.DIAGNOSTIC


async def test_switch_forwards_control_services(hass: HomeAssistant) -> None:
    """Forward switch actions to the mapped source."""
    hass.states.async_set(
        "switch.water_pump", "on", {"friendly_name": "Water Pump", "icon": "mdi:pump"}
    )
    entity = HavrvSwitch(_entry(), "water", "switch.water_pump", "parent")
    _attach_to_hass(entity, hass)

    assert entity.available
    assert entity.is_on is True
    assert entity.name == "Water Pump"
    assert entity.icon == "mdi:pump"

    with patch.object(
        type(hass.services), "async_call", new_callable=AsyncMock
    ) as async_call:
        await entity.async_turn_on()
        await entity.async_turn_off()
        await entity.async_toggle()

    assert [call.args[:3] for call in async_call.await_args_list] == [
        ("switch", "turn_on", {"entity_id": "switch.water_pump"}),
        ("switch", "turn_off", {"entity_id": "switch.water_pump"}),
        ("switch", "toggle", {"entity_id": "switch.water_pump"}),
    ]


async def test_light_mirrors_capabilities_and_forwards_control(
    hass: HomeAssistant,
) -> None:
    """Mirror light state and forward supported control arguments."""
    hass.states.async_set(
        "light.patio",
        "off",
        {
            "friendly_name": "Patio Light",
            "icon": "mdi:lightbulb",
            "supported_color_modes": ["onoff"],
        },
    )
    entity = HavrvLight(_entry(), "power", "light.patio", "parent")
    _attach_to_hass(entity, hass)

    assert entity.available
    assert entity.is_on is False
    assert entity.name == "Patio Light"
    assert entity.icon == "mdi:lightbulb"
    assert entity.supported_color_modes == {ColorMode.ONOFF}

    with patch.object(
        type(hass.services), "async_call", new_callable=AsyncMock
    ) as async_call:
        await entity.async_turn_on(brightness=120)
        await entity.async_turn_off()

    assert async_call.await_args_list[0].args[:3] == (
        "light",
        "turn_on",
        {"entity_id": "light.patio", "brightness": 120},
    )
    assert async_call.await_args_list[1].args[:3] == (
        "light",
        "turn_off",
        {"entity_id": "light.patio"},
    )


async def test_climate_mirrors_attributes_and_forwards_controls(
    hass: HomeAssistant,
) -> None:
    """Mirror climate capabilities and forward its supported controls."""
    features = ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE
    hass.states.async_set(
        "climate.living_area",
        "heat",
        {
            "friendly_name": "Living Area",
            "icon": "mdi:thermostat",
            "hvac_modes": ["off", "heat"],
            "current_temperature": 20.5,
            "current_humidity": 40,
            "temperature": 22,
            "target_temp_high": 25,
            "target_temp_low": 18,
            "fan_mode": "auto",
            "fan_modes": ["auto", "high"],
            "min_temp": 10,
            "max_temp": 30,
            "target_temp_step": 0.5,
            "temperature_unit": "°C",
            "supported_features": features,
            "preset_mode": "eco",
            "preset_modes": ["eco", "comfort"],
            "swing_mode": "on",
            "swing_modes": ["on", "off"],
            "humidity": 45,
            "min_humidity": 30,
            "max_humidity": 80,
        },
    )
    entity = HavrvClimate(_entry(), "climate", "climate.living_area", "parent")
    _attach_to_hass(entity, hass)

    assert entity.available
    assert entity.name == "Living Area"
    assert entity.icon == "mdi:thermostat"
    assert entity.hvac_mode == "heat"
    assert entity.hvac_modes == ["off", "heat"]
    assert entity.current_temperature == 20.5
    assert entity.current_humidity == 40
    assert entity.target_temperature == 22
    assert entity.target_temperature_high == 25
    assert entity.target_temperature_low == 18
    assert entity.fan_mode == "auto"
    assert entity.fan_modes == ["auto", "high"]
    assert entity.min_temp == 10
    assert entity.max_temp == 30
    assert entity.target_temperature_step == 0.5
    assert entity.temperature_unit == "°C"
    assert entity.supported_features == features
    assert entity.preset_mode == "eco"
    assert entity.preset_modes == ["eco", "comfort"]
    assert entity.swing_mode == "on"
    assert entity.swing_modes == ["on", "off"]
    assert entity.target_humidity == 45
    assert entity.min_humidity == 30
    assert entity.max_humidity == 80

    with patch.object(
        type(hass.services), "async_call", new_callable=AsyncMock
    ) as async_call:
        await entity.async_set_hvac_mode("off")
        await entity.async_set_temperature(temperature=21)
        await entity.async_set_fan_mode("high")
        await entity.async_set_preset_mode("comfort")
        await entity.async_set_swing_mode("off")
        await entity.async_set_humidity(50)

    assert [call.args[1:] for call in async_call.await_args_list] == [
        ("set_hvac_mode", {"entity_id": "climate.living_area", "hvac_mode": "off"}),
        (
            "set_temperature",
            {"entity_id": "climate.living_area", "temperature": 21},
        ),
        ("set_fan_mode", {"entity_id": "climate.living_area", "fan_mode": "high"}),
        (
            "set_preset_mode",
            {"entity_id": "climate.living_area", "preset_mode": "comfort"},
        ),
        ("set_swing_mode", {"entity_id": "climate.living_area", "swing_mode": "off"}),
        ("set_humidity", {"entity_id": "climate.living_area", "humidity": 50}),
    ]


@pytest.mark.parametrize(
    ("value", "unit", "measurement_system", "expected"),
    [
        (10, "psi", UNIT_SYSTEM_METRIC, pytest.approx(68.9476)),
        (100, "kPa", UNIT_SYSTEM_US_CUSTOMARY, pytest.approx(14.5038, abs=0.001)),
        (1, "bar", UNIT_SYSTEM_METRIC, 100),
        (1, "bar", UNIT_SYSTEM_US_CUSTOMARY, pytest.approx(14.5038, abs=0.001)),
        (10, None, UNIT_SYSTEM_METRIC, 10),
        (10, "mmHg", UNIT_SYSTEM_METRIC, None),
    ],
)
def test_pressure_conversion(
    value: float, unit: str | None, measurement_system: str, expected: float | None
) -> None:
    """Convert supported tire-pressure source units to profile units."""
    assert pressure_in_profile_units(value, unit, measurement_system) == expected


@pytest.mark.parametrize(
    ("value", "unit", "measurement_system", "expected"),
    [
        (32, "°F", UNIT_SYSTEM_METRIC, 0),
        (0, "°C", UNIT_SYSTEM_US_CUSTOMARY, 32),
        (20, "°C", UNIT_SYSTEM_METRIC, 20),
        (68, "°F", UNIT_SYSTEM_US_CUSTOMARY, 68),
        (20, None, UNIT_SYSTEM_METRIC, 20),
        (20, "K", UNIT_SYSTEM_METRIC, None),
    ],
)
def test_temperature_conversion(
    value: float, unit: str | None, measurement_system: str, expected: float | None
) -> None:
    """Convert supported tire-temperature source units to profile units."""
    assert temperature_in_profile_units(value, unit, measurement_system) == expected


def test_tire_positions_require_known_axle_and_wheel_layout() -> None:
    """Avoid inventing rear tire positions for incomplete or invalid layouts."""
    assert tire_positions({}) == []
    assert tire_positions({"rear_axle_count": 1})[0].key == "front_left"
    assert tire_positions(
        {
            "rear_axle_count": 1,
            "main_rear_wheel_configuration": "unknown",
        }
    ) == tire_positions({"rear_axle_count": 1})


async def test_tire_data_and_threshold_evaluation_reject_invalid_sources(
    hass: HomeAssistant,
) -> None:
    """Handle missing, nonnumeric, and unit-incompatible tire source readings."""
    position = TirePosition("front_left", "Front Left Tire", TIRE_FRONT)
    entry = _entry(
        options={
            CONF_TIRE_ENTITY_MAPPINGS: {
                "front_left_pressure": "sensor.tire_pressure",
                "front_left_temperature": "sensor.tire_temperature",
                "front_left_battery": "sensor.tire_battery",
            },
            CONF_TIRE_PRESSURE_THRESHOLDS: {
                TIRE_FRONT: {"low": 300, "high": 800},
            },
            CONF_TIRE_TEMPERATURE_HIGH: 60,
            CONF_TIRE_BATTERY_LOW: 20,
        }
    )
    entry.runtime_data = SimpleNamespace(measurement_system=UNIT_SYSTEM_METRIC)
    hass.states.async_set("sensor.tire_pressure", "nan", {"unit_of_measurement": "psi"})
    hass.states.async_set(
        "sensor.tire_temperature", "40", {"unit_of_measurement": "kelvin"}
    )
    hass.states.async_set("sensor.tire_battery", "10", {"unit_of_measurement": "V"})

    assert not tire_data_present(hass, entry, position)
    assert _numeric_state(hass, None) is None
    assert _numeric_state(hass, "sensor.missing") is None
    assert tire_problem(hass, entry, position, TIRE_PRESSURE) is None
    assert tire_problem(hass, entry, position, TIRE_TEMPERATURE) is None
    assert tire_problem(hass, entry, position, TIRE_BATTERY) is None
    with pytest.raises(ValueError, match="Unsupported tire problem"):
        tire_problem(hass, entry, position, "unknown")
    assert overall_tire_problem(hass, entry, position)

    hass.states.async_set("sensor.tire_pressure", "unavailable")
    assert _numeric_state(hass, "sensor.tire_pressure") is None
    hass.states.async_set("sensor.tire_pressure", "pressure-error")
    assert _numeric_state(hass, "sensor.tire_pressure") is None

    hass.states.async_set(
        "sensor.tire_pressure", "500", {"unit_of_measurement": "mmHg"}
    )
    hass.states.async_set(
        "sensor.tire_temperature", "20", {"unit_of_measurement": "°C"}
    )
    hass.states.async_set("sensor.tire_battery", "50", {"unit_of_measurement": "%"})
    assert tire_data_present(hass, entry, position)
    assert tire_problem(hass, entry, position, TIRE_PRESSURE) is None
    assert overall_tire_problem(hass, entry, position)


async def test_tire_problem_limits_default_battery_threshold(
    hass: HomeAssistant,
) -> None:
    """Evaluate battery problem with the default threshold when unset."""
    position = TirePosition("front_left", "Front Left Tire", TIRE_FRONT)
    entry = _entry(
        options={
            CONF_TIRE_ENTITY_MAPPINGS: {
                "front_left_pressure": "sensor.tire_pressure",
                "front_left_temperature": "sensor.tire_temperature",
                "front_left_battery": "sensor.tire_battery",
            },
        }
    )
    entry.runtime_data = SimpleNamespace(measurement_system=UNIT_SYSTEM_METRIC)
    hass.states.async_set("sensor.tire_pressure", "500", {"unit_of_measurement": "kPa"})
    hass.states.async_set(
        "sensor.tire_temperature", "20", {"unit_of_measurement": "°C"}
    )
    hass.states.async_set("sensor.tire_battery", "50")

    assert tire_problem(hass, entry, position, TIRE_PRESSURE) is None
    assert tire_problem(hass, entry, position, TIRE_TEMPERATURE) is None
    assert tire_problem(hass, entry, position, TIRE_BATTERY) is False
    assert tire_data_present(hass, entry, position)
    assert not overall_tire_problem(hass, entry, position)

    hass.states.async_set("sensor.tire_battery", "15", {"unit_of_measurement": "%"})
    assert tire_problem(hass, entry, position, TIRE_BATTERY) is True


@pytest.mark.parametrize("domain", ["binary_sensor", "input_boolean", "switch"])
@pytest.mark.parametrize("threshold", [None, 0, 100])
async def test_tire_boolean_battery_health(
    hass: HomeAssistant, domain: str, threshold: float | None
) -> None:
    """Mirror boolean health without percentages, thresholds, or numeric metadata."""
    position = TirePosition("front_left", "Front Left Tire", TIRE_FRONT)
    entity_id = f"{domain}.battery_ok"
    entry = _entry(
        options={
            CONF_TIRE_ENTITY_MAPPINGS: {
                "front_left_pressure": "sensor.pressure",
                "front_left_temperature": "sensor.temperature",
                "front_left_battery": entity_id,
            },
            **({CONF_TIRE_BATTERY_LOW: threshold} if threshold is not None else {}),
        }
    )
    entry.runtime_data = SimpleNamespace(
        measurement_system=UNIT_SYSTEM_METRIC, device_id="rv"
    )
    battery = HavrvTireSensor(entry, position, TIRE_BATTERY)
    _attach_to_hass(battery, hass)
    hass.states.async_set("sensor.pressure", "500")
    hass.states.async_set("sensor.temperature", "20")

    for state in (None, "unknown", "unavailable", "invalid", "50"):
        if state is not None:
            hass.states.async_set(entity_id, state)
        assert not battery.available
        assert battery.native_value is None
        assert tire_problem(hass, entry, position, TIRE_BATTERY) is None
        assert not tire_data_present(hass, entry, position)
        assert overall_tire_problem(hass, entry, position)

    for state, problem in (("on", False), ("off", True), ("on", False)):
        hass.states.async_set(
            entity_id,
            state,
            {"device_class": "battery", "state_class": "measurement"},
        )
        assert battery.available
        assert battery.native_value == state
        assert battery.native_unit_of_measurement is None
        assert battery.device_class is None
        assert battery.state_class is None
        assert tire_problem(hass, entry, position, TIRE_BATTERY) is problem
        assert tire_data_present(hass, entry, position)
        assert overall_tire_problem(hass, entry, position) is problem
