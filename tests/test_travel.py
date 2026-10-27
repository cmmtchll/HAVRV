"""Optional Operations travel readings, configuration, privacy and lifecycle."""

from copy import deepcopy
from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.const import Platform
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.icon import async_get_icons
from homeassistant.helpers.translation import async_get_translations
from homeassistant.util.unit_system import METRIC_SYSTEM, US_CUSTOMARY_SYSTEM
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.havrv.configuration import _normalize_options, _options_schema
from custom_components.havrv.const import CONF_OPERATIONS_SOURCES, DOMAIN
from custom_components.havrv.device_tracker import (
    HavrvLocationTracker,
)
from custom_components.havrv.device_tracker import (
    async_setup_entry as setup_tracker,
)
from custom_components.havrv.diagnostics import async_get_config_entry_diagnostics
from custom_components.havrv.management import (
    Candidate,
    editable_values,
    editor_schema,
    validate_values,
)
from custom_components.havrv.operations import finite_number, operations_device_info


def travel_entry(units="metric", sources=None):
    """Create a profile whose travel channels are independently optional."""
    return MockConfigEntry(
        domain=DOMAIN,
        version=3,
        title="RV",
        data={"name": "RV", "measurement_system": units},
        options={
            CONF_OPERATIONS_SOURCES: sources
            if sources is not None
            else {
                "location": "device_tracker.gps",
                "altitude": "sensor.altitude",
                "speed": "number.template_speed",
                "direction": "input_number.course",
            }
        },
    )


def entity_id(hass, entry, metric):
    """Find a stable travel identity without relying on translated entity IDs."""
    domain = "device_tracker" if metric == "location" else "sensor"
    return er.async_get(hass).async_get_entity_id(
        domain, DOMAIN, f"{entry.entry_id}_operations_{metric}"
    )


async def setup(hass, entry):
    """Set up a profile using the normal config-entry lifecycle."""
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def set_sources(hass):
    """Provide deliberately mismatched source units and a GPS fix."""
    hass.states.async_set(
        "device_tracker.gps",
        "not_home",
        {"latitude": 10, "longitude": 20, "gps_accuracy": 12, "private": "omit"},
    )
    hass.states.async_set("sensor.altitude", "100", {"unit_of_measurement": "ft"})
    hass.states.async_set("number.template_speed", "10", {"unit_of_measurement": "m/s"})
    hass.states.async_set("input_number.course", "270", {"unit_of_measurement": "°"})


