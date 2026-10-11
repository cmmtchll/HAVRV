"""Sensor platform for mapped HAVRV source entities."""

import math
from collections.abc import Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_state_change_event

from . import HavrvConfigEntry
from .const import (
    CONF_BLACK_WATER_TANK_CAPACITY,
    CONF_COACH_BUILDER,
    CONF_COACH_IDENTIFIER,
    CONF_COACH_YEAR,
    CONF_FRESH_WATER_TANK_CAPACITY,
    CONF_FUEL_TANK_CAPACITY,
    CONF_GRAY_WATER_TANK_CAPACITY,
    CONF_MAIN_REAR_WHEEL_CONFIGURATION,
    CONF_MAKE,
    CONF_MANUFACTURER,
    CONF_MEASUREMENT_SYSTEM,
    CONF_MODEL,
    CONF_OVERALL_HEIGHT,
    CONF_OVERALL_LENGTH,
    CONF_OVERALL_WIDTH,
    CONF_REAR_AXLE_COUNT,
    CONF_STORAGE_ZONE_ID,
    CONF_TAG_AXLE_PRESENT,
    CONF_TAG_AXLE_WHEEL_CONFIGURATION,
    DOMAIN,
    TIRE_PRESSURE,
    TIRE_TEMPERATURE,
    UNIT_SYSTEM_METRIC,
)
from .entity import HavrvSourceEntity, async_add_source_entities
from .tire import (
    HavrvTireEntity,
    TireMonitorGroup,
    TirePosition,
    source_entity_id,
    tire_monitor_groups,
    tire_monitor_outlier,
    tire_monitor_readings,
    tire_monitor_spread,
    tire_positions,
)

PARALLEL_UPDATES = 0

_PROFILE_SENSOR_DESCRIPTIONS = (
    SensorEntityDescription(
        key=CONF_COACH_YEAR,
        name="Coach year",
        translation_key=CONF_COACH_YEAR,
        icon="mdi:calendar",
    ),
    SensorEntityDescription(
        key=CONF_MANUFACTURER,
        name="Chassis manufacturer",
        translation_key=CONF_MANUFACTURER,
        icon="mdi:factory",
    ),
    SensorEntityDescription(
        key=CONF_COACH_BUILDER,
        name="Coach builder",
        translation_key=CONF_COACH_BUILDER,
        icon="mdi:bus",
    ),
    SensorEntityDescription(
        key=CONF_MAKE,
        name="Chassis make",
        translation_key=CONF_MAKE,
        icon="mdi:car-info",
    ),
    SensorEntityDescription(
        key=CONF_MODEL,
        name="Coach model",
        translation_key=CONF_MODEL,
        icon="mdi:bus",
    ),
    SensorEntityDescription(
        key=CONF_COACH_IDENTIFIER,
        name="Coach identifier",
        translation_key=CONF_COACH_IDENTIFIER,
        icon="mdi:identifier",
    ),
    SensorEntityDescription(
        key=CONF_STORAGE_ZONE_ID,
        name="Storage zone",
        translation_key=CONF_STORAGE_ZONE_ID,
        icon="mdi:map-marker",
    ),
    SensorEntityDescription(
        key=CONF_MEASUREMENT_SYSTEM,
        name="Measurement system",
        translation_key=CONF_MEASUREMENT_SYSTEM,
        icon="mdi:ruler-square",
    ),
    SensorEntityDescription(
        key=CONF_OVERALL_HEIGHT,
        name="Overall height",
        translation_key=CONF_OVERALL_HEIGHT,
        icon="mdi:arrow-expand-vertical",
    ),
    SensorEntityDescription(
        key=CONF_OVERALL_LENGTH,
        name="Overall length",
        translation_key=CONF_OVERALL_LENGTH,
        icon="mdi:arrow-expand-horizontal",
    ),
    SensorEntityDescription(
        key=CONF_OVERALL_WIDTH,
        name="Overall width",
        translation_key=CONF_OVERALL_WIDTH,
        icon="mdi:arrow-left-right",
    ),
    SensorEntityDescription(
        key=CONF_FUEL_TANK_CAPACITY,
        name="Fuel tank capacity",
        translation_key=CONF_FUEL_TANK_CAPACITY,
        icon="mdi:gas-station",
    ),
    SensorEntityDescription(
        name="Fresh-water tank capacity",
        key=CONF_FRESH_WATER_TANK_CAPACITY,
        translation_key=CONF_FRESH_WATER_TANK_CAPACITY,
        icon="mdi:water",
    ),
    SensorEntityDescription(
        name="Gray-water tank capacity",
        key=CONF_GRAY_WATER_TANK_CAPACITY,
        translation_key=CONF_GRAY_WATER_TANK_CAPACITY,
        icon="mdi:water-minus",
    ),
    SensorEntityDescription(
        name="Black-water tank capacity",
        key=CONF_BLACK_WATER_TANK_CAPACITY,
        translation_key=CONF_BLACK_WATER_TANK_CAPACITY,
        icon="mdi:toilet",
    ),
    SensorEntityDescription(
        key=CONF_REAR_AXLE_COUNT,
        name="Number of rear axle assemblies",
        translation_key=CONF_REAR_AXLE_COUNT,
        icon="mdi:car",
    ),
    SensorEntityDescription(
        name="Main rear axle wheel configuration",
        key=CONF_MAIN_REAR_WHEEL_CONFIGURATION,
        translation_key=CONF_MAIN_REAR_WHEEL_CONFIGURATION,
        icon="mdi:circle-multiple",
    ),
    SensorEntityDescription(
        key=CONF_TAG_AXLE_PRESENT,
        name="Tag axle present",
        translation_key=CONF_TAG_AXLE_PRESENT,
        icon="mdi:car",
    ),
    SensorEntityDescription(
        name="Tag axle wheel configuration",
        key=CONF_TAG_AXLE_WHEEL_CONFIGURATION,
        translation_key=CONF_TAG_AXLE_WHEEL_CONFIGURATION,
        icon="mdi:circle-multiple",
    ),
)


