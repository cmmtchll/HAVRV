"""Chassis source configuration, sparse history, ratios and profile-unit lifecycle."""

from collections import deque
from copy import deepcopy
from datetime import timedelta
from unittest.mock import patch

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_system import METRIC_SYSTEM, US_CUSTOMARY_SYSTEM
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.havrv.chassis import (
    WINDOWS,
    ChassisHistory,
    CounterChange,
    CounterSample,
    _restore_sample,
    change_value,
    storage_key,
)
from custom_components.havrv.configuration import _normalize_options, _options_schema
from custom_components.havrv.const import CHASSIS_METRICS, CONF_CHASSIS_SOURCES, DOMAIN
from custom_components.havrv.diagnostics import async_get_config_entry_diagnostics
from custom_components.havrv.management import (
    Candidate,
    editable_values,
    editor_schema,
    validate_values,
)
from custom_components.havrv.sensor import HavrvChassisSensor

SOURCES = {
    "distance": "sensor.odometer",
    "fuel": "number.template_fuel_used",
    "engine_hours": "input_number.engine_time",
}


def chassis_entry(units="metric", sources=None):
    """Create a profile with independently optional chassis counters."""
    return MockConfigEntry(
        domain=DOMAIN,
        version=3,
        title="RV",
        data={"name": "RV", "measurement_system": units},
        options={CONF_CHASSIS_SOURCES: SOURCES if sources is None else sources},
    )


def eid(hass, entry, metric, period="total"):
    """Resolve stable identities without assuming translated entity IDs."""
    return er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_chassis_counter_{metric}_{period}"
    )


def sources(hass, distance=1000, fuel=100, hours=100, units=("km", "L", "h")):
    """Set all current counters before their source events are processed."""
    for metric, value, unit in zip(
        CHASSIS_METRICS, (distance, fuel, hours), units, strict=True
    ):
        hass.states.async_set(
            SOURCES[metric], str(value), {"unit_of_measurement": unit}
        )


async def setup(hass, entry):
    """Use actual config-entry setup and platform forwarding."""
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.parametrize(
    ("profile", "ha_units", "distance", "fuel"),
    [
        ("metric", US_CUSTOMARY_SYSTEM, 1609.344, 378.5411784),
        ("us_customary", METRIC_SYSTEM, 1000, 100),
    ],
)
async def test_totals_units_and_user_overrides(hass, profile, ha_units, distance, fuel):
    """Counter and duration conversions follow the profile, not global defaults."""
    hass.config.units = ha_units
    sources(hass, 1000, 100, 360000, ("mi", "gal", "s"))
    entry = chassis_entry(profile)
    await setup(hass, entry)
    for metric, expected, unit in (
        ("distance", distance, "km" if profile == "metric" else "mi"),
        ("fuel", fuel, "L" if profile == "metric" else "gal"),
        ("engine_hours", 100, "h"),
    ):
        state = hass.states.get(eid(hass, entry, metric))
        assert float(state.state) == pytest.approx(expected)
        assert state.attributes["unit_of_measurement"] == unit
        assert state.attributes["state_class"] == "total_increasing"
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, f"{entry.entry_id}_chassis"), entry.entry_id
    )
    assert device.name == "Chassis"
    assert (
        er.async_get(hass).async_get(eid(hass, entry, "distance")).device_id
        == device.id
    )
    registry = er.async_get(hass)
    registry.async_update_entity_options(
        eid(hass, entry, "distance"), "sensor", {"unit_of_measurement": "m"}
    )
    await hass.async_block_till_done()
    assert float(hass.states.get(eid(hass, entry, "distance")).state) == pytest.approx(
        1609344
    )
    assert "Total fuel used" in hass.states.get(eid(hass, entry, "fuel")).name


