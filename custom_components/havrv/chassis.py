"""Observed chassis counters and persistent, sparse trailing-window history."""

from __future__ import annotations

import logging
from asyncio import Handle
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.core import (
    Event,
    EventStateChangedData,
    EventStateReportedData,
    HomeAssistant,
    callback,
)
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_state_report_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import (
    BaseUnitConverter,
    DistanceConverter,
    DurationConverter,
    VolumeConverter,
)

from .const import (
    CHASSIS_METRICS,
    CONF_CHASSIS_SOURCES,
    DOMAIN,
    UNIT_SYSTEM_METRIC,
)
from .operations import finite_number

if TYPE_CHECKING:
    from . import HavrvConfigEntry

_LOGGER = logging.getLogger(__name__)
WINDOWS = {
    "5m": 300,
    "1h": 3600,
    "8h": 28800,
    "1d": 86400,
    "7d": 604800,
    "30d": 2592000,
}
PERIODS = ("latest", *WINDOWS)
DEPENDENCIES = {
    "distance": ("distance",),
    "fuel": ("fuel",),
    "engine_hours": ("engine_hours",),
    "fuel_rate": ("fuel", "engine_hours"),
    "economy": ("distance", "fuel"),
}
_COUNTER_UNITS: dict[str, tuple[type[BaseUnitConverter], str]] = {
    "distance": (DistanceConverter, "km"),
    "fuel": (VolumeConverter, "L"),
    "engine_hours": (DurationConverter, "h"),
}
_MAX_SAMPLES = 100000


def storage_key(entry_id: str) -> str:
    """Return the private history key for one RV."""
    return f"{DOMAIN}.chassis.{entry_id}"


def chassis_entity_keys(sources: dict[str, str]) -> list[tuple[str, str]]:
    """Declare only readings whose required counter sources are configured."""
    return [
        *((metric, "total") for metric in CHASSIS_METRICS if sources.get(metric)),
        *(
            (metric, period)
            for metric, required in DEPENDENCIES.items()
            if all(sources.get(key) for key in required)
            for period in PERIODS
        ),
    ]


@dataclass
class CounterSample:
    """Counter endpoints observed together, always in canonical km/L/h units."""

    time: float
    values: dict[str, float]

    def as_dict(self) -> dict[str, Any]:
        """Serialize without sharing the mutable values with a pending save."""
        return {"time": self.time, "values": dict(self.values)}


@dataclass(frozen=True)
class CounterChange:
    """Matched historical endpoints, never extrapolated through a source gap."""

    start: CounterSample
    end: CounterSample

    @property
    def duration(self) -> float:
        """Return elapsed observed interval seconds, not engine operating time."""
        return self.end.time - self.start.time

    def delta(self, metric: str) -> float:
        """Return the source-owned cumulative increase over this interval."""
        return self.end.values[metric] - self.start.values[metric]


def profile_value(value: float, metric: str, measurement_system: str) -> float:
    """Convert canonical counters independently of source or HA display units."""
    if measurement_system == UNIT_SYSTEM_METRIC or metric == "engine_hours":
        return value
    converter, unit = _COUNTER_UNITS[metric]
    return converter.convert(value, unit, "mi" if metric == "distance" else "gal")


def change_value(
    change: CounterChange | None, metric: str, measurement_system: str
) -> float | None:
    """Derive only defined ratios of matched counter increases."""
    if change is None:
        return None
    if metric in CHASSIS_METRICS:
        value = profile_value(change.delta(metric), metric, measurement_system)
    else:
        fuel = profile_value(change.delta("fuel"), "fuel", measurement_system)
        denominator = (
            change.delta("engine_hours")
            if metric == "fuel_rate"
            else profile_value(change.delta("distance"), "distance", measurement_system)
            if measurement_system == UNIT_SYSTEM_METRIC
            else fuel
        )
        numerator = (
            fuel
            if metric == "fuel_rate"
            else fuel * 100
            if measurement_system == UNIT_SYSTEM_METRIC
            else profile_value(change.delta("distance"), "distance", measurement_system)
        )
        if denominator <= 0:
            return None
        value = numerator / denominator
    return finite_number(value)


def _restore_sample(raw: Any, now: float) -> CounterSample:
    """Reject corrupt history explicitly rather than manufacturing a baseline."""
    if not isinstance(raw, dict) or not isinstance(raw.get("values"), dict):
        raise ValueError("invalid counter sample")
    time = finite_number(raw.get("time"))
    if time is None or time < 0 or time > now:
        raise ValueError("invalid counter timestamp")
    values: dict[str, float] = {}
    for metric, raw_value in raw["values"].items():
        value = finite_number(raw_value)
        if metric not in CHASSIS_METRICS or value is None or value < 0:
            raise ValueError("invalid counter value")
        values[metric] = value
    return CounterSample(time, values)


