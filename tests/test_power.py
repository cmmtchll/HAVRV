"""Tests for independent RV power banks, electrical readings and statuses."""

from types import SimpleNamespace

import pytest
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util.unit_system import METRIC_SYSTEM, US_CUSTOMARY_SYSTEM
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.havrv.const import (
    CONF_CHASSIS_BATTERY_BANK_COUNT,
    CONF_HOUSE_BATTERY_BANK_COUNT,
    CONF_MEASUREMENT_SYSTEM,
    CONF_POWER_SOURCES,
    DOMAIN,
)
from custom_components.havrv.diagnostics import async_get_config_entry_diagnostics
from custom_components.havrv.power import (
    HavrvPowerSourceEntity,
    PowerSource,
    power_settings,
    power_sources,
)

SHORE_READINGS = {
    "voltage": ("120000", "mV", "120.0", "V"),
    "current": ("35000", "mA", "35.0", "A"),
    "frequency": ("0.06", "kHz", "60.0", "Hz"),
    "power": ("4.16", "kW", "4160.0", "W"),
    "line_2_voltage": ("119", "V", "119.0", "V"),
    "line_2_current": ("27", "A", "27.0", "A"),
    "line_2_frequency": ("60000", "mHz", "60.0", "Hz"),
    "line_2_power": ("3280", "W", "3280.0", "W"),
    "energy": ("2600", "Wh", "2.6", "kWh"),
}


@pytest.mark.parametrize("domain", ["sensor", "number", "input_number"])
@pytest.mark.parametrize("profile_system", ["metric", "us_customary"])
async def test_two_shore_lines_and_shared_energy(
    hass: HomeAssistant, domain: str, profile_system: str
) -> None:
    """Map all shore readings independently and honor physical meter resets."""
    hass.config.units = (
        US_CUSTOMARY_SYSTEM if profile_system == "metric" else METRIC_SYSTEM
    )
    mappings = {}
    for metric, (value, unit, _, _) in SHORE_READINGS.items():
        source_id = f"{domain}.template_{metric}"
        mappings[metric] = source_id
        hass.states.async_set(source_id, value, {"unit_of_measurement": unit})
    entry = await _setup(
        hass,
        {"shore_power": {"line_count": 2, **mappings}},
        **{CONF_MEASUREMENT_SYSTEM: profile_system},
    )
    entities = _entities(hass, entry)
    for metric, (_, _, expected, unit) in SHORE_READINGS.items():
        entity = entities[f"shore_power_{metric}"]
        state = hass.states.get(entity.entity_id)
        assert state.state == expected
        assert state.attributes["unit_of_measurement"] == unit
        assert state.attributes["state_class"] == (
            "total_increasing" if metric == "energy" else "measurement"
        )
        assert entity.translation_key == f"shore_{metric}"
        assert entity.device_id == entities["shore_power_energy"].device_id
        hass.states.async_set(mappings[metric], "1")
    await hass.async_block_till_done()
    assert all(
        hass.states.get(entities[f"shore_power_{metric}"].entity_id).state == "1.0"
        for metric in SHORE_READINGS
    )
    energy_id = entities["shore_power_energy"].entity_id
    hass.states.async_set(mappings["energy"], "0", {"unit_of_measurement": "kWh"})
    await hass.async_block_till_done()
    assert hass.states.get(energy_id).state == "0.0"
    assert not any(entity.domain == "button" for entity in entities.values())
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(energy_id).state == "0.0"


@pytest.mark.parametrize("metric", ["frequency", "power", "energy", "line_2_voltage"])
@pytest.mark.parametrize(
    ("value", "unit"),
    [("unavailable", None), ("nan", None), ("bad", None), ("5", "gal")],
)
async def test_new_shore_readings_fail_and_recover(
    hass: HomeAssistant, metric: str, value: str, unit: str | None
) -> None:
    """Invalid sources never become fabricated readings or hide other metrics."""
    entry = await _setup(
        hass, {"shore_power": {"line_count": 2, metric: "sensor.reading"}}
    )
    entity_id = _entities(hass, entry)[f"shore_power_{metric}"].entity_id
    assert hass.states.get(entity_id).state == "unavailable"
    hass.states.async_set("sensor.reading", value, {"unit_of_measurement": unit})
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "unavailable"
    hass.states.async_set("sensor.reading", "3")
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "3.0"