async def test_partial_windows_latest_ratios_and_sparse_history(hass, freezer):
    """Ignition-off keeps historical endpoints without extending or zero-filling."""
    freezer.move_to("2026-11-01T00:00:00Z")
    sources(hass)
    entry = chassis_entry()
    await setup(hass, entry)
    for metric in (*CHASSIS_METRICS, "fuel_rate", "economy"):
        assert hass.states.get(eid(hass, entry, metric, "5m")).state == "unavailable"
    freezer.tick(timedelta(seconds=30))
    sources(hass, 1001, 100.1, 100 + 30 / 3600)
    await hass.async_block_till_done()
    for period in ("latest", *WINDOWS):
        for metric, expected in (
            ("distance", 1),
            ("fuel", 0.1),
            ("engine_hours", 30 / 3600),
            ("fuel_rate", 12),
            ("economy", 10),
        ):
            state = hass.states.get(eid(hass, entry, metric, period))
            assert state.state != "unavailable", (
                metric,
                period,
                entry.runtime_data.chassis_history.recent,
            )
            assert float(state.state) == pytest.approx(expected)
            assert state.attributes["covered_seconds"] == 30
    freezer.tick(timedelta(seconds=90))
    sources(hass, 1003, 100.3, 100 + 120 / 3600)
    await hass.async_block_till_done()
    state = hass.states.get(eid(hass, entry, "distance", "5m"))
    assert float(state.state) == pytest.approx(3)
    assert state.attributes["requested_seconds"] == 300
    assert state.attributes["covered_seconds"] == 120
    end = state.attributes["interval_end"]
    freezer.tick(timedelta(seconds=1))
    for source in SOURCES.values():
        hass.states.async_set(source, "unavailable")
    await hass.async_block_till_done()
    for metric in CHASSIS_METRICS:
        assert hass.states.get(eid(hass, entry, metric)).state == "unavailable"
        assert (
            "last_valid_time" in hass.states.get(eid(hass, entry, metric)).attributes
        ), (
            metric,
            entry.runtime_data.chassis_history.last_valid,
            hass.states.get(eid(hass, entry, metric)).attributes,
        )
        assert (
            hass.states.get(eid(hass, entry, metric)).attributes["last_valid_time"]
            == end
        )
    assert (
        hass.states.get(eid(hass, entry, "distance", "5m")).attributes["interval_end"]
        == end
    )
    assert any(
        value is None
        for _, value in entry.runtime_data.chassis_history.trend("distance")
    )
    freezer.tick(timedelta(hours=6))
    entry.runtime_data.chassis_history._tick(dt_util.utcnow())
    await hass.async_block_till_done()
    assert hass.states.get(eid(hass, entry, "distance", "5m")).state == "unavailable"
    assert hass.states.get(eid(hass, entry, "distance", "1h")).state == "unavailable"
    assert float(hass.states.get(eid(hass, entry, "distance", "8h")).state) == 3
    assert (
        hass.states.get(eid(hass, entry, "distance", "8h")).attributes["interval_end"]
        == end
    )
    history = entry.runtime_data.chassis_history
    assert await hass.config_entries.async_unload(entry.entry_id)
    sources(hass, 1004, 100.4, 101)
    await hass.async_block_till_done()
    assert history.current == {}
    for source in SOURCES.values():
        hass.states.async_set(source, "unavailable")
    freezer.tick(timedelta(seconds=1))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert float(hass.states.get(eid(hass, entry, "distance", "8h")).state) == 3
    assert len(entry.runtime_data.chassis_history.samples) > 1
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["entry_options"][CONF_CHASSIS_SOURCES] == "**REDACTED**"


@pytest.mark.parametrize(
    ("value", "unit"),
    [
        ("unavailable", "km"),
        ("unknown", "km"),
        ("bad", "km"),
        ("nan", "km"),
        ("inf", "km"),
        ("-1", "km"),
        ("0", None),
        ("1", "L"),
    ],
)
async def test_invalid_source_recovers_without_erasing_history(
    hass, freezer, value, unit
):
    """Unavailable and incompatible units are unknown, not counter resets."""
    sources(hass)
    entry = chassis_entry()
    await setup(hass, entry)
    freezer.tick(timedelta(seconds=30))
    sources(hass, 1001, 101, 101)
    await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=1))
    hass.states.async_set(SOURCES["distance"], value, {"unit_of_measurement": unit})
    await hass.async_block_till_done()
    assert hass.states.get(eid(hass, entry, "distance")).state == "unavailable"
    assert float(hass.states.get(eid(hass, entry, "distance", "30d")).state) == 1
    freezer.tick(timedelta(seconds=1))
    sources(hass, 1002, 102, 102)
    await hass.async_block_till_done()
    assert float(hass.states.get(eid(hass, entry, "distance", "30d")).state) == 2


