"""Focused provider-neutral powertrain validation, units and lifecycle tests."""

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.havrv.configuration import _normalize_options, _options_schema
from custom_components.havrv.const import DOMAIN
from custom_components.havrv.management import editable_values, validate_values
from custom_components.havrv.powertrain import (
    CONF_POWERTRAIN,
    DEFAULT_MAX_AGE,
    LIMITS,
    METRICS,
    TEXT,
    HavrvPowertrainSensor,
    Readings,
    convert_value,
    entity_keys,
    normalize_options,
)


def entry(settings: dict[str, Any] | None = None) -> MockConfigEntry:
    """Create a metric RV without preexisting powertrain assumptions."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="RV",
        unique_id="rv",
        version=3,
        data={"name": "RV", "measurement_system": "metric", "fuel_tank_capacity": 200},
        options={CONF_POWERTRAIN: settings or {}},
    )


def entity_id(
    hass: HomeAssistant, config: MockConfigEntry, obj: str, metric: str
) -> str:
    """Find the stable identity, not its translated or source-dependent name."""
    return next(
        entity.entity_id
        for entity in er.async_entries_for_config_entry(
            er.async_get(hass), config.entry_id
        )
        if entity.unique_id == f"{config.entry_id}_powertrain_{obj}_{metric}"
    )


@pytest.mark.parametrize("domain", ["sensor", "number", "input_number"])
def test_native_selectors_and_defaults(domain: str) -> None:
    """Helper and template-backed numeric domains match submitted validation."""
    config = entry()
    schema = _options_schema(config).schema
    for obj, metrics in METRICS.items():
        for name, metric in metrics.items():
            field = f"powertrain_{obj}_{name}"
            marker = next(m for m in schema if str(m) == field)
            domains = schema[marker].serialize()["selector"]["entity"]["domain"]
            assert domains == (
                ["sensor"] if metric == TEXT else ["sensor", "number", "input_number"]
            )
            assert marker.default.__class__.__name__ == "Undefined"
    normalized, error = _normalize_options(
        {"powertrain_engine_rpm": f"{domain}.rpm"}, config
    )
    assert error is None
    assert normalized[CONF_POWERTRAIN]["engine"] == {
        "rpm": f"{domain}.rpm",
        "max_age": DEFAULT_MAX_AGE,
    }
    assert normalize_options({}) == ({}, None)


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("engine_rpm", "switch.bad", "source"),
        ("engine_rpm", 1, "source"),
        ("engine_rpm", "sensor.", "source"),
        ("transmission_current_gear", "number.gear", "source"),
        ("engine_max_age", 0, "max_age"),
        ("fuel_max_age", float("inf"), "max_age"),
        ("engine_max_age", True, "max_age"),
        ("engine_rpm_warning_low", float("nan"), "threshold"),
        ("engine_rpm_problem_high", True, "threshold"),
        ("engine_rpm_problem_high", "100", "threshold"),
        ("transmission_current_gear_warning_low", 2, "threshold"),
    ],
)
def test_validation_errors(field: str, value: Any, code: str) -> None:
    """Invalid units/types/mappings produce native and field-specific errors."""
    _, failure = normalize_options({f"powertrain_{field}": value})
    assert failure == (
        field.split("_")[0],
        f"powertrain_{field}",
        f"invalid_powertrain_{code}",
    )
    _, error = _normalize_options({f"powertrain_{field}": value}, entry())
    assert error == f"invalid_powertrain_{code}"


@pytest.mark.parametrize(
    "limits",
    [
        {"problem_low": 20, "warning_low": 10},
        {"warning_high": 50, "problem_high": 40},
        {"problem_low": 90, "problem_high": 10},
        {"warning_low": 90, "warning_high": 10},
    ],
)
def test_limit_order(limits: dict[str, int]) -> None:
    """Every configured low/high boundary participates in a consistent ordering."""
    _, failure = normalize_options(
        {f"powertrain_engine_rpm_{key}": value for key, value in limits.items()}
    )
    assert failure[2] == "invalid_powertrain_threshold"


def test_management_roundtrip_conversion_and_removal() -> None:
    """A full snapshot preserves mappings, converts thresholds and removes limits."""
    config = entry(
        {
            "engine": {
                "oil_pressure": "sensor.oil",
                "oil_pressure_warning_low": 100,
                "coolant_temperature": "sensor.coolant",
                "coolant_temperature_problem_high": 100,
                "max_age": 90,
            },
            "fuel": {
                "rate": "input_number.rate",
                "rate_warning_high": 10,
                "reported_average_economy": "sensor.economy",
                "reported_average_economy_warning_low": 4,
            },
        }
    )
    values = editable_values(config, "metric")
    candidate, _, errors, _ = validate_values(config, dict(values), "metric")
    assert not errors
    assert candidate.options == dict(config.options)
    values["profile"]["measurement_system"] = "us_customary"
    candidate, converted, errors, _ = validate_values(config, dict(values), "metric")
    assert not errors
    engine = candidate.options[CONF_POWERTRAIN]["engine"]
    assert engine["oil_pressure_warning_low"] == pytest.approx(14.50377)
    assert engine["coolant_temperature_problem_high"] == pytest.approx(212)
    assert candidate.options[CONF_POWERTRAIN]["fuel"]["rate_warning_high"] == (
        pytest.approx(2.6417205)
    )
    assert converted["unit_system"] == "us_customary"
    converted["options"].pop("powertrain_engine_oil_pressure_warning_low")
    candidate, _, errors, _ = validate_values(config, dict(converted), "metric")
    assert not errors
    assert (
        "oil_pressure_warning_low" not in candidate.options[CONF_POWERTRAIN]["engine"]
    )
    converted["options"]["powertrain_engine_max_age"] = 0
    _, _, errors, _ = validate_values(config, dict(converted), "metric")
    assert errors == [
        {
            "section": "engine",
            "field": "powertrain_engine_max_age",
            "code": "invalid_powertrain_max_age",
        }
    ]


async def test_readings_severity_freshness_and_recovery(
    hass: HomeAssistant,
    freezer: Any,
) -> None:
    """Direct values survive advisory problems, while missing/stale values do not."""
    config = entry(
        {
            "engine": {
                "rpm": "sensor.rpm",
                "load": "number.load",
                "rpm_problem_low": 10,
                "rpm_warning_low": 20,
                "rpm_warning_high": 80,
                "rpm_problem_high": 90,
            },
            "transmission": {"current_gear": "sensor.gear"},
            "fuel": {"level": "input_number.level"},
        }
    )
    hass.states.async_set("number.load", "50", {"unit_of_measurement": "%"})
    hass.states.async_set("sensor.rpm", "50", {"unit_of_measurement": "rpm"})
    hass.states.async_set("sensor.gear", "NC")
    hass.states.async_set("input_number.level", "50", {"unit_of_measurement": "%"})
    config.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config.entry_id)
    await hass.async_block_till_done()
    rpm = entity_id(hass, config, "engine", "rpm")
    status = entity_id(hass, config, "engine", "status")
    running = entity_id(hass, config, "engine", "running")
    remaining = entity_id(hass, config, "fuel", "remaining_volume")
    assert hass.states.get(remaining).state == "100.0"
    assert (
        hass.states.get(entity_id(hass, config, "transmission", "current_gear")).state
        == "NC"
    )
    assert hass.states.get(running).state == "running"
    for value, expected in [
        (10, "problem"),
        (20, "warning"),
        (50, "ok"),
        (80, "warning"),
        (90, "problem"),
        (0, "problem"),
    ]:
        hass.states.async_set("sensor.rpm", str(value), {"unit_of_measurement": "rpm"})
        await hass.async_block_till_done()
        assert float(hass.states.get(rpm).state) == value
        assert hass.states.get(rpm).attributes["status"] == expected
        assert hass.states.get(status).state == expected
    assert hass.states.get(running).state == "stopped"
    last_observed = hass.states.get(rpm).attributes["last_observed"]
    hass.states.async_set("sensor.rpm", "unavailable")
    await hass.async_block_till_done()
    assert hass.states.get(status).state == "unknown"
    assert (
        hass.states.get(status).attributes["readings"]["rpm"]["last_observed"]
        == last_observed
    )
    assert hass.states.get(status).attributes["missing_readings"] == ["rpm"]
    assert hass.states.get(rpm).state == "unavailable"
    assert hass.states.get(running).state == "unavailable"
    hass.states.async_set("sensor.rpm", "90", {"unit_of_measurement": "rpm"})
    hass.states.async_set("number.load", "unavailable")
    await hass.async_block_till_done()
    assert hass.states.get(status).state == "problem"
    assert hass.states.get(status).attributes["missing_readings"] == ["load"]
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert hass.states.get(rpm).state == "unavailable"
    assert hass.states.get(status).state == "unknown"
    hass.states.async_set("sensor.rpm", "90", {"unit_of_measurement": "rpm"})
    await hass.async_block_till_done()
    assert hass.states.get(rpm).state == "90.0"
    hass.states.async_set("input_number.level", "118", {"unit_of_measurement": "%"})
    await hass.async_block_till_done()
    assert hass.states.get(remaining).state == "unavailable"
    assert hass.states.get(entity_id(hass, config, "fuel", "status")).state == "unknown"
    assert await hass.config_entries.async_unload(config.entry_id)


async def test_profile_units_and_explicit_ha_override(hass: HomeAssistant) -> None:
    """Thresholds use profile units even when HA explicitly overrides display units."""
    hass.config.units = US_CUSTOMARY_SYSTEM
    config = entry(
        {
            "engine": {
                "coolant_temperature": "sensor.temperature",
                "coolant_temperature_warning_high": 90,
                "oil_pressure": "sensor.pressure",
            },
            "fuel": {
                "rate": "sensor.rate",
                "reported_average_economy": "sensor.economy",
            },
        }
    )
    for source, value, unit in [
        ("temperature", "212", "°F"),
        ("pressure", "10", "psi"),
        ("rate", "1", "gal/h"),
        ("economy", "10", "mpg"),
    ]:
        hass.states.async_set(f"sensor.{source}", value, {"unit_of_measurement": unit})
    config.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config.entry_id)
    await hass.async_block_till_done()
    temperature = entity_id(hass, config, "engine", "coolant_temperature")
    assert float(hass.states.get(temperature).state) == pytest.approx(100)
    assert hass.states.get(temperature).attributes["unit_of_measurement"] == "°C"
    er.async_get(hass).async_update_entity_options(
        temperature, "sensor", {"unit_of_measurement": "°F"}
    )
    await hass.async_block_till_done()
    assert float(hass.states.get(temperature).state) == pytest.approx(212)
    assert hass.states.get(temperature).attributes["status"] == "warning"
    assert hass.states.get(temperature).attributes["profile_unit"] == "°C"
    assert float(
        hass.states.get(entity_id(hass, config, "fuel", "rate")).state
    ) == pytest.approx(3.785411784)
    for raw, unit in [("nan", "°F"), ("100", "V"), ("unknown", "°C")]:
        hass.states.async_set("sensor.temperature", raw, {"unit_of_measurement": unit})
        await hass.async_block_till_done()
        assert hass.states.get(temperature).state == "unavailable"


async def test_reload_remap_remove(hass: HomeAssistant) -> None:
    """Stable identities survive remapping and obsolete objects remove only HAVRV."""
    config = entry({"engine": {"rpm": "sensor.one"}})
    hass.states.async_set("sensor.one", "1", {"unit_of_measurement": "rpm"})
    hass.states.async_set("sensor.two", "2", {"unit_of_measurement": "rpm"})
    config.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config.entry_id)
    await hass.async_block_till_done()
    rpm = entity_id(hass, config, "engine", "rpm")
    registry = er.async_get(hass)
    hass.config_entries.async_update_entry(
        config, options={CONF_POWERTRAIN: {"engine": {"rpm": "sensor.two"}}}
    )
    await hass.async_block_till_done()
    assert entity_id(hass, config, "engine", "rpm") == rpm
    assert hass.states.get(rpm).state == "2.0"
    assert hass.states.get(rpm).attributes["source_entity_id"] == "sensor.two"
    hass.config_entries.async_update_entry(config, options={CONF_POWERTRAIN: {}})
    await hass.async_block_till_done()
    assert registry.async_get(rpm) is None
    assert (
        dr.async_get(hass).async_get_device_by_identifier(
            (DOMAIN, f"{config.entry_id}_powertrain_engine"), config.entry_id
        )
        is None
    )
    assert hass.states.get("sensor.one") is not None
    assert hass.states.get("sensor.two") is not None
    assert not entity_keys({}, {})


@pytest.mark.parametrize(
    "raw,unit",
    [
        ("-1", "rpm"),
        ("abc", "rpm"),
        ("100", None),
        ("100", "V"),
    ],
)
async def test_invalid_reading(hass: HomeAssistant, raw: str, unit: str | None) -> None:
    """Invalid input never fabricates a zero or healthy advisory."""
    config = entry({"engine": {"rpm": "sensor.rpm"}})
    hass.states.async_set("sensor.rpm", raw, {"unit_of_measurement": unit})
    config.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config.entry_id)
    await hass.async_block_till_done()
    assert (
        hass.states.get(entity_id(hass, config, "engine", "rpm")).state == "unavailable"
    )
    assert (
        hass.states.get(entity_id(hass, config, "engine", "status")).state == "unknown"
    )


async def test_explicit_observation_timestamps(hass: HomeAssistant) -> None:
    """A newly reported stale source is not fresh; invalid observation stays unknown."""
    config = entry({"engine": {"rpm": "sensor.rpm"}})
    config.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config.entry_id)
    await hass.async_block_till_done()
    readings = Readings(hass, config, "engine")
    for timestamp in [
        "bad",
        None,
        "2026-01-01T00:00:00",
        dt_util.utcnow() + timedelta(seconds=10),
        (dt_util.utcnow() - timedelta(seconds=61)).isoformat(),
    ]:
        hass.states.async_set(
            "sensor.rpm",
            "10",
            {
                "unit_of_measurement": "rpm",
                "last_observed": timestamp,
            },
        )
        assert readings.reading("rpm")[0] is None
    hass.states.async_set(
        "sensor.rpm",
        "10",
        {
            "unit_of_measurement": "rpm",
            "source_reported": dt_util.utcnow().isoformat(),
        },
    )
    assert readings.reading("rpm")[0] == 10
    assert readings.reading("load")[1]["status"] == "not_configured"


@pytest.mark.parametrize(
    "source,value,target,expected",
    [
        ("km/L", 4, "mpg", 9.408583),
        ("L/100km", 25, "km/L", 4),
        ("L/100km", 0, "km/L", None),
        ("kWh", 4, "km/L", None),
    ],
)
def test_economy_units(
    source: str, value: float, target: str, expected: float | None
) -> None:
    """Only explicit compatible reported economy is converted."""
    result = convert_value(
        value, source, target, METRICS["fuel"]["reported_average_economy"]
    )
    assert result == (pytest.approx(expected) if expected is not None else None)


def test_translation_labels() -> None:
    """Every recovery field, reading and advisory enum is translated."""
    for file in ("strings.json", "translations/en.json"):
        translated = json.loads(
            (Path("custom_components/havrv") / file).read_text(encoding="utf-8")
        )
        labels = translated["options"]["step"]["init"]["data"]
        for obj, metrics in METRICS.items():
            assert labels[f"powertrain_{obj}_max_age"]
            for name, metric in metrics.items():
                key = f"powertrain_{obj}_{name}"
                assert labels[key]
                assert translated["entity"]["sensor"][key]["name"]
                if metric != TEXT:
                    for limit in LIMITS:
                        assert labels[f"{key}_{limit}"]
            assert translated["entity"]["sensor"][f"powertrain_{obj}_status"]["state"]
        for area in ("config", "options"):
            for error in ("source", "threshold", "max_age"):
                assert translated[area]["error"][f"invalid_powertrain_{error}"]


async def test_all_metrics_and_explicit_age(hass: HomeAssistant, freezer: Any) -> None:
    """All channels support profile units, actual reports and age overrides."""
    settings = {
        obj: {**{name: f"sensor.{obj}_{name}" for name in metrics}, "max_age": 120}
        for obj, metrics in METRICS.items()
    }
    config = entry(settings)
    for obj, metrics in METRICS.items():
        for name, metric in metrics.items():
            hass.states.async_set(
                f"sensor.{obj}_{name}",
                "N" if metric == TEXT else "10",
                {"unit_of_measurement": metric.metric_unit},
            )
    config.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config.entry_id)
    await hass.async_block_till_done()
    for obj, metrics in METRICS.items():
        for name, metric in metrics.items():
            state = hass.states.get(entity_id(hass, config, obj, name))
            assert state.state == ("N" if metric == TEXT else "10.0")
            assert state.attributes["status"] == "ok"
            assert state.attributes["max_age"] == 120
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    rpm = entity_id(hass, config, "engine", "rpm")
    assert hass.states.get(rpm).state == "10.0"
    before = hass.states.get(rpm).attributes["last_observed"]
    # Identical reports update last_reported even though last_changed stays old.
    hass.states.async_set("sensor.engine_rpm", "10", {"unit_of_measurement": "rpm"})
    await hass.async_block_till_done()
    assert hass.states.get(rpm).attributes["last_observed"] != before
    assert await hass.config_entries.async_unload(config.entry_id)
    unloaded_state = hass.states.get(rpm)
    freezer.tick(timedelta(seconds=121))
    async_fire_time_changed(hass, dt_util.utcnow())
    hass.states.async_set("sensor.engine_rpm", "20", {"unit_of_measurement": "rpm"})
    await hass.async_block_till_done()
    assert hass.states.get(rpm) == unloaded_state


async def test_unknown_and_disabled_advisories(hass: HomeAssistant) -> None:
    """Limits are optional and independent; aggregates expose unconfigured channels."""
    config = entry(
        {
            "engine": {
                "rpm": "sensor.rpm",
                "load": "sensor.missing",
                "rpm_warning_high": 80,
            }
        }
    )
    hass.states.async_set("sensor.rpm", "80", {"unit_of_measurement": "rpm"})
    config.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config.entry_id)
    await hass.async_block_till_done()
    status = hass.states.get(entity_id(hass, config, "engine", "status"))
    assert status.state == "warning"
    assert status.attributes["missing_readings"] == ["load"]
    assert status.attributes["readings"]["rpm"]["warning_high"] == 80
    assert "problem_high" not in status.attributes["readings"]["rpm"]
    assert status.attributes["readings"]["running"]["source_entity_id"] == "sensor.rpm"
    assert status.attributes["readings"]["voltage"]["status"] == "not_configured"
    readings = Readings(hass, config, "engine")
    readings.settings = {}
    assert HavrvPowertrainSensor(readings, "status").native_value == "not_configured"
    config.runtime_data.device_id = None
    with pytest.raises(RuntimeError, match="RV device"):
        HavrvPowertrainSensor(readings, "status")


def test_optional_derivatives_and_independent_limits() -> None:
    """Capacity alone creates no Fuel object; independently omitted limits disable."""
    assert entity_keys({}, {"fuel_tank_capacity": 100}) == []
    for capacity in (None, 0, float("nan")):
        keys = entity_keys(
            {CONF_POWERTRAIN: {"fuel": {"level": "sensor.level"}}},
            {"fuel_tank_capacity": capacity},
        )
        assert ("fuel", "remaining_volume") not in keys
    normalized, error = normalize_options(
        {
            "powertrain_engine_rpm": "",
            "powertrain_engine_rpm_warning_low": "",
            "powertrain_engine_rpm_problem_high": 100,
        }
    )
    assert error is None
    assert normalized == {"engine": {"rpm_problem_high": 100, "max_age": 60}}
    assert entity_keys({CONF_POWERTRAIN: normalized}, {}) == []


def test_threshold_conversion_overflow_is_error() -> None:
    """An unrepresentable converted limit must not silently disable the advisory."""
    config = entry(
        {
            "fuel": {
                "reported_average_economy": "sensor.economy",
                "reported_average_economy_problem_high": 1e308,
            }
        }
    )
    values = editable_values(config, "metric")
    values["profile"]["measurement_system"] = "us_customary"
    _, _, errors, _ = validate_values(config, dict(values), "metric")
    assert errors == [
        {
            "section": "fuel",
            "field": "powertrain_fuel_reported_average_economy_problem_high",
            "code": "invalid_powertrain_threshold",
        }
    ]


async def test_units_change_on_reload_preserves_override(hass: HomeAssistant) -> None:
    """Unit edits refresh profile defaults without discarding HA overrides."""
    config = entry(
        {
            "engine": {
                "coolant_temperature": "sensor.temp",
                "coolant_temperature_warning_high": 90,
                "oil_pressure": "sensor.pressure",
                "oil_pressure_problem_low": 100,
            }
        }
    )
    hass.states.async_set("sensor.temp", "100", {"unit_of_measurement": "°C"})
    hass.states.async_set("sensor.pressure", "10", {"unit_of_measurement": "psi"})
    config.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config.entry_id)
    await hass.async_block_till_done()
    temperature = entity_id(hass, config, "engine", "coolant_temperature")
    pressure = entity_id(hass, config, "engine", "oil_pressure")
    er.async_get(hass).async_update_entity_options(
        pressure, "sensor", {"unit_of_measurement": "kPa"}
    )
    await hass.async_block_till_done()
    values = editable_values(config, "metric")
    values["profile"]["measurement_system"] = "us_customary"
    candidate, _, errors, _ = validate_values(config, dict(values), "metric")
    assert not errors
    hass.config_entries.async_update_entry(
        config, data=candidate.data, options=candidate.options
    )
    await hass.async_block_till_done()
    assert entity_id(hass, config, "engine", "coolant_temperature") == temperature
    assert hass.states.get(temperature).attributes["unit_of_measurement"] == "°F"
    assert hass.states.get(temperature).attributes["status"] == "warning"
    assert float(hass.states.get(temperature).state) == pytest.approx(212)
    assert hass.states.get(pressure).attributes["unit_of_measurement"] == "kPa"
    assert hass.states.get(pressure).attributes["status"] == "problem"
    assert hass.states.get(pressure).attributes["problem_low"] == pytest.approx(
        14.50377
    )


async def test_setup_prunes_obsolete_registry_entries(hass: HomeAssistant) -> None:
    """Unconfigured setup removes leftovers without unregistering source devices."""
    config = entry()
    config.add_to_hass(hass)
    devices = dr.async_get(hass)
    registry = er.async_get(hass)
    device = devices.async_get_or_create(
        config_entry_id=config.entry_id,
        identifiers={(DOMAIN, f"{config.entry_id}_powertrain_fuel")},
        name="Fuel",
    )
    obsolete = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{config.entry_id}_powertrain_fuel_level",
        config_entry=config,
        device_id=device.id,
    )
    assert await hass.config_entries.async_setup(config.entry_id)
    await hass.async_block_till_done()
    assert registry.async_get(obsolete.entity_id) is None
    assert devices.async_get(device.id) is None
    assert not any(
        "powertrain" in item.unique_id
        for item in er.async_entries_for_config_entry(registry, config.entry_id)
    )


async def test_self_mapping_is_not_subscribed(hass: HomeAssistant) -> None:
    """A proxy mapped back to itself cannot generate a recursive report loop."""
    config = entry()
    config.add_to_hass(hass)
    registered = er.async_get(hass).async_get_or_create(
        "sensor",
        DOMAIN,
        f"{config.entry_id}_powertrain_engine_rpm",
        config_entry=config,
        suggested_object_id="self_rpm",
    )
    hass.config_entries.async_update_entry(
        config,
        options={
            CONF_POWERTRAIN: {"engine": {"rpm": registered.entity_id}},
        },
    )
    assert await hass.config_entries.async_setup(config.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(registered.entity_id).state == "unavailable"


async def test_derived_profile_units_and_limits(hass: HomeAssistant) -> None:
    """Volume markers use volume limits; enum metadata has no numeric limits."""
    config = entry(
        {
            "engine": {"rpm": "sensor.rpm", "rpm_warning_low": 20},
            "fuel": {"level": "sensor.level", "level_warning_low": 30},
        }
    )
    hass.states.async_set("sensor.rpm", "10", {"unit_of_measurement": "rpm"})
    hass.states.async_set("sensor.level", "25", {"unit_of_measurement": "%"})
    config.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config.entry_id)
    await hass.async_block_till_done()
    running = hass.states.get(entity_id(hass, config, "engine", "running"))
    remaining = hass.states.get(entity_id(hass, config, "fuel", "remaining_volume"))
    status = hass.states.get(entity_id(hass, config, "fuel", "status"))
    assert running.attributes["profile_unit"] is None
    assert "warning_low" not in running.attributes
    assert remaining.attributes["profile_unit"] == "L"
    assert remaining.attributes["warning_low"] == 60
    assert remaining.attributes["status"] == "warning"
    assert status.attributes["readings"]["level"]["profile_unit"] == "%"
    assert status.attributes["readings"]["level"]["warning_low"] == 30
    assert status.attributes["readings"]["remaining_volume"]["profile_unit"] == "L"
    assert status.attributes["readings"]["remaining_volume"]["warning_low"] == 60
