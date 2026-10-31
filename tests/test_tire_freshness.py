"""Explicit reception timestamps and historical tire reading metadata."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache,
)

from custom_components.havrv.const import CONF_TIRE_ENTITY_MAPPINGS, DOMAIN
from custom_components.havrv.sensor import HavrvTireSensor
from custom_components.havrv.tire import tire_data_present, tire_positions, tire_problem


def _entry(
    mappings: dict[str, str] | None = None, system: str = "metric"
) -> MockConfigEntry:
    """Create a small profile with deliberately nonuniform source names."""
    return MockConfigEntry(
        domain=DOMAIN,
        version=3,
        data={
            "name": "Freshness RV",
            "rear_axle_count": 1,
            "main_rear_wheel_configuration": "single",
            "measurement_system": system,
        },
        options={CONF_TIRE_ENTITY_MAPPINGS: mappings or {}},
    )


def _entity(
    hass: HomeAssistant, entry: MockConfigEntry, metric: str
) -> er.RegistryEntry:
    """Find a front-left tire mirror by stable identity."""
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_tire_front_left_{metric}"
    )
    assert entity_id is not None
    result = er.async_get(hass).async_get(entity_id)
    assert result is not None
    return result


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set up a profile using the normal platform lifecycle."""
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.parametrize("device_class", ["timestamp", None])
@pytest.mark.parametrize(
    "value",
    [
        "2026-02-28T12:34:56+02:00",
        "2026-02-28T10:34:56Z",
        "2026-02-28T03:34:56-07:00",
        "2026-02-28T10:34:56.123456+00:00",
    ],
)
async def test_explicit_timestamp(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    value: str,
    device_class: str | None,
) -> None:
    """Accept ISO timestamp sensors, including templates without a device class."""
    freezer.move_to("2026-03-01T00:00:00Z")
    hass.states.async_set(
        "sensor.packet_clock_x9",
        value,
        {"device_class": device_class} if device_class is not None else {},
    )
    entry = _entry({"front_left_last_received": "sensor.packet_clock_x9"})
    await _setup(hass, entry)
    entity = _entity(hass, entry, "last_received")
    state = hass.states.get(entity.entity_id)
    # HA's timestamp sensor serialization intentionally drops microseconds.
    assert dt_util.parse_datetime(state.state) == dt_util.parse_datetime(value).replace(
        microsecond=0
    )
    assert state.attributes["device_class"] == "timestamp"
    assert state.attributes["friendly_name"].endswith("Last received")
    assert not any(key.startswith("last_valid_") for key in state.attributes)
    device = dr.async_get(hass).async_get(entity.device_id)
    assert (DOMAIN, f"{entry.entry_id}_tire_front_left") in device.identifiers
    assert not tire_data_present(hass, entry, tire_positions(entry.data)[0])
    with pytest.raises(ValueError, match="Unsupported tire problem type"):
        tire_problem(hass, entry, tire_positions(entry.data)[0], "last_received")

    updated = "2026-02-28T23:59:00Z"
    hass.states.async_set("sensor.packet_clock_x9", updated)
    await hass.async_block_till_done()
    assert dt_util.parse_datetime(hass.states.get(entity.entity_id).state) == (
        dt_util.parse_datetime(updated)
    )
    assert await hass.config_entries.async_unload(entry.entry_id)
    hass.states.async_set("sensor.packet_clock_x9", "unavailable")
    await hass.async_block_till_done()


@pytest.mark.parametrize(
    "value",
    [
        None,
        "unknown",
        "unavailable",
        "not-a-date",
        "1234567890",
        "2026-02-28",
        "2026-02-28T10:34:56",
        "2026-02-30T10:34:56Z",
        "2026-02-28T10:34:56+99:00",
        "2026-03-01T00:00:01Z",
    ],
)
async def test_invalid_timestamp_is_unavailable(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, value: str | None
) -> None:
    """Reject missing, invalid, naive and future timestamps, then recover."""
    freezer.move_to("2026-03-01T00:00:00Z")
    if value is not None:
        hass.states.async_set("sensor.packet_clock", value)
    entry = _entry({"front_left_last_received": "sensor.packet_clock"})
    await _setup(hass, entry)
    entity = _entity(hass, entry, "last_received")
    assert hass.states.get(entity.entity_id).state == "unavailable"
    hass.states.async_set("sensor.packet_clock", "2026-02-28T23:59:59Z")
    await hass.async_block_till_done()
    assert hass.states.get(entity.entity_id).state != "unavailable"
    hass.states.async_set("sensor.packet_clock", "unavailable")
    await hass.async_block_till_done()
    assert hass.states.get(entity.entity_id).state == "unavailable"


