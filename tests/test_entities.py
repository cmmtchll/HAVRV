"""Tests for mapped HAVRV entities."""

from unittest.mock import AsyncMock, patch

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.climate import ClimateEntityFeature
from homeassistant.components.light import ColorMode
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.havrv.binary_sensor import HavrvBinarySensor
from custom_components.havrv.climate import HavrvClimate
from custom_components.havrv.const import DOMAIN
from custom_components.havrv.light import HavrvLight
from custom_components.havrv.sensor import HavrvSensor
from custom_components.havrv.switch import HavrvSwitch


def _entry() -> MockConfigEntry:
    """Create a profile entry for entity tests."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Test RV",
        data={CONF_NAME: "Test RV"},
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