@pytest.mark.parametrize(
    ("units", "ha_units", "altitude", "speed", "distance_unit", "speed_unit"),
    [
        ("metric", US_CUSTOMARY_SYSTEM, 30.48, 36, "m", "km/h"),
        ("us_customary", METRIC_SYSTEM, 100, 22.36936292, "ft", "mph"),
    ],
)
async def test_profile_units_gps_and_operations(
    hass, units, ha_units, altitude, speed, distance_unit, speed_unit
):
    """Travel readings follow the profile, never HA defaults or source naming."""
    hass.config.units = ha_units
    set_sources(hass)
    entry = travel_entry(units)
    await setup(hass, entry)
    registry = er.async_get(hass)
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, f"{entry.entry_id}_operations"), entry.entry_id
    )
    for metric, expected, unit in (
        ("altitude", altitude, distance_unit),
        ("speed", speed, speed_unit),
        ("direction", 270, "°"),
    ):
        eid = entity_id(hass, entry, metric)
        state = hass.states.get(eid)
        assert float(state.state) == pytest.approx(expected)
        assert state.attributes["unit_of_measurement"] == unit
        assert state.attributes["state_class"] == (
            "measurement_angle" if metric == "direction" else "measurement"
        )
        assert registry.async_get(eid).device_id == device.id
        assert registry.async_get(eid).entity_category is None
    gps = hass.states.get(entity_id(hass, entry, "location"))
    assert gps.attributes["latitude"] == 10
    assert gps.attributes["longitude"] == 20
    assert gps.attributes["gps_accuracy"] == 12
    assert gps.attributes["source_type"] == "gps"
    assert "private" not in gps.attributes
    assert registry.async_get(gps.entity_id).device_id == device.id
    assert Platform.DEVICE_TRACKER in entry.runtime_data.platforms

    # Explicit HA per-entity unit preferences still override the profile.
    for metric, target, expected in (
        ("altitude", "km", 0.03048),
        ("speed", "m/s", 10),
    ):
        eid = entity_id(hass, entry, metric)
        registry.async_update_entity_options(
            eid, "sensor", {"unit_of_measurement": target}
        )
        await hass.async_block_till_done()
        assert hass.states.get(eid).attributes["unit_of_measurement"] == target
        assert float(hass.states.get(eid).state) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("metric", "source", "value", "unit"),
    [
        ("altitude", "sensor.altitude", "unknown", "m"),
        ("altitude", "sensor.altitude", "unavailable", "m"),
        ("altitude", "sensor.altitude", "NaN", "m"),
        ("altitude", "sensor.altitude", "inf", "m"),
        ("altitude", "sensor.altitude", "bad", "m"),
        ("altitude", "sensor.altitude", "1", None),
        ("altitude", "sensor.altitude", "1", "km/h"),
        ("speed", "number.template_speed", "-1", "mph"),
        ("speed", "number.template_speed", "2", "m"),
        ("direction", "input_number.course", "-1", "°"),
        ("direction", "input_number.course", "360", "°"),
        ("direction", "input_number.course", "90", None),
        ("direction", "input_number.course", "90", "rad"),
        ("direction", "input_number.course", "north", "°"),
    ],
)
async def test_invalid_readings_recover(hass, metric, source, value, unit):
    """Invalid or incompatible inputs never turn into default travel readings."""
    set_sources(hass)
    entry = travel_entry()
    await setup(hass, entry)
    eid = entity_id(hass, entry, metric)
    hass.states.async_set(source, value, {"unit_of_measurement": unit})
    await hass.async_block_till_done()
    assert hass.states.get(eid).state == "unavailable"
    set_sources(hass)
    await hass.async_block_till_done()
    assert hass.states.get(eid).state != "unavailable"


@pytest.mark.parametrize(
    "attrs",
    [
        {},
        {"latitude": 10},
        {"latitude": True, "longitude": 0},
        {"latitude": "nan", "longitude": 20},
        {"latitude": 91, "longitude": 20},
        {"latitude": 10, "longitude": -181},
        {"latitude": [], "longitude": 20},
        {"latitude": 10**1000, "longitude": 20},
    ],
)
async def test_invalid_coordinates_and_recovery(hass, attrs):
    """A home/away tracker without a valid pair is not an RV GPS fix."""
    entry = travel_entry(sources={"location": "device_tracker.gps"})
    hass.states.async_set("device_tracker.gps", "home", attrs)
    await setup(hass, entry)
    eid = entity_id(hass, entry, "location")
    assert hass.states.get(eid).state == "unavailable"
    assert "latitude" not in hass.states.get(eid).attributes
    hass.states.async_set("device_tracker.gps", "home", {"latitude": 0, "longitude": 0})
    await hass.async_block_till_done()
    assert hass.states.get(eid).attributes["latitude"] == 0
    assert hass.states.get(eid).attributes["gps_accuracy"] == 0


