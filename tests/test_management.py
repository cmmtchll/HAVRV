"""Configuration snapshot, authorization and lifecycle tests for the management page."""

from copy import deepcopy
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState, OperationNotAllowed
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.havrv import _async_update_listener
from custom_components.havrv.const import DOMAIN
from custom_components.havrv.management import (
    Candidate,
    editable_values,
    editor_schema,
    revision,
    validate_values,
)
from custom_components.havrv.panel import async_register_management_panel
from custom_components.havrv.websocket_api import async_register_commands


def profile_entry(**kwargs):
    """Create a realistic saved profile without optional invented specifications."""
    return MockConfigEntry(
        domain=DOMAIN,
        version=3,
        title="Adventure RV",
        data={
            "name": "Adventure RV",
            "measurement_system": "us_customary",
            "rear_axle_count": 2,
            "tag_axle_present": True,
            "main_rear_wheel_configuration": "dual",
            "tag_axle_wheel_configuration": "single",
            "house_battery_bank_count": 2,
            "chassis_battery_bank_count": 1,
            "overall_length": 40,
            "fresh_water_tank_capacity": 100,
            "custom_future_field": {"preserve": True},
        },
        options={
            "entity_mappings": {"water": ["switch.pump"]},
            "tank_entity_mappings": {"fresh_water": "sensor.fresh"},
            "tank_thresholds": {"fresh_water": {"warning": 50, "problem": 25}},
            "tire_entity_mappings": {"front_left_pressure": "sensor.tpms"},
            "tire_pressure_thresholds": {"front": {"low": 100, "high": 150}},
            "tire_temperature_high": 150,
            "power_sources": {
                "house_bank_1": {"voltage": "sensor.voltage", "location": "left_mid"},
                "house_bank_2": {"voltage": "number.other_voltage"},
            },
            "custom_option": {"preserve": True},
        },
        **kwargs,
    )


@pytest.mark.parametrize("minimal", [False, True])
def test_noop_does_not_populate_defaults(minimal):
    """An unchanged form does not activate defaults or invent optional data."""
    entry = (
        MockConfigEntry(domain=DOMAIN, data={"name": "Minimal"}, version=3)
        if minimal
        else profile_entry()
    )
    values = editable_values(entry, "metric")
    before = deepcopy(values)
    result, _, errors, impacts = validate_values(entry, values, "metric")
    assert not errors
    assert not impacts
    assert result.data == entry.data
    assert result.options == entry.options
    assert values == before


@pytest.mark.parametrize("domain", ["binary_sensor", "input_boolean", "switch"])
def test_editor_accepts_boolean_tire_battery_sources(domain):
    """Use the native battery selector and validation in the management panel."""
    entry = profile_entry()
    schema = editor_schema(Candidate(dict(entry.data), dict(entry.options)), "metric")
    field = next(
        field
        for field in schema["options"]
        if field["name"] == "tire_front_left_battery"
    )
    assert domain in field["selector"]["entity"]["domain"]
    values = editable_values(entry, "metric")
    values["options"]["tire_front_left_battery"] = f"{domain}.battery_ok"
    candidate, _, errors, _ = validate_values(entry, values, "metric")
    assert not errors
    assert (
        candidate.options["tire_entity_mappings"]["front_left_battery"]
        == f"{domain}.battery_ok"
    )


