"""Tire topology and reading helpers."""

import math
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median
from typing import Any

from homeassistant.core import (
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    CONF_MAIN_REAR_WHEEL_CONFIGURATION,
    CONF_REAR_AXLE_COUNT,
    CONF_TAG_AXLE_PRESENT,
    CONF_TAG_AXLE_WHEEL_CONFIGURATION,
    CONF_TIRE_BATTERY_LOW,
    CONF_TIRE_ENTITY_MAPPINGS,
    CONF_TIRE_PRESSURE_THRESHOLDS,
    CONF_TIRE_TEMPERATURE_HIGH,
    DEFAULT_TIRE_BATTERY_LOW,
    DOMAIN,
    TIRE_AXLE,
    TIRE_BATTERY,
    TIRE_FRONT,
    TIRE_METRICS,
    TIRE_PRESSURE,
    TIRE_SOURCE_METRICS,
    TIRE_TAG,
    TIRE_TEMPERATURE,
    UNIT_SYSTEM_METRIC,
    WHEEL_CONFIGURATION_DUAL,
    WHEEL_CONFIGURATION_SINGLE,
)

TIRE_BATTERY_BOOLEAN_DOMAINS = ("binary_sensor", "input_boolean", "switch")


@dataclass(frozen=True)
class TirePosition:
    """A configured tire position on an RV."""

    key: str
    name: str
    group: str


@dataclass(frozen=True)
class TireMonitorGroup:
    """Tire positions analyzed together."""

    key: str
    name: str
    positions: tuple[TirePosition, ...]


class TireMonitorHistory:
    """Track recent normalized values for each tire in one monitor group."""

    _WINDOW = timedelta(hours=12)
    _MIN_SAMPLES = 3
    _OUTLIER_THRESHOLD = 3.5

    def __init__(self) -> None:
        """Initialize empty per-tire histories."""
        self._samples: dict[str, deque[tuple[datetime, float]]] = {}

    def record(self, position: TirePosition, now: datetime, value: float) -> None:
        """Record a reading and discard samples outside the rolling window."""
        samples = self._samples.setdefault(position.key, deque())
        samples.append((now, value))
        cutoff = now - self._WINDOW
        while samples and samples[0][0] < cutoff:
            samples.popleft()

    def can_analyze(
        self,
        readings: list[tuple[TirePosition, float]],
        now: datetime,
    ) -> bool:
        """Return whether two current readings have enough prior samples."""
        return (
            sum(self._baseline(position, now) is not None for position, _ in readings)
            >= 2
        )

    def outlier(
        self,
        readings: list[tuple[TirePosition, float]],
        now: datetime,
    ) -> str | None:
        """Identify a unique tire that deviates from its own recent baseline."""
        candidates = []
        for position, value in readings:
            if (baseline := self._baseline(position, now)) is None:
                continue
            center = median(baseline)
            mad = median(abs(sample - center) for sample in baseline)
            deviation = abs(value - center)
            score = (
                float("inf")
                if mad == 0 and deviation > 0
                else 0.0
                if mad == 0
                else 0.6745 * deviation / mad
            )
            if score > self._OUTLIER_THRESHOLD:
                candidates.append(position.name)

        if len(candidates) == 1:
            return candidates[0]
        return "No outlier"

    def _baseline(self, position: TirePosition, now: datetime) -> list[float] | None:
        """Return recent prior samples, excluding the latest reading."""
        samples = self._samples.get(position.key)
        if samples is None:
            return None
        cutoff = now - self._WINDOW
        baseline = [value for sample_time, value in samples if sample_time >= cutoff]
        if baseline:
            baseline.pop()
        if len(baseline) < self._MIN_SAMPLES:
            return None
        return baseline


