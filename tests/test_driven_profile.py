"""Private driven-profile sampling, matched intervals, permissions and lifecycle."""

from copy import deepcopy
from datetime import timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.havrv import HavrvRuntimeData, async_remove_entry
from custom_components.havrv.const import DOMAIN
from custom_components.havrv.diagnostics import async_get_config_entry_diagnostics
from custom_components.havrv.driven_profile import (
    CHANNELS,
    MAX_HISTORY,
    MAX_POINTS,
    MAX_TRIPS,
    OUTPUT_KEYS,
    DrivenProfile,
    _gap,
    _restore_points,
    horizontal_distance,
    storage_key,
)
from custom_components.havrv.websocket_api import (
    async_register_commands,
    websocket_driven_profile,
)

SOURCES = {
    "operations_sources": {
        "location": "device_tracker.gps",
        "altitude": "input_number.altitude",
    },
    "chassis_sources": {"distance": "number.odometer", "fuel": "sensor.fuel"},
}


@pytest.fixture(autouse=True)
async def cleanup_direct_collectors(hass):
    """Unload subscriptions for collectors exercised outside platform setup."""
    yield
    for entry in hass.config_entries.async_entries(DOMAIN):
        await entry._async_process_on_unload(hass)


def entry_for(hass, system="metric", options=None):
    """Provide variable source domains and independent profile units."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=3,
        data={"name": "RV", "measurement_system": system},
        options=deepcopy(SOURCES if options is None else options),
    )
    entry.add_to_hass(hass)
    entry.runtime_data = HavrvRuntimeData(name="RV", measurement_system=system)
    publish_outputs(hass, entry)
    entry.async_on_unload(
        async_track_state_change_event(
            hass,
            [
                "device_tracker.gps",
                "input_number.altitude",
                "number.odometer",
                "sensor.fuel",
            ],
            lambda event: publish_outputs(hass, entry),
        )
    )
    return entry


def publish_outputs(hass, entry):
    """Stand in for registered HAVRV mirrors while isolating the collector tests."""
    mappings = {
        "location": entry.options.get("operations_sources", {}).get("location"),
        "elevation": entry.options.get("operations_sources", {}).get("altitude"),
        "odometer": entry.options.get("chassis_sources", {}).get("distance"),
        "fuel": entry.options.get("chassis_sources", {}).get("fuel"),
    }
    for key, source in mappings.items():
        if not source:
            continue
        domain, suffix = OUTPUT_KEYS[key]
        registered = er.async_get(hass).async_get_or_create(
            domain,
            DOMAIN,
            f"{entry.entry_id}_{suffix}",
            config_entry=entry,
            suggested_object_id=f"renamed_{key}_{entry.entry_id}",
        )
        state = hass.states.get(source)
        attributes = dict(state.attributes) if state else {}
        attributes.update(
            source_entity_id=source,
            **{
                (
                    "source_reported"
                    if key in ("location", "elevation")
                    else "last_valid_time"
                ): state.last_reported.isoformat() if state else None
            },
        )
        hass.states.async_set(
            registered.entity_id, state.state if state else "unavailable", attributes
        )


def report(hass, lon=0, altitude=100, distance=1000, fuel=100, units=("m", "km", "L")):
    """Report explicitly configured synthetic readings without invented values."""
    hass.states.async_set(
        "device_tracker.gps", "not_home", {"latitude": 0, "longitude": lon}
    )
    for entity_id, value, unit in zip(
        ("input_number.altitude", "number.odometer", "sensor.fuel"),
        (altitude, distance, fuel),
        units,
        strict=True,
    ):
        hass.states.async_set(entity_id, str(value), {"unit_of_measurement": unit})


def sample(time, lon=0, altitude=100, distance=1000, fuel=100):
    """Construct a real endpoint representation in canonical units."""
    values = {
        "latitude": 0,
        "longitude": lon,
        "elevation": altitude,
        "odometer": distance,
        "fuel": fuel,
    }
    return {
        "time": time,
        **values,
        "reports": {key: time for key, value in values.items() if value is not None},
    }


async def collector(hass, entry):
    """Subscribe a collector using the same HA APIs as config-entry setup."""
    publish_outputs(hass, entry)
    history = entry.runtime_data.driven_profile = DrivenProfile(hass, entry)
    await history.async_setup()
    await hass.async_block_till_done()
    return history


@pytest.mark.parametrize("system", ["metric", "us_customary"])
async def test_real_endpoints_units_economy_grade(hass, freezer, system):
    """GPS polyline, cumulative deltas and matched economy follow profile units."""
    freezer.move_to("2026-11-01T00:00:00Z")
    report(hass, units=("ft", "mi", "gal"))
    entry = entry_for(hass, system)
    history = await collector(hass, entry)
    first = deepcopy(history.samples[-1])
    freezer.tick(timedelta(seconds=60))
    report(
        hass,
        lon=0.01,
        altitude=110,
        distance=1001,
        fuel=100.1,
        units=("ft", "mi", "gal"),
    )
    await hass.async_block_till_done()
    result = history.payload()
    last = result["points"][-1]
    metric = system == "metric"
    assert result["units"] == {
        "distance": "km" if metric else "mi",
        "elevation": "m" if metric else "ft",
        "fuel": "L" if metric else "gal",
        "economy": "L/100km" if metric else "mpg",
    }
    assert result["points"][0]["odometer"] == 0
    assert result["points"][0]["fuel"] == 0
    assert last["odometer"] == pytest.approx(1.609344 if metric else 1)
    assert last["fuel"] == pytest.approx(0.3785411784 if metric else 0.1)
    assert last["elevation"] == pytest.approx(33.528 if metric else 110)
    assert last["economy"] == pytest.approx(23.5214583 if metric else 10)
    horizontal = horizontal_distance(first, history.samples[-1])
    assert last["grade"] == pytest.approx(3.048 / (horizontal * 1000) * 100)
    assert result["summary"]["ascent"] == pytest.approx(3.048 if metric else 10)
    assert result["summary"]["spatial_distance"] > result["summary"]["gps_distance"]
    assert last["distance"] == result["summary"]["gps_distance"]
    assert "latitude" not in str(result) and "longitude" not in str(result)


async def test_gaps_reset_and_missing_channels(hass, freezer):
    """Reset and unavailable intervals never connect lifetime-counter or GPS gaps."""
    freezer.move_to("2026-11-01T00:00:00Z")
    report(hass)
    history = await collector(hass, entry_for(hass))
    freezer.tick(timedelta(seconds=60))
    report(hass, lon=0.01, distance=1001, fuel=100.1)
    await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=1))
    hass.states.async_set("device_tracker.gps", "unavailable")
    hass.states.async_set("sensor.fuel", "unknown")
    await hass.async_block_till_done()
    assert history.payload()["points"][-1]["distance"] is None
    assert history.payload()["points"][-1]["fuel"] is None
    freezer.tick(timedelta(seconds=60))
    report(hass, lon=1, distance=1, fuel=5)
    await hass.async_block_till_done()
    points = history.payload()["points"]
    assert any(p["odometer"] is None for p in points)
    assert points[-1]["odometer"] == 1
    assert points[-1]["fuel"] == pytest.approx(0.1)
    assert points[-1]["economy"] is None
    assert history.payload()["summary"]["gps_distance"] == pytest.approx(1.1119508)
    assert history.payload()["partial"]


async def test_stale_reports_and_event_cadence(hass, freezer):
    """A timer expires GPS and counters but never manufactures a fresh fix."""
    freezer.move_to("2026-11-01T00:00:00Z")
    report(hass)
    history = await collector(hass, entry_for(hass))
    freezer.tick(timedelta(seconds=5))
    report(hass, lon=0.001, distance=1000.1)
    await hass.async_block_till_done()
    assert len(history.samples) == 1
    freezer.tick(timedelta(seconds=60))
    report(hass, lon=0.002, distance=1000.2)
    await hass.async_block_till_done()
    assert len(history.samples) == 2
    history._tick(dt_util.utcnow())
    assert len(history.samples) == 2
    freezer.tick(timedelta(seconds=181))
    history._tick(dt_util.utcnow())
    assert all(history.samples[-1][key] is None for key in CHANNELS)
    freezer.tick(timedelta(seconds=1))
    report(hass, lon=1, distance=1100)
    await hass.async_block_till_done()
    result = history.payload()
    assert result["summary"]["gps_distance"] == pytest.approx(0.22239016)
    assert result["summary"]["odometer_distance"] == pytest.approx(0.2)
    assert result["partial"]


@pytest.mark.parametrize("stale", ["latitude", "elevation", "odometer", "fuel"])
async def test_ratios_require_shared_new_report_endpoints(hass, freezer, stale):
    """Current grade is never paired with fuel over an unrelated stale interval."""
    freezer.move_to("2026-11-01T01:00:00Z")
    history = DrivenProfile(hass, entry_for(hass))
    now = dt_util.utcnow().timestamp()
    a, b = (
        sample(now - 60),
        sample(now, lon=0.01, altitude=110, distance=1001, fuel=100.1),
    )
    b["reports"][stale] = a["time"]
    history.samples = [a, b]
    point = history.payload()["points"][-1]
    if stale in ("latitude", "elevation"):
        assert point["grade"] is None
    else:
        assert point["economy"] is None


async def test_report_time_gap_and_range_baselines(hass, freezer):
    """Even dense snapshot times cannot bridge sparse/stale GPS report endpoints."""
    freezer.move_to("2026-11-01T02:00:00Z")
    history = DrivenProfile(hass, entry_for(hass))
    now = dt_util.utcnow().timestamp()
    a, b = sample(now - 60), sample(now, lon=1, distance=1001)
    a["reports"] = {key: now - 240 for key in CHANNELS}
    history.samples = [sample(now - 3700), a, b]
    result = history.payload("1h")
    assert len(result["points"]) == 3
    assert all(
        result["points"][1][key] is None for key in result["points"][1] if key != "time"
    )
    assert result["points"][0]["odometer"] == 0
    assert result["summary"]["odometer_distance"] == 0
    assert result["summary"]["gps_distance"] == 0
    assert result["partial"]


@pytest.mark.parametrize(
    ("entity_id", "state", "attributes", "channel"),
    [
        ("device_tracker.gps", "home", {"latitude": 91, "longitude": 0}, "latitude"),
        ("device_tracker.gps", "home", {"latitude": True, "longitude": 0}, "latitude"),
        ("device_tracker.gps", "home", {"latitude": 1}, "latitude"),
        ("input_number.altitude", "nan", {"unit_of_measurement": "m"}, "elevation"),
        ("input_number.altitude", "10", {"unit_of_measurement": "°C"}, "elevation"),
        ("number.odometer", "-1", {"unit_of_measurement": "km"}, "odometer"),
        ("sensor.fuel", "1", {}, "fuel"),
    ],
)
async def test_invalid_passthrough_sources(
    hass, freezer, entity_id, state, attributes, channel
):
    """Source validation accepts helpers/templates but not invalid readings/units."""
    freezer.move_to("2026-11-01T00:00:00Z")
    report(hass)
    hass.states.async_set(entity_id, state, attributes)
    history = await collector(hass, entry_for(hass))
    assert history.samples[-1][channel] is None


async def test_trip_lifecycle_persistence_remapping_and_diagnostics(hass, freezer):
    """Trips survive reloads, independent history limits and source changes."""
    freezer.move_to("2026-11-01T00:00:00Z")
    report(hass)
    entry = entry_for(hass)
    history = await collector(hass, entry)
    await history.async_action("start", "  Hill route  ")
    trip_id = history.active["id"]
    assert history.active["name"] == "Hill route"
    assert history.payload(trip_id=trip_id)["points"][0]["fuel"] == 0
    with pytest.raises(ValueError, match="already active"):
        await history.async_action("start")
    freezer.tick(timedelta(seconds=60))
    report(hass, lon=0.01, distance=1001, fuel=100.1)
    await hass.async_block_till_done()
    await history.async_save()
    saved = await Store(hass, 1, storage_key(entry.entry_id)).async_load()
    assert saved["active"]["name"] == "Hill route"
    await entry._async_process_on_unload(hass)
    freezer.tick(timedelta(seconds=60))
    options = deepcopy(SOURCES)
    options["operations_sources"]["location"] = "device_tracker.other"
    hass.config_entries.async_update_entry(entry, options=options)
    hass.states.async_set(
        "device_tracker.other", "home", {"latitude": 0, "longitude": 1}
    )
    report(hass, distance=1002, fuel=100.2)
    restored = await collector(hass, entry)
    assert restored.active["id"] == trip_id
    assert "device_tracker.gps" in restored.source_ids
    assert "device_tracker.other" in restored.source_ids
    result = restored.payload(trip_id=trip_id)
    assert result["summary"]["gps_distance"] == pytest.approx(1.1119508)
    assert any(p["distance"] is None for p in result["points"])
    await restored.async_action("stop")
    assert restored.active is None
    assert restored.trips[0]["end"] == dt_util.utcnow().timestamp()
    assert restored.payload(trip_id=trip_id)["trips"][0]["id"] == trip_id
    with pytest.raises(ValueError, match="No driven-profile"):
        await restored.async_action("stop")
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert "Hill route" not in str(diagnostics)
    assert "longitude" not in str(diagnostics)
    await async_remove_entry(hass, entry)
    assert await Store(hass, 1, storage_key(entry.entry_id)).async_load() is None


async def test_bounded_trip_and_payload_history(hass, freezer):
    """Keep a day of minute samples, cap trip/response counts and rebase truncation."""
    freezer.move_to("2026-11-01T00:00:00Z")
    history = DrivenProfile(hass, entry_for(hass))
    now = dt_util.utcnow().timestamp()
    history.samples = [
        sample(now - (1440 - i) * 60, lon=i * 0.00001, distance=1000 + i)
        for i in range(1441)
    ]
    assert len(history.payload("1d")["points"]) == 1441
    await history.async_action("start")
    for i in range(MAX_HISTORY + 10):
        history._append(sample(now + i / 100, distance=1000 + i))
    assert len(history.samples) == MAX_HISTORY
    assert len(history.active["points"]) == MAX_POINTS
    assert history.active["partial"]
    freezer.tick(timedelta(seconds=100))
    result = history.payload(trip_id=history.active["id"])
    assert len(result["points"]) <= MAX_POINTS
    assert result["points"][0]["odometer"] == 0
    assert result["partial"]
    await history.async_action("stop")
    history.trips = [deepcopy(history.trips[0]) for _ in range(MAX_TRIPS)]
    with pytest.raises(ValueError, match="limit reached"):
        await history.async_action("start")


@pytest.mark.parametrize("name", ["", "   ", "x" * 81])
async def test_trip_name_validation(hass, name):
    """Reject empty/oversized user labels explicitly without creating a trip."""
    history = DrivenProfile(hass, entry_for(hass))
    with pytest.raises(ValueError, match="1 to 80"):
        await history.async_action("start", name)
    assert history.active is None


@pytest.mark.parametrize(
    "raw",
    [
        None,
        [{"time": -1}],
        [{**_gap(1), "latitude": 2}],
        [{**_gap(1), "fuel": float("nan")}],
        [{**_gap(1), "reports": {"fuel": 2}}],
        [_gap(2), _gap(1)],
    ],
)
def test_corrupt_samples(raw):
    """Malformed storage is an actionable error, not silently empty history."""
    with pytest.raises(ValueError):
        _restore_points(raw, 10, MAX_POINTS)


async def test_corrupt_storage_blocks_reads_and_mutations(hass, hass_storage):
    """Corrupt private storage is preserved and explicitly surfaced through the API."""
    entry = entry_for(hass)
    hass_storage[storage_key(entry.entry_id)] = {
        "version": 1,
        "data": {"samples": "broken", "trips": [], "source_ids": []},
    }
    history = await collector(hass, entry)
    assert history.error
    with pytest.raises(ValueError, match="restore"):
        history.payload()
    with pytest.raises(ValueError, match="restore"):
        await history.async_action("start")
    await history.async_save()
    assert hass_storage[storage_key(entry.entry_id)]["data"]["samples"] == "broken"


async def test_stop_event_flushes(hass, freezer):
    """A HA stop event saves active trip/history without stopping the user's trip."""
    freezer.move_to("2026-11-01T00:00:00Z")
    report(hass)
    history = await collector(hass, entry_for(hass))
    await history.async_action("start", "Private")
    with patch.object(history, "async_save", new_callable=AsyncMock) as save:
        hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
        await hass.async_block_till_done()
        save.assert_awaited_once()
    assert history.active is not None