async def test_reset_remap_profile_reload_and_clear(hass, freezer):
    """Reset affected history while preserving the remapped total identity."""
    sources(hass)
    entry = chassis_entry()
    await setup(hass, entry)
    identities = {metric: eid(hass, entry, metric) for metric in CHASSIS_METRICS}
    freezer.tick(timedelta(minutes=2))
    sources(hass, 1002, 101, 101)
    await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=1))
    sources(hass, 0, 101, 101)
    await hass.async_block_till_done()
    assert hass.states.get(eid(hass, entry, "distance", "30d")).state == "unavailable"
    assert float(hass.states.get(eid(hass, entry, "fuel", "30d")).state) == 1
    assert hass.states.get(eid(hass, entry, "economy", "latest")).state == "unavailable"
    freezer.tick(timedelta(seconds=30))
    sources(hass, 1, 102, 102)
    await hass.async_block_till_done()
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, "measurement_system": "us_customary"}
    )
    await hass.async_block_till_done()
    assert float(
        hass.states.get(eid(hass, entry, "distance", "30d")).state
    ) == pytest.approx(1 / 1.609344)
    new_sources = {**SOURCES, "distance": "number.new_odometer"}
    hass.states.async_set("number.new_odometer", "10", {"unit_of_measurement": "mi"})
    freezer.tick(timedelta(seconds=1))
    hass.config_entries.async_update_entry(
        entry, options={CONF_CHASSIS_SOURCES: new_sources}
    )
    await hass.async_block_till_done()
    assert identities == {
        metric: eid(hass, entry, metric) for metric in CHASSIS_METRICS
    }
    assert float(hass.states.get(identities["distance"]).state) == 10
    assert hass.states.get(eid(hass, entry, "distance", "30d")).state == "unavailable"
    assert float(
        hass.states.get(eid(hass, entry, "fuel", "30d")).state
    ) == pytest.approx(2 / 3.785411784)
    hass.config_entries.async_update_entry(entry, options={})
    await hass.async_block_till_done()
    assert all(er.async_get(hass).async_get(id) is None for id in identities.values())
    assert entry.runtime_data.chassis_history is None
    # Re-adding the same source after a clear must not resurrect the old counter era.
    hass.config_entries.async_update_entry(
        entry, options={CONF_CHASSIS_SOURCES: SOURCES}
    )
    await hass.async_block_till_done()
    assert hass.states.get(eid(hass, entry, "fuel", "30d")).state == "unavailable"
    assert await hass.config_entries.async_remove(entry.entry_id)


@pytest.mark.parametrize("domain", ["sensor", "number", "input_number"])
def test_shared_selectors_validation_and_roundtrip(domain):
    """Native recovery and panel forms accept identical helper/template domains."""
    entry = chassis_entry(sources={})
    native = {
        str(key): selector.serialize()["selector"]
        for key, selector in _options_schema(entry).schema.items()
    }
    panel = editor_schema(Candidate(dict(entry.data), {}), "metric")["options"]
    for metric in CHASSIS_METRICS:
        name = f"chassis_{metric}"
        assert native[name]["entity"]["domain"] == ["sensor", "number", "input_number"]
        assert (
            next(field for field in panel if field["name"] == name)["selector"]
            == native[name]
        )
        values = editable_values(entry, "metric")
        values["options"][name] = f"{domain}.template"
        candidate, _, errors, _ = validate_values(entry, values, "metric")
        assert not errors
        assert candidate.options[CONF_CHASSIS_SOURCES] == {metric: f"{domain}.template"}
    entry = chassis_entry()
    result, _, errors, impacts = validate_values(
        entry, deepcopy(editable_values(entry, "metric")), "metric"
    )
    assert not errors and not impacts and result.options == entry.options
    assert (
        _normalize_options({"chassis_distance": ""}, entry)[0][CONF_CHASSIS_SOURCES]
        == {}
    )


