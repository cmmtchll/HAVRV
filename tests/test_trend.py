"""Tests for tire pressure trend prediction."""

from datetime import UTC, datetime, timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.havrv.const import (
    CONF_MAIN_REAR_WHEEL_CONFIGURATION,
    CONF_MEASUREMENT_SYSTEM,
    CONF_REAR_AXLE_COUNT,
    CONF_TIRE_ENTITY_MAPPINGS,
    DOMAIN,
    UNIT_SYSTEM_METRIC,
)
from custom_components.havrv.trend import PressureTrendTracker

START = datetime(2026, 1, 1, 12, tzinfo=UTC)


def _feed(
    tracker: PressureTrendTracker,
    readings: list[tuple[int, float, float | None]],
) -> datetime:
    """Record (minute, pressure, temperature) readings and return the last time."""
    now = START
    for minute, pressure, temperature in readings:
        now = START + timedelta(minutes=minute)
        tracker.record(now, pressure, temperature)
    return now


def test_insufficient_history_is_unknown() -> None:
    """Report no answer until enough history has been collected."""
    tracker = PressureTrendTracker(UNIT_SYSTEM_METRIC)
    assert tracker.sudden_drop(START) is None
    assert tracker.slow_loss(START) is None
    now = _feed(tracker, [(0, 240, 20)])
    assert tracker.sudden_drop(now) is None
    now = _feed(tracker, [(0, 240, 20), (1, 200, 20)])
    assert tracker.sudden_drop(now) is None
    assert tracker.slow_loss(now) is None


def test_normal_pressure_rise_while_heating_is_not_loss() -> None:
    """Rising pressure and temperature must not look like loss."""
    tracker = PressureTrendTracker(UNIT_SYSTEM_METRIC)
    now = _feed(
        tracker,
        [(m, 240 + m * 0.5, 20 + m * 0.05) for m in range(0, 600, 10)],
    )
    assert tracker.sudden_drop(now) is False
    assert tracker.slow_loss(now) is False


def test_sudden_drop_detected() -> None:
    """Flag a sharp fall within minutes."""
    tracker = PressureTrendTracker(UNIT_SYSTEM_METRIC)
    now = _feed(tracker, [(0, 240, 20), (3, 238, 20), (6, 200, 20), (7, 198, 20)])
    assert tracker.sudden_drop(now) is True


def test_single_low_reading_is_not_a_sudden_drop() -> None:
    """A lone glitch that recovers does not raise an alert."""
    tracker = PressureTrendTracker(UNIT_SYSTEM_METRIC)
    now = _feed(tracker, [(0, 240, 20), (3, 150, 20), (6, 240, 20), (7, 240, 20)])
    assert tracker.sudden_drop(now) is False


def test_slow_loss_detected() -> None:
    """Flag a gradual decline at constant temperature over hours."""
    tracker = PressureTrendTracker(UNIT_SYSTEM_METRIC)
    now = _feed(tracker, [(m, 240 - m * 0.03, 20) for m in range(0, 480, 5)])
    assert tracker.slow_loss(now) is True
    assert tracker.sudden_drop(now) is False


def test_cooling_pressure_decline_is_not_slow_loss() -> None:
    """A fall explained by shade or cooler air is not treated as loss."""
    tracker = PressureTrendTracker(UNIT_SYSTEM_METRIC)
    # About 3.4% pressure fall for a 10 K drop, matching the gas law.
    now = _feed(
        tracker,
        [(m, 240 - m * 0.0185, 30 - m * 10 / 480) for m in range(0, 481, 30)],
    )
    assert tracker.slow_loss(now) is False


def test_loss_hidden_by_warming_is_still_found() -> None:
    """Flat raw pressure while warming means gas has been lost."""
    tracker = PressureTrendTracker(UNIT_SYSTEM_METRIC)
    now = _feed(tracker, [(m, 240, 15 + m * 10 / 480) for m in range(0, 481, 30)])
    assert tracker.slow_loss(now) is True


def test_slow_loss_requires_temperature() -> None:
    """Without temperature the slow detector declines to guess."""
    tracker = PressureTrendTracker(UNIT_SYSTEM_METRIC)
    now = _feed(tracker, [(m, 240 - m * 0.05, None) for m in range(0, 480, 30)])
    assert tracker.slow_loss(now) is None


def test_us_customary_units_use_fahrenheit_and_psi() -> None:
    """Compensate correctly in US customary units."""
    tracker = PressureTrendTracker("us_customary")
    now = _feed(
        tracker, [(m, 35 + m * 0.002, 68 + m * 0.02) for m in range(0, 480, 30)]
    )
    assert tracker.slow_loss(now) is False


def test_old_samples_are_discarded() -> None:
    """History does not grow beyond the longest observation window."""
    tracker = PressureTrendTracker(UNIT_SYSTEM_METRIC)
    _feed(tracker, [(m, 240, 20) for m in range(0, 2000, 60)])
    assert len(tracker._samples) <= 14


async def test_entities_report_and_reset_on_reload(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Detect loss from state changes, ignore unavailable, reset on reload."""
    freezer.move_to(START)
    attrs = {"unit_of_measurement": "kPa", "device_class": "pressure"}
    hass.states.async_set("sensor.fl_pressure", "240", attrs)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Trend RV",
        unique_id="trend rv",
        data={
            CONF_NAME: "Trend RV",
            CONF_MEASUREMENT_SYSTEM: UNIT_SYSTEM_METRIC,
            CONF_REAR_AXLE_COUNT: 1,
            CONF_MAIN_REAR_WHEEL_CONFIGURATION: "single",
        },
        options={
            CONF_TIRE_ENTITY_MAPPINGS: {"front_left_pressure": "sensor.fl_pressure"}
        },
        version=3,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    sudden = registry.async_get_entity_id(
        "binary_sensor",
        DOMAIN,
        f"{entry.entry_id}_tire_front_left_pressure_sudden_drop",
    )
    slow = registry.async_get_entity_id(
        "binary_sensor", DOMAIN, f"{entry.entry_id}_tire_front_left_pressure_slow_loss"
    )
    assert sudden is not None
    assert slow is not None
    assert hass.states.get(sudden).state == "unknown"

    freezer.tick(timedelta(minutes=5))
    hass.states.async_set("sensor.fl_pressure", "239", attrs)
    await hass.async_block_till_done()
    assert hass.states.get(sudden).state == "off"
    assert hass.states.get(slow).state == "unknown"

    freezer.tick(timedelta(minutes=2))
    hass.states.async_set("sensor.fl_pressure", "190", attrs)
    await hass.async_block_till_done()
    freezer.tick(timedelta(minutes=1))
    hass.states.async_set("sensor.fl_pressure", "189", attrs)
    await hass.async_block_till_done()
    assert hass.states.get(sudden).state == "on"

    hass.states.async_set("sensor.fl_pressure", "unavailable", attrs)
    await hass.async_block_till_done()
    assert hass.states.get(sudden).state == "unknown"

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    hass.states.async_set("sensor.fl_pressure", "189", attrs)
    await hass.async_block_till_done()
    assert hass.states.get(sudden).state == "unknown"