@pytest.mark.parametrize("legacy", [False, True])
def test_shore_editor_default_and_line_count_changes(legacy):
    """Share defaults, active fields and removal semantics with native options."""
    entry = profile_entry()
    if legacy:
        entry = MockConfigEntry(
            domain=DOMAIN,
            version=3,
            data=dict(entry.data),
            options={
                **entry.options,
                "power_sources": {
                    **entry.options["power_sources"],
                    "shore_power": {"voltage": "sensor.legacy"},
                },
            },
        )
    values = editable_values(entry, "metric")
    schema = editor_schema(Candidate(dict(entry.data), dict(entry.options)), "metric")
    shore = next(source for source in schema["power"] if source["key"] == "shore_power")
    count = next(field for field in shore["fields"] if field["name"] == "line_count")
    assert count["suggested_value"] == (1 if legacy else 2)
    values["power"].setdefault("shore_power", {})["energy"] = "sensor.energy"
    candidate, _, errors, _ = validate_values(entry, values, "metric")
    assert not errors
    assert candidate.options["power_sources"]["shore_power"]["line_count"] == (
        1 if legacy else 2
    )
    values["power"]["shore_power"].update(
        {"line_count": 2, "line_2_frequency": "input_number.frequency"}
    )
    candidate, _, errors, _ = validate_values(entry, values, "metric")
    assert not errors
    assert candidate.options["power_sources"]["shore_power"]["line_2_frequency"] == (
        "input_number.frequency"
    )
    expanded = MockConfigEntry(
        domain=DOMAIN, version=3, data=candidate.data, options=candidate.options
    )
    values["power"]["shore_power"]["line_count"] = 1
    candidate, _, errors, impacts = validate_values(expanded, values, "metric")
    assert not errors
    assert "line_2_frequency" not in candidate.options["power_sources"]["shore_power"]
    assert "power.input_number.frequency" in impacts
    values["power"]["shore_power"]["line_count"] = 3
    _, _, errors, _ = validate_values(entry, values, "metric")
    assert any(error["code"] == "invalid_shore_line_count" for error in errors)


def test_full_snapshot_clears_and_preserves_unknown_fields():
    """Cleared sources/limits disappear, while unrelated saved keys survive."""
    entry = profile_entry()
    values = editable_values(entry, "metric")
    values["options"].pop("fresh_water_tank_level")
    values["options"].pop("front_entities", None)
    values["options"]["water_entities"] = []
    values["options"].pop("tire_front_pressure_low")
    values["options"].pop("tire_front_pressure_high")
    values["options"].pop("tire_temperature_high")
    values["profile"].pop("overall_length")
    values["power"]["house_bank_1"].pop("voltage")
    result, _, errors, impacts = validate_values(entry, values, "metric")
    assert not errors
    assert result.options["tank_entity_mappings"] == {}
    assert result.options["entity_mappings"] == {}
    assert result.options["tire_pressure_thresholds"] == {}
    assert "tire_temperature_high" not in result.options
    assert "overall_length" not in result.data
    assert "voltage" not in result.options["power_sources"]["house_bank_1"]
    assert "options.sensor.fresh" in impacts
    assert "power.sensor.voltage" in impacts
    assert result.data["custom_future_field"] == {"preserve": True}
    assert result.options["custom_option"] == {"preserve": True}
    assert entry.options["tank_entity_mappings"]["fresh_water"] == "sensor.fresh"


@pytest.mark.parametrize("units", ["metric", "us_customary"])
def test_unit_switch_converts_exactly_once(units):
    """Physical dimensions, volumes and tire limits survive a profile unit change."""
    entry = profile_entry()
    values = editable_values(entry, "metric")
    values["profile"]["measurement_system"] = units
    result, converted, errors, _ = validate_values(entry, values, "metric")
    assert not errors
    factor = 0.3048 if units == "metric" else 1
    assert result.data["overall_length"] == pytest.approx(40 * factor)
    assert result.data["fresh_water_tank_capacity"] == pytest.approx(
        378.5411784 if units == "metric" else 100
    )
    assert result.options["tire_pressure_thresholds"]["front"]["low"] == pytest.approx(
        689.4757293 if units == "metric" else 100
    )
    assert result.options["tire_temperature_high"] == pytest.approx(
        65.5555556 if units == "metric" else 150
    )
    again, _, errors, _ = validate_values(entry, converted, "metric")
    assert not errors
    assert again.data == result.data
    assert again.options == result.options


@pytest.mark.parametrize("capacity", [False, True])
@pytest.mark.parametrize("source", [False, True])
def test_tank_removal_impacts_follow_definition(capacity, source):
    """Confirm tank removal only after the final defining field is cleared."""
    entry = profile_entry()
    values = editable_values(entry, "metric")
    if not capacity:
        values["profile"].pop("fresh_water_tank_capacity")
    if not source:
        values["options"].pop("fresh_water_tank_level")
    _, _, errors, impacts = validate_values(entry, values, "metric")
    assert not errors
    assert ("tanks.fresh_water" in impacts) == (not capacity and not source)


