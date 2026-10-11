"""Tests for the aggregate tire monitor."""

import pytest
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.havrv.const import (
    CONF_MAIN_REAR_WHEEL_CONFIGURATION,
    CONF_MEASUREMENT_SYSTEM,
    CONF_REAR_AXLE_COUNT,
    CONF_TIRE_ENTITY_MAPPINGS,
    DOMAIN,
    UNIT_SYSTEM_METRIC,
)


def _entry(
    readings: dict[str, tuple[str, float, str]],
    *,
    rear_wheels: str = "dual",
    rear_axles: int = 1,
) -> MockConfigEntry:
    """Create an RV profile with the requested mapped tire readings."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Monitor RV",
        unique_id="monitor rv",
        data={
            CONF_NAME: "Monitor RV",
            CONF_MEASUREMENT_SYSTEM: UNIT_SYSTEM_METRIC,
            CONF_REAR_AXLE_COUNT: rear_axles,
            CONF_MAIN_REAR_WHEEL_CONFIGURATION: rear_wheels,
        },
        options={
            CONF_TIRE_ENTITY_MAPPINGS: {
                key: entity_id for key, (entity_id, _, _) in readings.items()
            }
        },
        version=3,
    )


def _set_readings(
    hass: HomeAssistant, readings: dict[str, tuple[str, float, str]]
) -> None:
    """Set each mapped source state and its unit."""
    for entity_id, value, unit in readings.values():
        hass.states.async_set(entity_id, str(value), {"unit_of_measurement": unit})


def _entity(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    group_key: str,
    metric: str,
    analysis: str,
) -> er.RegistryEntry:
    """Find one monitor entity by its stable unique ID."""
    unique_id = f"{entry.entry_id}_tire_monitor_{group_key}_{metric}_{analysis}"
    return next(
        entity
        for entity in er.async_entries_for_config_entry(
            er.async_get(hass), entry.entry_id
        )
        if entity.unique_id == unique_id
    )


async def test_monitor_reports_spread_and_no_outlier_for_agreeing_peers(
    hass: HomeAssistant,
) -> None:
    """Report comparable pressure and separate inner/outer temperature spreads."""
    readings = {
        "rear_axle_1_left_inner_pressure": ("sensor.left_inner_pressure", 300, "kPa"),
        "rear_axle_1_right_inner_pressure": (
            "sensor.right_inner_pressure",
            300,
            "kPa",
        ),
        "rear_axle_1_left_outer_pressure": (
            "sensor.left_outer_pressure",
            300,
            "kPa",
        ),
        "rear_axle_1_right_outer_pressure": (
            "sensor.right_outer_pressure",
            300,
            "kPa",
        ),
        "rear_axle_1_left_inner_temperature": (
            "sensor.left_inner_temperature",
            40,
            "°C",
        ),
        "rear_axle_1_right_inner_temperature": (
            "sensor.right_inner_temperature",
            42,
            "°C",
        ),
        "rear_axle_1_left_outer_temperature": (
            "sensor.left_outer_temperature",
            55,
            "°C",
        ),
        "rear_axle_1_right_outer_temperature": (
            "sensor.right_outer_temperature",
            55,
            "°C",
        ),
    }
    _set_readings(hass, readings)
    entry = _entry(readings)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    pressure_spread = _entity(hass, entry, "rear_axle_1", "pressure", "spread")
    pressure_outlier = _entity(hass, entry, "rear_axle_1", "pressure", "outlier")
    inner_spread = _entity(hass, entry, "rear_axle_1_inner", "temperature", "spread")
    outer_spread = _entity(hass, entry, "rear_axle_1_outer", "temperature", "spread")
    assert hass.states.get(pressure_spread.entity_id).state == "0.0"
    assert (
        hass.states.get(pressure_spread.entity_id).attributes["unit_of_measurement"]
        == "kPa"
    )
    assert (
        hass.states.get(pressure_spread.entity_id)
        .attributes["friendly_name"]
        .endswith("Rear axle 1 pressure spread")
    )
    assert hass.states.get(pressure_outlier.entity_id).state == "No outlier"
    assert hass.states.get(inner_spread.entity_id).state == "2.0"
    assert hass.states.get(outer_spread.entity_id).state == "0.0"
    await hass.config_entries.async_unload(entry.entry_id)


async def test_monitor_finds_one_relative_outlier_and_normalizes_mixed_units(
    hass: HomeAssistant,
) -> None:
    """Find a unique peer outlier after converting pressure units."""
    readings = {
        "rear_axle_1_left_inner_pressure": ("sensor.left_inner_pressure", 300, "kPa"),
        "rear_axle_1_right_inner_pressure": (
            "sensor.right_inner_pressure",
            301,
            "kPa",
        ),
        "rear_axle_1_left_outer_pressure": (
            "sensor.left_outer_pressure",
            302,
            "kPa",
        ),
        "rear_axle_1_right_outer_pressure": (
            "sensor.right_outer_pressure",
            58.0151,
            "psi",
        ),
    }
    _set_readings(hass, readings)
    entry = _entry(readings)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    spread = _entity(hass, entry, "rear_axle_1", "pressure", "spread")
    outlier = _entity(hass, entry, "rear_axle_1", "pressure", "outlier")
    assert float(hass.states.get(spread.entity_id).state) == pytest.approx(100, abs=0.1)
    assert hass.states.get(outlier.entity_id).state == "Rear Axle 1 Right Outer Tire"
    await hass.config_entries.async_unload(entry.entry_id)


async def test_monitor_handles_missing_unavailable_and_incomparable_sources(
    hass: HomeAssistant,
) -> None:
    """Do not compare groups with too few usable, compatible readings."""
    readings = {
        "front_left_pressure": ("sensor.front_left_pressure", 300, "kPa"),
        "front_right_pressure": ("sensor.front_right_pressure", 50, "mmHg"),
    }
    _set_readings(hass, readings)
    hass.states.async_set("sensor.front_right_pressure", "unavailable")
    entry = _entry(readings, rear_wheels="single")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    spread = _entity(hass, entry, "front", "pressure", "spread")
    outlier = _entity(hass, entry, "front", "pressure", "outlier")
    assert hass.states.get(spread.entity_id).state == "unavailable"
    assert hass.states.get(outlier.entity_id).state == "unavailable"

    hass.states.async_set(
        "sensor.front_right_pressure", "50", {"unit_of_measurement": "mmHg"}
    )
    await hass.async_block_till_done()
    assert hass.states.get(spread.entity_id).state == "unavailable"
    await hass.config_entries.async_unload(entry.entry_id)


async def test_monitor_keeps_axle_comparisons_separate_and_reloads_cleanly(
    hass: HomeAssistant,
) -> None:
    """Keep per-axle statistics distinct and restore the same entities on reload."""
    readings = {
        "front_left_pressure": ("sensor.front_left_pressure", 300, "kPa"),
        "front_right_pressure": ("sensor.front_right_pressure", 310, "kPa"),
        "rear_axle_1_left_pressure": ("sensor.rear_left_pressure", 500, "kPa"),
        "rear_axle_1_right_pressure": ("sensor.rear_right_pressure", 520, "kPa"),
    }
    _set_readings(hass, readings)
    entry = _entry(readings, rear_wheels="single")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    front = _entity(hass, entry, "front", "pressure", "spread")
    rear = _entity(hass, entry, "rear_axle_1", "pressure", "spread")
    monitor = next(
        device
        for device in dr.async_entries_for_config_entry(
            dr.async_get(hass), entry.entry_id
        )
        if device.name == "All Tire Monitor"
    )
    rv_device = next(
        device
        for device in dr.async_entries_for_config_entry(
            dr.async_get(hass), entry.entry_id
        )
        if device.name == "Monitor RV"
    )
    assert monitor.via_device_id == rv_device.id
    assert hass.states.get(front.entity_id).state == "10.0"
    assert hass.states.get(rear.entity_id).state == "20.0"
    registered_ids = {
        entity.unique_id
        for entity in er.async_entries_for_config_entry(
            er.async_get(hass), entry.entry_id
        )
        if "_tire_monitor_" in entity.unique_id
    }

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert registered_ids == {
        entity.unique_id
        for entity in er.async_entries_for_config_entry(
            er.async_get(hass), entry.entry_id
        )
        if "_tire_monitor_" in entity.unique_id
    }

    hass.states.async_set(
        "sensor.front_right_pressure", "330", {"unit_of_measurement": "kPa"}
    )
    await hass.async_block_till_done()
    assert hass.states.get(front.entity_id).state == "30.0"
    await hass.config_entries.async_unload(entry.entry_id)
