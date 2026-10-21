"""Config flow for HAVRV."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_NAME

from .configuration import (
    _default_measurement_system as _default_measurement_system,
)
from .configuration import (
    _normalize_entity_mappings as _normalize_entity_mappings,
)
from .configuration import (
    _normalize_options as _normalize_options,
)
from .configuration import (
    _normalize_power_source as _normalize_power_source,
)
from .configuration import (
    _normalize_profile as _normalize_profile,
)
from .configuration import (
    _options_schema as _options_schema,
)
from .configuration import (
    _power_source_schema as _power_source_schema,
)
from .configuration import (
    _pressure_threshold_field as _pressure_threshold_field,
)
from .configuration import (
    _profile_schema as _profile_schema,
)
from .const import (
    AXLE_COUNT_ONE,
    CONF_CONFIGURE_POWER_SOURCES,
    CONF_MEASUREMENT_SYSTEM,
    CONF_POWER_SOURCES,
    CONF_REAR_AXLE_COUNT,
    CONF_TAG_AXLE_WHEEL_CONFIGURATION,
    DOMAIN,
)
from .management import _convert_units, editable_values, validate_values
from .power import power_settings, power_sources


class HavrvConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HAVRV."""

    VERSION = 3

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> HavrvOptionsFlow:
        """Get the options flow for this config entry."""
        return HavrvOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            raw_name = user_input[CONF_NAME]
            if not isinstance(raw_name, str) or not (name := raw_name.strip()):
                errors["base"] = "name_required"
            else:
                profile, error = _normalize_profile(
                    user_input,
                    default_measurement_system=_default_measurement_system(self.hass),
                )
                if error:
                    errors["base"] = error
                else:
                    await self.async_set_unique_id(name.casefold())
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(title=name, data=profile)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    marker: validator
                    for marker, validator in _profile_schema(
                        default_measurement_system=_default_measurement_system(
                            self.hass
                        )
                    ).schema.items()
                    if str(marker) in (CONF_NAME, CONF_MEASUREMENT_SYSTEM)
                }
            ),  # type: ignore[arg-type]
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit saved vehicle details without changing profile identity."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            if user_input.get(CONF_REAR_AXLE_COUNT) == AXLE_COUNT_ONE:
                user_input.pop(CONF_TAG_AXLE_WHEEL_CONFIGURATION, None)
            units = _default_measurement_system(self.hass)
            values = editable_values(entry, units)
            target_units = user_input.get(CONF_MEASUREMENT_SYSTEM, units)
            if target_units in ("metric", "us_customary"):
                values["profile"][CONF_MEASUREMENT_SYSTEM] = target_units
                _convert_units(values)
            values["profile"] = {CONF_NAME: entry.data[CONF_NAME], **user_input}
            candidate, _, validation_errors, _ = validate_values(
                entry, dict(values), units
            )
            if validation_errors:
                errors["base"] = validation_errors[0]["code"]
            else:
                self.hass.config_entries.async_update_entry(
                    entry, data=candidate.data, options=candidate.options
                )
                return self.async_abort(reason="reconfigure_successful")

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_profile_schema(
                default_measurement_system=_default_measurement_system(self.hass),
                existing_data=entry.data,
                include_name=False,
                include_mappings=False,
            ),  # type: ignore[arg-type]
            errors=errors,
        )


class HavrvOptionsFlow(config_entries.OptionsFlow):
    """Manage mapped source entities for an RV profile."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit source-entity mappings."""
        errors: dict[str, str] = {}

        if user_input is not None:
            options, error = _normalize_options(user_input, self.config_entry)
            if error:
                errors["base"] = error
            else:
                if user_input.get(CONF_CONFIGURE_POWER_SOURCES, False):
                    self._pending_options = options
                    self._power_index = 0
                    self._power_settings: dict[str, Any] = {}
                    return await self.async_step_power_source()
                return self.async_create_entry(
                    title="",
                    data=options,
                )

        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(
                self.config_entry,
                default_measurement_system=_default_measurement_system(self.hass),
            ),  # type: ignore[arg-type]
            errors=errors,
        )

    async def async_step_power_source(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit bank specifications, placements, and read-only mappings."""
        sources = power_sources(self.config_entry.data)
        source = sources[self._power_index]
        existing = (
            getattr(self, "_shore_settings", None)
            if source.key == "shore_power"
            else None
        )
        if existing is None:
            existing = power_settings(self.config_entry, source)
        errors: dict[str, str] = {}
        if user_input is not None:
            submitted = dict(user_input)
            if source.key == "shore_power":
                submitted.setdefault("line_count", existing["line_count"])
            settings, error = _normalize_power_source(submitted, source)
            if error:
                errors["base"] = error
            elif (
                source.key == "shore_power"
                and settings["line_count"] != existing["line_count"]
            ):
                line_draft = submitted if existing["line_count"] == 2 else existing
                self._shore_settings = {
                    **{
                        key: value
                        for key, value in line_draft.items()
                        if key.startswith("line_2_")
                    },
                    **settings,
                }
                return await self.async_step_power_source()
            else:
                self._power_settings[source.key] = settings
                self._power_index += 1
                if self._power_index == len(sources):
                    return self.async_create_entry(
                        title="",
                        data={
                            **self._pending_options,
                            CONF_POWER_SOURCES: self._power_settings,
                        },
                    )
                return await self.async_step_power_source()
        return self.async_show_form(
            step_id="power_source",
            data_schema=_power_source_schema(
                source,
                user_input if user_input is not None else existing,
            ),  # type: ignore[arg-type]
            description_placeholders={"source": source.name},
            errors=errors,
        )
