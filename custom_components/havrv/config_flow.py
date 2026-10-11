"""Config flow for HAVRV."""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import date
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector
from homeassistant.util.unit_system import METRIC_SYSTEM, US_CUSTOMARY_SYSTEM

from .const import (
    AXLE_COUNT_ONE,
    AXLE_COUNT_THREE,
    AXLE_COUNT_TWO,
    CONF_BLACK_WATER_TANK_CAPACITY,
    CONF_COACH_BUILDER,
    CONF_COACH_IDENTIFIER,
    CONF_COACH_YEAR,
    CONF_ENTITY_MAPPINGS,
    CONF_FRESH_WATER_TANK_CAPACITY,
    CONF_FUEL_TANK_CAPACITY,
    CONF_GRAY_WATER_TANK_CAPACITY,
    CONF_MAIN_REAR_WHEEL_CONFIGURATION,
    CONF_MAKE,
    CONF_MANUFACTURER,
    CONF_MEASUREMENT_SYSTEM,
    CONF_MODEL,
    CONF_OVERALL_HEIGHT,
    CONF_OVERALL_LENGTH,
    CONF_OVERALL_WIDTH,
    CONF_REAR_AXLE_COUNT,
    CONF_STORAGE_ZONE_ID,
    CONF_TAG_AXLE_PRESENT,
    CONF_TAG_AXLE_WHEEL_CONFIGURATION,
    CONF_TANK_ENTITY_MAPPINGS,
    CONF_TANK_THRESHOLDS,
    CONF_TIRE_BATTERY_LOW,
    CONF_TIRE_ENTITY_MAPPINGS,
    CONF_TIRE_PRESSURE_HIGH,
    CONF_TIRE_PRESSURE_LOW,
    CONF_TIRE_PRESSURE_THRESHOLDS,
    CONF_TIRE_TEMPERATURE_HIGH,
    DEFAULT_TANK_THRESHOLDS,
    DEFAULT_TIRE_PRESSURE,
    DEFAULT_TIRE_TEMPERATURE_HIGH,
    DOMAIN,
    SUPPORTED_ENTITY_DOMAINS,
    SYSTEM_CATEGORIES,
    TANK_PROBLEM,
    TANK_TYPES,
    TANK_WARNING,
    TIRE_AXLE,
    TIRE_FRONT,
    TIRE_TAG,
    UNIT_SYSTEM_METRIC,
    UNIT_SYSTEM_US_CUSTOMARY,
    WHEEL_CONFIGURATION_DUAL,
    WHEEL_CONFIGURATION_SINGLE,
)
from .tank import thresholds_valid
from .tire import tire_entity_key, tire_positions

_PROFILE_TEXT_FIELDS = (
    CONF_MANUFACTURER,
    CONF_COACH_BUILDER,
    CONF_MAKE,
    CONF_MODEL,
    CONF_COACH_IDENTIFIER,
)
_MEASUREMENT_FIELDS = (
    CONF_OVERALL_HEIGHT,
    CONF_OVERALL_LENGTH,
    CONF_OVERALL_WIDTH,
    CONF_FUEL_TANK_CAPACITY,
    CONF_FRESH_WATER_TANK_CAPACITY,
    CONF_GRAY_WATER_TANK_CAPACITY,
    CONF_BLACK_WATER_TANK_CAPACITY,
)
_UNIT_SYSTEMS = {UNIT_SYSTEM_METRIC, UNIT_SYSTEM_US_CUSTOMARY}
_WHEEL_CONFIGURATIONS = {
    WHEEL_CONFIGURATION_SINGLE,
    WHEEL_CONFIGURATION_DUAL,
}
_NUMERIC_ENTITY_DOMAINS = ("sensor", "number", "input_number")


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
            data_schema=_profile_schema(
                default_measurement_system=_default_measurement_system(self.hass)
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
            profile, error = _normalize_profile(
                {CONF_NAME: entry.data[CONF_NAME], **user_input},
                default_measurement_system=_default_measurement_system(self.hass),
            )
            if error:
                errors["base"] = error
            else:
                profile_updates = {
                    key: value
                    for key, value in profile.items()
                    if key not in (CONF_NAME, CONF_ENTITY_MAPPINGS)
                }
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates=profile_updates,
                    reason="reconfigure_successful",
                )

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
                return self.async_create_entry(
                    title="",
                    data=options,
                )

        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(self.config_entry),  # type: ignore[arg-type]
            errors=errors,
        )