class HavrvTireEntity(Entity):
    """Base entity associated with a configured RV tire."""

    _attr_has_entity_name = True

    def __init__(self, entry: Any, position: TirePosition) -> None:
        """Initialize a tire entity and its stable device association."""
        self._entry = entry
        self._position = position
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{entry.entry_id}_tire_{position.key}")},
            "name": position.name,
            "via_device_id": entry.runtime_data.device_id,
        }

    @property
    def _source_entity_ids(self) -> list[str]:
        """Return all configured source sensors for this tire."""
        mappings = self._entry.options.get(CONF_TIRE_ENTITY_MAPPINGS, {})
        return list(
            dict.fromkeys(
                mappings[key]
                for metric in TIRE_SOURCE_METRICS
                if (key := tire_entity_key(self._position, metric)) in mappings
            )
        )

    @callback
    def async_on_source_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Write the tire state when one of its source sensors changes."""
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Subscribe to source sensor state changes."""
        await super().async_added_to_hass()
        if self._source_entity_ids:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass,
                    self._source_entity_ids,
                    self.async_on_source_state_changed,
                )
            )

    def _source_state(self, metric: str) -> State | None:
        """Return the configured source state for one tire metric."""
        entity_id = source_entity_id(self._entry, self._position, metric)
        return None if entity_id is None else self.hass.states.get(entity_id)

    def _source_attributes(self, metric: str) -> dict[str, Any]:
        """Return the configured source attributes for one tire metric."""
        state = self._source_state(metric)
        return {} if state is None else state.attributes


def tire_positions(profile: Mapping[str, Any]) -> list[TirePosition]:
    """Build stable tire positions from the configured axle and wheel layout."""
    rear_axle_count = profile.get(CONF_REAR_AXLE_COUNT)
    has_tag_axle = profile.get(CONF_TAG_AXLE_PRESENT, False)
    if rear_axle_count is None and has_tag_axle:
        rear_axle_count = 1
    if rear_axle_count is None:
        return []

    positions = _axle_positions("front", "Front", TIRE_FRONT, False)
    drive_axle_count = rear_axle_count - int(has_tag_axle)
    wheel_configuration = profile.get(CONF_MAIN_REAR_WHEEL_CONFIGURATION)
    if drive_axle_count > 0 and wheel_configuration in (
        WHEEL_CONFIGURATION_SINGLE,
        WHEEL_CONFIGURATION_DUAL,
    ):
        for axle_number in range(1, drive_axle_count + 1):
            positions.extend(
                _axle_positions(
                    f"rear_axle_{axle_number}",
                    f"Rear Axle {axle_number}",
                    TIRE_AXLE,
                    wheel_configuration == WHEEL_CONFIGURATION_DUAL,
                )
            )

    if has_tag_axle:
        tag_wheels = profile.get(CONF_TAG_AXLE_WHEEL_CONFIGURATION)
        if tag_wheels in (WHEEL_CONFIGURATION_SINGLE, WHEEL_CONFIGURATION_DUAL):
            positions.extend(
                _axle_positions(
                    "tag_axle",
                    "Tag Axle",
                    TIRE_TAG,
                    tag_wheels == WHEEL_CONFIGURATION_DUAL,
                )
            )
    return positions


def tire_monitor_groups(profile: dict[str, Any], metric: str) -> list[TireMonitorGroup]:
    """Build axle-specific and all-tire comparison groups."""
    if metric not in (TIRE_PRESSURE, TIRE_TEMPERATURE):
        raise ValueError(f"Unsupported tire monitor metric: {metric}")

    axles: dict[str, list[TirePosition]] = {}
    all_positions = tire_positions(profile)
    for position in all_positions:
        axle_key = _axle_key(position)
        axles.setdefault(axle_key, []).append(position)

    groups: list[TireMonitorGroup] = []
    for axle_key, axle_positions in axles.items():
        axle_name = _axle_name(axle_key)
        if metric == TIRE_TEMPERATURE and any(
            position.key.endswith(("_inner", "_outer")) for position in axle_positions
        ):
            for wheel in ("inner", "outer"):
                wheel_positions = tuple(
                    position
                    for position in axle_positions
                    if position.key.endswith(f"_{wheel}")
                )
                if wheel_positions:
                    groups.append(
                        TireMonitorGroup(
                            key=f"{axle_key}_{wheel}",
                            name=f"{axle_name} {wheel} tires",
                            positions=wheel_positions,
                        )
                    )
        else:
            groups.append(
                TireMonitorGroup(
                    key=axle_key,
                    name=axle_name,
                    positions=tuple(axle_positions),
                )
            )
    if all_positions:
        groups.append(
            TireMonitorGroup(
                key="all_tires",
                name="All tires",
                positions=tuple(all_positions),
            )
        )
    return groups


def tire_monitor_readings(
    hass: HomeAssistant,
    entry: Any,
    group: TireMonitorGroup,
    metric: str,
) -> list[tuple[TirePosition, float]]:
    """Read comparable, normalized values for one monitor group."""
    readings = []
    for position in group.positions:
        if (value := _source_value(hass, entry, position, metric)) is not None:
            readings.append((position, value))
    return readings


