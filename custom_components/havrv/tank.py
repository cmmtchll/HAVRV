"""Helpers for derived tank values."""

from homeassistant.util.unit_conversion import VolumeConverter

from .const import (
    TANK_FRESH_WATER,
    TANK_PROBLEM,
    TANK_WARNING,
)

STATUS_OK = "ok"
STATUS_OPTIONS = (STATUS_OK, TANK_WARNING, TANK_PROBLEM)


def tank_percent(
    value: float,
    unit: str | None,
    capacity: float | None,
    capacity_unit: str | None,
) -> float | None:
    """Return a fill percentage from a source reading, or None if not derivable."""
    if unit == "%":
        percent = value
    elif capacity and capacity > 0 and unit in VolumeConverter.VALID_UNITS:
        if capacity_unit not in VolumeConverter.VALID_UNITS:
            return None
        converted = VolumeConverter.convert(value, unit, capacity_unit)
        percent = converted / capacity * 100
    else:
        return None
    return max(0.0, min(100.0, percent))


def tank_status(
    tank: str, percent: float | None, warning: float, problem: float
) -> str | None:
    """Return ok/warning/problem; fresh water is bad when low, waste when high."""
    if percent is None:
        return None
    if tank == TANK_FRESH_WATER:
        if percent <= problem:
            return TANK_PROBLEM
        if percent <= warning:
            return TANK_WARNING
        return STATUS_OK
    if percent >= problem:
        return TANK_PROBLEM
    if percent >= warning:
        return TANK_WARNING
    return STATUS_OK


def thresholds_valid(tank: str, warning: float, problem: float) -> bool:
    """Check that thresholds are in range and ordered for the tank direction."""
    if not 0 <= warning <= 100 or not 0 <= problem <= 100:
        return False
    if tank == TANK_FRESH_WATER:
        return problem < warning
    return warning < problem