async def test_missing_unavailable_removed_sources_and_unload(hass):
    """Missing/removed sources stay unavailable and subscriptions unload cleanly."""
    entry = travel_entry()
    await setup(hass, entry)
    ids = {m: entity_id(hass, entry, m) for m in entry.options[CONF_OPERATIONS_SOURCES]}
    assert all(hass.states.get(eid).state == "unavailable" for eid in ids.values())
    set_sources(hass)
    await hass.async_block_till_done()
    for source in entry.options[CONF_OPERATIONS_SOURCES].values():
        hass.states.async_set(source, "unavailable")
    await hass.async_block_till_done()
    assert all(hass.states.get(eid).state == "unavailable" for eid in ids.values())
    set_sources(hass)
    await hass.async_block_till_done()
    for source in entry.options[CONF_OPERATIONS_SOURCES].values():
        hass.states.async_remove(source)
    await hass.async_block_till_done()
    assert all(hass.states.get(eid).state == "unavailable" for eid in ids.values())
    assert await hass.config_entries.async_unload(entry.entry_id)
    unloaded = {eid: hass.states.get(eid) for eid in ids.values()}
    set_sources(hass)
    await hass.async_block_till_done()
    assert {eid: hass.states.get(eid) for eid in ids.values()} == unloaded


async def test_remap_clear_reload_and_legacy(hass):
    """Remapping preserves identity; clearing removes stale entities, not Operations."""
    set_sources(hass)
    entry = travel_entry()
    await setup(hass, entry)
    ids = {m: entity_id(hass, entry, m) for m in entry.options[CONF_OPERATIONS_SOURCES]}
    hass.states.async_set(
        "input_number.other_speed", "50", {"unit_of_measurement": "km/h"}
    )
    hass.states.async_set(
        "device_tracker.other", "not_home", {"latitude": -12, "longitude": 24}
    )
    sources = {
        **entry.options[CONF_OPERATIONS_SOURCES],
        "location": "device_tracker.other",
        "speed": "input_number.other_speed",
    }
    hass.config_entries.async_update_entry(
        entry, options={CONF_OPERATIONS_SOURCES: sources}
    )
    await hass.async_block_till_done()
    assert ids == {m: entity_id(hass, entry, m) for m in sources}
    assert hass.states.get(ids["speed"]).state == "50.0"
    assert hass.states.get(ids["location"]).attributes["latitude"] == -12
    set_sources(hass)
    await hass.async_block_till_done()
    assert hass.states.get(ids["speed"]).state == "50.0"
    assert hass.states.get(ids["location"]).attributes["latitude"] == -12
    hass.config_entries.async_update_entry(entry, options={CONF_OPERATIONS_SOURCES: {}})
    await hass.async_block_till_done()
    assert all(er.async_get(hass).async_get(eid) is None for eid in ids.values())
    assert all(hass.states.get(eid) is None for eid in ids.values())
    assert Platform.DEVICE_TRACKER not in entry.runtime_data.platforms
    assert er.async_get(hass).async_get_entity_id(
        "select", DOMAIN, f"{entry.entry_id}_operations_mode"
    )
    # A name-only legacy entry does not invent optional sources or readings.
    legacy = MockConfigEntry(domain=DOMAIN, version=3, data={"name": "Legacy"})
    await setup(hass, legacy)
    assert not any(entity_id(hass, legacy, m) for m in sources)


@pytest.mark.parametrize("domain", ["sensor", "number", "input_number"])
def test_shared_numeric_selectors_and_validation(domain):
    """All numeric helper/template domains share native and panel selectors."""
    entry = travel_entry(sources={})
    schema = _options_schema(entry)
    fields = {str(k): v.serialize()["selector"] for k, v in schema.schema.items()}
    panel = editor_schema(Candidate(dict(entry.data), {}), "metric")["options"]
    for metric in ("altitude", "speed", "direction"):
        field = f"operations_{metric}"
        assert fields[field]["entity"]["domain"] == ["sensor", "number", "input_number"]
        assert next(f for f in panel if f["name"] == field)["selector"] == fields[field]
        candidate, _, errors, _ = validate_values(
            entry,
            {
                **editable_values(entry, "metric"),
                "options": {field: f"{domain}.template"},
            },
            "metric",
        )
        assert not errors
        assert candidate.options[CONF_OPERATIONS_SOURCES] == {
            metric: f"{domain}.template"
        }
    assert fields["operations_location"]["entity"]["domain"] == ["device_tracker"]