async def test_websocket_schema_actions_and_errors(hass, hass_ws_client):
    """Exercise actual HA schemas, result shape and explicit action validation."""
    report(hass)
    entry = entry_for(hass)
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
        new_callable=AsyncMock,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
    async_register_commands(hass)
    client = await hass_ws_client(hass)
    expected = {
        "units",
        "points",
        "summary",
        "trips",
        "active_trip",
        "start",
        "end",
        "partial",
    }
    for request_id, action in enumerate(("get", "start", "stop"), 1):
        await client.send_json(
            {
                "id": request_id,
                "type": "havrv/driven_profile",
                "entry_id": entry.entry_id,
                "action": action,
            }
        )
        response = await client.receive_json()
        assert response["success"], response
        assert set(response["result"]) == expected
    for request_id, extra in enumerate(
        (
            {"range": "7d"},
            {"action": "delete"},
            {"action": "get", "name": "bad"},
            {"trip_id": "missing"},
        ),
        4,
    ):
        await client.send_json(
            {
                "id": request_id,
                "type": "havrv/driven_profile",
                "entry_id": entry.entry_id,
                "action": "get",
                **extra,
            }
        )
        response = await client.receive_json()
        assert not response["success"]


async def test_source_permissions_include_historic_mappings(hass):
    """Non-admin reads require every source permission; edits require admin."""
    entry = entry_for(hass)
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
        new_callable=AsyncMock,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
    history = entry.runtime_data.driven_profile
    history.source_ids.add("device_tracker.former")
    connection = Mock()
    connection.user.is_admin = False
    connection.user.permissions.check_entity.side_effect = lambda entity, policy: (
        entity != "device_tracker.former"
    )
    handler = websocket_driven_profile.__wrapped__
    msg = {"id": 1, "entry_id": entry.entry_id, "action": "get", "range": "8h"}
    await handler(hass, connection, msg)
    assert connection.send_error.call_args.args[1] == "unauthorized"
    connection.reset_mock()
    connection.user.permissions.check_entity.side_effect = None
    connection.user.permissions.check_entity.return_value = True
    await handler(hass, connection, msg)
    connection.send_result.assert_called_once()
    await handler(hass, connection, {**msg, "action": "start"})
    assert connection.send_error.call_args.args[1] == "unauthorized"


