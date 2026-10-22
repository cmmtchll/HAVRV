"""Tests for always-present, runtime-editable tow controls."""

from unittest.mock import AsyncMock

import pytest
from homeassistant.components.number import NumberExtraStoredData
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.icon import async_get_icons
from homeassistant.helpers.translation import async_get_translations
from homeassistant.util.unit_system import (
    METRIC_SYSTEM,
    US_CUSTOMARY_SYSTEM,
    UnitSystem,
)
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache,
)

from custom_components.havrv import HavrvRuntimeData
from custom_components.havrv.const import CONF_MEASUREMENT_SYSTEM, DOMAIN
from custom_components.havrv.tow import (
    HavrvTowingSwitch,
    HavrvTowTypeSelect,
    HavrvTowWeightNumber,
    tow_device_info,
)


async def _setup(hass: HomeAssistant, units: str = "metric") -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_NAME: "RV", CONF_MEASUREMENT_SYSTEM: units},
        version=3,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _entities(hass: HomeAssistant, entry: MockConfigEntry) -> dict[str, str]:
    return {
        entity.unique_id.removeprefix(f"{entry.entry_id}_tow_"): entity.entity_id
        for entity in er.async_entries_for_config_entry(
            er.async_get(hass), entry.entry_id
        )
        if entity.unique_id.startswith(f"{entry.entry_id}_tow_")
    }


async def test_tow_runtime_controls_and_reload(hass: HomeAssistant) -> None:
    """Every profile has independent controls that never edit configuration."""
    entry = await _setup(hass)
    entities = _entities(hass, entry)
    assert set(entities) == {"towing", "type", "weight"}
    assert hass.states.get(entities["towing"]).state == "off"
    assert hass.states.get(entities["type"]).state == "car"
    assert hass.states.get(entities["type"]).attributes["options"] == ["car", "trailer"]
    assert hass.states.get(entities["weight"]).state == "unknown"
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, f"{entry.entry_id}_tow"), entry.entry_id
    )
    assert device.name == "Tow"
    assert device.via_device_id == entry.runtime_data.device_id
    assert all(
        er.async_get(hass).async_get(eid).device_id == device.id
        for eid in entities.values()
    )
    assert all(
        er.async_get(hass).async_get(eid).entity_category is None
        for eid in entities.values()
    )
    assert all(
        not entity_type(entry).should_poll
        for entity_type in (HavrvTowingSwitch, HavrvTowTypeSelect, HavrvTowWeightNumber)
    )
    runtime = entry.runtime_data
    data, options = dict(entry.data), dict(entry.options)
    for domain, service, role, extra in [
        ("switch", "turn_on", "towing", {}),
        ("select", "select_option", "type", {"option": "trailer"}),
        ("number", "set_value", "weight", {"value": 2500}),
        ("switch", "turn_off", "towing", {}),
    ]:
        await hass.services.async_call(
            domain, service, {"entity_id": entities[role], **extra}, blocking=True
        )
    await hass.async_block_till_done()
    assert entry.runtime_data is runtime
    assert entry.data == data and entry.options == options
    assert hass.states.get(entities["type"]).state == "trailer"
    assert float(hass.states.get(entities["weight"]).state) == 2500
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert _entities(hass, entry) == entities
    assert hass.states.get(entities["towing"]).state == "off"
    assert hass.states.get(entities["type"]).state == "trailer"
    assert float(hass.states.get(entities["weight"]).state) == 2500
    await hass.services.async_call(
        "switch", "toggle", {"entity_id": entities["towing"]}, blocking=True
    )
    assert hass.states.get(entities["towing"]).state == "on"
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert all(hass.states.get(eid).state == "unavailable" for eid in entities.values())


@pytest.mark.parametrize(
    ("profile", "ha_units", "expected"),
    [("metric", US_CUSTOMARY_SYSTEM, "kg"), ("us_customary", METRIC_SYSTEM, "lb")],
)
async def test_tow_weight_units_and_override(
    hass: HomeAssistant, profile: str, ha_units: UnitSystem, expected: str
) -> None:
    """Profile units win over HA defaults; entity overrides convert writes."""
    hass.config.units = ha_units
    entry = await _setup(hass, profile)
    entity = _entities(hass, entry)["weight"]
    assert hass.states.get(entity).attributes["unit_of_measurement"] == expected
    registry = er.async_get(hass)
    registry.async_update_entity_options(
        entity, "number", {"unit_of_measurement": "oz"}
    )
    await hass.async_block_till_done()
    await hass.services.async_call(
        "number", "set_value", {"entity_id": entity, "value": 16}, blocking=True
    )
    assert hass.states.get(entity).attributes["unit_of_measurement"] == "oz"
    assert float(hass.states.get(entity).state) == pytest.approx(16)
    registry.async_update_entity_options(entity, "number", {})
    await hass.async_block_till_done()
    assert float(hass.states.get(entity).state) == pytest.approx(
        0.45359237 if expected == "kg" else 1
    )
    new_profile = "us_customary" if profile == "metric" else "metric"
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_MEASUREMENT_SYSTEM: new_profile}
    )
    await hass.async_block_till_done()
    assert hass.states.get(entity).attributes["unit_of_measurement"] == (
        "lb" if new_profile == "us_customary" else "kg"
    )
    assert float(hass.states.get(entity).state) == pytest.approx(
        1 if new_profile == "us_customary" else 0.45359237
    )


