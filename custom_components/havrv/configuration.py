"""Shared configuration schemas and normalization for HAVRV."""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import date
from typing import Any, Protocol

import voluptuous as vol
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, valid_entity_id
from homeassistant.helpers import selector
from homeassistant.util.unit_system import METRIC_SYSTEM, US_CUSTOMARY_SYSTEM

from .const import (
    AXLE_COUNT_ONE,
    AXLE_COUNT_THREE,
    AXLE_COUNT_TWO,
    CONF_BLACK_WATER_TANK_CAPACITY,
    CONF_CHASSIS_BATTERY_BANK_COUNT,
    CONF_COACH_BUILDER,
    CONF_COACH_IDENTIFIER,
    CONF_COACH_YEAR,
    CONF_CONFIGURE_POWER_SOURCES,
    CONF_ENTITY_MAPPINGS,
    CONF_FRESH_WATER_TANK_CAPACITY,
    CONF_FUEL_TANK_CAPACITY,
    CONF_GRAY_WATER_TANK_CAPACITY,
    CONF_HOUSE_BATTERY_BANK_COUNT,
    CONF_MAIN_REAR_WHEEL_CONFIGURATION,
    CONF_MAKE,
    CONF_MANUFACTURER,
    CONF_MEASUREMENT_SYSTEM,
    CONF_MODEL,
    CONF_OVERALL_HEIGHT,
    CONF_OVERALL_LENGTH,
    CONF_OVERALL_WIDTH,
    CONF_POWER_SOURCES,
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
    DEFAULT_BATTERY_BANK_COUNT,
    DEFAULT_BATTERY_NOMINAL_VOLTAGE,
    DEFAULT_TANK_THRESHOLDS,
    DEFAULT_TIRE_BATTERY_LOW,
    DEFAULT_TIRE_PRESSURE,
    DEFAULT_TIRE_TEMPERATURE_HIGH,
    POWER_LOCATIONS,
    SHORE_LOCATIONS,
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
from .power import (
    BINARY_POWER_DOMAINS,
    DEFAULT_SHORE_LINE_COUNT,
    NUMERIC_POWER_DOMAINS,
    PowerSource,
    power_numeric_metrics,
    shore_line_count,
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


class ConfigurationEntry(Protocol):
    """Read-only configuration needed by shared forms and validators."""

    @property
    def data(self) -> Mapping[str, Any]:
        """Return saved profile data."""
        ...

    @property
    def options(self) -> Mapping[str, Any]:
        """Return saved options."""
        ...


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
    for field in (CONF_HOUSE_BATTERY_BANK_COUNT, CONF_CHASSIS_BATTERY_BANK_COUNT):
        schema[
            vol.Optional(
                field, default=marker_defaults.get(field, DEFAULT_BATTERY_BANK_COUNT)
            )
        ] = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0, step=1, mode=selector.NumberSelectorMode.BOX
            )
        )
    if include_mappings:
        schema[vol.Optional(CONF_CONFIGURE_POWER_SOURCES, default=True)] = (
            selector.BooleanSelector()
        )
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
    for field in (CONF_HOUSE_BATTERY_BANK_COUNT, CONF_CHASSIS_BATTERY_BANK_COUNT):
        count = user_input.get(field, DEFAULT_BATTERY_BANK_COUNT)
        if not _is_finite_number(count) or count < 0 or not float(count).is_integer():
            return data, "invalid_battery_bank_count"
        data[field] = int(count)

    mappings, mapping_error = _normalize_entity_mappings(user_input)
    if mapping_error:
        return data, mapping_error
    data[CONF_ENTITY_MAPPINGS] = mappings

    measurement_system = user_input.get(
        CONF_MEASUREMENT_SYSTEM, default_measurement_system
    )
    if measurement_system not in (UNIT_SYSTEM_METRIC, UNIT_SYSTEM_US_CUSTOMARY):
        return data, "invalid_measurement"
    data[CONF_MEASUREMENT_SYSTEM] = measurement_system

    coach_year = user_input.get(CONF_COACH_YEAR)
    if coach_year is not None:
        if (
            not _is_finite_number(coach_year)
            or not float(coach_year).is_integer()
            or not 1900 <= coach_year <= date.today().year + 1
        ):
            return data, "invalid_coach_year"
        data[CONF_COACH_YEAR] = int(coach_year)

    for field in _PROFILE_TEXT_FIELDS:
        value = user_input.get(field)
        if value is not None:
            if not isinstance(value, str):
                return data, "invalid_measurement"
            if clean_value := value.strip():
                data[field] = clean_value

    zone_id = user_input.get(CONF_STORAGE_ZONE_ID)
    if zone_id is not None:
        if (
            not isinstance(zone_id, str)
            or not valid_entity_id(zone_id)
            or not zone_id.startswith("zone.")
        ):
            return data, "invalid_entity_mapping"
        if clean_zone_id := zone_id.strip():
            data[CONF_STORAGE_ZONE_ID] = clean_zone_id

    for field in _MEASUREMENT_FIELDS:
        value = user_input.get(field)
        if value is not None:
            if not _is_finite_number(value) or value <= 0:
                return data, "invalid_measurement"
            data[field] = float(value)

    rear_axle_count = user_input.get(CONF_REAR_AXLE_COUNT)
    if rear_axle_count is not None:
        if rear_axle_count not in (AXLE_COUNT_ONE, AXLE_COUNT_TWO, AXLE_COUNT_THREE):
            return data, "invalid_measurement"
        data[CONF_REAR_AXLE_COUNT] = {
            AXLE_COUNT_ONE: 1,
            AXLE_COUNT_TWO: 2,
            AXLE_COUNT_THREE: 3,
        }[rear_axle_count]

    rear_axle_count = data.get(CONF_REAR_AXLE_COUNT)
    tag_axle_present = rear_axle_count is not None and rear_axle_count > 1
    data[CONF_TAG_AXLE_PRESENT] = tag_axle_present

    tag_wheel_configuration = user_input.get(CONF_TAG_AXLE_WHEEL_CONFIGURATION)
    for field in (
        CONF_MAIN_REAR_WHEEL_CONFIGURATION,
        CONF_TAG_AXLE_WHEEL_CONFIGURATION,
    ):
        if user_input.get(field) is not None and user_input[field] not in (
            WHEEL_CONFIGURATION_SINGLE,
            WHEEL_CONFIGURATION_DUAL,
        ):
            return data, "invalid_measurement"
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