async def test_setup_unload_flushes_and_no_source_defaults(hass):
    """Config-entry lifecycle flushes private history even for unmapped profiles."""
    entry = entry_for(hass, options={})
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
        new_callable=AsyncMock,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
    history = entry.runtime_data.driven_profile
    assert all(value is None for value in history.payload()["summary"].values())
    with (
        patch(
            "homeassistant.config_entries.ConfigEntries.async_unload_platforms",
            return_value=True,
        ),
        patch.object(history, "async_save", new_callable=AsyncMock) as save,
    ):
        assert await hass.config_entries.async_unload(entry.entry_id)
        save.assert_awaited_once()


@pytest.mark.parametrize(
    "change",
    [
        {"name": ""},
        {"id": None},
        {"partial": 1},
        {"start": -1},
        {"end": -1},
        {"end": "nan"},
        {"points": [_gap(100)]},
    ],
)
async def test_corrupt_trip_metadata(hass, change):
    """Saved trip errors never disclose coordinates or user-provided labels."""
    history = DrivenProfile(hass, entry_for(hass))
    trip = {
        "id": "trip",
        "name": "Private route",
        "start": 1,
        "end": 2,
        "partial": False,
        "points": [_gap(1)],
        **change,
    }
    with pytest.raises(ValueError):
        history._restore_trip(trip, 10)


