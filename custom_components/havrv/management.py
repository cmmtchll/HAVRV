"""Editable configuration snapshots shared by the HAVRV management commands."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from hashlib import sha256
from json import dumps
from typing import Any, TypedDict

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers import selector
from homeassistant.util.unit_conversion import (
    DistanceConverter,
    PressureConverter,
    TemperatureConverter,
    VolumeConverter,
)

from .configuration import (
    _MEASUREMENT_FIELDS,
    _entry_entity_mappings,
    _is_finite_number,
    _normalize_options,
    _normalize_power_source,
    _normalize_profile,
    _options_schema,
    _power_source_schema,
    _profile_schema,
)
from .const import (
    CONF_CONFIGURE_POWER_SOURCES,
    CONF_ENTITY_MAPPINGS,
    CONF_MEASUREMENT_SYSTEM,
    CONF_OPERATIONS_SOURCES,
    CONF_POWER_SOURCES,
    CONF_REAR_AXLE_COUNT,
    CONF_TAG_AXLE_PRESENT,
    CONF_TANK_ENTITY_MAPPINGS,
    CONF_TANK_THRESHOLDS,
    CONF_TIRE_BATTERY_LOW,
    CONF_TIRE_ENTITY_MAPPINGS,
    CONF_TIRE_PRESSURE_THRESHOLDS,
    CONF_TIRE_TEMPERATURE_HIGH,
    OPERATIONS_METRICS,
    SYSTEM_CATEGORIES,
    TANK_TYPES,
    TIRE_SOURCE_METRICS,
    UNIT_SYSTEM_METRIC,
)
from .power import power_sources, shore_line_count
from .tank import defined_tanks
from .tire import tire_entity_key, tire_positions


class EditableValues(TypedDict):
    """Form values and the units in which their numeric quantities are expressed."""

    profile: dict[str, Any]
    options: dict[str, Any]
    power: dict[str, Any]
    unit_system: str


class FieldError(TypedDict):
    """A validation failure linked to an editor section and field."""

    section: str
    field: str
    code: str


@dataclass
class Candidate:
    """A complete candidate, without mutating a Home Assistant config entry."""

    data: dict[str, Any]
    options: dict[str, Any]


def revision(entry: ConfigEntry) -> str:
    """Fingerprint persisted configuration, not live state or entry load state."""
    return sha256(
        dumps(
            [dict(entry.data), dict(entry.options)],
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


def editable_values(
    entry: ConfigEntry | Candidate, default_units: str
) -> EditableValues:
    """Project saved configuration into flat forms, without filling optional values."""
    profile = {
        key: deepcopy(value)
        for key, value in entry.data.items()
        if key not in (CONF_ENTITY_MAPPINGS, CONF_TAG_AXLE_PRESENT)
    }
    if CONF_REAR_AXLE_COUNT in profile:
        profile[CONF_REAR_AXLE_COUNT] = {1: "one", 2: "two", 3: "three"}[
            profile[CONF_REAR_AXLE_COUNT]
        ]
    profile.setdefault(CONF_MEASUREMENT_SYSTEM, default_units)
    options: dict[str, Any] = {
        f"{category}_entities": _entry_entity_mappings(entry).get(category, [])
        for category in SYSTEM_CATEGORIES
    }
    for tank, source in entry.options.get(CONF_TANK_ENTITY_MAPPINGS, {}).items():
        options[f"{tank}_tank_level"] = source
    for metric, source in entry.options.get(CONF_OPERATIONS_SOURCES, {}).items():
        options[f"operations_{metric}"] = source
    for tank, limits in entry.options.get(CONF_TANK_THRESHOLDS, {}).items():
        for level, value in limits.items():
            options[f"{tank}_tank_{level}"] = value
    for key, source in entry.options.get(CONF_TIRE_ENTITY_MAPPINGS, {}).items():
        options[f"tire_{key}"] = source
    for group, limits in entry.options.get(CONF_TIRE_PRESSURE_THRESHOLDS, {}).items():
        for limit, value in limits.items():
            options[f"tire_{group}_pressure_{limit}"] = value
    for key in (CONF_TIRE_TEMPERATURE_HIGH, CONF_TIRE_BATTERY_LOW):
        if key in entry.options:
            options[key] = entry.options[key]
    return {
        "profile": profile,
        "options": options,
        "power": deepcopy(dict(entry.options.get(CONF_POWER_SOURCES, {}))),
        "unit_system": profile[CONF_MEASUREMENT_SYSTEM],
    }


def _fields(schema: vol.Schema) -> list[dict[str, Any]]:
    """Serialize selector metadata without applying form defaults."""
    fields: list[dict[str, Any]] = []
    for marker, validator in schema.schema.items():
        if str(marker) == CONF_CONFIGURE_POWER_SOURCES:
            continue
        assert isinstance(validator, selector.Selector)
        field = {"name": str(marker), **deepcopy(validator.serialize())}
        if marker.default is not vol.UNDEFINED:
            field["suggested_value"] = marker.default()
        fields.append(field)
    return fields


def editor_schema(candidate: Candidate, default_units: str) -> dict[str, Any]:
    """Describe every supported editor using the native flow's selectors."""
    schema: dict[str, Any] = {
        "profile": _fields(
            _profile_schema(
                default_measurement_system=default_units,
                existing_data=candidate.data,
                include_name=False,
                include_mappings=False,
            )
        ),
        "options": _fields(
            _options_schema(candidate, default_measurement_system=default_units)
        ),
        "power": [
            {
                **asdict(source),
                "fields": _fields(
                    _power_source_schema(
                        source,
                        candidate.options.get(CONF_POWER_SOURCES, {}).get(
                            source.key, {}
                        ),
                    )
                ),
            }
            for source in power_sources(candidate.data)
        ],
        "tires": [asdict(position) for position in tire_positions(candidate.data)],
        "defaults": {},
    }
    metric = (
        candidate.data.get(CONF_MEASUREMENT_SYSTEM, default_units) == UNIT_SYSTEM_METRIC
    )
    for field in schema["profile"]:
        if field["name"] in _MEASUREMENT_FIELDS:
            field["selector"]["number"]["unit_of_measurement"] = (
                ("m" if metric else "ft")
                if field["name"] in _MEASUREMENT_FIELDS[:3]
                else ("L" if metric else "gal")
            )
    for field in schema["options"]:
        name = field["name"]
        if name.startswith("tire_") and "_pressure_" in name:
            field["selector"]["number"]["unit_of_measurement"] = (
                "kPa" if metric else "psi"
            )
        elif name == CONF_TIRE_TEMPERATURE_HIGH:
            field["selector"]["number"]["unit_of_measurement"] = (
                UnitOfTemperature.CELSIUS if metric else UnitOfTemperature.FAHRENHEIT
            )
        elif name == CONF_TIRE_BATTERY_LOW:
            field["selector"]["number"]["unit_of_measurement"] = "%"
    return schema