def tire_monitor_spread(
    hass: HomeAssistant,
    entry: Any,
    group: TireMonitorGroup,
    metric: str,
) -> float | None:
    """Return the max-minus-min spread when at least two readings are usable."""
    values = [value for _, value in tire_monitor_readings(hass, entry, group, metric)]
    if len(values) < 2:
        return None
    return max(values) - min(values)


def _axle_key(position: TirePosition) -> str:
    """Return the stable axle prefix from a generated tire position."""
    if position.key.startswith("front_"):
        return "front"
    if position.key.startswith("tag_axle_"):
        return "tag_axle"
    return "_".join(position.key.split("_")[:3])


def _axle_name(axle_key: str) -> str:
    """Return a human-readable name for a stable axle key."""
    if axle_key == "front":
        return "Front axle"
    if axle_key == "tag_axle":
        return "Tag axle"
    return f"Rear axle {axle_key.removeprefix('rear_axle_')}"


def _axle_positions(key: str, name: str, group: str, dual: bool) -> list[TirePosition]:
    """Create left/right positions, including inner and outer dual wheels."""
    tires = []
    for side in ("left", "right"):
        if dual:
            for wheel in ("inner", "outer"):
                tires.append(
                    TirePosition(
                        key=f"{key}_{side}_{wheel}",
                        name=f"{name} {side.title()} {wheel.title()} Tire",
                        group=group,
                    )
                )
        else:
            tires.append(
                TirePosition(
                    key=f"{key}_{side}",
                    name=f"{name} {side.title()} Tire",
                    group=group,
                )
            )
    return tires


def tire_entity_key(position: TirePosition, metric: str) -> str:
    """Return the options-flow key for a tire's source entity."""
    return f"{position.key}_{metric}"


def source_entity_id(entry: Any, position: TirePosition, metric: str) -> str | None:
    """Return the configured source entity for a tire metric."""
    mappings = entry.options.get(CONF_TIRE_ENTITY_MAPPINGS, {})
    entity_id = mappings.get(tire_entity_key(position, metric))
    return entity_id if isinstance(entity_id, str) else None


def is_boolean_battery_source(entry: Any, position: TirePosition) -> bool:
    """Return whether the battery mapping supplies an on/off health status."""
    entity_id = source_entity_id(entry, position, TIRE_BATTERY)
    return (
        entity_id is not None
        and entity_id.partition(".")[0] in TIRE_BATTERY_BOOLEAN_DOMAINS
    )


def configured_threshold(
    entry: Any, position: TirePosition, threshold: str
) -> float | None:
    """Return a pressure threshold for the position's axle group."""
    thresholds = entry.options.get(CONF_TIRE_PRESSURE_THRESHOLDS, {})
    value = thresholds.get(position.group, {}).get(threshold)
    return None if value is None else float(value)


def _numeric_state(hass: HomeAssistant, entity_id: str | None) -> float | None:
    """Read a numeric, available state from Home Assistant."""
    if entity_id is None:
        return None
    state = hass.states.get(entity_id)
    if state is None or state.state in ("unknown", "unavailable"):
        return None
    try:
        value = float(state.state)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def tire_data_present(hass: HomeAssistant, entry: Any, position: TirePosition) -> bool:
    """Return whether all three configured source readings are available."""
    return all(
        (entity_id := source_entity_id(entry, position, metric)) is not None
        and (
            tire_problem(hass, entry, position, metric) is not None
            if metric == TIRE_BATTERY and is_boolean_battery_source(entry, position)
            else _numeric_state(hass, entity_id) is not None
        )
        for metric in TIRE_METRICS
    )


def pressure_in_profile_units(
    value: float, unit: str | None, measurement_system: str
) -> float | None:
    """Convert pressure to the profile's configured unit."""
    if unit is None:
        return value
    normalized_unit = unit.casefold()
    if measurement_system == UNIT_SYSTEM_METRIC:
        if normalized_unit in ("kpa", "kilopascals"):
            return value
        if normalized_unit in (
            "psi",
            "pound per square inch",
            "pounds per square inch",
        ):
            return value * 6.894757293168
        if normalized_unit == "bar":
            return value * 100
    else:
        if normalized_unit in (
            "psi",
            "pound per square inch",
            "pounds per square inch",
        ):
            return value
        if normalized_unit in ("kpa", "kilopascals"):
            return value / 6.894757293168
        if normalized_unit == "bar":
            return value * 14.503773773
    return None