def test_capacity_only_tank_removal_impact():
    """Removing a tank without a mapped source still requires confirmation."""
    entry = MockConfigEntry(
        domain=DOMAIN, data={"name": "RV", "gray_water_tank_capacity": 100}, version=3
    )
    values = editable_values(entry, "metric")
    values["profile"].pop("gray_water_tank_capacity")
    _, _, errors, impacts = validate_values(entry, values, "metric")
    assert not errors
    assert impacts == ["tanks.gray_water"]


def test_layout_reduction_prunes_only_havrv_settings():
    """Reduced axle/bank counts produce impacts and drop inactive per-device data."""
    entry = profile_entry()
    values = editable_values(entry, "metric")
    values["profile"]["house_battery_bank_count"] = 1
    values["profile"]["rear_axle_count"] = "one"
    values["profile"].pop("tag_axle_wheel_configuration")
    values["options"]["tire_tag_axle_left_pressure"] = "sensor.tag"
    result, _, errors, impacts = validate_values(entry, values, "metric")
    # New arbitrary fields cannot be injected in place of saved inactive fields.
    assert errors
    values["options"].pop("tire_tag_axle_left_pressure")
    result, _, errors, impacts = validate_values(entry, values, "metric")
    assert not errors
    assert "house_bank_2" not in result.options["power_sources"]
    assert "power.house_bank_2" in impacts
    assert "tires.tag_axle_left" in impacts
    assert result.data["tag_axle_present"] is False


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("profile", "coach_year", True),
        ("profile", "coach_year", "2000"),
        ("profile", "overall_width", []),
        ("profile", "measurement_system", []),
        ("profile", "measurement_system", "bogus"),
        ("profile", "storage_zone_id", "switch.zone"),
        ("profile", "manufacturer", {}),
        ("profile", "rear_axle_count", "four"),
        ("profile", "main_rear_wheel_configuration", "triple"),
        ("profile", "house_battery_bank_count", -1),
        ("profile", "mystery", 1),
        ("profile", "name", "Different profile"),
        ("options", "water_entities", ["switch.pump", "number.not a source"]),
        ("options", "water_entities", ["input_boolean.wrong_domain"]),
        ("options", "fresh_water_tank_level", "sensor.bad source"),
        ("options", "fresh_water_tank_level", []),
        ("options", "tire_front_left_pressure", "sensor.bad source"),
        ("options", "tire_front_pressure_low", float("nan")),
        ("options", "tire_front_pressure_low", "100"),
        ("options", "mystery", "sensor.mystery"),
        ("power", "house_bank_1", []),
        ("power", "mystery", {}),
        ("power", "house_bank_1", {"unexpected": 1}),
        ("power", "house_bank_1", {"voltage": "sensor.bad source"}),
    ],
)
def test_invalid_drafts_are_rejected(section, field, value):
    """Reject malformed/unrecognized inputs without changing saved configuration."""
    entry = profile_entry()
    values = editable_values(entry, "metric")
    values[section][field] = value
    _, _, errors, _ = validate_values(entry, values, "metric")
    assert errors
    assert entry.data["overall_length"] == 40


@pytest.mark.parametrize(
    "values",
    [
        {},
        {"profile": []},
        {
            "profile": {},
            "options": {},
            "power": {},
            "unit_system": "invalid",
        },
    ],
)
def test_invalid_snapshot_shape(values):
    """Malformed top-level snapshots fail explicitly."""
    _, _, errors, _ = validate_values(profile_entry(), values, "metric")
    assert errors[0]["code"] == "invalid_config"


def test_new_numeric_and_template_sources():
    """Generic mappings accept numeric helpers and template sources."""
    entry = profile_entry()
    values = editable_values(entry, "metric")
    values["options"]["power_entities"] = [
        "number.template_voltage",
        "input_number.voltage",
        "sensor.template_current",
    ]
    values["options"]["fresh_water_tank_level"] = "input_number.fresh"
    values["power"]["house_bank_1"]["voltage"] = "number.template_voltage"
    result, _, errors, _ = validate_values(entry, values, "metric")
    assert not errors
    assert (
        result.options["entity_mappings"]["power"]
        == values["options"]["power_entities"]
    )
    assert result.options["tank_entity_mappings"]["fresh_water"] == "input_number.fresh"


