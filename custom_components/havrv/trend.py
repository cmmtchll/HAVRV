"""Tire pressure trend detection from in-memory readings."""

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta

from .const import (
    TIRE_SLOW_LOSS_FRACTION,
    TIRE_SLOW_LOSS_MIN_SAMPLES,
    TIRE_SLOW_LOSS_MIN_SPAN_SECONDS,
    TIRE_SLOW_LOSS_WINDOW_SECONDS,
    TIRE_SUDDEN_DROP_FRACTION,
    TIRE_SUDDEN_DROP_MIN_SPAN_SECONDS,
    TIRE_SUDDEN_DROP_WINDOW_SECONDS,
    UNIT_SYSTEM_METRIC,
)

_REFERENCE_KELVIN = 293.15
_ATMOSPHERE_KPA = 101.325
_ATMOSPHERE_PSI = 14.696
# Two readings must agree so that one glitchy low reading cannot raise an alert.
_CONFIRMING_SAMPLES = 2


@dataclass(frozen=True)
class PressureSample:
    """A pressure reading and its temperature-compensated equivalent."""

    time: datetime
    raw: float
    normalized: float | None


class PressureTrendTracker:
    """Detect sudden and slow pressure loss from a bounded reading history."""

    def __init__(self, measurement_system: str) -> None:
        """Initialize an empty history for one tire."""
        self._metric = measurement_system == UNIT_SYSTEM_METRIC
        self._samples: deque[PressureSample] = deque()

    def record(self, now: datetime, pressure: float, temperature: float | None) -> None:
        """Add a reading and discard history older than the longest window."""
        self._samples.append(
            PressureSample(now, pressure, self._normalize(pressure, temperature))
        )
        cutoff = now - timedelta(seconds=TIRE_SLOW_LOSS_WINDOW_SECONDS)
        while self._samples[0].time < cutoff:
            self._samples.popleft()

    def _normalize(self, pressure: float, temperature: float | None) -> float | None:
        """Convert a gauge pressure to its value at a reference temperature."""
        if temperature is None:
            return None
        kelvin = (
            temperature + 273.15
            if self._metric
            else (temperature - 32) * 5 / 9 + 273.15
        )
        if kelvin <= 0:
            return None
        atmosphere = _ATMOSPHERE_KPA if self._metric else _ATMOSPHERE_PSI
        return (pressure + atmosphere) * _REFERENCE_KELVIN / kelvin - atmosphere

    def sudden_drop(self, now: datetime) -> bool | None:
        """Return whether pressure fell sharply, or None without enough history."""
        window = self._window(now, TIRE_SUDDEN_DROP_WINDOW_SECONDS)
        if _span(window) < TIRE_SUDDEN_DROP_MIN_SPAN_SECONDS:
            return None
        values = (
            [s.normalized for s in window]
            if all(s.normalized is not None for s in window)
            else [s.raw for s in window]
        )
        return _fell(values, TIRE_SUDDEN_DROP_FRACTION)

    def slow_loss(self, now: datetime) -> bool | None:
        """Return whether temperature-compensated pressure steadily declined."""
        window = [
            s
            for s in self._window(now, TIRE_SLOW_LOSS_WINDOW_SECONDS)
            if s.normalized is not None
        ]
        if (
            len(window) < TIRE_SLOW_LOSS_MIN_SAMPLES
            or _span(window) < TIRE_SLOW_LOSS_MIN_SPAN_SECONDS
        ):
            return None
        return _fell([s.normalized for s in window], TIRE_SLOW_LOSS_FRACTION)

    def _window(self, now: datetime, seconds: int) -> list[PressureSample]:
        """Return samples inside the trailing window."""
        cutoff = now - timedelta(seconds=seconds)
        return [s for s in self._samples if s.time >= cutoff]


def _span(samples: list[PressureSample]) -> float:
    """Return the seconds covered by the samples."""
    if len(samples) < 2:
        return 0
    return (samples[-1].time - samples[0].time).total_seconds()


def _fell(values: list[float | None], fraction: float) -> bool:
    """Return whether recent values sit below the window peak by the fraction."""
    peak = max(v for v in values if v is not None)
    current = max(v for v in values[-_CONFIRMING_SAMPLES:] if v is not None)
    return peak > 0 and (peak - current) / peak >= fraction