class ChassisHistory:
    """Collect real reports, retain gaps, and publish shared historical results."""

    def __init__(self, hass: HomeAssistant, entry: HavrvConfigEntry) -> None:
        """Initialize a bounded history tied to source mappings, not display units."""
        self.hass = hass
        self.entry = entry
        self.sources: dict[str, str] = dict(entry.options.get(CONF_CHASSIS_SOURCES, {}))
        self.signal = f"{DOMAIN}_chassis_{entry.entry_id}"
        self.store = Store[dict[str, Any]](hass, 1, storage_key(entry.entry_id))
        self.samples: deque[CounterSample] = deque()
        self.recent: dict[str, list[CounterSample]] = {}
        self.current: dict[str, float] = {}
        self.last_valid: dict[str, CounterSample] = {}
        self._pending: Handle | None = None
        self._cache: dict[tuple[str, str], CounterChange | None] = {}
        self._trends: dict[str, list[tuple[float, float | None]]] = {}

    async def async_setup(self) -> None:
        """Restore matching source histories before subscribing to real reports."""
        now = dt_util.utcnow().timestamp()
        if not self.sources:
            await self.store.async_remove()
            return
        saved = await self.store.async_load()
        if saved is not None:
            try:
                if not isinstance(saved, dict) or not all(
                    isinstance(saved.get(key), expected)
                    for key, expected in (
                        ("sources", dict),
                        ("samples", list),
                        ("recent", dict),
                        ("last_valid", dict),
                    )
                ):
                    raise ValueError("invalid saved history structure")
                self.samples = deque(
                    _restore_sample(raw, now) for raw in saved["samples"]
                )
                if any(
                    a.time >= b.time
                    for a, b in zip(self.samples, list(self.samples)[1:], strict=False)
                ):
                    raise ValueError("unordered counter history")
                self.recent = {
                    metric: [_restore_sample(raw, now) for raw in pair]
                    for metric, pair in saved["recent"].items()
                    if metric in DEPENDENCIES
                }
                self.last_valid = {
                    metric: _restore_sample(raw, now)
                    for metric, raw in saved["last_valid"].items()
                    if metric in CHASSIS_METRICS
                }
                if any(
                    metric not in sample.values
                    for metric, sample in self.last_valid.items()
                ):
                    raise ValueError("invalid retained counter")
                if any(
                    len(pair) > 2
                    or len(pair) == 2
                    and pair[0].time >= pair[1].time
                    or any(
                        not all(key in sample.values for key in DEPENDENCIES[metric])
                        for sample in pair
                    )
                    for metric, pair in self.recent.items()
                ):
                    raise ValueError("invalid latest interval")
            except (KeyError, TypeError, ValueError) as err:
                _LOGGER.warning("Unable to restore chassis history: %s", err)
                self.samples.clear()
                self.recent.clear()
                self.last_valid.clear()
            else:
                for metric in CHASSIS_METRICS:
                    if saved["sources"].get(metric) != self.sources.get(metric):
                        self._clear_metric(metric)
        self.capture()
        self.entry.async_on_unload(self._cancel_capture)
        ids = list(set(self.sources.values()))
        self.entry.async_on_unload(
            async_track_state_change_event(self.hass, ids, self._source_changed)
        )
        self.entry.async_on_unload(
            async_track_state_report_event(self.hass, ids, self._source_reported)
        )
        self.entry.async_on_unload(
            async_track_time_interval(self.hass, self._tick, timedelta(minutes=1))
        )

    def read_sources(self) -> dict[str, float]:
        """Require nonnegative, finite, unit-bearing numeric sources."""
        values: dict[str, float] = {}
        registry = er.async_get(self.hass)
        for metric, entity_id in self.sources.items():
            registered = registry.async_get(entity_id)
            if (
                registered is not None
                and registered.platform == DOMAIN
                and "_chassis_counter_" in registered.unique_id
            ):
                continue
            state = self.hass.states.get(entity_id)
            if state is None:
                continue
            value = finite_number(state.state)
            converter, target = _COUNTER_UNITS[metric]
            unit = state.attributes.get("unit_of_measurement")
            if (
                value is None
                or value < 0
                or not isinstance(unit, str)
                or unit not in converter.VALID_UNITS
            ):
                continue
            converted = finite_number(converter.convert(value, unit, target))
            if converted is not None:
                values[metric] = converted
        return values

    def _clear_metric(self, metric: str) -> None:
        """Invalidate only a reset/remapped counter and its dependent results."""
        for sample in self.samples:
            sample.values.pop(metric, None)
        self.last_valid.pop(metric, None)
        for key in list(self.recent):
            if metric in DEPENDENCIES[key]:
                del self.recent[key]

    @callback
    def capture(self) -> None:
        """Observe source endpoints; an unavailable interval is never zero-filled."""
        now = dt_util.utcnow().timestamp()
        self.current = values = self.read_sources()
        for metric, value in values.items():
            previous = self.last_valid.get(metric)
            if previous is not None and value < previous.values[metric]:
                self._clear_metric(metric)
        sample = CounterSample(now, dict(values))
        reports: dict[str, float] = {}
        for metric, value in values.items():
            state = self.hass.states.get(self.sources[metric])
            assert state is not None
            time = state.last_reported.timestamp()
            reports[metric] = time
            self.last_valid[metric] = CounterSample(time, {metric: value})
        if not self.samples or now > self.samples[-1].time:
            # Keep first/last reports per minute without discarding availability gaps.
            if (
                len(self.samples) >= 2
                and int(self.samples[-2].time // 60) == int(now // 60)
                and self.samples[-2].values.keys()
                == self.samples[-1].values.keys()
                == values.keys()
            ):
                self.samples.pop()
            self.samples.append(sample)
        for metric, required in DEPENDENCIES.items():
            if not all(key in values for key in required):
                continue
            pair = self.recent.setdefault(metric, [])
            if not pair:
                pair.append(sample)
            elif now > pair[-1].time and all(
                reports[key] > pair[-1].time for key in required
            ):
                pair.append(sample)
                del pair[:-2]
        self._prune(now)
        self._cache.clear()
        self._trends.clear()
        self.store.async_delay_save(self._serialize, 60)
        async_dispatcher_send(self.hass, self.signal)

    @callback
    def _source_changed(self, _event: Event[EventStateChangedData]) -> None:
        """Capture changed, unavailable and removed sources."""
        self._schedule_capture()

    @callback
    def _source_reported(self, _event: Event[EventStateReportedData]) -> None:
        """Capture unchanged valid reports as observations, not invented samples."""
        self._schedule_capture()

    @callback
    def _schedule_capture(self) -> None:
        """Coalesce a batch of related counter reports into one coherent snapshot."""
        if self._pending is None:
            self._pending = self.hass.loop.call_soon(self._capture_pending)

    @callback
    def _capture_pending(self) -> None:
        """Read every updated input after the current source-event batch."""
        self._pending = None
        self.capture()

    @callback
    def _cancel_capture(self) -> None:
        """Do not leave a scheduled history write behind after unloading."""
        if self._pending is not None:
            self._pending.cancel()
            self._pending = None

    @callback
    def _tick(self, _now: datetime) -> None:
        """Expire trailing windows without extending a stale reading to the present."""
        self._prune(dt_util.utcnow().timestamp())
        self._cache.clear()
        self._trends.clear()
        async_dispatcher_send(self.hass, self.signal)

    def _prune(self, now: float) -> None:
        """Bound persisted history by age and count even with noisy source gaps."""
        cutoff = now - WINDOWS["30d"]
        while self.samples and (
            self.samples[0].time < cutoff or len(self.samples) > _MAX_SAMPLES
        ):
            self.samples.popleft()

    def change(self, metric: str, period: str) -> CounterChange | None:
        """Use real matched endpoints inside the requested window, allowing partials."""
        key = metric, period
        if key in self._cache:
            return self._cache[key]
        if period == "latest":
            samples = self.recent.get(metric, [])
        else:
            cutoff = dt_util.utcnow().timestamp() - WINDOWS[period]
            required = DEPENDENCIES[metric]
            samples = [
                sample
                for sample in self.samples
                if sample.time >= cutoff and all(k in sample.values for k in required)
            ]
        result = (
            CounterChange(samples[0], samples[-1])
            if len(samples) >= 2 and samples[-1].time > samples[0].time
            else None
        )
        self._cache[key] = result
        return result

    def _serialize(self) -> dict[str, Any]:
        """Save only this RV's source mappings and observed canonical counters."""
        return {
            "sources": self.sources,
            "samples": [sample.as_dict() for sample in self.samples],
            "recent": {
                metric: [sample.as_dict() for sample in pair]
                for metric, pair in self.recent.items()
            },
            "last_valid": {
                metric: sample.as_dict() for metric, sample in self.last_valid.items()
            },
        }

    def trend(self, metric: str) -> list[tuple[float, float | None]]:
        """Bound an eight-hour 5m-delta trace while preserving unavailable breaks."""
        if metric in self._trends:
            return self._trends[metric]
        cutoff = dt_util.utcnow().timestamp() - WINDOWS["8h"]
        required = DEPENDENCIES[metric]
        window: deque[CounterSample] = deque()
        buckets: dict[int, tuple[tuple[float, float | None], float | None]] = {}
        for sample in self.samples:
            if sample.time < cutoff - WINDOWS["5m"]:
                continue
            while window and window[0].time < sample.time - WINDOWS["5m"]:
                window.popleft()
            if not all(key in sample.values for key in required):
                window.clear()
                value = None
            else:
                window.append(sample)
                change = CounterChange(window[0], sample) if len(window) >= 2 else None
                value = change_value(
                    change, metric, self.entry.runtime_data.measurement_system
                )
            if sample.time < cutoff:
                continue
            bucket = int(sample.time // 600)
            previous = buckets.get(bucket)
            gap = previous[1] if previous is not None else None
            if value is None and gap is None:
                gap = sample.time
            buckets[bucket] = ((sample.time, value), gap)
        points: list[tuple[float, float | None]] = []
        for point, gap in buckets.values():
            if gap is not None and gap < point[0]:
                points.append((gap, None))
            points.append(point)
        self._trends[metric] = points
        return points

    async def async_save(self) -> None:
        """Flush pending observations on successful config-entry unload."""
        await self.store.async_save(self._serialize())