def _options_schema(
    entry: ConfigurationEntry,
    *,
    default_measurement_system: str = UNIT_SYSTEM_METRIC,
) -> vol.Schema:
    """Build source mapping and alert threshold options."""
    existing_options = entry.options
    fields = _entity_mapping_fields(_entry_entity_mappings(entry))
    fields[vol.Optional(CONF_CONFIGURE_POWER_SOURCES, default=False)] = (
        selector.BooleanSelector()
    )
    tank_mappings = existing_options.get(CONF_TANK_ENTITY_MAPPINGS, {})
    for tank in TANK_TYPES:
        field = f"{tank}_tank_level"
        marker = (
            vol.Optional(field, default=tank_mappings[tank])
            if tank in tank_mappings
            else vol.Optional(field)
        )
        fields[marker] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain=list(_NUMERIC_ENTITY_DOMAINS))
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
    measurement_system = entry.data.get(
        CONF_MEASUREMENT_SYSTEM, default_measurement_system
    )
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
        battery_marker = vol.Optional(
            CONF_TIRE_BATTERY_LOW,
            default=existing_options.get(
                CONF_TIRE_BATTERY_LOW, DEFAULT_TIRE_BATTERY_LOW
            ),
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
    user_input: dict[str, Any], entry: ConfigurationEntry
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
            not valid_entity_id(entity_id)
            or not separator
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
                not valid_entity_id(entity_id)
                or not separator
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
        CONF_TIRE_BATTERY_LOW,
        entry.options.get(CONF_TIRE_BATTERY_LOW),
    )
    if battery_low is None:
        battery_low = DEFAULT_TIRE_BATTERY_LOW
    if battery_low is not None and (
        not _is_finite_number(battery_low) or not 0 <= battery_low <= 100
    ):
        return {}, "invalid_tire_battery_threshold"

    options: dict[str, Any] = {
        **entry.options,
        CONF_ENTITY_MAPPINGS: mappings,
        CONF_TANK_ENTITY_MAPPINGS: tank_mappings,
        CONF_TANK_THRESHOLDS: tank_thresholds,
    }
    if CONF_POWER_SOURCES in entry.options:
        options[CONF_POWER_SOURCES] = entry.options[CONF_POWER_SOURCES]
    if positions:
        options[CONF_TIRE_ENTITY_MAPPINGS] = tire_mappings
        options[CONF_TIRE_PRESSURE_THRESHOLDS] = pressure_thresholds
        if temperature_high is not None:
            options[CONF_TIRE_TEMPERATURE_HIGH] = float(temperature_high)
        options[CONF_TIRE_BATTERY_LOW] = float(battery_low)
    return options, None