async def test_duplicate_and_invalid_active_trips(hass):
    """Reject duplicate identities and inconsistent stopped/active metadata."""
    history = DrivenProfile(hass, entry_for(hass))
    trip = {
        "id": "trip",
        "name": "Route",
        "start": 1,
        "end": 2,
        "points": [_gap(1)],
        "partial": False,
    }
    raw = {"source_ids": [], "samples": [], "trips": [trip, trip], "active": None}
    with pytest.raises(ValueError, match="Duplicate"):
        history._restore(raw, 10)
    raw["trips"] = []
    raw["active"] = trip
    with pytest.raises(ValueError, match="active trip"):
        history._restore(raw, 10)
    raw["active"] = None
    raw["trips"] = [{**trip, "end": None}]
    with pytest.raises(ValueError, match="active trip"):
        history._restore(raw, 10)


async def test_payload_caps_inserted_gaps_without_hidden_baselines(hass, freezer):
    """Insert gaps before valid restarts and rebase after leading-prefix truncation."""
    history = DrivenProfile(hass, entry_for(hass))
    now = dt_util.utcnow().timestamp()
    history.samples = [
        sample(now - (MAX_POINTS - i) * 0.1, distance=1000 + i)
        for i in range(MAX_POINTS)
    ]
    # Every other fresh endpoint follows an old report timestamp, creating
    # explicit gaps even when snapshot times themselves are close together.
    for i in range(0, MAX_POINTS, 2):
        history.samples[i]["reports"] = {
            key: history.samples[i]["time"] - 181 for key in CHANNELS
        }
    result = history.payload()
    assert len(result["points"]) <= MAX_POINTS
    assert result["points"][0]["odometer"] == 0
    assert result["partial"]
    assert any(p["distance"] is None for p in result["points"])