async def test_shore_line_count_lifecycle_and_energy_override(
    hass: HomeAssistant,
) -> None:
    """Keep legacy Line 1 identity, clean Line 2, and respect user unit overrides."""
    hass.states.async_set("sensor.voltage", "120", {"unit_of_measurement": "V"})
    hass.states.async_set("sensor.energy", "2", {"unit_of_measurement": "kWh"})
    entry = await _setup(hass, {"shore_power": {"voltage": "sensor.voltage"}})
    source = PowerSource("shore_power", "Shore Power")
    assert power_settings(entry, source)["line_count"] == 1
    voltage_id = _entities(hass, entry)["shore_power_voltage"].entity_id
    for count in (2, 1):
        hass.config_entries.async_update_entry(
            entry,
            options={
                CONF_POWER_SOURCES: {
                    "shore_power": {
                        "line_count": count,
                        "voltage": "sensor.voltage",
                        "line_2_voltage": "sensor.voltage",
                        "energy": "sensor.energy",
                    }
                }
            },
        )
        await hass.async_block_till_done()
        entities = _entities(hass, entry)
        assert entities["shore_power_voltage"].entity_id == voltage_id
        assert ("shore_power_line_2_voltage" in entities) == (count == 2)
    energy = entities["shore_power_energy"]
    er.async_get(hass).async_update_entity_options(
        energy.entity_id, "sensor", {"unit_of_measurement": "Wh"}
    )
    await hass.async_block_till_done()
    hass.states.async_set("sensor.energy", "3", {"unit_of_measurement": "kWh"})
    await hass.async_block_till_done()
    assert hass.states.get(energy.entity_id).state == "3000.0"
    hass.states.async_set("sensor.energy", "-1", {"unit_of_measurement": "kWh"})
    await hass.async_block_till_done()
    assert hass.states.get(energy.entity_id).state == "unavailable"
    hass.config_entries.async_update_entry(entry, options={CONF_POWER_SOURCES: {}})
    await hass.async_block_till_done()
    assert "shore_power_energy" not in _entities(hass, entry)
    assert power_settings(entry, source)["line_count"] == 2