@pytest.mark.parametrize("restored_type", ["trailer", "boat", "unknown"])
async def test_tow_restart_restore(hass: HomeAssistant, restored_type: str) -> None:
    """Restart restores a known on-state and only supported dropdown options."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_NAME: "RV"}, version=3)
    registry = er.async_get(hass)
    switch = registry.async_get_or_create(
        "switch", DOMAIN, f"{entry.entry_id}_tow_towing"
    )
    select = registry.async_get_or_create(
        "select", DOMAIN, f"{entry.entry_id}_tow_type"
    )
    mock_restore_cache(
        hass, [State(switch.entity_id, "on"), State(select.entity_id, restored_type)]
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(switch.entity_id).state == "on"
    assert hass.states.get(select.entity_id).state == (
        "trailer" if restored_type == "trailer" else "car"
    )


@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [
        (2204.62262185, "lb", 1000),
        (0, "kg", 0),
        (-1, "kg", None),
        (float("nan"), "kg", None),
        (float("inf"), "kg", None),
        (100, "bananas", None),
        (None, "kg", None),
        (1e101, "kg", None),
    ],
)
async def test_tow_weight_restore(
    hass: HomeAssistant, value: float | None, unit: str, expected: float | None
) -> None:
    """Restore native weight across profile-unit changes, ignoring invalid data."""
    entry = await _setup(hass)
    number = HavrvTowWeightNumber(entry)
    number.hass = hass
    number.async_get_last_number_data = AsyncMock(
        return_value=NumberExtraStoredData(1e100, 0, 0.1, unit, value)
    )
    await number.async_added_to_hass()
    if expected is None:
        assert number.native_value is None
    else:
        assert number.native_value == pytest.approx(expected)


async def test_tow_invalid_writes_and_missing_parent(hass: HomeAssistant) -> None:
    """Reject invalid changes without replacing valid values or creating orphans."""
    entry = await _setup(hass)
    number = HavrvTowWeightNumber(entry)
    number.hass = hass
    number.async_write_ha_state = lambda: None
    await number.async_set_native_value(0)
    for value in [-1, float("nan"), float("inf"), 1e101]:
        with pytest.raises(ServiceValidationError):
            await number.async_set_native_value(value)
        assert number.native_value == 0
    select = HavrvTowTypeSelect(entry)
    with pytest.raises(ServiceValidationError):
        await select.async_select_option("boat")
    entry.runtime_data = HavrvRuntimeData(name="RV")
    with pytest.raises(RuntimeError, match="RV device"):
        tow_device_info(entry)


async def test_tow_translations_and_icons(hass: HomeAssistant) -> None:
    """Runtime control names, dropdown choices and icons are translatable."""
    translations = await async_get_translations(hass, "en", "entity", {DOMAIN})
    icons = (await async_get_icons(hass, "entity", {DOMAIN}))[DOMAIN]
    for domain, key, name in [
        ("switch", "towing", "Towing"),
        ("select", "tow_type", "Type"),
        ("number", "tow_weight", "Weight"),
    ]:
        assert translations[f"component.{DOMAIN}.entity.{domain}.{key}.name"] == name
        assert icons[domain][key]["default"].startswith("mdi:")
    for option in ("car", "trailer"):
        assert translations[f"component.{DOMAIN}.entity.select.tow_type.state.{option}"]
        assert icons["select"]["tow_type"]["state"][option].startswith("mdi:")


async def test_tow_controls_are_independent_between_profiles(
    hass: HomeAssistant,
) -> None:
    """A second RV never shares runtime controls or restored values."""
    first = await _setup(hass)
    second = await _setup(hass, "us_customary")
    first_entities = _entities(hass, first)
    second_entities = _entities(hass, second)
    assert set(first_entities.values()).isdisjoint(second_entities.values())
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": first_entities["towing"]}, blocking=True
    )
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": first_entities["weight"], "value": 1000},
        blocking=True,
    )
    assert hass.states.get(second_entities["towing"]).state == "off"
    assert hass.states.get(second_entities["weight"]).state == "unknown"
    assert await hass.config_entries.async_unload(first.entry_id)
    assert hass.states.get(second_entities["towing"]).state == "off"
