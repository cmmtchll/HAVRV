"""Binary sensor platform for mapped HAVRV source entities."""

from collections.abc import Callable

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.components.binary_sensor.const import BinarySensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import (
    Event,
    EventStateChangedData,
    HomeAssistant,
    callback,
)
from homeassistant.helpers.entity import Entity
from homeassistant.util import dt as dt_util

from . import HavrvConfigEntry
from .const import TIRE_SLOW_LOSS, TIRE_SUDDEN_DROP
from .entity import HavrvSourceEntity, async_add_source_entities
from .power import (
    POWER_BINARY_METRICS,
    HavrvPowerSourceEntity,
    PowerSource,
    power_settings,
    power_sources,
)
from .tire import (
    HavrvTireEntity,
    TirePosition,
    overall_tire_problem,
    tire_data_present,
    tire_positions,
    tire_problem,
    tire_trend_reading,
)
from .trend import PressureTrendTracker

PARALLEL_UPDATES = 0


class HavrvBinarySensor(HavrvSourceEntity, BinarySensorEntity):
    """Expose a mapped source binary sensor."""

    @property
    def name(self) -> str | None:
        """Return the source sensor name."""
        return self.source_name

    @property
    def is_on(self) -> bool | None:
        """Return whether the source sensor is on."""
        state = self._source_state
        if state is None or not self.available:
            return None
        return state.state == "on"

    @property
    def icon(self) -> str | None:
        """Return the source icon."""
        return self.source_icon

    @property
    def device_class(self) -> BinarySensorDeviceClass | None:
        """Return the source sensor device class."""
        device_class = self.source_attributes.get("device_class")
        return None if device_class is None else BinarySensorDeviceClass(device_class)


class HavrvTireBinarySensor(HavrvTireEntity, BinarySensorEntity):
    """Expose a tire diagnostic on its generated tire device."""

    entity_description: BinarySensorEntityDescription

    def __init__(
        self,
        entry: HavrvConfigEntry,
        position: TirePosition,
        problem: str,
    ) -> None:
        """Initialize a tire problem or data-presence sensor."""
        super().__init__(entry, position)
        descriptions = {
            "pressure": (
                "tire_pressure_problem",
                BinarySensorDeviceClass.PROBLEM,
            ),
            "temperature": (
                "tire_temperature_problem",
                BinarySensorDeviceClass.PROBLEM,
            ),
            "battery": (
                "tire_battery_problem",
                BinarySensorDeviceClass.PROBLEM,
            ),
            "data_present": (
                "tire_data_present",
                BinarySensorDeviceClass.CONNECTIVITY,
            ),
            "problem": (
                "tire_problem",
                BinarySensorDeviceClass.PROBLEM,
            ),
        }
        translation_key, device_class = descriptions[problem]
        self.entity_description = BinarySensorEntityDescription(
            key=problem,
            translation_key=translation_key,
            device_class=device_class,
            entity_category=EntityCategory.DIAGNOSTIC,
        )
        self._problem = problem
        self._attr_unique_id = f"{entry.entry_id}_tire_{position.key}_{problem}"

    @property
    def is_on(self) -> bool | None:
        """Return whether the tire has the configured problem."""
        if self._problem == "data_present":
            return tire_data_present(self.hass, self._entry, self._position)
        if self._problem == "problem":
            return overall_tire_problem(self.hass, self._entry, self._position)
        return tire_problem(self.hass, self._entry, self._position, self._problem)


class HavrvPowerBinarySensor(HavrvPowerSourceEntity, BinarySensorEntity):
    """Mirror declared electrical statuses without inference or forwarding actions."""

    def __init__(
        self, entry: HavrvConfigEntry, source: PowerSource, metric: str
    ) -> None:
        """Initialize one explicitly configured read-only status."""
        super().__init__(entry, source, metric)
        self.entity_description = BinarySensorEntityDescription(
            key=metric,
            translation_key=f"power_{metric}",
            device_class=(
                BinarySensorDeviceClass.PROBLEM
                if metric in ("warning", "problem")
                else None
            ),
        )

    @property
    def available(self) -> bool:
        """Only definite on/off source states are usable."""
        state = self._source_state
        return state is not None and state.state in ("on", "off")

    @property
    def is_on(self) -> bool | None:
        """Return the declared source state, including independent charging."""
        state = self._source_state
        if not self.available or state is None:
            return None
        return state.state == "on"


class HavrvTirePressureTrendBinarySensor(HavrvTireEntity, BinarySensorEntity):
    """Predict tire pressure loss from the recent in-memory pressure history."""

    entity_description: BinarySensorEntityDescription

    def __init__(
        self,
        entry: HavrvConfigEntry,
        position: TirePosition,
        trend: str,
    ) -> None:
        """Initialize a sudden-drop or slow-loss detector."""
        super().__init__(entry, position)
        self._trend = trend
        self._tracker = PressureTrendTracker(entry.runtime_data.measurement_system)
        self.entity_description = BinarySensorEntityDescription(
            key=trend,
            translation_key=f"tire_{trend}",
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_category=EntityCategory.DIAGNOSTIC,
        )
        self._attr_unique_id = f"{entry.entry_id}_tire_{position.key}_{trend}"

    def _record_reading(self) -> None:
        """Store the current reading when the pressure is usable."""
        if (
            reading := tire_trend_reading(self.hass, self._entry, self._position)
        ) is not None:
            self._tracker.record(dt_util.utcnow(), *reading)

    async def async_added_to_hass(self) -> None:
        """Seed the history with the current reading."""
        await super().async_added_to_hass()
        self._record_reading()

    @callback
    def async_on_source_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Record the new reading before writing the detector state."""
        self._record_reading()
        super().async_on_source_state_changed(event)

    @property
    def is_on(self) -> bool | None:
        """Return the detector state, or None without usable data."""
        if tire_trend_reading(self.hass, self._entry, self._position) is None:
            return None
        now = dt_util.utcnow()
        if self._trend == TIRE_SUDDEN_DROP:
            return self._tracker.sudden_drop(now)
        return self._tracker.slow_loss(now)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: Callable[[list[Entity]], None],
) -> None:
    """Set up mapped binary sensor entities."""
    async_add_source_entities(
        entry, "binary_sensor", HavrvBinarySensor, async_add_entities
    )
    async_add_entities(
        [
            HavrvPowerBinarySensor(entry, source, metric)
            for source in power_sources(entry.data)
            for metric in POWER_BINARY_METRICS
            if (source.battery or metric != "charging")
            and power_settings(entry, source).get(metric) is not None
        ]
    )
    async_add_entities(
        [
            HavrvTireBinarySensor(entry, position, problem)
            for position in tire_positions(entry.data)
            for problem in (
                "pressure",
                "temperature",
                "battery",
                "data_present",
                "problem",
            )
        ]
    )
    async_add_entities(
        [
            HavrvTirePressureTrendBinarySensor(entry, position, trend)
            for position in tire_positions(entry.data)
            for trend in (TIRE_SUDDEN_DROP, TIRE_SLOW_LOSS)
        ]
    )