async def _setup(
    hass: HomeAssistant, settings: dict, **profile: object
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Power RV",
        unique_id="power rv",
        version=3,
        data={CONF_NAME: "Power RV", **profile},
        options={CONF_POWER_SOURCES: settings},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _entities(hass: HomeAssistant, entry: MockConfigEntry) -> dict:
    return {
        entity.unique_id.removeprefix(f"{entry.entry_id}_source_"): entity
        for entity in er.async_entries_for_config_entry(
            er.async_get(hass), entry.entry_id
        )
        if entity.unique_id.startswith(f"{entry.entry_id}_source_")
    }


async def test_legacy_default_power_devices_do_not_invent_readings(
    hass: HomeAssistant,
) -> None:
    """Legacy entries have one independent bank of each type and no fake telemetry."""
    entry = await _setup(hass, {})
    entities = _entities(hass, entry)
    assert set(entities) == {
        "house_bank_1_nominal_voltage",
        "chassis_bank_1_nominal_voltage",
        "house_bank_1_location",
        "chassis_bank_1_location",
        "inverter_location",
        "generator_location",
        "shore_power_location",
    }
    assert (
        hass.states.get(entities["house_bank_1_nominal_voltage"].entity_id).state
        == "24"
    )
    assert hass.states.get(entities["inverter_location"].entity_id).state == "not_shown"
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    rv = next(device for device in devices if device.name == "Power RV")
    children = [device for device in devices if "_source_" in str(device.identifiers)]
    assert len(children) == 5
    assert all(device.via_device_id == rv.id for device in children)
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize(
    ("metric", "source", "unit", "value", "expected"),
    [
        ("voltage", "sensor.template_voltage", "mV", "24500", "24.5"),
        ("voltage", "number.voltage", "kV", "0.024", "24.0"),
        ("voltage", "input_number.voltage", None, "48", "48.0"),
        ("current", "sensor.template_current", "mA", "-2500", "-2.5"),
        ("current", "number.current", "A", "3.5", "3.5"),
        ("current", "input_number.current", None, "4", "4.0"),
    ],
)
@pytest.mark.parametrize("profile_system", ["metric", "us_customary"])
async def test_power_readings_convert_units_and_update(
    hass: HomeAssistant,
    metric: str,
    source: str,
    unit: str | None,
    value: str,
    expected: str,
    profile_system: str,
) -> None:
    """Electrical V/A are consistent across source, profile and HA unit systems."""
    hass.config.units = (
        US_CUSTOMARY_SYSTEM if profile_system == "metric" else METRIC_SYSTEM
    )
    hass.states.async_set(source, value, {"unit_of_measurement": unit})
    entry = await _setup(
        hass,
        {"house_bank_1": {metric: source}},
        **{CONF_MEASUREMENT_SYSTEM: profile_system},
    )
    entity = _entities(hass, entry)[f"house_bank_1_{metric}"]
    state = hass.states.get(entity.entity_id)
    assert state.state == expected
    assert state.attributes["unit_of_measurement"] == (
        "V" if metric == "voltage" else "A"
    )
    assert state.attributes["state_class"] == "measurement"
    hass.states.async_set(source, "2")
    await hass.async_block_till_done()
    assert hass.states.get(entity.entity_id).state == "2.0"
    assert await hass.config_entries.async_unload(entry.entry_id)
    hass.states.async_set(source, "3")
    await hass.async_block_till_done()
    assert hass.states.get(entity.entity_id).state == "unavailable"


@pytest.mark.parametrize(
    ("value", "unit"),
    [
        ("unknown", "V"),
        ("unavailable", "V"),
        ("bad", "V"),
        ("nan", "V"),
        ("inf", "V"),
        ("24", "W"),
        ("1e308", "kV"),
        ("24", ["V"]),
    ],
)
async def test_invalid_power_readings_recover(
    hass: HomeAssistant,
    value: str,
    unit: object,
) -> None:
    """Invalid readings stay unavailable and recover independently of specifications."""
    entry = await _setup(hass, {"house_bank_1": {"voltage": "sensor.voltage"}})
    entity = _entities(hass, entry)["house_bank_1_voltage"]
    assert hass.states.get(entity.entity_id).state == "unavailable"
    hass.states.async_set("sensor.voltage", value, {"unit_of_measurement": unit})
    await hass.async_block_till_done()
    assert hass.states.get(entity.entity_id).state == "unavailable"
    hass.states.async_set("sensor.voltage", "13.4", {"unit_of_measurement": "V"})
    await hass.async_block_till_done()
    assert hass.states.get(entity.entity_id).state == "13.4"


@pytest.mark.parametrize("domain", ["binary_sensor", "switch", "input_boolean"])
async def test_enabled_and_charging_are_independent_readonly_statuses(
    hass: HomeAssistant,
    domain: str,
) -> None:
    """Charging follows only its own mapping, regardless of current or shore status."""
    hass.states.async_set(f"{domain}.enabled", "on")
    hass.states.async_set(f"{domain}.charging", "off")
    hass.states.async_set("sensor.current", "-25", {"unit_of_measurement": "A"})
    entry = await _setup(
        hass,
        {
            "house_bank_1": {
                "enabled": f"{domain}.enabled",
                "charging": f"{domain}.charging",
                "current": "sensor.current",
            },
            "shore_power": {"enabled": f"{domain}.enabled", "location": "left"},
        },
    )
    entities = _entities(hass, entry)
    enabled = entities["house_bank_1_enabled"]
    charging = entities["house_bank_1_charging"]
    assert enabled.domain == charging.domain == "binary_sensor"
    assert hass.states.get(enabled.entity_id).state == "on"
    assert hass.states.get(charging.entity_id).state == "off"
    assert hass.states.get(entities["house_bank_1_current"].entity_id).state == "-25.0"
    for value, expected in [
        ("on", "on"),
        ("off", "off"),
        ("unknown", "unavailable"),
        ("unavailable", "unavailable"),
        ("charging", "unavailable"),
    ]:
        hass.states.async_set(f"{domain}.charging", value)
        await hass.async_block_till_done()
        assert hass.states.get(charging.entity_id).state == expected
    hass.states.async_remove(f"{domain}.enabled")
    await hass.async_block_till_done()
    assert hass.states.get(enabled.entity_id).state == "unavailable"
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("domain", ["binary_sensor", "switch", "input_boolean"])
@pytest.mark.parametrize(
    "key", ["house_bank_1", "chassis_bank_1", "inverter", "generator", "shore_power"]
)
async def test_power_alerts_are_independent_recover_and_clear(
    hass: HomeAssistant, domain: str, key: str
) -> None:
    """Explicit alerts load alone, recover, remap and remove without stale entities."""
    hass.states.async_set(f"{domain}.warning", "on")
    hass.states.async_set(f"{domain}.problem", "off")
    entry = await _setup(
        hass,
        {key: {"warning": f"{domain}.warning", "problem": f"{domain}.problem"}},
        **{
            CONF_HOUSE_BATTERY_BANK_COUNT: 0 if "bank" not in key else 1,
            CONF_CHASSIS_BATTERY_BANK_COUNT: 0 if "bank" not in key else 1,
        },
    )
    entities = _entities(hass, entry)
    warning = entities[f"{key}_warning"]
    problem = entities[f"{key}_problem"]
    assert warning.domain == problem.domain == "binary_sensor"
    assert hass.states.get(warning.entity_id).state == "on"
    assert hass.states.get(problem.entity_id).state == "off"
    assert hass.states.get(problem.entity_id).attributes["device_class"] == "problem"
    assert f"{key}_enabled" not in entities
    for metric, entity in (("warning", warning), ("problem", problem)):
        for value, expected in [
            ("unknown", "unavailable"),
            ("unavailable", "unavailable"),
            ("bad", "unavailable"),
            ("on", "on"),
            ("off", "off"),
        ]:
            hass.states.async_set(f"{domain}.{metric}", value)
            await hass.async_block_till_done()
            assert hass.states.get(entity.entity_id).state == expected
        hass.states.async_remove(f"{domain}.{metric}")
        await hass.async_block_till_done()
        assert hass.states.get(entity.entity_id).state == "unavailable"
    registry = er.async_get(hass)
    registry.async_update_entity(
        warning.entity_id, new_entity_id="binary_sensor.my_warning"
    )
    hass.states.async_set("binary_sensor.new_warning", "on")
    hass.config_entries.async_update_entry(
        entry,
        options={CONF_POWER_SOURCES: {key: {"warning": "binary_sensor.new_warning"}}},
    )
    await hass.async_block_till_done()
    assert (
        _entities(hass, entry)[f"{key}_warning"].entity_id == "binary_sensor.my_warning"
    )
    assert hass.states.get("binary_sensor.my_warning").state == "on"
    assert f"{key}_problem" not in _entities(hass, entry)
    assert registry.async_get(problem.entity_id) is None
    hass.config_entries.async_update_entry(
        entry, options={CONF_POWER_SOURCES: {key: {}}}
    )
    await hass.async_block_till_done()
    assert f"{key}_warning" not in _entities(hass, entry)
    assert registry.async_get("binary_sensor.my_warning") is None
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_independent_banks_specs_remapping_cleanup_and_reconfiguration(
    hass: HomeAssistant,
) -> None:
    """Bank identities survive remapping and obsolete entities/devices are removed."""
    hass.states.async_set("sensor.old", "25")
    hass.states.async_set("sensor.new", "26")
    entry = await _setup(
        hass,
        {
            "house_bank_1": {
                "voltage": "sensor.old",
                "nominal_capacity": 300,
                "nominal_voltage": 24,
                "location": "right_rear",
            },
            "house_bank_2": {
                "nominal_voltage": 48,
                "nominal_capacity": 200,
                "enabled": "binary_sensor.enabled",
            },
        },
        **{CONF_HOUSE_BATTERY_BANK_COUNT: 2, CONF_CHASSIS_BATTERY_BANK_COUNT: 0},
    )
    registry = er.async_get(hass)
    entities = _entities(hass, entry)
    voltage = entities["house_bank_1_voltage"]
    assert (
        hass.states.get(entities["house_bank_2_nominal_voltage"].entity_id).state
        == "48"
    )
    assert (
        hass.states.get(entities["house_bank_1_nominal_capacity"].entity_id).state
        == "300"
    )
    assert (
        hass.states.get(entities["house_bank_1_nominal_capacity"].entity_id).attributes[
            "unit_of_measurement"
        ]
        == "Ah"
    )
    registry.async_update_entity(
        voltage.entity_id, new_entity_id="sensor.my_bank_voltage"
    )
    changed = {
        **entry.options[CONF_POWER_SOURCES],
        "house_bank_1": {"voltage": "sensor.new"},
    }
    hass.config_entries.async_update_entry(entry, options={CONF_POWER_SOURCES: changed})
    await hass.async_block_till_done()
    assert (
        _entities(hass, entry)["house_bank_1_voltage"].entity_id
        == "sensor.my_bank_voltage"
    )
    assert hass.states.get("sensor.my_bank_voltage").state == "26.0"
    assert "house_bank_1_nominal_capacity" not in _entities(hass, entry)
    form = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "reconfigure", "entry_id": entry.entry_id},
    )
    result = await hass.config_entries.flow.async_configure(
        form["flow_id"],
        user_input={
            CONF_HOUSE_BATTERY_BANK_COUNT: 1,
            CONF_CHASSIS_BATTERY_BANK_COUNT: 0,
        },
    )
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert "house_bank_2" not in entry.options[CONF_POWER_SOURCES]
    assert not any(key.startswith("house_bank_2_") for key in _entities(hass, entry))
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert not any("house_bank_2" in str(device.identifiers) for device in devices)
    hass.config_entries.async_update_entry(
        entry, options={CONF_POWER_SOURCES: {"house_bank_1": {}}}
    )
    await hass.async_block_till_done()
    assert "house_bank_1_voltage" not in _entities(hass, entry)
    assert not registry.async_get("sensor.my_bank_voltage")