async def test_timestamp_domain_and_omission(hass: HomeAssistant) -> None:
    """Legacy non-sensor mappings are unavailable; omitted mappings add nothing."""
    hass.states.async_set("input_number.clock", dt_util.utcnow().isoformat())
    entry = _entry({"front_left_last_received": "input_number.clock"})
    await _setup(hass, entry)
    entity = _entity(hass, entry, "last_received")
    assert hass.states.get(entity.entity_id).state == "unavailable"
    assert (
        er.async_get(hass).async_get_entity_id(
            "sensor", DOMAIN, f"{entry.entry_id}_tire_front_right_last_received"
        )
        is None
    )


@pytest.mark.parametrize("domain", ["sensor", "number", "input_number"])
@pytest.mark.parametrize(
    ("metric", "value", "unit", "expected", "native_unit"),
    [
        ("pressure", 50, "psi", 344.7378646584, "kPa"),
        ("temperature", 86, "°F", 30, "°C"),
    ],
)
async def test_retains_real_samples_during_outage(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    domain: str,
    metric: str,
    value: float,
    unit: str,
    expected: float,
    native_unit: str,
) -> None:
    """Retain native values, not outage times, even for helper/template sources."""
    freezer.move_to("2026-03-01T00:00:00Z")
    source = f"{domain}.arbitrary_channel"
    hass.states.async_set(source, str(value), {"unit_of_measurement": unit})
    report_time = hass.states.get(source).last_reported.isoformat()
    entry = _entry(
        {
            f"front_left_{metric}": source,
            "front_left_last_received": "sensor.radio_clock",
        }
    )
    await _setup(hass, entry)
    entity = _entity(hass, entry, metric)
    attributes = hass.states.get(entity.entity_id).attributes
    assert attributes["last_valid_value"] == pytest.approx(expected)
    assert attributes["last_valid_unit"] == native_unit
    assert attributes["last_valid_time"] == report_time
    assert attributes["last_valid_source"] == source
    # An unrelated timestamp/other tire channel must not advance retained time.
    freezer.tick(timedelta(minutes=2))
    hass.states.async_set("sensor.radio_clock", "2026-02-28T23:59:59Z")
    await hass.async_block_till_done()
    assert (
        hass.states.get(entity.entity_id).attributes["last_valid_time"] == report_time
    )
    for bad in ("unavailable", "unknown", "nan", "inf", "bad"):
        freezer.tick(timedelta(seconds=1))
        hass.states.async_set(source, bad)
        await hass.async_block_till_done()
        state = hass.states.get(entity.entity_id)
        assert state.state == "unavailable"
        assert state.attributes["last_valid_time"] == report_time
        assert state.attributes["last_valid_value"] == pytest.approx(expected)
    hass.states.async_remove(source)
    await hass.async_block_till_done()
    assert (
        hass.states.get(entity.entity_id).attributes["last_valid_time"] == report_time
    )
    # A new valid reading recovers availability and advances the report time.
    freezer.tick(timedelta(minutes=1))
    hass.states.async_set(source, str(value), {"unit_of_measurement": unit})
    await hass.async_block_till_done()
    assert hass.states.get(entity.entity_id).state != "unavailable"
    report_time = hass.states.get(source).last_reported.isoformat()
    assert (
        hass.states.get(entity.entity_id).attributes["last_valid_time"] == report_time
    )
    # Identical real reports update last_reported, not last_updated.
    freezer.tick(timedelta(minutes=1))
    hass.states.async_set(source, str(value), {"unit_of_measurement": unit})
    await hass.async_block_till_done()
    new_time = hass.states.get(source).last_reported.isoformat()
    assert new_time != report_time
    assert hass.states.get(entity.entity_id).attributes["last_valid_time"] == new_time
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize(
    ("metric", "old_unit", "value", "new_unit", "expected"),
    [
        ("pressure", "psi", 50, "kPa", 344.7378646584),
        ("temperature", "°F", 86, "°C", 30),
    ],
)
async def test_restart_restores_metadata_not_state(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    metric: str,
    old_unit: str,
    value: float,
    new_unit: str,
    expected: float,
) -> None:
    """Restore historical native-unit data even when the persisted state is offline."""
    freezer.move_to("2026-03-01T00:00:00Z")
    source = "sensor.irregular"
    entry = _entry({f"front_left_{metric}": source})
    entity = er.async_get(hass).async_get_or_create(
        "sensor", DOMAIN, f"{entry.entry_id}_tire_front_left_{metric}"
    )
    mock_restore_cache(
        hass,
        [
            State(
                entity.entity_id,
                "unavailable",
                {
                    "last_valid_value": value,
                    "last_valid_unit": old_unit,
                    "last_valid_time": "2026-02-28T23:59:00+00:00",
                    "last_valid_source": source,
                },
            )
        ],
    )
    await _setup(hass, entry)
    state = hass.states.get(entity.entity_id)
    assert state.state == "unavailable"
    assert state.attributes["last_valid_value"] == pytest.approx(expected)
    assert state.attributes["last_valid_unit"] == new_unit
    assert state.attributes["last_valid_time"] == "2026-02-28T23:59:00+00:00"