def _default_measurement_system(hass: HomeAssistant) -> str:
    """Use Home Assistant's configured unit system when it is supported."""
    if hass.config.units == METRIC_SYSTEM:
        return UNIT_SYSTEM_METRIC
    if hass.config.units == US_CUSTOMARY_SYSTEM:
        return UNIT_SYSTEM_US_CUSTOMARY
    return UNIT_SYSTEM_METRIC


def _profile_schema(
    *,
    default_measurement_system: str,
    existing_data: Mapping[str, Any] | None = None,
    include_name: bool = True,
    include_mappings: bool = True,
) -> vol.Schema:
    """Build the RV profile form schema."""
    marker_defaults = dict(existing_data or {})
    marker_defaults.setdefault(CONF_MEASUREMENT_SYSTEM, default_measurement_system)
    if isinstance(marker_defaults.get(CONF_REAR_AXLE_COUNT), int):
        marker_defaults[CONF_REAR_AXLE_COUNT] = {
            1: AXLE_COUNT_ONE,
            2: AXLE_COUNT_TWO,
            3: AXLE_COUNT_THREE,
        }.get(marker_defaults[CONF_REAR_AXLE_COUNT])

    def marker(field: str) -> vol.Optional:
        """Create an optional field marker with its saved profile value."""
        if field in marker_defaults:
            return vol.Optional(field, default=marker_defaults[field])
        return vol.Optional(field)

    numeric_selector = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0,
            step=0.1,
            mode=selector.NumberSelectorMode.BOX,
        )
    )
    wheel_selector = selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=sorted(_WHEEL_CONFIGURATIONS),
            mode=selector.SelectSelectorMode.DROPDOWN,
            translation_key="wheel_configuration",
        )
    )

    schema: dict[vol.Marker, Any] = {}
    if include_name:
        schema[vol.Required(CONF_NAME, default="My RV")] = selector.TextSelector()
    schema[marker(CONF_COACH_YEAR)] = selector.NumberSelector(
        selector.NumberSelectorConfig(
            step=1,
            mode=selector.NumberSelectorMode.BOX,
        )
    )
    if include_mappings:
        schema.update(_entity_mapping_fields())
    schema.update(
        {marker(field): selector.TextSelector() for field in _PROFILE_TEXT_FIELDS}
    )
    schema.update(
        {
            marker(CONF_MEASUREMENT_SYSTEM): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=sorted(_UNIT_SYSTEMS),
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    translation_key="measurement_system",
                )
            ),
            marker(CONF_STORAGE_ZONE_ID): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="zone")
            ),
        }
    )
    schema.update({marker(field): numeric_selector for field in _MEASUREMENT_FIELDS})
    schema.update(
        {
            marker(CONF_REAR_AXLE_COUNT): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[AXLE_COUNT_ONE, AXLE_COUNT_TWO, AXLE_COUNT_THREE],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    translation_key="rear_axle_count",
                )
            ),
            marker(CONF_MAIN_REAR_WHEEL_CONFIGURATION): wheel_selector,
            marker(CONF_TAG_AXLE_WHEEL_CONFIGURATION): wheel_selector,
        }
    )
    return vol.Schema(schema)


