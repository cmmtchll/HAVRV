"""Tests for the HAVRV Operations device."""

import pytest
from homeassistant.components.select import (
    ATTR_OPTION,
    ATTR_OPTIONS,
    SERVICE_SELECT_OPTION,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, CONF_NAME
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache,
)

from custom_components.havrv.const import (
    CONF_MEASUREMENT_SYSTEM,
    CONF_TANK_ENTITY_MAPPINGS,
    DOMAIN,
    OPERATION_MODES,
    UNIT_SYSTEM_METRIC,
)


def _entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="RV",
        unique_id="rv",
        data={CONF_NAME: "RV", CONF_MEASUREMENT_SYSTEM: UNIT_SYSTEM_METRIC},
        options={
            CONF_TANK_ENTITY_MAPPINGS: {
                "fresh_water": "sensor.fresh",
                "gray_water": "sensor.gray",
            },
        },
        version=3,
    )


def _entity_id(hass: HomeAssistant, entry: MockConfigEntry, suffix: str) -> str:
    registry = er.async_get(hass)
    return next(
        ent.entity_id
        for ent in er.async_entries_for_config_entry(registry, entry.entry_id)
        if ent.unique_id == f"{entry.entry_id}_{suffix}"
    )


async def _select(hass: HomeAssistant, entity_id: str, option: str) -> None:
    await hass.services.async_call(
        "select",
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: entity_id, ATTR_OPTION: option},
        blocking=True,
    )
    await hass.async_block_till_done()


async def test_operations_device_mode_drives_tank_alerts(hass: HomeAssistant) -> None:
    """The mode select lives on its own device and adjusts tank status."""
    hass.states.async_set("sensor.fresh", "10", {"unit_of_measurement": "%"})
    hass.states.async_set("sensor.gray", "90", {"unit_of_measurement": "%"})
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    mode = _entity_id(hass, entry, "operations_mode")
    fresh = _entity_id(hass, entry, "tank_fresh_water_status")
    gray = _entity_id(hass, entry, "tank_gray_water_status")
    state = hass.states.get(mode)
    assert state.state == "unknown"
    assert state.attributes[ATTR_OPTIONS] == list(OPERATION_MODES)
    assert hass.states.get(fresh).state == "problem"

    device_registry = dr.async_get(hass)
    operations = device_registry.async_get_device_by_identifier(
        (DOMAIN, f"{entry.entry_id}_operations"), entry.entry_id
    )
    rv_device = device_registry.async_get_device_by_identifier(
        (DOMAIN, entry.entry_id), entry.entry_id
    )
    assert operations is not None
    assert operations.name == "Operations"
    assert operations.via_device_id == rv_device.id
    assert er.async_get(hass).async_get(mode).device_id == operations.id

    await _select(hass, mode, "storage")
    assert hass.states.get(mode).state == "storage"
    assert hass.states.get(fresh).state == "ok"
    assert hass.states.get(gray).state == "problem"

    await _select(hass, mode, "driving")
    assert hass.states.get(fresh).state == "problem"

    with pytest.raises(ServiceValidationError):
        await _select(hass, mode, "parked")
    assert hass.states.get(mode).state == "driving"

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_operation_mode_restored_before_tank_status(
    hass: HomeAssistant,
) -> None:
    """A restored mode applies to tank status from the first state written."""
    hass.states.async_set("sensor.fresh", "10", {"unit_of_measurement": "%"})
    entry = _entry()
    registry = er.async_get(hass)
    mode_entry = registry.async_get_or_create(
        "select",
        DOMAIN,
        f"{entry.entry_id}_operations_mode",
        suggested_object_id="rv_operation_mode",
    )
    mock_restore_cache(hass, [State(mode_entry.entity_id, "storage")])
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    fresh = _entity_id(hass, entry, "tank_fresh_water_status")
    assert hass.states.get(mode_entry.entity_id).state == "storage"
    assert entry.runtime_data.operation_mode == "storage"
    assert hass.states.get(fresh).state == "ok"

    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(mode_entry.entity_id).state == "storage"
    assert hass.states.get(fresh).state == "ok"


async def test_unknown_restored_mode_is_ignored(hass: HomeAssistant) -> None:
    """An unsupported restored mode leaves the mode unselected."""
    entry = _entry()
    registry = er.async_get(hass)
    mode_entry = registry.async_get_or_create(
        "select",
        DOMAIN,
        f"{entry.entry_id}_operations_mode",
        suggested_object_id="rv_operation_mode",
    )
    mock_restore_cache(hass, [State(mode_entry.entity_id, "parked")])
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(mode_entry.entity_id).state == "unknown"
    assert entry.runtime_data.operation_mode is None