def test_schema_dynamic_positions_and_suggestions():
    """Selectors match native validation without activating suggested defaults."""
    entry = profile_entry()
    schema = editor_schema(Candidate(dict(entry.data), dict(entry.options)), "metric")
    assert len(schema["tires"]) == 8
    assert len(schema["power"]) == 6
    fields = {field["name"]: field for field in schema["options"]}
    assert fields["fresh_water_tank_level"]["selector"]["entity"]["domain"] == [
        "sensor",
        "number",
        "input_number",
    ]
    assert fields["tire_front_pressure_low"]["suggested_value"] == 100
    assert "tire_battery_low" not in editable_values(entry, "metric")["options"]
    assert (
        fields["tire_front_pressure_low"]["selector"]["number"]["unit_of_measurement"]
        == "psi"
    )
    assert (
        fields["tire_temperature_high"]["selector"]["number"]["unit_of_measurement"]
        == "°F"
    )
    candidate, _, errors, _ = validate_values(
        entry,
        {
            **editable_values(entry, "metric"),
            "profile": {
                **editable_values(entry, "metric")["profile"],
                "measurement_system": "metric",
            },
        },
        "metric",
    )
    assert not errors
    schema = editor_schema(candidate, "metric")
    profile_fields = {field["name"]: field for field in schema["profile"]}
    fields = {field["name"]: field for field in schema["options"]}
    assert (
        profile_fields["overall_length"]["selector"]["number"]["unit_of_measurement"]
        == "m"
    )
    assert (
        profile_fields["fresh_water_tank_capacity"]["selector"]["number"][
            "unit_of_measurement"
        ]
        == "L"
    )
    assert (
        fields["tire_front_pressure_low"]["selector"]["number"]["unit_of_measurement"]
        == "kPa"
    )
    assert (
        fields["tire_temperature_high"]["selector"]["number"]["unit_of_measurement"]
        == "°C"
    )


async def test_revision_ignores_states_but_tracks_options(hass: HomeAssistant):
    """External configuration edits, but not source state changes, invalidate drafts."""
    entry = profile_entry()
    entry.add_to_hass(hass)
    before = revision(entry)
    hass.states.async_set("sensor.voltage", "14")
    assert revision(entry) == before
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, "external": True}
    )
    assert revision(entry) != before


async def test_panel_registration_once_and_absent_frontend(hass: HomeAssistant):
    """Gear association is hidden, admin-only and registered once."""
    with patch(
        "custom_components.havrv.panel.async_register_panel", new_callable=AsyncMock
    ) as register:
        await async_register_management_panel(hass)
        register.assert_not_called()
        hass.http = Mock()
        hass.config.components.add("frontend")
        with patch("custom_components.havrv.panel.Path", create=True):
            # No real panel implementation is needed to verify registration plumbing.
            with patch("pathlib.Path.read_bytes", return_value=b"panel module"):
                await async_register_management_panel(hass)
                await async_register_management_panel(hass)
        register.assert_awaited_once()
        args = register.call_args.kwargs
        assert args["config_panel_domain"] == DOMAIN
        assert args["require_admin"]
        assert args["sidebar_title"] is None
        assert args["module_url"].startswith(
            "/havrv_frontend/havrv-config-panel.js?rev="
        )