def _convert_units(values: EditableValues) -> None:
    """Convert all draft unit-bearing quantities once when profile units change."""
    target = values["profile"][CONF_MEASUREMENT_SYSTEM]
    original = values["unit_system"]
    if target == original:
        return
    metric = original == UNIT_SYSTEM_METRIC
    old_distance, new_distance = ("m", "ft") if metric else ("ft", "m")
    old_volume, new_volume = ("L", "gal") if metric else ("gal", "L")
    old_pressure, new_pressure = ("kPa", "psi") if metric else ("psi", "kPa")
    old_temp, new_temp = ("°C", "°F") if metric else ("°F", "°C")
    for key in _MEASUREMENT_FIELDS:
        if key not in values["profile"]:
            continue
        value = values["profile"][key]
        values["profile"][key] = (
            DistanceConverter.convert(value, old_distance, new_distance)
            if key in _MEASUREMENT_FIELDS[:3]
            else VolumeConverter.convert(value, old_volume, new_volume)
        )
    for key, value in values["options"].items():
        if key.startswith("tire_") and "_pressure_" in key:
            values["options"][key] = PressureConverter.convert(
                value, old_pressure, new_pressure
            )
        elif key == CONF_TIRE_TEMPERATURE_HIGH:
            values["options"][key] = TemperatureConverter.convert(
                value, old_temp, new_temp
            )
    values["unit_system"] = target