@pytest.mark.parametrize(
    "value", [True, 1, [], "sensor.", "bad", "device_tracker.other", "switch.other"]
)
def test_invalid_numeric_source_validation(value):
    """Shared validation rejects wrong domains and malformed submitted values."""
    entry = travel_entry()
    options, error = _normalize_options({"operations_speed": value}, entry)
    assert options == {}
    assert error == "invalid_operations_source"
    values = editable_values(entry, "metric")
    values["options"]["operations_speed"] = value
    _, _, errors, _ = validate_values(entry, values, "metric")
    assert errors == [
        {"section": "operations", "field": "", "code": "invalid_operations_source"}
    ]


def test_location_validation_and_configuration_roundtrip():
    """Saved mappings survive no-op and reconfigure projections, and can be cleared."""
    entry = travel_entry()
    values = editable_values(entry, "metric")
    result, _, errors, impacts = validate_values(entry, deepcopy(values), "metric")
    assert not errors
    assert not impacts
    assert result.options == entry.options
    assert _normalize_options({"operations_location": "sensor.gps"}, entry)[1]
    for metric in entry.options[CONF_OPERATIONS_SOURCES]:
        values["options"].pop(f"operations_{metric}")
    candidate, _, errors, impacts = validate_values(entry, values, "metric")
    assert not errors
    assert CONF_OPERATIONS_SOURCES not in candidate.options
    assert len(impacts) == 4
    assert (
        _normalize_options({"operations_speed": ""}, entry)[0][CONF_OPERATIONS_SOURCES]
        == {}
    )


async def test_native_options_clearing_and_reconfigure_preservation(hass):
    """Native recovery uses the same sources and omission really clears a mapping."""
    entry = travel_entry()
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    markers = {str(k): k for k in result["data_schema"].schema}
    assert (
        markers["operations_speed"].description["suggested_value"]
        == "number.template_speed"
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "operations_speed": "input_number.recovered",
            "operations_location": "device_tracker.new",
        },
    )
    assert result["data"][CONF_OPERATIONS_SOURCES] == {
        "speed": "input_number.recovered",
        "location": "device_tracker.new",
    }
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"measurement_system": "us_customary"}
    )
    assert result["reason"] == "reconfigure_successful"
    assert entry.options[CONF_OPERATIONS_SOURCES]["speed"] == "input_number.recovered"
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={}
    )
    assert result["data"][CONF_OPERATIONS_SOURCES] == {}


@pytest.mark.parametrize("domain", ["sensor", "number", "input_number"])
@pytest.mark.parametrize(
    ("metric", "value", "unit"),
    [("altitude", "-12", "m"), ("speed", "0", "km/h"), ("direction", "0", "°")],
)
async def test_numeric_domains_and_zero_negative_altitude(
    hass, domain, metric, value, unit
):
    """Helpers/templates support every numeric channel, zero and negative altitude."""
    source = f"{domain}.travel"
    hass.states.async_set(source, value, {"unit_of_measurement": unit})
    entry = travel_entry(sources={metric: source})
    await setup(hass, entry)
    eid = entity_id(hass, entry, metric)
    assert float(hass.states.get(eid).state) == float(value)
    hass.states.async_set(source, "1e308", {"unit_of_measurement": "m/s"})
    await hass.async_block_till_done()
    assert hass.states.get(eid).state == "unavailable"


async def test_native_invalid_submission_keeps_form(hass):
    """The native recovery path surfaces the shared source-domain error."""
    entry = travel_entry(sources={})
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    # Drive the step directly to exercise defensive validation beyond selectors.
    flow = hass.config_entries.options._progress[result["flow_id"]]
    invalid = await flow.async_step_init({"operations_location": "sensor.not_gps"})
    assert invalid["errors"] == {"base": "invalid_operations_source"}
    assert entry.options[CONF_OPERATIONS_SOURCES] == {}