async def test_numeric_overflow_validation(hass):
    """Finite raw numbers must not result in non-JSON finite calculated outputs."""
    history = DrivenProfile(hass, entry_for(hass))
    now = dt_util.utcnow().timestamp()
    history.samples = [
        sample(now - 60, altitude=-1e308),
        sample(now, lon=0.01, altitude=1e308),
    ]
    with pytest.raises(ValueError, match="numeric limits"):
        history.payload()


async def test_missing_profile_invalid_action_and_unknown_trip(hass):
    """Surface lookup/action errors rather than silently returning another route."""
    history = DrivenProfile(hass, entry_for(hass))
    with pytest.raises(ValueError, match="action"):
        await history.async_action("delete")
    with pytest.raises(ValueError, match="not found"):
        history.payload(trip_id="missing")
    connection = Mock()
    await websocket_driven_profile.__wrapped__(
        hass, connection, {"id": 1, "entry_id": "missing", "action": "get"}
    )
    assert connection.send_error.call_args.args[1] == "not_found"


async def test_stop_force_captures_last_subminute_endpoint(hass, freezer):
    """Manual stop records fresh endpoints even inside the regular minute cadence."""
    freezer.move_to("2026-11-01T00:00:00Z")
    report(hass)
    history = await collector(hass, entry_for(hass))
    await history.async_action("start", "Short")
    freezer.tick(timedelta(seconds=10))
    report(hass, lon=0.001, distance=1000.1, fuel=100.01)
    await hass.async_block_till_done()
    assert len(history.active["points"]) == 1
    await history.async_action("stop")
    result = history.payload(trip_id=history.trips[0]["id"])
    assert result["summary"]["odometer_distance"] == pytest.approx(0.1)
    assert result["summary"]["fuel_used"] == pytest.approx(0.01)
    assert result["points"][-1]["economy"] == pytest.approx(10)