@pytest.mark.parametrize(
    "invalid",
    [
        {"last_valid_source": "sensor.previous_mapping"},
        {"last_valid_source": None},
        {"last_valid_value": "50"},
        {"last_valid_value": True},
        {"last_valid_value": float("nan")},
        {"last_valid_value": float("inf")},
        {"last_valid_value": None},
        {"last_valid_unit": None},
        {"last_valid_unit": "°C"},
        {"last_valid_unit": "bananas"},
        {"last_valid_value": 1e308, "last_valid_unit": "bar"},
        {"last_valid_time": None},
        {"last_valid_time": "2026-03-01T00:00:00"},
        {"last_valid_time": "2026-03-01T00:00:01Z"},
    ],
)
async def test_bad_restore_is_discarded(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, invalid: dict
) -> None:
    """Never trust mismatched sources, nonnumeric values or invalid unit/time data."""
    freezer.move_to("2026-03-01T00:00:00Z")
    entry = _entry({"front_left_pressure": "sensor.current_mapping"})
    entity = er.async_get(hass).async_get_or_create(
        "sensor", DOMAIN, f"{entry.entry_id}_tire_front_left_pressure"
    )
    attributes = {
        "last_valid_value": 50,
        "last_valid_unit": "psi",
        "last_valid_time": "2026-02-28T23:59:00Z",
        "last_valid_source": "sensor.current_mapping",
        **invalid,
    }
    mock_restore_cache(hass, [State(entity.entity_id, "50", attributes)])
    await _setup(hass, entry)
    state = hass.states.get(entity.entity_id)
    assert state.state == "unavailable"
    assert not any(key.startswith("last_valid_") for key in state.attributes)