def validate_values(
    entry: ConfigEntry, submitted: dict[str, Any], default_units: str
) -> tuple[Candidate, EditableValues, list[FieldError], list[str]]:
    """Validate a full draft, preserving absent defaults and unowned saved keys."""
    baseline = editable_values(entry, default_units)
    candidate = Candidate(dict(entry.data), dict(entry.options))
    values = deepcopy(submitted)
    errors: list[FieldError] = []

    def error(section: str, field: str, code: str) -> None:
        errors.append({"section": section, "field": field, "code": code})

    if (
        set(values) != {"profile", "options", "power", "unit_system"}
        or any(
            not isinstance(values.get(key), dict)
            for key in ("profile", "options", "power")
        )
        or values.get("unit_system") not in ("metric", "us_customary")
    ):
        error("profile", "", "invalid_config")
        return candidate, baseline, errors, []
    typed_values = EditableValues(
        profile=values["profile"],
        options=values["options"],
        power=values["power"],
        unit_system=values["unit_system"],
    )
    profile_input = typed_values["profile"]
    if profile_input.get("name", entry.data["name"]) != entry.data["name"]:
        error("profile", "name", "invalid_config")
        return candidate, typed_values, errors, []
    profile_input["name"] = entry.data["name"]
    profile_input.setdefault(CONF_MEASUREMENT_SYSTEM, default_units)
    profile_fields = {
        field["name"] for field in editor_schema(candidate, default_units)["profile"]
    }
    if set(profile_input) - profile_fields - set(baseline["profile"]):
        error("profile", "", "invalid_config")
        return candidate, typed_values, errors, []
    for field in editor_schema(candidate, default_units)["profile"]:
        name = field["name"]
        if name not in profile_input:
            continue
        value = profile_input[name]
        kind = next(iter(field["selector"]))
        if (
            kind == "number"
            and not _is_finite_number(value)
            or (kind != "number" and not isinstance(value, str))
        ):
            error("profile", name, "invalid_measurement")
    for name, value in typed_values["options"].items():
        if (
            name.startswith("tire_")
            and "_pressure_" in name
            or name == CONF_TIRE_TEMPERATURE_HIGH
        ) and not _is_finite_number(value):
            error("tires", name, "invalid_measurement")
    if errors:
        return candidate, typed_values, errors, []
    profile, profile_error = _normalize_profile(
        profile_input, default_measurement_system=default_units
    )
    if profile_error:
        error("profile", "", profile_error)
        return candidate, typed_values, errors, []
    # Shared normalizers reject invalid numeric types before conversion.
    options_input = typed_values["options"]
    for category in SYSTEM_CATEGORIES:
        options_input.setdefault(f"{category}_entities", [])
    # A complete submitted snapshot has no implicit fallback to old mappings.
    clean = Candidate(profile, {})
    allowed_options = {
        field["name"] for field in editor_schema(clean, default_units)["options"]
    }
    old_options = set(baseline["options"])
    if set(options_input) - allowed_options - old_options:
        error("systems", "", "invalid_config")
    options, option_error = _normalize_options(options_input, clean)
    if option_error:
        section = (
            "tanks"
            if "tank" in option_error
            else "tires"
            if "tire" in option_error
            else "systems"
        )
        if option_error == "invalid_operations_source":
            section = "operations"
        error(section, "", option_error)
    if errors:
        return candidate, typed_values, errors, []
    _convert_units(typed_values)
    profile, profile_error = _normalize_profile(
        typed_values["profile"], default_measurement_system=default_units
    )
    if profile_error:
        error("profile", "", profile_error)
        return candidate, typed_values, errors, []
    clean = Candidate(profile, {})
    options, option_error = _normalize_options(typed_values["options"], clean)
    if option_error:
        error("tires", "", option_error)
        return candidate, typed_values, errors, []

    for key in profile_fields | {CONF_TAG_AXLE_PRESENT}:
        if key in profile:
            if (
                key in entry.data
                or typed_values["profile"].get(key) != baseline["profile"].get(key)
                or key == CONF_TAG_AXLE_PRESENT
                and typed_values["profile"].get(CONF_REAR_AXLE_COUNT)
                != baseline["profile"].get(CONF_REAR_AXLE_COUNT)
            ):
                candidate.data[key] = profile[key]
        else:
            candidate.data.pop(key, None)
    flat_before, flat_after = baseline["options"], typed_values["options"]
    for key, prefixes in (
        (CONF_OPERATIONS_SOURCES, tuple(f"operations_{m}" for m in OPERATIONS_METRICS)),
        (CONF_ENTITY_MAPPINGS, tuple(f"{c}_entities" for c in SYSTEM_CATEGORIES)),
        (CONF_TANK_ENTITY_MAPPINGS, tuple(f"{t}_tank_level" for t in TANK_TYPES)),
        (
            CONF_TANK_THRESHOLDS,
            tuple(f"{t}_tank_{s}" for t in TANK_TYPES for s in ("warning", "problem")),
        ),
        (
            CONF_TIRE_ENTITY_MAPPINGS,
            tuple(
                f"tire_{tire_entity_key(p, m)}"
                for p in tire_positions(entry.data) + tire_positions(profile)
                for m in TIRE_SOURCE_METRICS
            ),
        ),
        (
            CONF_TIRE_PRESSURE_THRESHOLDS,
            tuple(
                f"tire_{g}_pressure_{s}"
                for g in ("front", "axle", "tag")
                for s in ("low", "high")
            ),
        ),
        (CONF_TIRE_TEMPERATURE_HIGH, (CONF_TIRE_TEMPERATURE_HIGH,)),
        (CONF_TIRE_BATTERY_LOW, (CONF_TIRE_BATTERY_LOW,)),
    ):
        if any(flat_before.get(field) != flat_after.get(field) for field in prefixes):
            if key in options:
                candidate.options[key] = options[key]
            else:
                candidate.options.pop(key, None)

    # Prune sources and tire fields excluded by the candidate layout.
    active_positions = {p.key for p in tire_positions(profile)}
    old_positions = {p.key for p in tire_positions(entry.data)}
    if active_positions != old_positions:
        candidate.options[CONF_TIRE_ENTITY_MAPPINGS] = options.get(
            CONF_TIRE_ENTITY_MAPPINGS, {}
        )
        candidate.options[CONF_TIRE_PRESSURE_THRESHOLDS] = options.get(
            CONF_TIRE_PRESSURE_THRESHOLDS, {}
        )
    settings = {}
    sources = power_sources(profile)
    old_sources = {source.key for source in power_sources(entry.data)}
    allowed_sources = {source.key for source in sources} | old_sources
    if set(typed_values["power"]) - allowed_sources:
        error("power", "", "invalid_config")
    for source in sources:
        raw = typed_values["power"].get(source.key, {})
        if not isinstance(raw, dict):
            error("power", source.key, "invalid_config")
            continue
        allowed = {
            field["name"]
            for field in _fields(_power_source_schema(source, {"line_count": 2}))
        }
        if set(raw) - allowed:
            error("power", source.key, "invalid_config")
            continue
        submitted = dict(raw)
        if source.key == "shore_power":
            submitted.setdefault(
                "line_count",
                shore_line_count(
                    entry.options.get(CONF_POWER_SOURCES, {}).get(source.key, {})
                ),
            )
        normalized, power_error = _normalize_power_source(submitted, source)
        if power_error:
            error("power", source.key, power_error)
        elif raw != baseline["power"].get(source.key, {}):
            settings[source.key] = normalized
        elif source.key in entry.options.get(CONF_POWER_SOURCES, {}):
            settings[source.key] = entry.options[CONF_POWER_SOURCES][source.key]
    if settings or CONF_POWER_SOURCES in entry.options:
        candidate.options[CONF_POWER_SOURCES] = settings
    impacts = [f"power.{key}" for key in sorted(old_sources - {s.key for s in sources})]
    impacts += [f"tires.{key}" for key in sorted(old_positions - active_positions)]
    impacts += [
        f"tanks.{tank}"
        for tank in sorted(
            defined_tanks(entry.data, entry.options.get(CONF_TANK_ENTITY_MAPPINGS, {}))
            - defined_tanks(
                candidate.data, candidate.options.get(CONF_TANK_ENTITY_MAPPINGS, {})
            )
        )
    ]
    for section, before, after in (
        ("options", baseline["options"], typed_values["options"]),
        (
            "power",
            baseline["power"],
            candidate.options.get(CONF_POWER_SOURCES, {}),
        ),
    ):
        impacts += [
            f"{section}.{source}"
            for source in sorted(_source_ids(before) - _source_ids(after))
        ]
    return candidate, typed_values, errors, impacts


def _source_ids(value: Any) -> set[str]:
    """Collect explicit source identifiers, excluding configuration quantities."""
    if isinstance(value, dict):
        return set().union(*(_source_ids(v) for v in value.values()), set())
    if isinstance(value, list):
        return set().union(*(_source_ids(v) for v in value), set())
    return {value} if isinstance(value, str) and "." in value else set()
