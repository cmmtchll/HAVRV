"""Provider-neutral live powertrain readings and explicitly configured advisories."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import (
    Event,
    EventStateChangedData,
    EventStateReportedData,
    HomeAssistant,
    callback,
    valid_entity_id,
)
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_state_report_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import (
    BaseUnitConverter,
    ElectricPotentialConverter,
    PressureConverter,
    TemperatureConverter,
    VolumeConverter,
    VolumeFlowRateConverter,
)

from .const import CONF_FUEL_TANK_CAPACITY, DOMAIN, UNIT_SYSTEM_METRIC
from .operations import finite_number

if TYPE_CHECKING:
    from . import HavrvConfigEntry

CONF_POWERTRAIN = "powertrain"
DEFAULT_MAX_AGE = 60
LIMITS = ("problem_low", "warning_low", "warning_high", "problem_high")


@dataclass(frozen=True)
class Metric:
    """Declare supported units without guessing a source's measurement type."""

    metric_unit: str | None
    customary_unit: str | None
    converter: type[BaseUnitConverter] | None = None
    device_class: SensorDeviceClass | None = None

    def unit(self, units: str) -> str | None:
        """Return the profile unit, independent of HA's display overrides."""
        return self.metric_unit if units == UNIT_SYSTEM_METRIC else self.customary_unit


PERCENT = Metric("%", "%")
TEMPERATURE = Metric("°C", "°F", TemperatureConverter, SensorDeviceClass.TEMPERATURE)
PRESSURE = Metric("kPa", "psi", PressureConverter, SensorDeviceClass.PRESSURE)
TEXT = Metric(None, None)
METRICS: dict[str, dict[str, Metric]] = {
    "engine": {
        "rpm": Metric("rpm", "rpm"),
        "load": PERCENT,
        "accelerator": PERCENT,
        "oil_pressure": PRESSURE,
        "coolant_temperature": TEMPERATURE,
        "oil_temperature": TEMPERATURE,
        "coolant_level": PERCENT,
        "intake_temperature": TEMPERATURE,
        "ambient_temperature": TEMPERATURE,
        "manifold_pressure": PRESSURE,
        "barometric_pressure": PRESSURE,
        "voltage": Metric(
            "V", "V", ElectricPotentialConverter, SensorDeviceClass.VOLTAGE
        ),
    },
    "transmission": {
        "selected_gear": TEXT,
        "current_gear": TEXT,
        "oil_temperature": TEMPERATURE,
        "retarder_temperature": TEMPERATURE,
    },
    "fuel": {
        "rate": Metric(
            "L/h", "gal/h", VolumeFlowRateConverter, SensorDeviceClass.VOLUME_FLOW_RATE
        ),
        "level": PERCENT,
        "reported_instantaneous_economy": Metric("km/L", "mpg"),
        "reported_average_economy": Metric("km/L", "mpg"),
    },
}


def option_fields(saved: dict[str, Any], units: str) -> dict[vol.Marker, Any]:
    """Build removable native fields; only freshness has a default."""
    fields: dict[vol.Marker, Any] = {}
    for obj, metrics in METRICS.items():
        settings = saved.get(obj, {})
        fields[
            vol.Optional(
                f"powertrain_{obj}_max_age",
                default=settings.get("max_age", DEFAULT_MAX_AGE),
            )
        ] = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1,
                step=1,
                unit_of_measurement="s",
                mode=selector.NumberSelectorMode.BOX,
            )
        )
        for name, metric in metrics.items():
            prefix = f"powertrain_{obj}_{name}"
            fields[
                vol.Optional(
                    prefix,
                    description={"suggested_value": settings[name]}
                    if settings.get(name)
                    else {},
                )
            ] = selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain=["sensor"]
                    if metric == TEXT
                    else ["sensor", "number", "input_number"]
                )
            )
            if metric == TEXT:
                continue
            for limit in LIMITS:
                key = f"{name}_{limit}"
                fields[
                    vol.Optional(
                        f"{prefix}_{limit}",
                        description={"suggested_value": settings[key]}
                        if key in settings
                        else {},
                    )
                ] = selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        step="any",
                        unit_of_measurement=metric.unit(units) or "",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                )
    return fields