@pytest.mark.parametrize("value", [True, 1, [], "bad", "sensor.", "switch.test"])
def test_invalid_mapping_reported_in_chassis(value):
    """Invalid submitted sources surface in the correct management section."""
    entry = chassis_entry()
    assert (
        _normalize_options({"chassis_distance": value}, entry)[1]
        == "invalid_chassis_source"
    )
    values = editable_values(entry, "metric")
    values["options"]["chassis_distance"] = value
    _, _, errors, _ = validate_values(entry, values, "metric")
    assert errors == [
        {"section": "chassis", "field": "", "code": "invalid_chassis_source"}
    ]


@pytest.mark.parametrize(
    ("metric", "units", "expected"),
    [
        ("economy", "metric", None),
        ("economy", "us_customary", 0),
        ("fuel_rate", "metric", None),
        ("distance", "metric", 0),
    ],
)
def test_zero_denominators_are_not_fabricated(metric, units, expected):
    """Idling and zero increments are handled without infinity or guessed rates."""
    change = CounterChange(
        CounterSample(1, {"distance": 0, "fuel": 0, "engine_hours": 0}),
        CounterSample(2, {"distance": 0, "fuel": 1, "engine_hours": 0}),
    )
    assert change_value(change, metric, units) == expected


@pytest.mark.parametrize(
    "raw",
    [
        {},
        {"time": "bad", "values": {}},
        {"time": 5, "values": {"fuel": -1}},
        {"time": 5, "values": {"unknown": 1}},
        {"time": 11, "values": {}},
    ],
)
def test_invalid_persistent_samples(raw):
    """Corrupt, nonfinite and future samples cannot become counter baselines."""
    with pytest.raises(ValueError):
        _restore_sample(raw, 10)


async def test_partial_mappings_legacy_and_self_mapping(hass):
    """A missing mapping creates no invented channel; recursive sources are unknown."""
    sources(hass)
    entry = chassis_entry(sources={"distance": SOURCES["distance"]})
    await setup(hass, entry)
    assert eid(hass, entry, "distance")
    assert eid(hass, entry, "fuel") is None
    assert eid(hass, entry, "economy", "5m") is None
    with patch.object(entry.runtime_data, "device_id", None):
        with pytest.raises(RuntimeError):
            HavrvChassisSensor(
                entry, entry.runtime_data.chassis_history, "distance", "total"
            )
    self_source = eid(hass, entry, "distance")
    hass.config_entries.async_update_entry(
        entry, options={CONF_CHASSIS_SOURCES: {"distance": self_source}}
    )
    await hass.async_block_till_done()
    assert hass.states.get(self_source).state == "unavailable"
    legacy = MockConfigEntry(domain=DOMAIN, version=3, data={"name": "Legacy"})
    await setup(hass, legacy)
    assert eid(hass, legacy, "distance") is None
    assert storage_key(entry.entry_id) != storage_key(legacy.entry_id)


async def test_asynchronous_and_unchanged_reports_have_matched_latest_intervals(
    hass, freezer
):
    """Latest ratios wait for each input, and unrelated reports cannot refresh ages."""
    sources(hass)
    entry = chassis_entry()
    await setup(hass, entry)
    freezer.tick(timedelta(seconds=10))
    hass.states.async_set(SOURCES["distance"], "1001", {"unit_of_measurement": "km"})
    await hass.async_block_till_done()
    distance_time = hass.states.get(eid(hass, entry, "distance")).attributes[
        "last_valid_time"
    ]
    assert hass.states.get(eid(hass, entry, "economy", "latest")).state == "unavailable"
    freezer.tick(timedelta(seconds=10))
    hass.states.async_set(SOURCES["fuel"], "100.1", {"unit_of_measurement": "L"})
    await hass.async_block_till_done()
    assert float(
        hass.states.get(eid(hass, entry, "economy", "latest")).state
    ) == pytest.approx(10)
    assert (
        hass.states.get(eid(hass, entry, "fuel_rate", "latest")).state == "unavailable"
    )
    freezer.tick(timedelta(seconds=10))
    hass.states.async_set(
        SOURCES["engine_hours"], "100.01", {"unit_of_measurement": "h"}
    )
    await hass.async_block_till_done()
    assert float(
        hass.states.get(eid(hass, entry, "fuel_rate", "latest")).state
    ) == pytest.approx(10)
    assert (
        hass.states.get(eid(hass, entry, "distance")).attributes["last_valid_time"]
        == distance_time
    )
    freezer.tick(timedelta(seconds=10))
    hass.states.async_set(SOURCES["fuel"], "100.1", {"unit_of_measurement": "L"})
    await hass.async_block_till_done()
    assert float(hass.states.get(eid(hass, entry, "fuel", "latest")).state) == 0
    freezer.tick(timedelta(seconds=10))
    hass.states.async_set(
        SOURCES["engine_hours"], "100.01", {"unit_of_measurement": "h"}
    )
    await hass.async_block_till_done()
    assert (
        hass.states.get(eid(hass, entry, "fuel_rate", "latest")).state == "unavailable"
    )