async def test_grade_economy_reject_differently_timed_valid_intervals(hass):
    """Individually valid grade/economy cannot be paired over different intervals."""
    history = DrivenProfile(hass, entry_for(hass))
    now = dt_util.utcnow().timestamp()
    a = sample(now - 60)
    b = sample(now, lon=0.01, altitude=110, distance=1001, fuel=100.1)
    # Both counters have coherent matching endpoints, but their start reports
    # are 30 seconds older than the GPS/altitude start endpoint.
    for key in ("odometer", "fuel"):
        a["reports"][key] -= 30
    history.samples = [a, b]
    result = history.payload()
    assert result["points"][-1]["economy"] is None
    assert result["points"][-1]["grade"] is not None
    assert result["partial"]
    a["reports"]["fuel"] -= 10
    assert history.payload()["points"][-1]["economy"] is None


async def test_real_havrv_outputs_only_and_renames(hass, freezer):
    """Collect the selected RV's exposed outputs, never unrelated raw entities."""
    freezer.move_to("2026-11-01T00:00:00Z")
    report(hass)
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=3,
        data={"name": "RV", "measurement_system": "metric"},
        options=deepcopy(SOURCES),
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    history = entry.runtime_data.driven_profile
    registry = er.async_get(hass)
    assert set(history.outputs) == set(OUTPUT_KEYS)
    assert all(
        registry.async_get(entity).platform == DOMAIN
        for entity in history.outputs.values()
    )
    assert not set(history.outputs.values()) & set(history.sources.values())
    assert history.samples[-1]["elevation"] == 100
    freezer.tick(timedelta(seconds=30))
    report(hass)
    await hass.async_block_till_done()
    for key, source in (
        ("location", "device_tracker.gps"),
        ("elevation", "input_number.altitude"),
    ):
        assert hass.states.get(history.outputs[key]).attributes["source_reported"] == (
            hass.states.get(source).last_reported.isoformat()
        )
    assert len(history.samples) == 1
    freezer.tick(timedelta(seconds=30))
    report(hass, lon=0.01, altitude=110, distance=1001, fuel=100.1)
    await hass.async_block_till_done()
    assert history.payload()["summary"]["odometer_distance"] == pytest.approx(1)
    assert history.payload()["summary"]["gps_distance"] == pytest.approx(1.1119508)
    location = history.outputs["location"]
    registry.async_update_entity(location, new_entity_id="device_tracker.havrv_renamed")
    await hass.async_block_till_done()
    assert history.outputs["location"] == "device_tracker.havrv_renamed"
    freezer.tick(timedelta(seconds=60))
    report(hass, lon=0.02, altitude=120, distance=1002, fuel=100.2)
    await hass.async_block_till_done()
    assert history.payload()["summary"]["gps_distance"] == pytest.approx(2.2239016)
    registry.async_update_entity(
        history.outputs["location"], disabled_by=er.RegistryEntryDisabler.USER
    )
    await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=60))
    report(hass, lon=1, distance=1100)
    await hass.async_block_till_done()
    assert history.samples[-1]["latitude"] is None
    assert history.payload()["summary"]["gps_distance"] == pytest.approx(2.2239016)


async def test_stopped_trip_end_contains_real_stop_sample(hass, freezer):
    """A stop sampled after the click timestamp must remain restorable."""
    freezer.move_to("2026-11-01T00:00:00Z")
    report(hass)
    history = await collector(hass, entry_for(hass))
    await history.async_action("start", "Trip")
    original = history.capture

    def delayed_capture(*, force=False):
        freezer.tick(timedelta(milliseconds=1))
        original(force=force)

    with patch.object(history, "capture", side_effect=delayed_capture):
        await history.async_action("stop")
    saved = await history.store.async_load()
    restored = DrivenProfile(hass, history.entry)
    restored._restore(saved, dt_util.utcnow().timestamp())
    assert restored.trips[0]["points"][-1]["time"] <= restored.trips[0]["end"]
