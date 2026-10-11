"""Tests for derived tank values."""

from datetime import UTC, datetime

from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache,
)

from custom_components.havrv.const import (
    CONF_ENTITY_MAPPINGS,
    CONF_FRESH_WATER_TANK_CAPACITY,
    CONF_MEASUREMENT_SYSTEM,
    CONF_TANK_ENTITY_MAPPINGS,
    CONF_TANK_THRESHOLDS,
    DOMAIN,
)
from custom_components.havrv.const import (
    UNIT_SYSTEM_METRIC as METRIC,
)
from custom_components.havrv.tank import tank_percent, tank_status, thresholds_valid


def test_tank_percent() -> None:
    """Derive percentages from percent or volume sources."""
    assert tank_percent(40, "%", None, None) == 40
    assert tank_percent(150, "%", None, None) == 100
    assert tank_percent(-5, "%", None, None) == 0
    assert tank_percent(50, "L", 200, "L") == 25
    assert tank_percent(50, "gal", 100, "L") == 100
    assert tank_percent(50, "L", None, None) is None
    assert tank_percent(50, "L", 200, "bogus") is None
    assert tank_percent(50, "psi", 200, "L") is None


def test_tank_status_direction() -> None:
    """Fresh water trips low; waste trips high."""
    assert tank_status("fresh_water", None, 20, 10) is None
    assert tank_status("fresh_water", 50, 20, 10) == "ok"
    assert tank_status("fresh_water", 15, 20, 10) == "warning"
    assert tank_status("fresh_water", 5, 20, 10) == "problem"
    assert tank_status("gray_water", 50, 80, 95) == "ok"
    assert tank_status("gray_water", 85, 80, 95) == "warning"
    assert tank_status("gray_water", 99, 80, 95) == "problem"


def test_thresholds_valid() -> None:
    """Validate range and ordering."""
    assert thresholds_valid("fresh_water", 20, 10)
    assert not thresholds_valid("fresh_water", 10, 20)
    assert thresholds_valid("black_water", 80, 95)
    assert not thresholds_valid("black_water", 95, 80)
    assert not thresholds_valid("black_water", 80, 101)


def _entry(thresholds: dict | None = None) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="RV",
        unique_id="rv",
        data={
            CONF_NAME: "RV",
            CONF_MEASUREMENT_SYSTEM: METRIC,
            CONF_ENTITY_MAPPINGS: {},
            CONF_FRESH_WATER_TANK_CAPACITY: 200.0,
        },
        options={
            CONF_TANK_ENTITY_MAPPINGS: {
                "fresh_water": "sensor.fresh",
                "gray_water": "sensor.gray",
            },
            CONF_TANK_THRESHOLDS: thresholds or {},
        },
        version=3,
    )


def _find(hass: HomeAssistant, entry: MockConfigEntry, suffix: str) -> str | None:
    registry = er.async_get(hass)
    for ent in er.async_entries_for_config_entry(registry, entry.entry_id):
        if ent.unique_id == f"{entry.entry_id}_{suffix}":
            return ent.entity_id
    return None


async def test_derived_tank_entities(hass: HomeAssistant) -> None:
    """Percentage, status and history entities follow the source."""
    hass.states.async_set("sensor.fresh", "100", {"unit_of_measurement": "L"})
    hass.states.async_set("sensor.gray", "50", {"unit_of_measurement": "%"})
    entry = _entry({"fresh_water": {"warning": 30.0, "problem": 10.0}})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    pct = _find(hass, entry, "tank_fresh_water_percentage")
    status = _find(hass, entry, "tank_fresh_water_status")
    filled = _find(hass, entry, "tank_fresh_water_last_filled")
    emptied = _find(hass, entry, "tank_gray_water_last_emptied")
    assert _find(hass, entry, "tank_gray_water_status") is not None
    assert hass.states.get(pct).state == "50.0"
    assert hass.states.get(status).state == "ok"
    assert hass.states.get(filled).state == "unknown"

    hass.states.async_set("sensor.fresh", "50", {"unit_of_measurement": "L"})
    await hass.async_block_till_done()
    assert hass.states.get(status).state == "warning"
    hass.states.async_set("sensor.fresh", "10", {"unit_of_measurement": "L"})
    await hass.async_block_till_done()
    assert hass.states.get(status).state == "problem"

    hass.states.async_set("sensor.fresh", "unavailable")
    await hass.async_block_till_done()
    assert hass.states.get(pct).state == "unavailable"
    assert hass.states.get(filled).state == "unknown"
    hass.states.async_set("sensor.fresh", "199", {"unit_of_measurement": "L"})
    await hass.async_block_till_done()
    assert hass.states.get(filled).state != "unknown"

    hass.states.async_set("sensor.gray", "nan", {"unit_of_measurement": "%"})
    await hass.async_block_till_done()
    assert hass.states.get(emptied).state == "unknown"
    hass.states.async_set("sensor.gray", "60", {"unit_of_measurement": "%"})
    await hass.async_block_till_done()
    hass.states.async_set("sensor.gray", "2", {"unit_of_measurement": "%"})
    await hass.async_block_till_done()
    assert hass.states.get(emptied).state != "unknown"


async def test_history_restored(hass: HomeAssistant) -> None:
    """The last event survives a restart."""
    when = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    hass.states.async_set("sensor.fresh", "50", {"unit_of_measurement": "%"})
    entry = _entry()
    registry = er.async_get(hass)
    ent = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_tank_fresh_water_last_filled",
        config_entry=None,
        suggested_object_id="rv_fresh_last_filled",
    )
    mock_restore_cache(hass, [State(ent.entity_id, when.isoformat())])
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    entity_id = _find(hass, entry, "tank_fresh_water_last_filled")
    assert entity_id == ent.entity_id
    assert hass.states.get(entity_id).state == when.isoformat()