def normalize_options(
    values: dict[str, Any],
) -> tuple[dict[str, Any], tuple[str, str, str] | None]:
    """Validate finite limits and their complete ordering; absent limits disable."""
    result: dict[str, Any] = {}
    for obj, metrics in METRICS.items():
        settings: dict[str, Any] = {}
        age_field = f"powertrain_{obj}_max_age"
        age = values.get(age_field, DEFAULT_MAX_AGE)
        if (
            isinstance(age, bool)
            or not isinstance(age, (int, float))
            or (finite_number(age) is None or age < 1)
        ):
            return {}, (obj, age_field, "invalid_powertrain_max_age")
        for name, metric in metrics.items():
            field = f"powertrain_{obj}_{name}"
            source = values.get(field)
            if source not in (None, ""):
                if (
                    not isinstance(source, str)
                    or not valid_entity_id(source)
                    or (
                        source.partition(".")[0]
                        not in (
                            ("sensor",)
                            if metric == TEXT
                            else ("sensor", "number", "input_number")
                        )
                    )
                ):
                    return {}, (obj, field, "invalid_powertrain_source")
                settings[name] = source
            limits: list[float] = []
            for limit in LIMITS:
                key = f"{name}_{limit}"
                value = values.get(f"powertrain_{obj}_{key}")
                if value is None or value == "":
                    continue
                if (
                    metric == TEXT
                    or isinstance(value, bool)
                    or (
                        not isinstance(value, (int, float))
                        or finite_number(value) is None
                    )
                ):
                    return {}, (
                        obj,
                        f"powertrain_{obj}_{key}",
                        "invalid_powertrain_threshold",
                    )
                settings[key] = float(value)
                limits.append(float(value))
            if limits != sorted(limits):
                return {}, (obj, field, "invalid_powertrain_threshold")
        if settings or age != DEFAULT_MAX_AGE:
            settings["max_age"] = float(age)
            result[obj] = settings
    return result, None


def convert_value(
    value: float, source: str, target: str, metric: Metric
) -> float | None:
    """Convert compatible units, including source-reported economy."""
    if metric.converter:
        if source not in metric.converter.VALID_UNITS:
            return None
        return finite_number(metric.converter.convert(value, source, target))
    if metric.metric_unit == "km/L":
        # US gallons, matching the profile's existing VolumeConverter contract.
        km_per_l = (
            value
            if source == "km/L"
            else value * 1.609344 / 3.785411784
            if source == "mpg"
            else 100 / value
            if source == "L/100km" and value > 0
            else None
        )
        if km_per_l is None:
            return None
        return finite_number(
            km_per_l if target == "km/L" else km_per_l * 3.785411784 / 1.609344
        )
    return value if source == target else None


def entity_keys(options: dict[str, Any], data: dict[str, Any]) -> list[tuple[str, str]]:
    """Declare entities only for explicitly mapped objects and feasible derivatives."""
    keys: list[tuple[str, str]] = []
    for obj, metrics in METRICS.items():
        settings = options.get(CONF_POWERTRAIN, {}).get(obj, {})
        configured = [name for name in metrics if settings.get(name)]
        if not configured:
            continue
        keys.extend((obj, name) for name in [*configured, "status"])
        if obj == "engine" and "rpm" in configured:
            keys.append((obj, "running"))
        if (
            obj == "fuel"
            and "level" in configured
            and (
                (capacity := finite_number(data.get(CONF_FUEL_TANK_CAPACITY)))
                is not None
                and capacity > 0
            )
        ):
            keys.append((obj, "remaining_volume"))
    return keys