def _power_source_schema(
    source: PowerSource, settings: Mapping[str, Any]
) -> vol.Schema:
    """Build one source form with the same defaults used at runtime."""
    fields: dict[vol.Marker, Any] = {}
    if source.key == "shore_power":
        fields[vol.Required("line_count", default=shore_line_count(settings))] = (
            selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1, max=2, step=1, mode=selector.NumberSelectorMode.BOX
                )
            )
        )
    for metric, domains in (
        *(
            (metric, NUMERIC_POWER_DOMAINS)
            for metric in power_numeric_metrics(source, settings)
        ),
        ("enabled", BINARY_POWER_DOMAINS),
        ("warning", BINARY_POWER_DOMAINS),
        ("problem", BINARY_POWER_DOMAINS),
        *([("charging", BINARY_POWER_DOMAINS)] if source.battery else []),
    ):
        marker = vol.Optional(
            metric, description={"suggested_value": settings.get(metric)}
        )
        fields[marker] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain=list(domains))
        )
    locations = SHORE_LOCATIONS if source.key == "shore_power" else POWER_LOCATIONS
    fields[vol.Optional("location", default=settings.get("location", "not_shown"))] = (
        selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=list(locations),
                mode=selector.SelectSelectorMode.DROPDOWN,
                translation_key="power_location",
            )
        )
    )
    if source.battery:
        fields[
            vol.Optional(
                "nominal_voltage",
                default=str(
                    settings.get("nominal_voltage", DEFAULT_BATTERY_NOMINAL_VOLTAGE)
                ),
            )
        ] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=["12", "24", "48"],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )
        marker = vol.Optional(
            "nominal_capacity",
            description={"suggested_value": settings.get("nominal_capacity")},
        )
        fields[marker] = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0,
                step=0.1,
                unit_of_measurement="Ah",
                mode=selector.NumberSelectorMode.BOX,
            )
        )
    return vol.Schema(fields)


def _normalize_power_source(
    user_input: Mapping[str, Any], source: PowerSource
) -> tuple[dict[str, Any], str | None]:
    """Validate optional read-only mappings without guessing source states."""
    settings: dict[str, Any] = {}
    if source.key == "shore_power":
        count = user_input.get("line_count", DEFAULT_SHORE_LINE_COUNT)
        if not _is_finite_number(count) or count not in (1, 2):
            return {}, "invalid_shore_line_count"
        settings["line_count"] = int(count)
    selected: set[str] = set()
    for metric, domains in (
        *(
            (metric, NUMERIC_POWER_DOMAINS)
            for metric in power_numeric_metrics(source, settings)
        ),
        ("enabled", BINARY_POWER_DOMAINS),
        ("warning", BINARY_POWER_DOMAINS),
        ("problem", BINARY_POWER_DOMAINS),
        *([("charging", BINARY_POWER_DOMAINS)] if source.battery else []),
    ):
        entity_id = user_input.get(metric)
        if entity_id is None:
            continue
        if not isinstance(entity_id, str):
            return {}, "invalid_power_entity_mapping"
        domain, separator, object_id = entity_id.partition(".")
        if (
            not valid_entity_id(entity_id)
            or not separator
            or not object_id
            or domain not in domains
        ):
            return {}, "invalid_power_entity_mapping"
        if entity_id in selected:
            return {}, "duplicate_power_entity_mapping"
        selected.add(entity_id)
        settings[metric] = entity_id
    location = user_input.get("location", "not_shown")
    locations = SHORE_LOCATIONS if source.key == "shore_power" else POWER_LOCATIONS
    if location not in locations:
        return {}, "invalid_power_location"
    settings["location"] = location
    if source.battery:
        voltage = user_input.get("nominal_voltage", DEFAULT_BATTERY_NOMINAL_VOLTAGE)
        if voltage not in (12, 24, 48, "12", "24", "48"):
            return {}, "invalid_nominal_voltage"
        settings["nominal_voltage"] = int(voltage)
        capacity = user_input.get("nominal_capacity")
        if capacity is not None:
            if not _is_finite_number(capacity) or capacity <= 0:
                return {}, "invalid_nominal_capacity"
            settings["nominal_capacity"] = float(capacity)
    return settings, None


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
        if any(
            entity_id.partition(".")[0] not in SUPPORTED_ENTITY_DOMAINS
            or not valid_entity_id(entity_id)
            for entity_id in unique_entities
        ):
            return {}, "invalid_entity_mapping"
        if assigned_entities.intersection(unique_entities):
            return {}, "duplicate_entity_mapping"
        assigned_entities.update(unique_entities)
        if unique_entities:
            mappings[category] = unique_entities
    return mappings, None


def _entry_entity_mappings(
    entry: ConfigurationEntry,
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