async def test_reload_units_remap_and_override(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Keep retained samples through reload and profile edits, but not source remaps."""
    freezer.move_to("2026-03-01T00:00:00Z")
    hass.config.units = US_CUSTOMARY_SYSTEM
    hass.states.async_set(
        "sensor.nonuniform",
        "50",
        {"unit_of_measurement": "psi", "device_class": "pressure"},
    )
    entry = _entry({"front_left_pressure": "sensor.nonuniform"})
    await _setup(hass, entry)
    entity = _entity(hass, entry, "pressure")
    assert hass.states.get(entity.entity_id).attributes["unit_of_measurement"] == "kPa"
    er.async_get(hass).async_update_entity_options(
        entity.entity_id, "sensor", {"unit_of_measurement": "bar"}
    )
    await hass.async_block_till_done()
    state = hass.states.get(entity.entity_id)
    assert float(state.state) == pytest.approx(3.447378646584)
    assert state.attributes["last_valid_unit"] == "kPa"
    report_time = state.attributes["last_valid_time"]
    freezer.tick(timedelta(minutes=10))
    hass.states.async_set("sensor.nonuniform", "unavailable")
    await hass.async_block_till_done()
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert (
        hass.states.get(entity.entity_id).attributes["last_valid_time"] == report_time
    )
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, "measurement_system": "us_customary"}
    )
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get(entity.entity_id)
    assert state.state == "unavailable"
    assert state.attributes["last_valid_value"] == pytest.approx(50)
    assert state.attributes["last_valid_unit"] == "psi"
    assert state.attributes["last_valid_time"] == report_time
    # User display override remains separate from native retained-unit metadata.
    assert er.async_get(hass).async_get(entity.entity_id).options["sensor"] == {
        "unit_of_measurement": "bar"
    }
    hass.config_entries.async_update_entry(
        entry,
        options={
            CONF_TIRE_ENTITY_MAPPINGS: {"front_left_pressure": "sensor.new_radio"}
        },
    )
    await hass.async_block_till_done()
    state = hass.states.get(entity.entity_id)
    assert state.state == "unavailable"
    assert "last_valid_value" not in state.attributes
    assert _entity(hass, entry, "pressure").entity_id == entity.entity_id


async def test_current_sample_wins_and_no_retention_for_other_metrics(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Live valid source samples replace restored metadata; battery is not retained."""
    freezer.move_to("2026-03-01T00:00:00Z")
    entry = _entry(
        {
            "front_left_pressure": "sensor.radio",
            "front_left_battery": "sensor.cell",
        }
    )
    entity = er.async_get(hass).async_get_or_create(
        "sensor", DOMAIN, f"{entry.entry_id}_tire_front_left_pressure"
    )
    mock_restore_cache(
        hass,
        [
            State(
                entity.entity_id,
                "42",
                {
                    "last_valid_value": 42,
                    "last_valid_unit": "kPa",
                    "last_valid_time": "2026-02-28T23:59:00Z",
                    "last_valid_source": "sensor.radio",
                },
            )
        ],
    )
    hass.states.async_set("sensor.radio", "300", {"unit_of_measurement": "kPa"})
    hass.states.async_set("sensor.cell", "90", {"unit_of_measurement": "%"})
    await _setup(hass, entry)
    assert hass.states.get(entity.entity_id).attributes["last_valid_value"] == 300
    battery = hass.states.get(_entity(hass, entry, "battery").entity_id)
    assert "last_valid_value" not in battery.attributes
    # Missing optional mappings never acquire historical values from other channels.
    temperature = hass.states.get(_entity(hass, entry, "temperature").entity_id)
    assert temperature.state == "unavailable"
    assert "last_valid_value" not in temperature.attributes
    # An incompatible current source unit neither fabricates state nor erases history.
    hass.states.async_set("sensor.radio", "5", {"unit_of_measurement": "°C"})
    await hass.async_block_till_done()
    assert hass.states.get(entity.entity_id).state == "unavailable"
    assert hass.states.get(entity.entity_id).attributes["last_valid_value"] == 300
    # Ignore impossible report timestamps rather than retaining a future age.
    sensor = HavrvTireSensor(entry, tire_positions(entry.data)[0], "pressure")
    sensor.hass = hass
    source_state = State(
        "sensor.radio",
        "400",
        {"unit_of_measurement": "kPa"},
        last_reported=dt_util.utcnow() + timedelta(days=1),
    )
    with patch.object(sensor, "_source_state", return_value=source_state):
        sensor._capture_last_valid()
    assert not sensor.extra_state_attributes


async def test_timestamp_not_required_by_numeric_advisories(
    hass: HomeAssistant,
) -> None:
    """Reception clocks do not participate in numeric data presence/problem loops."""
    entry = _entry(
        {
            "front_left_pressure": "sensor.p",
            "front_left_temperature": "input_number.t",
            "front_left_battery": "number.b",
            "front_left_last_received": "sensor.offline_clock",
        }
    )
    hass.states.async_set("sensor.p", "750", {"unit_of_measurement": "kPa"})
    hass.states.async_set("input_number.t", "25", {"unit_of_measurement": "°C"})
    hass.states.async_set("number.b", "90", {"unit_of_measurement": "%"})
    await _setup(hass, entry)
    position = tire_positions(entry.data)[0]
    assert tire_data_present(hass, entry, position)
    assert not tire_problem(hass, entry, position, "pressure")
    assert hass.states.get(_entity(hass, entry, "last_received").entity_id).state == (
        "unavailable"
    )


async def test_conversion_overflow_is_not_a_valid_sample(
    hass: HomeAssistant,
) -> None:
    """Finite raw numbers whose conversion overflows are not retained or current."""
    entry = _entry({"front_left_pressure": "sensor.overflow"})
    hass.states.async_set("sensor.overflow", "1e308", {"unit_of_measurement": "psi"})
    await _setup(hass, entry)
    state = hass.states.get(_entity(hass, entry, "pressure").entity_id)
    assert state.state == "unavailable"
    assert "last_valid_value" not in state.attributes


@pytest.mark.parametrize(
    ("metric", "unit"),
    [("pressure", "kPa"), ("temperature", "°C"), ("battery", "%")],
)
async def test_current_source_capability(
    hass: HomeAssistant, metric: str, unit: str
) -> None:
    """Distinguish omitted/offline mappings using config, never restored sources."""
    entry = _entry()
    registry = er.async_get(hass)
    entity = registry.async_get_or_create(
        "sensor", DOMAIN, f"{entry.entry_id}_tire_front_left_{metric}"
    )
    mock_restore_cache(
        hass,
        [State(entity.entity_id, "unavailable", {"source_entity_id": "sensor.old"})],
    )
    await _setup(hass, entry)
    state = hass.states.get(entity.entity_id)
    assert state.state == "unavailable"
    assert "source_entity_id" in state.attributes
    assert state.attributes["source_entity_id"] is None

    source = "sensor.irregular_channel"
    hass.config_entries.async_update_entry(
        entry,
        options={CONF_TIRE_ENTITY_MAPPINGS: {f"front_left_{metric}": source}},
    )
    await hass.async_block_till_done()
    # Configured but missing/never valid must still expose the current source.
    state = hass.states.get(entity.entity_id)
    assert state.state == "unavailable"
    assert state.attributes["source_entity_id"] == source
    assert "last_valid_value" not in state.attributes
    hass.states.async_set(source, "bad", {"unit_of_measurement": unit})
    await hass.async_block_till_done()
    assert hass.states.get(entity.entity_id).attributes["source_entity_id"] == source

    hass.states.async_set(source, "25", {"unit_of_measurement": unit})
    await hass.async_block_till_done()
    state = hass.states.get(entity.entity_id)
    assert state.state != "unavailable"
    assert state.attributes["source_entity_id"] == source
    retained = {
        key: value
        for key, value in state.attributes.items()
        if key.startswith("last_valid_")
    }
    hass.states.async_set(source, "unavailable")
    await hass.async_block_till_done()
    state = hass.states.get(entity.entity_id)
    assert state.state == "unavailable"
    assert state.attributes["source_entity_id"] == source
    assert all(state.attributes[key] == value for key, value in retained.items())

    # A missing replacement immediately identifies the new mapping after reload;
    # neither restored capability attributes nor retained old samples may win.
    replacement = "sensor.new_radio"
    hass.config_entries.async_update_entry(
        entry,
        options={CONF_TIRE_ENTITY_MAPPINGS: {f"front_left_{metric}": replacement}},
    )
    await hass.async_block_till_done()
    state = hass.states.get(entity.entity_id)
    assert state.state == "unavailable"
    assert state.attributes["source_entity_id"] == replacement
    assert "last_valid_value" not in state.attributes
    assert _entity(hass, entry, metric).entity_id == entity.entity_id

    hass.config_entries.async_update_entry(
        entry, options={CONF_TIRE_ENTITY_MAPPINGS: {}}
    )
    await hass.async_block_till_done()
    state = hass.states.get(entity.entity_id)
    assert state.state == "unavailable"
    assert state.attributes["source_entity_id"] is None