async def test_profile_unit_changes_reload_preserving_sources_and_overrides(hass):
    """Profile edits update default units, without losing explicit HA overrides."""
    set_sources(hass)
    entry = travel_entry()
    await setup(hass, entry)
    altitude = entity_id(hass, entry, "altitude")
    speed = entity_id(hass, entry, "speed")
    sources = deepcopy(entry.options[CONF_OPERATIONS_SOURCES])
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, "measurement_system": "us_customary"}
    )
    await hass.async_block_till_done()
    assert entry.options[CONF_OPERATIONS_SOURCES] == sources
    assert entity_id(hass, entry, "speed") == speed
    assert hass.states.get(altitude).attributes["unit_of_measurement"] == "ft"
    assert float(hass.states.get(altitude).state) == pytest.approx(100)
    assert hass.states.get(speed).attributes["unit_of_measurement"] == "mph"
    er.async_get(hass).async_update_entity_options(
        speed, "sensor", {"unit_of_measurement": "m/s"}
    )
    await hass.async_block_till_done()
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, "measurement_system": "metric"}
    )
    await hass.async_block_till_done()
    assert hass.states.get(altitude).attributes["unit_of_measurement"] == "m"
    assert hass.states.get(speed).attributes["unit_of_measurement"] == "m/s"
    assert float(hass.states.get(speed).state) == pytest.approx(10)


async def test_reconfigure_invalid_saved_source_has_translated_error(hass):
    """Malformed persisted mappings are actionable in native recovery too."""
    entry = travel_entry(sources={"speed": "switch.invalid"})
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"measurement_system": "us_customary"}
    )
    assert result["errors"] == {"base": "invalid_operations_source"}
    translations = await async_get_translations(hass, "en", "config", {DOMAIN})
    assert translations[f"component.{DOMAIN}.config.error.invalid_operations_source"]


async def test_self_mappings_are_unavailable_without_feedback(hass):
    """A stable output cannot become its own GPS or numeric source on remapping."""
    set_sources(hass)
    entry = travel_entry()
    await setup(hass, entry)
    sources = {
        metric: entity_id(hass, entry, metric)
        for metric in entry.options[CONF_OPERATIONS_SOURCES]
    }
    hass.config_entries.async_update_entry(
        entry, options={CONF_OPERATIONS_SOURCES: sources}
    )
    await hass.async_block_till_done()
    assert all(hass.states.get(eid).state == "unavailable" for eid in sources.values())
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_privacy_translations_and_helper_edges(hass):
    """Diagnostics contain neither travel readings nor source identifiers."""
    set_sources(hass)
    entry = travel_entry()
    await setup(hass, entry)
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["entry_options"][CONF_OPERATIONS_SOURCES] == "**REDACTED**"
    assert "latitude" not in str(diagnostics)
    assert "device_tracker.gps" not in str(diagnostics)
    translations = await async_get_translations(hass, "en", "entity", {DOMAIN})
    assert (
        translations[f"component.{DOMAIN}.entity.device_tracker.rv_location.name"]
        == "RV location"
    )
    icons = (await async_get_icons(hass, "entity", {DOMAIN}))[DOMAIN]
    for metric in ("altitude", "speed", "direction"):
        assert translations[f"component.{DOMAIN}.entity.sensor.detected_{metric}.name"]
        assert icons["sensor"][f"detected_{metric}"]["default"].startswith("mdi:")
    tracker = HavrvLocationTracker(entry)
    tracker.hass = hass
    for accuracy in (-1, "bad", float("inf"), None):
        hass.states.async_set(
            "device_tracker.gps",
            "home",
            {"latitude": 10, "longitude": 20, "gps_accuracy": accuracy},
        )
        assert tracker.location_accuracy == 0
    with patch.object(entry.runtime_data, "device_id", None):
        with pytest.raises(RuntimeError, match="registered"):
            operations_device_info(entry)
    added = []
    empty = travel_entry(sources={})
    await setup_tracker(hass, empty, added.extend)
    assert not added
    assert finite_number(True) is None
    assert finite_number({}) is None
    assert finite_number(10**1000) is None