@pytest.mark.parametrize(
    "damage",
    [
        "root",
        "sources",
        "samples",
        "recent",
        "last_valid",
        "recent_container",
        "last_valid_container",
    ],
)
async def test_corrupt_saved_history_reports_warning_and_starts_unknown(
    hass, caplog, damage
):
    """Bad mappings/order/intervals/retained samples cannot masquerade as history."""
    sources(hass)
    entry = chassis_entry()
    await setup(hass, entry)
    saved = entry.runtime_data.chassis_history._serialize()
    if damage == "root":
        saved = []
    elif damage == "sources":
        saved["sources"] = []
    elif damage == "samples":
        saved["samples"] *= 2
    elif damage == "recent":
        saved["recent"]["economy"] = [CounterSample(1, {}).as_dict()]
    elif damage == "last_valid":
        saved["last_valid"]["distance"] = CounterSample(1, {}).as_dict()
    elif damage == "recent_container":
        saved["recent"] = []
    else:
        saved["last_valid"] = []
    history = ChassisHistory(hass, entry)
    with patch.object(history.store, "async_load", return_value=saved):
        await history.async_setup()
    assert "Unable to restore chassis history" in caplog.text
    assert history.change("distance", "30d") is None
    assert history.current["distance"] == 1000


async def test_history_is_bounded_and_retains_only_observed_endpoints(hass):
    """A noisy source cannot grow the month buffer without limit or extrapolation."""
    sources(hass)
    entry = chassis_entry()
    await setup(hass, entry)
    history = entry.runtime_data.chassis_history
    now = dt_util.utcnow().timestamp()
    history.samples = deque(
        CounterSample(now - 100001 + index, {"distance": float(index)})
        for index in range(100001)
    )
    history._tick(dt_util.utcnow())
    assert len(history.samples) == 100000
    assert history.samples[0].values["distance"] == 1
    assert history.change("distance", "1d").end.time == now - 1
    assert len(history.trend("distance")) <= 100
    history._prune(now + WINDOWS["30d"] + 1)
    assert not history.samples


async def test_counter_reset_after_month_long_gap_clears_retained_latest(hass, freezer):
    """A reset remains detectable after the rolling samples have all expired."""
    sources(hass)
    entry = chassis_entry()
    await setup(hass, entry)
    freezer.tick(timedelta(minutes=1))
    sources(hass, distance=1010, fuel=101, hours=101)
    await hass.async_block_till_done()
    for entity_id in SOURCES.values():
        hass.states.async_set(entity_id, "unavailable")
    await hass.async_block_till_done()
    freezer.tick(timedelta(days=31))
    history = entry.runtime_data.chassis_history
    history._tick(dt_util.utcnow())
    assert not history.samples
    assert history.change("distance", "latest") is not None
    sources(hass, distance=10, fuel=1, hours=1)
    await hass.async_block_till_done()
    for metric in ("distance", "fuel", "engine_hours", "fuel_rate", "economy"):
        assert history.change(metric, "latest") is None
        assert history.change(metric, "30d") is None
    assert float(hass.states.get(eid(hass, entry, "distance")).state) == 10


async def test_native_chassis_recovery_fields_can_be_cleared(hass):
    """Native options have saved suggestions but do not force omitted sources back."""
    entry = chassis_entry()
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    markers = {str(key): key for key in result["data_schema"].schema}
    assert (
        markers["chassis_distance"].description["suggested_value"]
        == SOURCES["distance"]
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={}
    )
    assert result["data"][CONF_CHASSIS_SOURCES] == {}