class Readings:
    """Evaluate one object's profile-unit readings and retain valid observation ages."""

    def __init__(self, hass: HomeAssistant, entry: HavrvConfigEntry, obj: str) -> None:
        """Bind provider-neutral mappings to the current profile."""
        self.hass = hass
        self.entry = entry
        self.obj = obj
        self.settings = entry.options[CONF_POWERTRAIN][obj]
        self.units = entry.runtime_data.measurement_system
        self.last_observed: dict[str, str] = {}

    def reading(self, name: str) -> tuple[float | str | None, dict[str, Any]]:
        """Require a valid, fresh report; never use last_changed as observation time."""
        source = self.settings.get(name)
        state = self.hass.states.get(source) if source else None
        metadata: dict[str, Any] = {
            "source_entity_id": source,
            "status": "unknown" if source else "not_configured",
            "last_observed": self.last_observed.get(name),
            "source_reported": state.last_reported.isoformat() if state else None,
            "max_age": self.settings.get("max_age", DEFAULT_MAX_AGE),
            "profile_unit": METRICS[self.obj][name].unit(self.units),
        }
        for limit in LIMITS:
            if f"{name}_{limit}" in self.settings:
                metadata[limit] = self.settings[f"{name}_{limit}"]
        if state is None or state.state in ("unknown", "unavailable"):
            return None, metadata
        # Explicit observation timestamps, when present, must themselves be valid.
        observed: datetime | None = state.last_reported
        for key in ("last_observed", "source_reported"):
            if key in state.attributes:
                raw = state.attributes[key]
                observed = (
                    raw
                    if isinstance(raw, datetime)
                    else dt_util.parse_datetime(raw)
                    if isinstance(raw, str)
                    else None
                )
                break
        now = dt_util.utcnow()
        if observed is None or observed.tzinfo is None or observed > now:
            return None, metadata
        metric = METRICS[self.obj][name]
        value: float | str | None = state.state
        if metric != TEXT:
            numeric = finite_number(value)
            unit = state.attributes.get("unit_of_measurement")
            target = metric.unit(self.units)
            value = (
                convert_value(numeric, unit, target, metric)
                if numeric is not None and isinstance(unit, str) and target
                else None
            )
            if isinstance(value, float) and (
                metric == PERCENT
                and not 0 <= value <= 100
                or name in ("rpm", "rate")
                and value < 0
                or metric.metric_unit == "km/L"
                and value < 0
            ):
                value = None
        if value is None:
            return None, metadata
        self.last_observed[name] = observed.isoformat()
        metadata["last_observed"] = observed.isoformat()
        if (now - observed).total_seconds() > metadata["max_age"]:
            return None, metadata
        metadata["status"] = "ok"
        if isinstance(value, float):
            for severity in ("warning", "problem"):
                low, high = (
                    metadata.get(f"{severity}_low"),
                    metadata.get(f"{severity}_high"),
                )
                if (
                    low is not None
                    and value <= low
                    or high is not None
                    and value >= high
                ):
                    metadata["status"] = severity
        return value, metadata

    def derived_metadata(self, name: str, metadata: dict[str, Any]) -> dict[str, Any]:
        """Express derived limits in derived units, not the dependency's units."""
        result = dict(metadata)
        if name == "running":
            result["profile_unit"] = None
            for limit in LIMITS:
                result.pop(limit, None)
        else:
            result["profile_unit"] = "L" if self.units == UNIT_SYSTEM_METRIC else "gal"
            capacity = float(self.entry.data[CONF_FUEL_TANK_CAPACITY])
            for limit in LIMITS:
                if limit in result:
                    result[limit] *= capacity / 100
        return result