class HavrvSensor(HavrvSourceEntity, SensorEntity):
    """Expose a mapped source sensor."""

    @property
    def name(self) -> str | None:
        """Return the source sensor name."""
        return self.source_attributes.get("friendly_name", self._source_entity_id)

    @property
    def native_value(self) -> float | str | None:
        """Return the source sensor state."""
        state = self._source_state
        if state is None or not self.available:
            return None
        try:
            return float(state.state)
        except ValueError:
            return state.state

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the source unit."""
        return self.source_attributes.get("unit_of_measurement")

    @property
    def icon(self) -> str | None:
        """Return the source icon."""
        return self.source_attributes.get("icon")

    @property
    def device_class(self) -> SensorDeviceClass | None:
        """Return the source sensor device class."""
        device_class = self.source_attributes.get("device_class")
        return None if device_class is None else SensorDeviceClass(device_class)

    @property
    def state_class(self) -> SensorStateClass | None:
        """Return the source sensor state class."""
        state_class = self.source_attributes.get("state_class")
        return None if state_class is None else SensorStateClass(state_class)

    @property
    def suggested_display_precision(self) -> int | None:
        """Return the source sensor's suggested display precision."""
        return self.source_attributes.get("suggested_display_precision")


class HavrvProfileSensor(SensorEntity):
    """Expose one configured RV profile value on its RV device."""

    entity_description: SensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        entry: HavrvConfigEntry,
        description: SensorEntityDescription,
        native_value: str | int | float | bool,
        unit: str | None = None,
    ) -> None:
        """Initialize a configured profile sensor."""
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_profile_{description.key}"
        self._native_value = native_value
        self._attr_native_unit_of_measurement = unit
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
        }

    @property
    def native_value(self) -> str | int | float | bool:
        """Return the configured profile value."""
        return self._native_value


