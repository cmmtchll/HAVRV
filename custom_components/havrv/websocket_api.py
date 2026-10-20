"""Authenticated HAVRV configuration commands for the management panel."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import probatio as vol
from homeassistant.components import websocket_api
from homeassistant.components.websocket_api.connection import ActiveConnection
from homeassistant.components.websocket_api.decorators import (
    async_response,
    require_admin,
    websocket_command,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    OperationNotAllowed,
    UnknownEntry,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .configuration import _default_measurement_system
from .const import DOMAIN
from .management import (
    Candidate,
    editable_values,
    editor_schema,
    revision,
    validate_values,
)

_REGISTERED = f"{DOMAIN}_management_commands"
RELOAD_RESULTS = f"{DOMAIN}_management_reload"


async def async_reload_profile(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Track one actual reload without suppressing lifecycle exceptions."""
    results = hass.data.setdefault(RELOAD_RESULTS, {})
    results[entry.entry_id] = "pending"
    loaded = False
    try:
        loaded = await hass.config_entries.async_reload(entry.entry_id)
        return loaded
    finally:
        results[entry.entry_id] = (
            "loaded"
            if loaded
            else "failed"
            if entry.state.recoverable
            else "restart_required"
        )


def _entry(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
    *,
    editable: bool = False,
) -> ConfigEntry | None:
    """Resolve only HAVRV entries, rejecting unsupported edits explicitly."""
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    if entry is None or entry.domain != DOMAIN:
        connection.send_error(msg["id"], "not_found", "HAVRV profile not found")
        return None
    if entry.version != 3:
        connection.send_error(
            msg["id"], "not_loaded", "HAVRV profile requires native recovery"
        )
        return None
    if editable and (
        entry.state is not ConfigEntryState.LOADED or entry.disabled_by is not None
    ):
        connection.send_error(msg["id"], "not_loaded", "HAVRV profile is not editable")
        return None
    if editable and revision(entry) != msg["revision"]:
        connection.send_error(
            msg["id"], "conflict", "Saved configuration changed; reload before applying"
        )
        return None
    return entry


def _decorate_schema(
    schema: dict[str, Any], translations: dict[str, Any]
) -> dict[str, Any]:
    """Attach existing translated labels, descriptions and selection options."""
    config = translations["config"]["step"]
    options = translations["options"]["step"]["init"]
    for fields, steps in (
        (schema["profile"], [config["user"]]),
        (schema["options"], [options, config["user"]]),
        *[(source["fields"], [config["power_source"]]) for source in schema["power"]],
    ):
        for field in fields:
            name = field["name"]
            for step in steps:
                if name in step.get("data", {}):
                    field["label"] = step["data"][name]
                    field["description"] = step.get("data_description", {}).get(
                        name, ""
                    )
                    break
            selection = field.get("selector", {}).get("select")
            if selection and (key := selection.get("translation_key")):
                labels = (
                    translations.get("selector", {}).get(key, {}).get("options", {})
                )
                selection["options"] = [
                    {
                        "value": value,
                        "label": labels.get(value, value),
                    }
                    for option in selection["options"]
                    for value in [
                        option["value"] if isinstance(option, dict) else option
                    ]
                ]
    return schema


async def _translations(hass: HomeAssistant, language: str) -> dict[str, Any]:
    """Read bundled translations outside the event loop, falling back to English."""
    folder = Path(__file__).parent
    path = folder / "translations" / f"{language}.json"
    # Only use filenames selected from HA's language setting, not filesystem paths.
    if (
        "/" in language
        or "\\" in language
        or not await hass.async_add_executor_job(path.is_file)
    ):
        path = folder / "translations" / "en.json"
    content = await hass.async_add_executor_job(path.read_text, "utf-8")
    result: dict[str, Any] = json.loads(content)
    return result