@pytest.fixture
async def management_entry(hass):
    """Load a real entry with its normal update listener, without platform overhead."""
    entry = profile_entry()
    entry.add_to_hass(hass)
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
        new_callable=AsyncMock,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_websocket_get_validate_and_apply(hass, hass_ws_client, management_entry):
    """Exercise actual HA WebSocket schemas, serialization and one reload path."""
    client = await hass_ws_client(hass)
    entry = management_entry
    async_register_commands(hass)
    async_register_commands(hass)
    await client.send_json(
        {"id": 1, "type": "havrv/config/get", "entry_id": entry.entry_id}
    )
    response = await client.receive_json()
    assert response["success"], response
    saved = response["result"]
    assert saved["schema"]["profile"]
    assert saved["entry_state"] == "loaded"
    values = saved["values"]
    values["profile"]["manufacturer"] = "Example"
    for request_id, command in ((2, "validate"), (3, "apply")):
        with patch(
            "homeassistant.config_entries.ConfigEntries.async_reload", return_value=True
        ) as reload:
            await client.send_json(
                {
                    "id": request_id,
                    "type": f"havrv/config/{command}",
                    "entry_id": entry.entry_id,
                    "revision": saved["revision"],
                    "values": values,
                }
            )
            response = await client.receive_json()
            assert response["success"], response
            await hass.async_block_till_done()
            assert reload.call_count == (1 if command == "apply" else 0)
    assert entry.data["manufacturer"] == "Example"
    assert entry.data["custom_future_field"] == {"preserve": True}
    assert entry.options["custom_option"] == {"preserve": True}


async def test_applying_tank_removal_reloads_and_cleans_registry(hass, hass_ws_client):
    """Apply the user's cleared tank through the real management/reload path."""
    source_entry = MockConfigEntry(domain="input_number")
    source_entry.add_to_hass(hass)
    devices = dr.async_get(hass)
    source_device = devices.async_get_or_create(
        config_entry_id=source_entry.entry_id,
        identifiers={("input_number", "gray_source")},
    )
    registry = er.async_get(hass)
    source = registry.async_get_or_create(
        "input_number",
        "input_number",
        "gray_source",
        config_entry=source_entry,
        device_id=source_device.id,
    )
    hass.states.async_set(source.entity_id, "50", {"unit_of_measurement": "%"})
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "RV", "gray_water_tank_capacity": 100},
        options={"tank_entity_mappings": {"gray_water": source.entity_id}},
        version=3,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    tank = devices.async_get_device_by_identifier(
        (DOMAIN, f"{entry.entry_id}_tank_gray_water"), entry.entry_id
    )
    assert tank
    values = editable_values(entry, "metric")
    values["profile"].pop("gray_water_tank_capacity")
    values["options"].pop("gray_water_tank_level")
    client = await hass_ws_client(hass)
    await client.send_json(
        {
            "id": 1,
            "type": "havrv/config/apply",
            "entry_id": entry.entry_id,
            "revision": revision(entry),
            "values": values,
            "confirm_impacts": True,
        }
    )
    response = await client.receive_json()
    assert response["success"], response
    await hass.async_block_till_done()
    assert hass.data["havrv_management_reload"][entry.entry_id] == "loaded"
    assert devices.async_get(tank.id) is None
    assert not any(
        entity.unique_id.startswith(f"{entry.entry_id}_tank_")
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id)
    )
    assert registry.async_get(source.entity_id) == source
    assert devices.async_get(source_device.id) == source_device
    assert hass.states.get(source.entity_id).state == "50"


@pytest.mark.parametrize("command", ["get", "validate", "apply", "reload"])
async def test_websocket_admin_required(
    hass, hass_ws_client, hass_read_only_access_token, command
):
    """The backend denies configuration access regardless of panel visibility."""
    async_register_commands(hass)
    client = await hass_ws_client(hass, hass_read_only_access_token)
    msg = {"id": 1, "type": f"havrv/config/{command}", "entry_id": "missing"}
    if command in ("validate", "apply"):
        msg.update(revision="stale", values={})
    await client.send_json(msg)
    result = await client.receive_json()
    assert not result["success"]
    assert result["error"]["code"] == "unauthorized"


