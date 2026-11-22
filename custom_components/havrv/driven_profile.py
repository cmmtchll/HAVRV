"""Private sampled routes; distance/economy correlations are observational only."""

from __future__ import annotations

import math
from asyncio import Lock, Task, current_task, sleep
from collections.abc import Callable
from copy import deepcopy
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from homeassistant.const import (
    EVENT_HOMEASSISTANT_STOP,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_state_report_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import DistanceConverter, VolumeConverter

from .chassis import profile_value
from .const import CONF_CHASSIS_SOURCES, CONF_OPERATIONS_SOURCES, DOMAIN
from .operations import finite_number

if TYPE_CHECKING:
    from . import HavrvConfigEntry

RANGES = {"1h": 3600, "8h": 28800, "1d": 86400}
SAMPLE_SECONDS = 60
FRESH_SECONDS = 180
MAX_ENDPOINT_SKEW_SECONDS = 5
MAX_POINTS = 2000
MAX_HISTORY = 4000
MAX_TRIPS = 20
MAX_NAME = 80
MAX_SOURCE_IDS = 128
CHANNELS = ("latitude", "longitude", "elevation", "odometer", "fuel")
OUTPUT_KEYS = {
    "location": ("device_tracker", "operations_location"),
    "elevation": ("sensor", "operations_altitude"),
    "odometer": ("sensor", "chassis_counter_distance_total"),
    "fuel": ("sensor", "chassis_counter_fuel_total"),
}


def storage_key(entry_id: str) -> str:
    """Keep coordinates local to HA's private storage, never Recorder/diagnostics."""
    return f"{DOMAIN}.driven_profile.{entry_id}"


def horizontal_distance(a: dict[str, Any], b: dict[str, Any]) -> float:
    """Return haversine sampled-polyline km, not road distance or odometer truth."""
    lat1, lat2 = math.radians(a["latitude"]), math.radians(b["latitude"])
    dlat = lat2 - lat1
    dlon = math.radians(b["longitude"] - a["longitude"])
    hav = math.sin(dlat / 2) ** 2 + (
        math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1, max(0, hav))))


def _gap(time: float) -> dict[str, Any]:
    """Represent a discontinuity explicitly for every independently plotted channel."""
    return {"time": time, **dict.fromkeys(CHANNELS), "reports": {}}


def _restore_points(raw: Any, now: float, maximum: int) -> list[dict[str, Any]]:
    """Reject corrupt private history instead of silently returning empty success."""
    if not isinstance(raw, list) or len(raw) > maximum:
        raise ValueError("Invalid driven-profile sample list")
    previous = -1.0
    result = []
    for point in raw:
        if not isinstance(point, dict) or not isinstance(point.get("reports"), dict):
            raise ValueError("Invalid driven-profile sample")
        time = finite_number(point.get("time"))
        if time is None or time < 0 or not previous <= time <= now:
            raise ValueError("Invalid driven-profile timestamp order")
        previous = time
        sample = _gap(time)
        for key in CHANNELS:
            if key not in point:
                raise ValueError("Missing driven-profile channel")
            value = point[key]
            if value is not None:
                value = finite_number(value)
                if value is None:
                    raise ValueError("Invalid driven-profile value")
                if key in ("odometer", "fuel") and value < 0:
                    raise ValueError("Invalid driven-profile counter")
                if key == "latitude" and not -90 <= value <= 90:
                    raise ValueError("Invalid latitude")
                if key == "longitude" and not -180 <= value <= 180:
                    raise ValueError("Invalid longitude")
            sample[key] = value
        if (sample["latitude"] is None) != (sample["longitude"] is None):
            raise ValueError("Incomplete driven-profile fix")
        for key, value in point["reports"].items():
            report = finite_number(value)
            if key not in CHANNELS or report is None or not 0 <= report <= time:
                raise ValueError("Invalid driven-profile report time")
            sample["reports"][key] = report
        if any(
            sample[key] is not None and key not in sample["reports"] for key in CHANNELS
        ):
            raise ValueError("Missing driven-profile report time")
        result.append(sample)
    return result