class HavrvTireSensor(HavrvTireEntity, SensorEntity):
    """Expose a configured source reading on its generated tire device."""

    entity_description: SensorEntityDescription

    def __init__(
        self,
        entry: HavrvConfigEntry,
        position: TirePosition,
        metric: str,
    ) -> None:
        """Initialize a tire reading sensor."""
        super().__init__(entry, position)
        descriptions = {
            "pressure": ("Pressure", "tire_pressure", "mdi:gauge"),
            "temperature": (
                "Temperature",
                "tire_temperature",
                "mdi:thermometer",
            ),
            "battery": ("Battery level", "tire_battery", "mdi:battery"),
        }
        name, translation_key, icon = descriptions[metric]
        self.entity_description = SensorEntityDescription(
            key=metric,
            name=name,
            translation_key=translation_key,
            icon=icon,
        )
        self._metric = metric
        self._attr_unique_id = f"{entry.entry_id}_tire_{position.key}_{metric}"

    @property
    def native_value(self) -> float | None:
        """Return the configured source's numeric reading."""
        state = self._source_state(self._metric)
        if state is None or state.state in ("unknown", "unavailable"):
            return None
        try:
            value = float(state.state)
        except ValueError:
            return None
        return value if math.isfinite(value) else None

    @property
    def available(self) -> bool:
        """Return whether the configured source has a usable numeric reading."""
        return self.native_value is not None

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the configured source unit."""
        return self._source_attributes(self._metric).get("unit_of_measurement")

    @property
    def device_class(self) -> SensorDeviceClass | None:
        """Forward the configured source device class."""
        value = self._source_attributes(self._metric).get("device_class")
        return None if value is None else SensorDeviceClass(value)

    @property
    def state_class(self) -> SensorStateClass | None:
        """Forward the configured source state class."""
        value = self._source_attributes(self._metric).get("state_class")
        return None if value is None else SensorStateClass(value)


class HavrvTireMonitorSensor(SensorEntity):
    """Analyze comparable tire readings on one axle of the RV."""

    entity_description: SensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        entry: HavrvConfigEntry,
        group: TireMonitorGroup,
        metric: str,
        analysis: str,
    ) -> None:
        """Initialize a spread or relative-outlier sensor."""
        self._entry = entry
        self._group = group
        self._metric = metric
        self._analysis = analysis
        metric_name = "pressure" if metric == TIRE_PRESSURE else "temperature"
        if analysis == "spread":
            name = f"{group.name} {metric_name} spread"
            icon = "mdi:chart-bell-curve-cumulative"
            # A temperature spread is a delta, not an absolute temperature.
            device_class = (
                SensorDeviceClass.PRESSURE if metric == TIRE_PRESSURE else None
            )
            state_class = SensorStateClass.MEASUREMENT
        else:
            name = f"{group.name} {metric_name} outlier tire"
            icon = "mdi:tire"
            device_class = None
            state_class = None
        self.entity_description = SensorEntityDescription(
            key=f"tire_monitor_{metric}_{analysis}",
            name=name,
            translation_key=f"tire_monitor_{metric}_{analysis}",
            icon=icon,
            device_class=device_class,
            state_class=state_class,
            suggested_display_precision=1 if analysis == "spread" else None,
        )
        self._attr_translation_placeholders = {"group": group.name}
        self._attr_unique_id = (
            f"{entry.entry_id}_tire_monitor_{group.key}_{metric}_{analysis}"
        )
        device_id = entry.runtime_data.device_id
        if device_id is None:
            raise RuntimeError("RV device must be registered before tire monitor setup")
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{entry.entry_id}_tire_monitor")},
            "name": "All Tire Monitor",
            "via_device_id": device_id,
        }

    @property
    def _source_entity_ids(self) -> list[str]:
        """Return source entities used by this comparison group."""
        return list(
            dict.fromkeys(
                entity_id
                for position in self._group.positions
                if (entity_id := source_entity_id(self._entry, position, self._metric))
                is not None
            )
        )

    @callback
    def async_on_source_state_changed(self, event: Event) -> None:
        """Recalculate the comparison when one of its sources changes."""
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Subscribe to source state changes."""
        await super().async_added_to_hass()
        if self._source_entity_ids:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass,
                    self._source_entity_ids,
                    self.async_on_source_state_changed,
                )
            )

    @property
    def _minimum_readings(self) -> int:
        """Return the minimum sample count needed for this analysis."""
        return 2 if self._analysis == "spread" else 3

    @property
    def _readings(self) -> list[tuple[TirePosition, float]]:
        """Return currently usable normalized readings."""
        return tire_monitor_readings(self.hass, self._entry, self._group, self._metric)

    @property
    def available(self) -> bool:
        """Require enough comparable, normalized readings for the analysis."""
        return len(self._readings) >= self._minimum_readings

    @property
    def native_value(self) -> float | str | None:
        """Return a spread value or the unique tire identified as an outlier."""
        if not self.available:
            return None
        if self._analysis == "spread":
            return tire_monitor_spread(
                self.hass, self._entry, self._group, self._metric
            )
        return tire_monitor_outlier(self.hass, self._entry, self._group, self._metric)

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the RV profile unit for a numeric spread."""
        if self._analysis != "spread":
            return None
        metric = self._entry.runtime_data.measurement_system == UNIT_SYSTEM_METRIC
        if self._metric == TIRE_PRESSURE:
            return "kPa" if metric else "psi"
        return "°C" if metric else "°F"

    @property
    def extra_state_attributes(self) -> dict[str, int | str]:
        """Describe the usable and expected readings in this comparison."""
        return {
            "valid_readings": len(self._readings),
            "compared_tires": len(self._group.positions),
            "minimum_readings": self._minimum_readings,
            "analysis": (
                "maximum minus minimum"
                if self._analysis == "spread"
                else "modified z-score greater than 3.5 using median absolute deviation"
            ),
        }


def _profile_sensor_unit(entry: HavrvConfigEntry, key: str) -> str | None:
    """Return the unit used when this profile value was entered."""
    metric = entry.runtime_data.measurement_system == UNIT_SYSTEM_METRIC
    if key in (CONF_OVERALL_HEIGHT, CONF_OVERALL_LENGTH, CONF_OVERALL_WIDTH):
        return "m" if metric else "ft"
    if key in (
        CONF_FUEL_TANK_CAPACITY,
        CONF_FRESH_WATER_TANK_CAPACITY,
        CONF_GRAY_WATER_TANK_CAPACITY,
        CONF_BLACK_WATER_TANK_CAPACITY,
    ):
        return "L" if metric else "gal"
    return None


def _profile_sensors(entry: HavrvConfigEntry) -> list[HavrvProfileSensor]:
    """Create sensors for configured RV profile fields."""
    profile_data = entry.data
    sensors: list[HavrvProfileSensor] = []
    for description in _PROFILE_SENSOR_DESCRIPTIONS:
        value = profile_data.get(description.key)
        if description.key == CONF_MEASUREMENT_SYSTEM:
            value = entry.runtime_data.measurement_system
        elif description.key == CONF_TAG_AXLE_PRESENT:
            value = "Yes" if profile_data.get(CONF_TAG_AXLE_PRESENT, False) else "No"
        if value is not None:
            sensors.append(
                HavrvProfileSensor(
                    entry,
                    description,
                    value,
                    _profile_sensor_unit(entry, description.key),
                )
            )
    return sensors


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HavrvConfigEntry,
    async_add_entities: Callable[[list[Entity]], None],
) -> None:
    """Set up mapped sensor entities."""
    async_add_source_entities(entry, "sensor", HavrvSensor, async_add_entities)
    async_add_entities(_profile_sensors(entry))
    async_add_entities(
        [
            HavrvTireSensor(entry, position, metric)
            for position in tire_positions(entry.data)
            for metric in ("pressure", "temperature", "battery")
        ]
    )
    async_add_entities(
        [
            HavrvTireMonitorSensor(entry, group, metric, analysis)
            for metric in (TIRE_PRESSURE, TIRE_TEMPERATURE)
            for group in tire_monitor_groups(entry.data, metric)
            for analysis in ("spread", "outlier")
        ]
    )