class HavrvPowertrainSensor(SensorEntity):
    """Expose direct readings independently of configured advisory severity."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _unrecorded_attributes = frozenset({"readings", "source_reported", "last_observed"})

    def __init__(self, readings: Readings, name: str) -> None:
        """Use stable identities across provider remapping."""
        self.readings = readings
        self.name_key = name
        entry, obj = readings.entry, readings.obj
        parent_device_id = entry.runtime_data.device_id
        if parent_device_id is None:
            raise RuntimeError("RV device must be registered before platform setup")
        self._attr_unique_id = f"{entry.entry_id}_powertrain_{obj}_{name}"
        self._attr_translation_key = f"powertrain_{obj}_{name}"
        info: DeviceInfo = {
            "identifiers": {(DOMAIN, f"{entry.entry_id}_powertrain_{obj}")},
            "name": obj.title(),
            "via_device_id": parent_device_id,
        }
        self._attr_device_info = info
        metric = METRICS[obj].get(name)
        if name == "remaining_volume":
            metric = Metric(
                "L", "gal", VolumeConverter, SensorDeviceClass.VOLUME_STORAGE
            )
        if metric and metric != TEXT:
            self._attr_native_unit_of_measurement = metric.unit(readings.units)
            self._attr_suggested_unit_of_measurement = metric.unit(readings.units)
            self._attr_device_class = metric.device_class
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif name in ("status", "running"):
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = (
                ["ok", "warning", "problem", "unknown", "not_configured"]
                if name == "status"
                else ["running", "stopped"]
            )

    def _result(self) -> tuple[float | str | None, dict[str, Any]]:
        """Share the same evaluation for values and their metadata."""
        if self.name_key == "status":
            channels = {
                name: self.readings.reading(name)[1]
                for name in METRICS[self.readings.obj]
            }
            statuses = {channel["status"] for channel in channels.values()}
            for obj, name in entity_keys(
                dict(self.readings.entry.options), dict(self.readings.entry.data)
            ):
                if obj != self.readings.obj:
                    continue
                dependency = {"running": "rpm", "remaining_volume": "level"}.get(name)
                if dependency:
                    channels[name] = self.readings.derived_metadata(
                        name, channels[dependency]
                    )
            status = next(
                (s for s in ("problem", "warning", "unknown", "ok") if s in statuses),
                "not_configured",
            )
            return status, {
                "status": status,
                "readings": channels,
                "missing_readings": [
                    name
                    for name, channel in channels.items()
                    if channel["status"] == "unknown"
                    and name in METRICS[self.readings.obj]
                ],
            }
        name = {"running": "rpm", "remaining_volume": "level"}.get(
            self.name_key, self.name_key
        )
        value, metadata = self.readings.reading(name)
        if value is not None and self.name_key == "running":
            value = "running" if float(value) > 0 else "stopped"
        elif value is not None and self.name_key == "remaining_volume":
            value = (
                float(value) * self.readings.entry.data[CONF_FUEL_TANK_CAPACITY] / 100
            )
        if self.name_key in ("running", "remaining_volume"):
            metadata = self.readings.derived_metadata(self.name_key, metadata)
        return value, metadata

    @property
    def native_value(self) -> float | str | None:
        """Return the valid direct reading or explicitly labeled derivative."""
        return self._result()[0]

    @property
    def available(self) -> bool:
        """Leave the aggregate available to explain invalid or missing readings."""
        return self.native_value is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose safe mapping/freshness/advisory metadata, not source attributes."""
        return self._result()[1]

    async def async_added_to_hass(self) -> None:
        """Track actual reports and timer expiry with entity-owned unload cleanup."""
        await super().async_added_to_hass()
        sources = [
            self.readings.settings[name]
            for name in METRICS[self.readings.obj]
            if self.readings.settings.get(name)
        ]
        if self.entity_id in sources:
            sources.remove(self.entity_id)
        if sources:
            self.async_on_remove(
                async_track_state_change_event(self.hass, sources, self._reported)
            )
            self.async_on_remove(
                async_track_state_report_event(self.hass, sources, self._reported)
            )
        self.async_on_remove(
            async_track_time_interval(self.hass, self._expired, timedelta(seconds=1))
        )
        if self.native_unit_of_measurement:
            defaults = self.get_initial_entity_options()
            assert defaults is not None
            er.async_get(self.hass).async_update_entity_options(
                self.entity_id, "sensor.private", defaults["sensor.private"]
            )
            self.async_registry_entry_updated()

    @callback
    def _reported(
        self, _event: Event[EventStateReportedData] | Event[EventStateChangedData]
    ) -> None:
        """Reevaluate unchanged but freshly reported source readings."""
        self.async_write_ha_state()

    @callback
    def _expired(self, _now: datetime) -> None:
        """Make still-present sources unavailable after the configured age."""
        self.async_write_ha_state()


def sensors(
    hass: HomeAssistant, entry: HavrvConfigEntry
) -> list[HavrvPowertrainSensor]:
    """Create only mapped powertrain objects; legacy entries remain unchanged."""
    objects: dict[str, Readings] = {}
    entities: list[HavrvPowertrainSensor] = []
    for obj, name in entity_keys(dict(entry.options), dict(entry.data)):
        if obj not in objects:
            objects[obj] = Readings(hass, entry, obj)
        entities.append(HavrvPowertrainSensor(objects[obj], name))
    return entities