class DrivenProfile:
    """Event-driven bounded route history and independent manually captured trips."""

    def __init__(self, hass: HomeAssistant, entry: HavrvConfigEntry) -> None:
        """Initialize canonical km/metres/litres storage, not display-unit storage."""
        self.hass = hass
        self.entry = entry
        operations = entry.options.get(CONF_OPERATIONS_SOURCES, {})
        chassis = entry.options.get(CONF_CHASSIS_SOURCES, {})
        self.sources = {
            key: value
            for key, value in {
                "location": operations.get("location"),
                "elevation": operations.get("altitude"),
                "odometer": chassis.get("distance"),
                "fuel": chassis.get("fuel"),
            }.items()
            if value
        }
        self.source_ids = set(self.sources.values())
        self.admin_only = False
        self.store = Store[dict[str, Any]](hass, 1, storage_key(entry.entry_id))
        self.samples: list[dict[str, Any]] = []
        self.trips: list[dict[str, Any]] = []
        self.active: dict[str, Any] | None = None
        self.error: str | None = None
        self._pending: Task[None] | None = None
        self._lock = Lock()
        self.outputs: dict[str, str] = {}
        self._subscriptions: list[Callable[[], None]] = []

    async def async_setup(self) -> None:
        """Restore local history and force a gap across reload/restart/remapping."""
        now = dt_util.utcnow().timestamp()
        try:
            saved = await self.store.async_load()
            if saved is not None:
                self._restore(saved, now)
        except (ValueError, TypeError, KeyError) as err:
            self.error = f"Unable to restore driven-profile history: {err}"
            # Do not overwrite corrupt storage with success-shaped empty history.
            return
        self._subscribe_outputs()
        if self.samples or self.active:
            self._append(_gap(now))
        self.capture()
        self.entry.async_on_unload(
            self.hass.bus.async_listen(
                er.EVENT_ENTITY_REGISTRY_UPDATED, self._registry_updated
            )
        )
        self.entry.async_on_unload(
            async_track_time_interval(
                self.hass, self._tick, timedelta(seconds=60), cancel_on_shutdown=True
            )
        )
        self.entry.async_on_unload(
            self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self._stop)
        )
        self.entry.async_on_unload(self._cancel)

    @callback
    def _subscribe_outputs(self) -> None:
        """Resolve this entry's stable HAVRV outputs, never raw sources."""
        for unsubscribe in self._subscriptions:
            unsubscribe()
        self._subscriptions.clear()
        registry = er.async_get(self.hass)
        self.outputs = {}
        for key in self.sources:
            domain, suffix = OUTPUT_KEYS[key]
            entity_id = registry.async_get_entity_id(
                domain, DOMAIN, f"{self.entry.entry_id}_{suffix}"
            )
            registered = registry.async_get(entity_id) if entity_id else None
            if (
                registered
                and registered.config_entry_id == self.entry.entry_id
                and registered.disabled_by is None
                and registered.entity_id != self.sources[key]
            ):
                self.outputs[key] = registered.entity_id
        self.source_ids.update(self.outputs.values())
        if len(self.source_ids) > MAX_SOURCE_IDS:
            self.source_ids = set(sorted(self.source_ids)[:MAX_SOURCE_IDS])
            self.admin_only = True
        if ids := list(self.outputs.values()):
            self._subscriptions.extend(
                (
                    async_track_state_change_event(self.hass, ids, self._event),
                    async_track_state_report_event(self.hass, ids, self._event),
                )
            )

    @callback
    def _registry_updated(self, event: Event[Any]) -> None:
        """Follow output renames/removal without accepting other integrations."""
        registered = er.async_get(self.hass).async_get(event.data.get("entity_id", ""))
        expected_ids = {
            f"{self.entry.entry_id}_{suffix}" for _, suffix in OUTPUT_KEYS.values()
        }
        if (
            event.data.get("entity_id") in self.outputs.values()
            or (event.data.get("changes", {}).get("entity_id") in self.outputs.values())
            or (
                registered is not None
                and registered.platform == DOMAIN
                and registered.config_entry_id == self.entry.entry_id
                and registered.unique_id in expected_ids
            )
        ):
            self._subscribe_outputs()
            self.capture(force=True)

    def _restore(self, saved: Any, now: float) -> None:
        """Validate complete persisted trips before making any restored data public."""
        if (
            not isinstance(saved, dict)
            or not isinstance(saved.get("source_ids"), list)
            or not all(isinstance(item, str) for item in saved["source_ids"])
            or len(saved["source_ids"]) > MAX_SOURCE_IDS
            or not isinstance(saved.get("admin_only", False), bool)
            or not isinstance(saved.get("trips"), list)
            or len(saved["trips"]) > MAX_TRIPS
        ):
            raise ValueError("Invalid driven-profile storage")
        samples = _restore_points(saved.get("samples"), now, MAX_HISTORY)
        trips = [self._restore_trip(trip, now) for trip in saved["trips"]]
        active = (
            self._restore_trip(saved["active"], now)
            if saved.get("active") is not None
            else None
        )
        if any(trip["end"] is None for trip in trips) or (
            active is not None and active["end"] is not None
        ):
            raise ValueError("Invalid driven-profile active trip")
        ids = [trip["id"] for trip in trips + ([active] if active else [])]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate driven-profile trip")
        self.samples, self.trips, self.active = samples, trips, active
        self.source_ids.update(saved["source_ids"])
        self.admin_only = saved.get("admin_only", False)
        if len(self.source_ids) > MAX_SOURCE_IDS:
            # Never relax permissions when bounding unusually frequent remaps.
            self.source_ids = set(sorted(self.source_ids)[:MAX_SOURCE_IDS])
            self.admin_only = True

    def _restore_trip(self, trip: Any, now: float) -> dict[str, Any]:
        """Validate metadata and separately bounded samples for one saved trip."""
        if (
            not isinstance(trip, dict)
            or not isinstance(trip.get("id"), str)
            or not trip["id"]
            or not isinstance(trip.get("name"), str)
            or not 1 <= len(trip["name"]) <= MAX_NAME
            or not isinstance(trip.get("partial"), bool)
        ):
            raise ValueError("Invalid driven-profile trip")
        start, end = finite_number(trip.get("start")), trip.get("end")
        if start is None or not 0 <= start <= now:
            raise ValueError("Invalid trip start")
        if end is not None:
            end = finite_number(end)
            if end is None or not start <= end <= now:
                raise ValueError("Invalid trip end")
        points = _restore_points(trip.get("points"), now, MAX_POINTS)
        if any(p["time"] < start or p["time"] > (end or now) for p in points):
            raise ValueError("Sample outside trip")
        return {
            "id": trip["id"],
            "name": trip["name"],
            "partial": trip["partial"],
            "start": start,
            "end": end,
            "points": points,
        }

    def _read(self, now: float) -> dict[str, Any]:
        """Use only valid configured sources and their actual freshness timestamps."""
        sample = _gap(now)
        for key, entity_id in self.outputs.items():
            state = self.hass.states.get(entity_id)
            raw_time = (
                state.attributes.get(
                    "source_reported"
                    if key in ("location", "elevation")
                    else "last_valid_time",
                )
                if state
                else None
            )
            report_time = (
                dt_util.parse_datetime(raw_time) if isinstance(raw_time, str) else None
            )
            report = report_time.timestamp() if report_time else None
            if (
                state is None
                or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN)
                or state.attributes.get("source_entity_id") != self.sources[key]
                or report is None
                or not 0 <= now - report <= FRESH_SECONDS
            ):
                continue
            if key == "location":
                lat = finite_number(state.attributes.get("latitude"))
                lon = finite_number(state.attributes.get("longitude"))
                if (
                    lat is not None
                    and lon is not None
                    and (-90 <= lat <= 90 and -180 <= lon <= 180)
                ):
                    sample["latitude"], sample["longitude"] = lat, lon
                    sample["reports"].update(latitude=report, longitude=report)
            else:
                value = finite_number(state.state)
                unit = state.attributes.get("unit_of_measurement")
                converter = VolumeConverter if key == "fuel" else DistanceConverter
                if (
                    value is not None
                    and (key == "elevation" or value >= 0)
                    and isinstance(unit, str)
                    and unit in converter.VALID_UNITS
                ):
                    converted = finite_number(
                        converter.convert(
                            value,
                            unit,
                            "L"
                            if key == "fuel"
                            else "km"
                            if key == "odometer"
                            else "m",
                        )
                    )
                    if converted is not None:
                        sample[key] = converted
                        sample["reports"][key] = report
        return sample

    @callback
    def capture(self, *, force: bool = False) -> None:
        """Coalesce valid observations to one/minute, preserving validity/reset gaps."""
        if self.error is not None:
            return
        now = dt_util.utcnow().timestamp()
        sample = self._read(now)
        previous = self.samples[-1] if self.samples else None
        if previous:
            reset = [
                key
                for key in ("odometer", "fuel")
                if sample[key] is not None
                and previous[key] is not None
                and sample[key] < previous[key]
            ]
            if reset:
                barrier = dict(sample)
                barrier["time"] = now
                barrier["reports"] = dict(sample["reports"])
                for key in reset:
                    barrier[key] = None
                    barrier["reports"].pop(key, None)
                self._append(barrier)
            changed_validity = any(
                (sample[key] is None) != (previous[key] is None) for key in CHANNELS
            )
            if (
                not force
                and not reset
                and not changed_validity
                and (now - previous["time"] < SAMPLE_SECONDS)
            ):
                if (
                    now - previous["time"] <= MAX_ENDPOINT_SKEW_SECONDS
                    and previous["reports"].get("latitude") is not None
                    and sample["reports"].get("latitude")
                    == previous["reports"]["latitude"]
                    and sample["reports"] != previous["reports"]
                ):
                    # Complete the same GPS endpoint as asynchronously published
                    # HAVRV channels arrive; never replace a new GPS fix or gap.
                    self.samples[-1] = sample
                    if self.active and self.active["points"][-1] is previous:
                        self.active["points"][-1] = sample
                    self.store.async_delay_save(self._serialize, 60)
                return
            # Timer checks expire stale channels but never manufacture valid endpoints.
            if (
                not force
                and not changed_validity
                and not reset
                and (sample["reports"] == previous["reports"])
            ):
                return
        self._append(sample)
        self.store.async_delay_save(self._serialize, 60)

    def _append(self, sample: dict[str, Any]) -> None:
        """Prune only the leading portion; never decimate across internal gaps."""
        self.samples.append(sample)
        cutoff = sample["time"] - RANGES["1d"]
        self.samples = [
            point for point in self.samples[-MAX_HISTORY:] if point["time"] >= cutoff
        ]
        if self.active is not None:
            self.active["points"].append(sample)
            if len(self.active["points"]) > MAX_POINTS:
                self.active["points"] = self.active["points"][-MAX_POINTS:]
                self.active["partial"] = True

    @callback
    def _event(self, _event: Event[Any]) -> None:
        """Batch state changes and unchanged reports in the event loop."""
        if self._pending is None:
            self._pending = self.hass.async_create_task(self._capture_pending())

    async def _capture_pending(self) -> None:
        """Yield to deferred mirror publication before observing a coherent endpoint."""
        try:
            await sleep(0)
            self.capture()
        finally:
            if self._pending is current_task():
                self._pending = None

    @callback
    def _cancel(self) -> None:
        """Cancel any pending event batch during config-entry unload."""
        if self._pending:
            self._pending.cancel()
            self._pending = None
        for unsubscribe in self._subscriptions:
            unsubscribe()
        self._subscriptions.clear()

    @callback
    def _tick(self, _now: datetime) -> None:
        """Make stale-source gaps visible even when no further source reports arrive."""
        cutoff = dt_util.utcnow().timestamp() - RANGES["1d"]
        self.samples = [point for point in self.samples if point["time"] >= cutoff]
        self.capture()

    async def _stop(self, _event: Event[Any]) -> None:
        """Flush private history on Home Assistant stop."""
        await self.async_save()

    def _serialize(self) -> dict[str, Any]:
        """Serialize local samples, trip metadata and historical permission scope."""
        return deepcopy(
            {
                "source_ids": sorted(self.source_ids),
                "admin_only": self.admin_only,
                "samples": self.samples,
                "trips": self.trips,
                "active": self.active,
            }
        )

    async def async_save(self) -> None:
        """Flush pending source events before saving, preserving corrupt storage."""
        if self._pending:
            self._pending.cancel()
            self._pending = None
        if self.error is None:
            self.capture()
            await self.store.async_save(self._serialize())

    async def async_action(self, action: str, name: str | None = None) -> None:
        """Persist admin mutations serially, with explicit validation failures."""
        async with self._lock:
            if self.error:
                raise ValueError(self.error)
            now = dt_util.utcnow().timestamp()
            if action == "start":
                if self.active:
                    raise ValueError("A driven-profile trip is already active")
                if len(self.trips) >= MAX_TRIPS:
                    raise ValueError("Saved trip limit reached")
                label = (
                    name.strip() if name is not None else dt_util.utcnow().isoformat()
                )
                if not 1 <= len(label) <= MAX_NAME:
                    raise ValueError("Trip name must contain 1 to 80 characters")
                self.active = {
                    "id": uuid4().hex,
                    "name": label,
                    "start": now,
                    "end": None,
                    "partial": False,
                    "points": [self._read(now)],
                }
                # First baseline is an actual fresh observation at start, not an
                # earlier rolling-history point extrapolated into the new trip.
            elif action == "stop":
                if self.active is None:
                    raise ValueError("No driven-profile trip is active")
                self.capture(force=True)
                self.active["end"] = dt_util.utcnow().timestamp()
                self.trips.append(self.active)
                self.active = None
            else:
                raise ValueError("Invalid driven-profile action")
            await self.async_save()

    def payload(
        self, range_key: str = "8h", trip_id: str | None = None
    ) -> dict[str, Any]:
        """Calculate bounded profile-unit plots without returning coordinates."""
        if self.error:
            raise ValueError(self.error)
        now = dt_util.utcnow().timestamp()
        start, end = now - RANGES[range_key], now
        partial = False
        if trip_id is not None:
            trip = next(
                (
                    trip
                    for trip in self.trips + ([self.active] if self.active else [])
                    if trip["id"] == trip_id
                ),
                None,
            )
            if trip is None:
                raise ValueError("Driven-profile trip not found")
            start, end = trip["start"], trip["end"] or now
            samples, partial = trip["points"], trip["partial"]
        else:
            samples = [p for p in self.samples if start <= p["time"] <= end]
        if len(samples) > MAX_POINTS:
            samples, partial = samples[-MAX_POINTS:], True
        extra = sum(
            self._discontinuity(a, b)
            for a, b in zip(samples, samples[1:], strict=False)
        )
        # Reserve space for null gaps, then rebase at the first returned endpoint.
        while len(samples) + extra > MAX_POINTS:
            extra -= self._discontinuity(samples[0], samples[1])
            samples = samples[1:]
            partial = True
        # No baseline before the selected range. A truncated leading portion
        # always starts a new zero baseline and is explicitly partial.
        partial |= not samples or samples[0]["time"] > start
        points, summary, gaps = self._calculate(samples)
        if any(
            value is not None and finite_number(value) is None
            for row in [*points, summary]
            for value in row.values()
        ):
            raise ValueError("Driven-profile calculation exceeds numeric limits")
        return {
            "units": self._units(),
            "points": points,
            "summary": summary,
            "trips": [self._metadata(trip) for trip in self.trips],
            "active_trip": self._metadata(self.active) if self.active else None,
            "start": start,
            "end": end,
            "partial": partial or gaps,
        }

    @staticmethod
    def _metadata(trip: dict[str, Any]) -> dict[str, Any]:
        """Return metadata without exposing route samples or coordinates."""
        return {key: trip[key] for key in ("id", "name", "start", "end")}

    def _units(self) -> dict[str, str]:
        """Declare every numeric channel's profile-selected display units."""
        metric = self.entry.runtime_data.measurement_system == "metric"
        return {
            "distance": "km" if metric else "mi",
            "elevation": "m" if metric else "ft",
            "fuel": "L" if metric else "gal",
            "economy": "L/100km" if metric else "mpg",
        }

    def _calculate(
        self, samples: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], dict[str, float | None], bool]:
        """Integrate only adjacent valid intervals; nulls break individual traces."""
        system = self.entry.runtime_data.measurement_system
        metric = system == "metric"
        totals = dict.fromkeys(
            (
                "gps_distance",
                "spatial_distance",
                "odometer_distance",
                "fuel_used",
                "ascent",
                "descent",
            ),
            0.0,
        )
        seen: set[str] = set()
        previous: dict[str, Any] | None = None
        points: list[dict[str, Any]] = []
        partial = False
        for sample in samples:
            point: dict[str, Any] = {
                "time": sample["time"],
                **dict.fromkeys(
                    ("distance", "elevation", "odometer", "fuel", "economy", "grade")
                ),
            }
            adjacent = previous is not None and (
                0 <= sample["time"] - previous["time"] <= FRESH_SECONDS
            )
            if previous is not None and self._discontinuity(previous, sample):
                # Insert an all-channel gap before resuming an isolated endpoint.
                points.append({**dict.fromkeys(point), "time": sample["time"]})
                partial = True
            gps = sample["latitude"] is not None
            if gps:
                seen.add("gps_distance")
                horizontal = None
                if (
                    adjacent
                    and previous is not None
                    and self._connected(previous, sample, "latitude")
                ):
                    horizontal = horizontal_distance(previous, sample)
                    totals["gps_distance"] += horizontal
                    if self._matched(previous, sample, ("latitude", "elevation")):
                        height = sample["elevation"] - previous["elevation"]
                        totals["spatial_distance"] += math.hypot(
                            horizontal, height / 1000
                        )
                        totals["ascent"] += max(0, height)
                        totals["descent"] += max(0, -height)
                        seen.update(("spatial_distance", "ascent", "descent"))
                        if horizontal > 0:
                            point["grade"] = height / (horizontal * 1000) * 100
                    elif horizontal > 0:
                        partial = True
                point["distance"] = profile_value(
                    totals["gps_distance"], "distance", system
                )
            for key, total in (
                ("odometer", "odometer_distance"),
                ("fuel", "fuel_used"),
            ):
                if sample[key] is not None:
                    seen.add(total)
                    if previous is not None and self._connected(previous, sample, key):
                        delta = sample[key] - previous[key]
                        if delta >= 0:
                            totals[total] += delta
                        else:
                            partial = True
                            continue
                    point[key] = profile_value(
                        totals[total],
                        "distance" if key == "odometer" else "fuel",
                        system,
                    )
            if sample["elevation"] is not None:
                point["elevation"] = DistanceConverter.convert(
                    sample["elevation"], "m", "m" if metric else "ft"
                )
            if (
                adjacent
                and previous is not None
                and self._matched(previous, sample, ("odometer", "fuel"))
                and gps
                and self._matched(previous, sample, ("latitude", "odometer", "fuel"))
            ):
                distance = sample["odometer"] - previous["odometer"]
                fuel = sample["fuel"] - previous["fuel"]
                if distance >= 0 and fuel >= 0:
                    denominator = (
                        distance if metric else profile_value(fuel, "fuel", system)
                    )
                    if denominator > 0:
                        point["economy"] = (
                            fuel * 100
                            if metric
                            else profile_value(distance, "distance", system)
                        ) / denominator
            if previous is not None and (
                point["economy"] is not None and point["grade"] is not None
            ):
                if not self._matched(
                    previous, sample, ("latitude", "elevation", "odometer", "fuel")
                ):
                    # A valid meter interval can be longer than this GPS interval.
                    # Never emit a paired scatter point for unrelated endpoints.
                    point["grade"] = None
                    partial = True
            if any(sample[key] is None for key in CHANNELS):
                partial = True
            points.append(point)
            previous = sample
        summary: dict[str, float | None] = {}
        for key, value in totals.items():
            summary[key] = (
                None
                if key not in seen
                else DistanceConverter.convert(value, "m", "m" if metric else "ft")
                if key in ("ascent", "descent")
                else profile_value(
                    value, "fuel" if key == "fuel_used" else "distance", system
                )
            )
        return points, summary, partial

    @staticmethod
    def _connected(a: dict[str, Any], b: dict[str, Any], key: str) -> bool:
        """Never join endpoints separated by stale reports or invalid data."""
        return (
            a[key] is not None
            and b[key] is not None
            and 0 <= b["time"] - a["time"] <= FRESH_SECONDS
            and 0 <= b["reports"][key] - a["reports"][key] <= FRESH_SECONDS
        )

    def _matched(
        self, a: dict[str, Any], b: dict[str, Any], keys: tuple[str, ...]
    ) -> bool:
        """Require new reports within one sample cadence of both shared endpoints."""
        valid = all(
            self._connected(a, b, key)
            and b["reports"][key] > a["time"]
            and a["time"] - a["reports"][key] <= SAMPLE_SECONDS
            and b["time"] - b["reports"][key] <= SAMPLE_SECONDS
            for key in keys
        )
        return valid and all(
            max(endpoint["reports"][key] for key in keys)
            - min(endpoint["reports"][key] for key in keys)
            <= MAX_ENDPOINT_SKEW_SECONDS
            for endpoint in (a, b)
        )

    def _discontinuity(self, a: dict[str, Any], b: dict[str, Any]) -> bool:
        """Detect transitions requiring an extra explicit null plot point."""
        return any(
            a[key] is not None and b[key] is not None and not self._connected(a, b, key)
            for key in CHANNELS
        )