@pytest.mark.parametrize(
    ("case", "code"),
    [
        ("missing", "not_found"),
        ("wrong_domain", "not_found"),
        ("not_loaded", "not_loaded"),
        ("stale", "conflict"),
        ("invalid", "invalid_config"),
        ("impact", "confirmation_required"),
        ("tank", "confirmation_required"),
    ],
)
async def test_apply_rejects_without_writes(
    hass, hass_ws_client, management_entry, case, code
):
    """Lifecycle failures, stale writes, bad values and removals never partly save."""
    entry = management_entry
    values = editable_values(entry, "metric")
    msg = {
        "id": 1,
        "type": "havrv/config/apply",
        "entry_id": entry.entry_id,
        "revision": revision(entry),
        "values": values,
    }
    if case == "missing":
        msg["entry_id"] = "missing"
    elif case == "wrong_domain":
        other = MockConfigEntry(domain="other")
        other.add_to_hass(hass)
        msg["entry_id"] = other.entry_id
    elif case == "not_loaded":
        entry.mock_state(hass, ConfigEntryState.NOT_LOADED)
    elif case == "stale":
        msg["revision"] = "stale"
    elif case == "invalid":
        values["profile"]["overall_length"] = -1
    elif case == "tank":
        values["profile"].pop("fresh_water_tank_capacity")
        values["options"].pop("fresh_water_tank_level")
    else:
        values["profile"]["house_battery_bank_count"] = 1
    client = await hass_ws_client(hass)
    before = revision(entry)
    await client.send_json(msg)
    result = await client.receive_json()
    assert not result["success"]
    assert result["error"]["code"] == code
    assert revision(entry) == before


async def test_apply_noop_and_failed_reload(hass, hass_ws_client, management_entry):
    """No-op saves avoid reloads; failed reloads do not imply failed persistence."""
    client = await hass_ws_client(hass)
    entry = management_entry
    values = editable_values(entry, "metric")
    msg = {
        "id": 1,
        "type": "havrv/config/apply",
        "entry_id": entry.entry_id,
        "revision": revision(entry),
        "values": values,
        "confirm_impacts": True,
    }
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_reload", return_value=False
    ) as reload:
        await client.send_json(msg)
        result = await client.receive_json()
        assert result["success"]
        assert result["result"]["unchanged"]
        await hass.async_block_till_done()
        reload.assert_not_called()
        values["profile"]["house_battery_bank_count"] = 1
        msg["id"] = 2
        await client.send_json(msg)
        result = await client.receive_json()
        assert result["result"]["saved"]
        assert result["result"]["reload_required"]
        await hass.async_block_till_done()
        reload.assert_called_once()
        assert hass.data["havrv_management_reload"][entry.entry_id] == "failed"


async def test_reload_exception_is_reported_without_suppressing_error(
    hass,
    management_entry,
):
    """An exceptional reload cannot leave a persisted save permanently pending."""
    with (
        patch(
            "homeassistant.config_entries.ConfigEntries.async_reload",
            side_effect=HomeAssistantError("Reload interrupted"),
        ),
        pytest.raises(HomeAssistantError, match="Reload interrupted"),
    ):
        await _async_update_listener(hass, management_entry)
    assert hass.data["havrv_management_reload"][management_entry.entry_id] == "failed"