async def test_explicit_electrical_unit_override_is_respected(
    hass: HomeAssistant,
) -> None:
    """Default amperes do not prevent a user's explicit per-entity display override."""
    hass.states.async_set("sensor.current", "2", {"unit_of_measurement": "A"})
    entry = await _setup(hass, {"inverter": {"current": "sensor.current"}})
    entity = _entities(hass, entry)["inverter_current"]
    er.async_get(hass).async_update_entity_options(
        entity.entity_id, "sensor", {"unit_of_measurement": "mA"}
    )
    await hass.async_block_till_done()
    assert hass.states.get(entity.entity_id).state == "2000.0"
    assert hass.states.get(entity.entity_id).attributes["unit_of_measurement"] == "mA"


async def test_power_diagnostics_are_redacted(hass: HomeAssistant) -> None:
    """Source IDs, specifications and placements do not leak through diagnostics."""
    entry = await _setup(
        hass,
        {"house_bank_1": {"voltage": "sensor.private"}},
        **{CONF_HOUSE_BATTERY_BANK_COUNT: 2},
    )
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["entry_data"][CONF_HOUSE_BATTERY_BANK_COUNT] == "**REDACTED**"
    assert diagnostics["entry_options"][CONF_POWER_SOURCES] == "**REDACTED**"


def test_power_source_requires_registered_parent() -> None:
    """Platform entities cannot attach to an unregistered parent RV."""
    entry = SimpleNamespace(runtime_data=SimpleNamespace(device_id=None))
    with pytest.raises(RuntimeError, match="RV device must be registered"):
        HavrvPowerSourceEntity(entry, PowerSource("inverter", "Inverter"), "voltage")
    assert [
        source.key
        for source in power_sources(
            {CONF_HOUSE_BATTERY_BANK_COUNT: 0, CONF_CHASSIS_BATTERY_BANK_COUNT: 0}
        )
    ] == ["inverter", "generator", "shore_power"]