def _normalize_profile(
    user_input: dict[str, Any], *, default_measurement_system: str
) -> tuple[dict[str, Any], str | None]:
    """Validate and normalize submitted RV profile values."""
    name = user_input[CONF_NAME].strip()
    data: dict[str, Any] = {CONF_NAME: name}

    mappings, mapping_error = _normalize_entity_mappings(user_input)
    if mapping_error:
        return data, mapping_error
    data[CONF_ENTITY_MAPPINGS] = mappings

    measurement_system = user_input.get(
        CONF_MEASUREMENT_SYSTEM, default_measurement_system
    )
    data[CONF_MEASUREMENT_SYSTEM] = measurement_system

    coach_year = user_input.get(CONF_COACH_YEAR)
    if coach_year is not None:
        if (
            not math.isfinite(coach_year)
            or not float(coach_year).is_integer()
            or not 1900 <= coach_year <= date.today().year + 1
        ):
            return data, "invalid_coach_year"
        data[CONF_COACH_YEAR] = int(coach_year)

    for field in _PROFILE_TEXT_FIELDS:
        value = user_input.get(field)
        if value is not None:
            if clean_value := value.strip():
                data[field] = clean_value

    zone_id = user_input.get(CONF_STORAGE_ZONE_ID)
    if zone_id is not None:
        if clean_zone_id := zone_id.strip():
            data[CONF_STORAGE_ZONE_ID] = clean_zone_id

    for field in _MEASUREMENT_FIELDS:
        value = user_input.get(field)
        if value is not None:
            if not math.isfinite(value) or value <= 0:
                return data, "invalid_measurement"
            data[field] = float(value)

    rear_axle_count = user_input.get(CONF_REAR_AXLE_COUNT)
    if rear_axle_count is not None:
        data[CONF_REAR_AXLE_COUNT] = {
            AXLE_COUNT_ONE: 1,
            AXLE_COUNT_TWO: 2,
            AXLE_COUNT_THREE: 3,
        }[rear_axle_count]

    rear_axle_count = data.get(CONF_REAR_AXLE_COUNT)
    tag_axle_present = rear_axle_count is not None and rear_axle_count > 1
    data[CONF_TAG_AXLE_PRESENT] = tag_axle_present

    tag_wheel_configuration = user_input.get(CONF_TAG_AXLE_WHEEL_CONFIGURATION)
    if tag_axle_present:
        if tag_wheel_configuration is None:
            return data, "tag_axle_wheel_configuration_required"
        data[CONF_TAG_AXLE_WHEEL_CONFIGURATION] = tag_wheel_configuration
    elif tag_wheel_configuration is not None:
        return data, "tag_wheel_configuration_without_tag_axle"

    main_wheel_configuration = user_input.get(CONF_MAIN_REAR_WHEEL_CONFIGURATION)
    rear_axle_count = data.get(CONF_REAR_AXLE_COUNT)
    main_rear_axle_count = (rear_axle_count or 0) - int(tag_axle_present)
    if main_rear_axle_count > 0 and main_wheel_configuration is None:
        return data, "main_rear_wheel_configuration_required"
    if main_wheel_configuration is not None:
        data[CONF_MAIN_REAR_WHEEL_CONFIGURATION] = main_wheel_configuration

    return data, None


def _entity_mapping_fields(
    mappings: dict[str, list[str]] | None = None,
) -> dict[vol.Marker, Any]:
    """Create selectors for source entities grouped by RV system."""
    mappings = mappings or {}
    return {
        vol.Optional(
            _mapping_field(category), default=mappings.get(category, [])
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain=list(SUPPORTED_ENTITY_DOMAINS),
                multiple=True,
            )
        )
        for category in SYSTEM_CATEGORIES
    }


def _mapping_field(category: str) -> str:
    """Return the form field for a system category."""
    return f"{category}_entities"


def _options_schema(entry: config_entries.ConfigEntry) -> vol.Schema:
    """Build source mapping and alert threshold options."""
    existing_options = entry.options
    fields = _entity_mapping_fields(_entry_entity_mappings(entry))
    tank_mappings = existing_options.get(CONF_TANK_ENTITY_MAPPINGS, {})
    for tank in TANK_TYPES:
        field = f"{tank}_tank_level"
        marker = (
            vol.Optional(field, default=tank_mappings[tank])
            if tank in tank_mappings
            else vol.Optional(field)
        )
        fields[marker] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        )

    percent_selector = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0,
            max=100,
            step=1,
            unit_of_measurement="%",
            mode=selector.NumberSelectorMode.BOX,
        )
    )
    tank_thresholds = existing_options.get(CONF_TANK_THRESHOLDS, {})
    for tank in TANK_TYPES:
        configured = tank_thresholds.get(tank, {})
        for level in (TANK_WARNING, TANK_PROBLEM):
            field = f"{tank}_tank_{level}"
            default = configured.get(
                level, DEFAULT_TANK_THRESHOLDS[tank][level == TANK_PROBLEM]
            )
            fields[vol.Optional(field, default=default)] = percent_selector

    tire_mappings = existing_options.get(CONF_TIRE_ENTITY_MAPPINGS, {})
    for position in tire_positions(entry.data):
        for metric in ("pressure", "temperature", "battery"):
            key = tire_entity_key(position, metric)
            field = f"tire_{key}"
            marker = (
                vol.Optional(field, default=tire_mappings[key])
                if key in tire_mappings
                else vol.Optional(field)
            )
            fields[marker] = selector.EntitySelector(
                selector.EntitySelectorConfig(domain=list(_NUMERIC_ENTITY_DOMAINS))
            )

    number_selector = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0,
            step=0.1,
            mode=selector.NumberSelectorMode.BOX,
        )
    )
    measurement_system = entry.data.get(CONF_MEASUREMENT_SYSTEM, UNIT_SYSTEM_METRIC)
    if measurement_system not in DEFAULT_TIRE_PRESSURE:
        measurement_system = UNIT_SYSTEM_METRIC
    pressure_thresholds = existing_options.get(CONF_TIRE_PRESSURE_THRESHOLDS, {})
    tire_groups = {position.group for position in tire_positions(entry.data)}
    for group in (TIRE_FRONT, TIRE_AXLE, TIRE_TAG):
        if group not in tire_groups:
            continue
        configured = pressure_thresholds.get(group, {})
        low_key = _pressure_threshold_field(group, CONF_TIRE_PRESSURE_LOW)
        high_key = _pressure_threshold_field(group, CONF_TIRE_PRESSURE_HIGH)
        default_low, default_high = DEFAULT_TIRE_PRESSURE[measurement_system]
        low_marker = vol.Optional(low_key, default=configured.get("low", default_low))
        high_marker = vol.Optional(
            high_key, default=configured.get("high", default_high)
        )
        fields[low_marker] = number_selector
        fields[high_marker] = number_selector

    if tire_groups:
        temperature_marker = vol.Optional(
            CONF_TIRE_TEMPERATURE_HIGH,
            default=existing_options.get(
                CONF_TIRE_TEMPERATURE_HIGH,
                DEFAULT_TIRE_TEMPERATURE_HIGH[measurement_system],
            ),
        )
        battery_marker = (
            vol.Optional(
                CONF_TIRE_BATTERY_LOW,
                default=existing_options[CONF_TIRE_BATTERY_LOW],
            )
            if CONF_TIRE_BATTERY_LOW in existing_options
            else vol.Optional(CONF_TIRE_BATTERY_LOW)
        )
        fields[temperature_marker] = number_selector
        fields[battery_marker] = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0,
                max=100,
                step=1,
                mode=selector.NumberSelectorMode.BOX,
            )
        )
    return vol.Schema(fields)