@websocket_command(
    {
        vol.Required("type"): "havrv/config/get",
        vol.Required("entry_id"): str,
    }
)
@require_admin
@async_response
async def websocket_get(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return saved configuration, native selectors and scoped registry counts."""
    translations = await _translations(hass, hass.config.language)
    if (entry := _entry(hass, connection, msg)) is None:
        return
    default = _default_measurement_system(hass)
    connection.send_result(
        msg["id"],
        {
            "revision": revision(entry),
            "profile": dict(entry.data),
            "options": dict(entry.options),
            "values": editable_values(entry, default),
            "schema": _decorate_schema(
                editor_schema(
                    Candidate(dict(entry.data), dict(entry.options)), default
                ),
                translations,
            ),
            "translations": translations,
            "devices": len(
                dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
            ),
            "entities": len(
                er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
            ),
            "entry_state": entry.state.value,
            "reload_result": hass.data.get(RELOAD_RESULTS, {}).get(entry.entry_id),
        },
    )


@websocket_command(
    {
        vol.Required("type"): "havrv/config/validate",
        vol.Required("entry_id"): str,
        vol.Required("revision"): str,
        vol.Required("values"): dict,
    }
)
@require_admin
@async_response
async def websocket_validate(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Validate and describe a draft without committing it."""
    translations = await _translations(hass, hass.config.language)
    if (entry := _entry(hass, connection, msg, editable=True)) is None:
        return
    default = _default_measurement_system(hass)
    candidate, values, errors, impacts = validate_values(entry, msg["values"], default)
    connection.send_result(
        msg["id"],
        {
            "valid": not errors,
            "errors": errors,
            "impacts": impacts,
            "revision": revision(entry),
            "values": values,
            "schema": _decorate_schema(editor_schema(candidate, default), translations),
        },
    )


@websocket_command(
    {
        vol.Required("type"): "havrv/config/apply",
        vol.Required("entry_id"): str,
        vol.Required("revision"): str,
        vol.Required("values"): dict,
        vol.Optional("confirm_impacts", default=False): bool,
    }
)
@require_admin
@callback
def websocket_apply(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Commit a validated complete draft in one synchronous config-entry update."""
    if (entry := _entry(hass, connection, msg, editable=True)) is None:
        return
    candidate, _values, errors, impacts = validate_values(
        entry, msg["values"], _default_measurement_system(hass)
    )
    if errors:
        connection.send_error(
            msg["id"], "invalid_config", "Review configuration errors"
        )
        return
    if impacts and not msg["confirm_impacts"]:
        connection.send_error(
            msg["id"],
            "confirmation_required",
            "Confirm removal impacts before applying",
        )
        return
    changed = candidate.data != entry.data or candidate.options != entry.options
    if changed:
        hass.data.setdefault(RELOAD_RESULTS, {})[entry.entry_id] = "pending"
        hass.config_entries.async_update_entry(
            entry, data=candidate.data, options=candidate.options
        )
    connection.send_result(
        msg["id"],
        {
            "saved": True,
            "revision": revision(entry),
            "reload_required": changed,
            "unchanged": not changed,
        },
    )


@websocket_command(
    {
        vol.Required("type"): "havrv/config/reload",
        vol.Required("entry_id"): str,
    }
)
@require_admin
@async_response
async def websocket_reload(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Retry persisted configuration without another write or invented HA command."""
    if (entry := _entry(hass, connection, msg)) is None:
        return
    if entry.disabled_by is not None:
        connection.send_error(msg["id"], "not_loaded", "HAVRV profile cannot reload")
        return
    if not entry.state.recoverable:
        hass.data.setdefault(RELOAD_RESULTS, {})[entry.entry_id] = "restart_required"
        connection.send_result(msg["id"], {"loaded": False, "restart_required": True})
        return
    try:
        loaded = await async_reload_profile(hass, entry)
    except OperationNotAllowed, UnknownEntry:
        connection.send_error(msg["id"], "not_loaded", "HAVRV profile cannot reload")
        return
    connection.send_result(
        msg["id"],
        {"loaded": loaded, "restart_required": not entry.state.recoverable},
    )


@callback
def async_register_commands(hass: HomeAssistant) -> None:
    """Register handlers once for all RV profiles."""
    if hass.data.get(_REGISTERED):
        return
    for command in (
        websocket_get,
        websocket_validate,
        websocket_apply,
        websocket_reload,
    ):
        websocket_api.async_register_command(hass, command)
    hass.data[_REGISTERED] = True