async def test_apply_reloads_real_entities_and_removes_only_havrv_devices(
    hass,
    hass_ws_client,
):
    """API saves preserve identities and clean only removed HAVRV devices."""
    entry = profile_entry()
    entry.add_to_hass(hass)
    hass.states.async_set(
        "number.template_voltage",
        "13.6",
        {"unit_of_measurement": "V"},
    )
    hass.states.async_set(
        "input_number.pressure",
        "110",
        {"unit_of_measurement": "psi"},
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    registry = er.async_get(hass)
    unique_id = f"{entry.entry_id}_tire_front_left_pressure"
    pressure_id = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
    assert pressure_id
    values = editable_values(entry, "metric")
    values["profile"]["house_battery_bank_count"] = 1
    values["profile"]["rear_axle_count"] = "one"
    values["profile"].pop("tag_axle_wheel_configuration")
    values["options"]["tire_front_left_pressure"] = "input_number.pressure"
    values["options"]["power_entities"] = ["number.template_voltage"]
    values["power"]["house_bank_1"]["voltage"] = "number.template_voltage"
    client = await hass_ws_client(hass)
    await client.send_json(
        {
            "id": 1,
            "type": "havrv/config/apply",
            "entry_id": entry.entry_id,
            "revision": revision(entry),
            "values": values,
            "confirm_impacts": True,
        }
    )
    response = await client.receive_json()
    assert response["success"], response
    assert response["result"]["saved"]
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert hass.data["havrv_management_reload"][entry.entry_id] == "loaded"
    assert entry.runtime_data.rear_axle_count == 1
    assert registry.async_get_entity_id("sensor", DOMAIN, unique_id) == pressure_id
    assert float(hass.states.get(pressure_id).state) == 110
    generic_id = registry.async_get_entity_id(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_power_number.template_voltage",
    )
    assert hass.states.get(generic_id).state == "13.6"
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert all(
        "house_bank_2" not in str(device.identifiers)
        and "tag_axle_" not in str(device.identifiers)
        for device in devices
    )
    assert "house_bank_2" not in entry.options["power_sources"]
    assert hass.states.get("number.template_voltage").state == "13.6"
    assert hass.states.get("input_number.pressure").state == "110"
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("command", ["get", "validate", "reload"])
async def test_read_commands_reject_missing_entry(hass, hass_ws_client, command):
    """Neither async read operation falls back to a different profile."""
    async_register_commands(hass)
    client = await hass_ws_client(hass)
    msg = {"id": 1, "type": f"havrv/config/{command}", "entry_id": "missing"}
    if command == "validate":
        msg.update(revision="none", values={})
    await client.send_json(msg)
    response = await client.receive_json()
    assert response["error"]["code"] == "not_found"


@pytest.mark.parametrize("loaded", [False, True])
async def test_reload_retry_uses_actual_result_without_another_write(
    hass,
    hass_ws_client,
    management_entry,
    loaded,
):
    """Retries scope the entry and distinguish acknowledgement from actual loading."""
    entry = management_entry
    client = await hass_ws_client(hass)
    before = revision(entry)
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_reload",
        return_value=loaded,
    ) as reload:
        await client.send_json(
            {
                "id": 1,
                "type": "havrv/config/reload",
                "entry_id": entry.entry_id,
            }
        )
        response = await client.receive_json()
    assert response["success"], response
    assert response["result"] == {"loaded": loaded, "restart_required": False}
    reload.assert_awaited_once_with(entry.entry_id)
    assert revision(entry) == before
    assert hass.data["havrv_management_reload"][entry.entry_id] == (
        "loaded" if loaded else "failed"
    )


@pytest.mark.parametrize(
    "case", ["old_version", "restart_required", "operation_blocked"]
)
async def test_reload_retry_reports_lifecycle_constraints(
    hass,
    hass_ws_client,
    management_entry,
    case,
):
    """Unsupported entries and nonrecoverable states are never reported as loaded."""
    entry = management_entry
    if case == "old_version":
        hass.config_entries.async_update_entry(entry, version=2)
    elif case == "restart_required":
        entry.mock_state(hass, ConfigEntryState.FAILED_UNLOAD)
    client = await hass_ws_client(hass)
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_reload",
        side_effect=OperationNotAllowed("Entry is busy"),
    ) as reload:
        await client.send_json(
            {
                "id": 1,
                "type": "havrv/config/reload",
                "entry_id": entry.entry_id,
            }
        )
        response = await client.receive_json()
    if case == "restart_required":
        assert response["result"] == {"loaded": False, "restart_required": True}
        assert (
            hass.data["havrv_management_reload"][entry.entry_id] == "restart_required"
        )
    else:
        assert response["error"]["code"] == "not_loaded"
    assert reload.call_count == (1 if case == "operation_blocked" else 0)


async def test_listener_preserves_restart_requirement(hass, management_entry):
    """Nonrecoverable unload failures remain visible after reopening the page."""
    entry = management_entry
    entry.mock_state(hass, ConfigEntryState.FAILED_UNLOAD)
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_reload",
        return_value=False,
    ):
        await _async_update_listener(hass, entry)
    assert hass.data["havrv_management_reload"][entry.entry_id] == "restart_required"


async def test_get_old_profile_uses_native_recovery_instead_of_invalid_schema(
    hass,
    hass_ws_client,
):
    """An old axle model is rejected explicitly rather than interpreted as version 3."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        data={"name": "Old profile", "rear_axle_count": 0},
    )
    entry.add_to_hass(hass)
    async_register_commands(hass)
    client = await hass_ws_client(hass)
    await client.send_json(
        {
            "id": 1,
            "type": "havrv/config/get",
            "entry_id": entry.entry_id,
        }
    )
    response = await client.receive_json()
    assert response["error"]["code"] == "not_loaded"