def _pressure_threshold_field(group: str, limit: str) -> str:
    """Return a form field key for one axle pressure limit."""
    return f"tire_{group}_pressure_{limit}"


def _normalize_options(
    user_input: dict[str, Any], entry: config_entries.ConfigEntry
) -> tuple[dict[str, Any], str | None]:
    """Validate source mappings and tire alert thresholds."""
    mappings, error = _normalize_entity_mappings(user_input)
    if error:
        return {}, error

    existing_tank_mappings = entry.options.get(CONF_TANK_ENTITY_MAPPINGS, {})
    tank_mappings: dict[str, str] = {}
    selected_tank_sources: set[str] = set()
    for tank in TANK_TYPES:
        entity_id = user_input.get(
            f"{tank}_tank_level", existing_tank_mappings.get(tank)
        )
        if entity_id is None:
            continue
        if not isinstance(entity_id, str):
            return {}, "invalid_tank_entity_mapping"
        entity_domain, separator, object_id = entity_id.partition(".")
        if (
            not separator
            or not object_id
            or entity_domain not in _NUMERIC_ENTITY_DOMAINS
        ):
            return {}, "invalid_tank_entity_mapping"
        if entity_id in selected_tank_sources:
            return {}, "duplicate_tank_entity_mapping"
        selected_tank_sources.add(entity_id)
        tank_mappings[tank] = entity_id

    existing_tank_thresholds = entry.options.get(CONF_TANK_THRESHOLDS, {})
    tank_thresholds: dict[str, dict[str, float]] = {}
    for tank in TANK_TYPES:
        existing = existing_tank_thresholds.get(tank, {})
        warning = user_input.get(f"{tank}_tank_{TANK_WARNING}", existing.get("warning"))
        problem = user_input.get(f"{tank}_tank_{TANK_PROBLEM}", existing.get("problem"))
        if (warning is None) != (problem is None):
            return {}, "incomplete_tank_threshold"
        if warning is not None:
            if (
                not _is_finite_number(warning)
                or not _is_finite_number(problem)
                or not thresholds_valid(tank, warning, problem)
            ):
                return {}, "invalid_tank_threshold"
            tank_thresholds[tank] = {
                TANK_WARNING: float(warning),
                TANK_PROBLEM: float(problem),
            }

    positions = tire_positions(entry.data)
    existing_tire_mappings = entry.options.get(CONF_TIRE_ENTITY_MAPPINGS, {})
    tire_mappings: dict[str, str] = {}
    selected_entities: set[str] = set()
    for position in positions:
        for metric in ("pressure", "temperature", "battery"):
            key = tire_entity_key(position, metric)
            entity_id = user_input.get(f"tire_{key}", existing_tire_mappings.get(key))
            if entity_id is None:
                continue
            if not isinstance(entity_id, str):
                return {}, "invalid_tire_entity_mapping"
            entity_domain, separator, object_id = entity_id.partition(".")
            if (
                not separator
                or not object_id
                or entity_domain not in _NUMERIC_ENTITY_DOMAINS
            ):
                return {}, "invalid_tire_entity_mapping"
            if entity_id in selected_entities:
                return {}, "duplicate_tire_entity_mapping"
            selected_entities.add(entity_id)
            tire_mappings[key] = entity_id

    pressure_thresholds: dict[str, dict[str, float]] = {}
    groups = {position.group for position in positions}
    existing_pressure_thresholds = entry.options.get(CONF_TIRE_PRESSURE_THRESHOLDS, {})
    for group in (TIRE_FRONT, TIRE_AXLE, TIRE_TAG):
        if group not in groups:
            continue
        existing = existing_pressure_thresholds.get(group, {})
        low = user_input.get(
            _pressure_threshold_field(group, CONF_TIRE_PRESSURE_LOW),
            existing.get("low"),
        )
        high = user_input.get(
            _pressure_threshold_field(group, CONF_TIRE_PRESSURE_HIGH),
            existing.get("high"),
        )
        if (low is None) != (high is None):
            return {}, "incomplete_tire_pressure_threshold"
        if low is not None:
            if (
                not _is_finite_number(low)
                or not _is_finite_number(high)
                or low < 0
                or high <= low
            ):
                return {}, "invalid_tire_pressure_threshold"
            pressure_thresholds[group] = {"low": float(low), "high": float(high)}

    temperature_high = user_input.get(
        CONF_TIRE_TEMPERATURE_HIGH,
        entry.options.get(CONF_TIRE_TEMPERATURE_HIGH),
    )
    if temperature_high is not None and (
        not _is_finite_number(temperature_high) or temperature_high < 0
    ):
        return {}, "invalid_tire_temperature_threshold"

    battery_low = user_input.get(
        CONF_TIRE_BATTERY_LOW, entry.options.get(CONF_TIRE_BATTERY_LOW)
    )
    if battery_low is not None and (
        not _is_finite_number(battery_low) or not 0 <= battery_low <= 100
    ):
        return {}, "invalid_tire_battery_threshold"

    options: dict[str, Any] = {
        CONF_ENTITY_MAPPINGS: mappings,
        CONF_TANK_ENTITY_MAPPINGS: tank_mappings,
        CONF_TANK_THRESHOLDS: tank_thresholds,
    }
    if positions:
        options[CONF_TIRE_ENTITY_MAPPINGS] = tire_mappings
        options[CONF_TIRE_PRESSURE_THRESHOLDS] = pressure_thresholds
        if temperature_high is not None:
            options[CONF_TIRE_TEMPERATURE_HIGH] = float(temperature_high)
        if battery_low is not None:
            options[CONF_TIRE_BATTERY_LOW] = float(battery_low)
    return options, None