def temperature_in_profile_units(
    value: float, unit: str | None, measurement_system: str
) -> float | None:
    """Convert temperature to the profile's configured unit."""
    if unit is None:
        return value
    normalized_unit = unit.casefold()
    if measurement_system == UNIT_SYSTEM_METRIC:
        if normalized_unit in ("°c", "c", "°celsius", "celsius"):
            return value
        if normalized_unit in ("°f", "f", "°fahrenheit", "fahrenheit"):
            return (value - 32) * 5 / 9
    else:
        if normalized_unit in ("°f", "f", "°fahrenheit", "fahrenheit"):
            return value
        if normalized_unit in ("°c", "c", "°celsius", "celsius"):
            return value * 9 / 5 + 32
    return None


def tire_trend_reading(
    hass: HomeAssistant, entry: Any, position: TirePosition
) -> tuple[float, float | None] | None:
    """Return the pressure and optional temperature in profile units."""
    pressure = _source_value(hass, entry, position, TIRE_PRESSURE)
    if pressure is None:
        return None
    return pressure, _source_value(hass, entry, position, TIRE_TEMPERATURE)


def _source_value(
    hass: HomeAssistant, entry: Any, position: TirePosition, metric: str
) -> float | None:
    """Read and normalize one numeric tire measurement."""
    entity_id = source_entity_id(entry, position, metric)
    value = _numeric_state(hass, entity_id)
    if value is None or entity_id is None:
        return None
    state = hass.states.get(entity_id)
    unit = state.attributes.get("unit_of_measurement") if state else None
    if metric == TIRE_PRESSURE:
        return pressure_in_profile_units(
            value,
            unit,
            entry.runtime_data.measurement_system,
        )
    if metric == TIRE_TEMPERATURE:
        return temperature_in_profile_units(
            value,
            unit,
            entry.runtime_data.measurement_system,
        )
    if unit is not None and unit != "%":
        return None
    return value


def tire_problem(
    hass: HomeAssistant,
    entry: Any,
    position: TirePosition,
    problem: str,
) -> bool | None:
    """Return whether a configured tire limit is crossed."""
    if problem not in TIRE_METRICS:
        raise ValueError(f"Unsupported tire problem type: {problem}")
    if problem == TIRE_BATTERY and is_boolean_battery_source(entry, position):
        entity_id = source_entity_id(entry, position, TIRE_BATTERY)
        state = hass.states.get(entity_id) if entity_id is not None else None
        if state is None or state.state not in ("on", "off"):
            return None
        alarm_source = (
            entity_id is not None
            and entity_id.startswith("binary_sensor.")
            and state.attributes.get("device_class") in ("battery", "problem")
        )
        return state.state == ("on" if alarm_source else "off")
    value = _source_value(hass, entry, position, problem)
    if value is None:
        return None

    if problem == TIRE_PRESSURE:
        low = configured_threshold(entry, position, "low")
        high = configured_threshold(entry, position, "high")
        if low is None or high is None:
            return None
        return value < low or value > high
    if problem == TIRE_TEMPERATURE:
        high = entry.options.get(CONF_TIRE_TEMPERATURE_HIGH)
        if high is None:
            return None
        return value > float(high)
    if problem == TIRE_BATTERY:
        low = entry.options.get(CONF_TIRE_BATTERY_LOW)
        if low is None:
            low = DEFAULT_TIRE_BATTERY_LOW
        return value < float(low)
    return None


def overall_tire_problem(
    hass: HomeAssistant, entry: Any, position: TirePosition
) -> bool:
    """Treat missing readings, invalid units, and configured limits as a problem."""
    if not tire_data_present(hass, entry, position):
        return True
    for problem in TIRE_METRICS:
        status = tire_problem(hass, entry, position, problem)
        if status is True:
            return True
        if status is None and _has_threshold(entry, position, problem):
            return True
    return False


def _has_threshold(entry: Any, position: TirePosition, problem: str) -> bool:
    """Return whether this tire problem has a configured limit."""
    if problem == TIRE_PRESSURE:
        return (
            configured_threshold(entry, position, "low") is not None
            and configured_threshold(entry, position, "high") is not None
        )
    if problem == TIRE_TEMPERATURE:
        return entry.options.get(CONF_TIRE_TEMPERATURE_HIGH) is not None
    return problem == TIRE_BATTERY