def _is_finite_number(value: Any) -> bool:
    """Check that a submitted configuration value is a finite number."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _normalize_entity_mappings(
    user_input: dict[str, Any],
) -> tuple[dict[str, list[str]], str | None]:
    """Validate and normalize entity selections grouped by system."""
    mappings: dict[str, list[str]] = {}
    assigned_entities: set[str] = set()
    for category in SYSTEM_CATEGORIES:
        entities = user_input.get(_mapping_field(category), [])
        if not isinstance(entities, list) or any(
            not isinstance(entity_id, str) for entity_id in entities
        ):
            return {}, "invalid_entity_mapping"
        unique_entities = list(dict.fromkeys(entities))
        if assigned_entities.intersection(unique_entities):
            return {}, "duplicate_entity_mapping"
        assigned_entities.update(unique_entities)
        if unique_entities:
            mappings[category] = unique_entities
    return mappings, None


def _entry_entity_mappings(
    entry: config_entries.ConfigEntry,
) -> dict[str, list[str]]:
    """Read mappings, retaining compatibility with profile entries."""
    mappings = entry.options.get(CONF_ENTITY_MAPPINGS)
    if mappings is None:
        mappings = entry.data.get(CONF_ENTITY_MAPPINGS, {})
    return {
        category: list(entities)
        for category, entities in mappings.items()
        if category in SYSTEM_CATEGORIES
    }
