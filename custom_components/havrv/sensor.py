"""Sensor platform for mapped HAVRV source entities."""

import math
from collections.abc import Callable
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import VolumeConverter

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
    CONF_TANK_ENTITY_MAPPINGS,
    CONF_TANK_THRESHOLDS,
    DEFAULT_TANK_THRESHOLDS,
    DOMAIN,
    SIGNAL_OPERATION_MODE_CHANGED,
    TANK_EMPTY_PERCENT,
    TANK_FRESH_WATER,
    TANK_FULL_PERCENT,
    TANK_PROBLEM,
    TANK_TYPES,
    TANK_WARNING,
    TIRE_PRESSURE,
    TIRE_TEMPERATURE,
    UNIT_SYSTEM_METRIC,
)
from .entity import HavrvSourceEntity, async_add_source_entities
from .tank import STATUS_OPTIONS, TANK_DEFINITIONS, tank_percent, tank_status
from .tire import (
    HavrvTireEntity,
    TireMonitorGroup,
    TireMonitorHistory,
    TirePosition,
    pressure_in_profile_units,
    source_entity_id,
    temperature_in_profile_units,
    tire_monitor_groups,
    tire_monitor_readings,
    tire_monitor_spread,
    tire_positions,
)

PARALLEL_UPDATES = 0

_PROFILE_SENSOR_DESCRIPTIONS = (
    SensorEntityDescription(
        key=CONF_COACH_YEAR,
        translation_key=CONF_COACH_YEAR,
    ),
    SensorEntityDescription(
        key=CONF_MANUFACTURER,
        translation_key=CONF_MANUFACTURER,
    ),
    SensorEntityDescription(
        key=CONF_COACH_BUILDER,
        translation_key=CONF_COACH_BUILDER,
    ),
    SensorEntityDescription(
        key=CONF_MAKE,
        translation_key=CONF_MAKE,
    ),
    SensorEntityDescription(
        key=CONF_MODEL,
        translation_key=CONF_MODEL,
    ),
    SensorEntityDescription(
        key=CONF_COACH_IDENTIFIER,
        translation_key=CONF_COACH_IDENTIFIER,
    ),
    SensorEntityDescription(
        key=CONF_STORAGE_ZONE_ID,
        translation_key=CONF_STORAGE_ZONE_ID,
    ),
    SensorEntityDescription(
        key=CONF_MEASUREMENT_SYSTEM,
        translation_key=CONF_MEASUREMENT_SYSTEM,
    ),
    SensorEntityDescription(
        key=CONF_OVERALL_HEIGHT,
        translation_key=CONF_OVERALL_HEIGHT,
        device_class=SensorDeviceClass.DISTANCE,
    ),
    SensorEntityDescription(
        key=CONF_OVERALL_LENGTH,
        translation_key=CONF_OVERALL_LENGTH,
        device_class=SensorDeviceClass.DISTANCE,
    ),
    SensorEntityDescription(
        key=CONF_OVERALL_WIDTH,
        translation_key=CONF_OVERALL_WIDTH,
        device_class=SensorDeviceClass.DISTANCE,
    ),
    SensorEntityDescription(
        key=CONF_FUEL_TANK_CAPACITY,
        translation_key=CONF_FUEL_TANK_CAPACITY,
        device_class=SensorDeviceClass.VOLUME_STORAGE,
    ),
    SensorEntityDescription(
        key=CONF_FRESH_WATER_TANK_CAPACITY,
        translation_key=CONF_FRESH_WATER_TANK_CAPACITY,
        device_class=SensorDeviceClass.VOLUME_STORAGE,
    ),
    SensorEntityDescription(
        key=CONF_GRAY_WATER_TANK_CAPACITY,
        translation_key=CONF_GRAY_WATER_TANK_CAPACITY,
        device_class=SensorDeviceClass.VOLUME_STORAGE,
    ),
    SensorEntityDescription(
        key=CONF_BLACK_WATER_TANK_CAPACITY,
        translation_key=CONF_BLACK_WATER_TANK_CAPACITY,
        device_class=SensorDeviceClass.VOLUME_STORAGE,
    ),
    SensorEntityDescription(
        key=CONF_REAR_AXLE_COUNT,
        translation_key=CONF_REAR_AXLE_COUNT,
    ),
    SensorEntityDescription(
        key=CONF_MAIN_REAR_WHEEL_CONFIGURATION,
        translation_key=CONF_MAIN_REAR_WHEEL_CONFIGURATION,
    ),
    SensorEntityDescription(
        key=CONF_TAG_AXLE_PRESENT,
        translation_key=CONF_TAG_AXLE_PRESENT,
    ),
    SensorEntityDescription(
        key=CONF_TAG_AXLE_WHEEL_CONFIGURATION,
        translation_key=CONF_TAG_AXLE_WHEEL_CONFIGURATION,
    ),
)


class HavrvSensor(HavrvSourceEntity, SensorEntity):
    """Expose a mapped source sensor."""

    @property
    def name(self) -> str | None:
        """Return the source sensor name."""
        return self.source_name

    @property
    def native_value(self) -> float | str | None:
        """Return the source sensor state."""
        state = self._source_state
        if state is None or not self.available:
            return None
        try:
            value = float(state.state)
        except ValueError:
            return state.state
        return value if math.isfinite(value) else None

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the source unit."""
        unit = self.source_attributes.get("unit_of_measurement")
        return unit if isinstance(unit, str) else None

    @property
    def icon(self) -> str | None:
        """Return the source icon."""
        return self.source_icon

    @property
    def device_class(self) -> SensorDeviceClass | None:
        """Return the source sensor device class."""
        device_class = self.source_attributes.get("device_class")
        return (
            SensorDeviceClass(device_class) if isinstance(device_class, str) else None
        )

    @property
    def state_class(self) -> SensorStateClass | None:
        """Return the source sensor state class."""
        state_class = self.source_attributes.get("state_class")
        return SensorStateClass(state_class) if isinstance(state_class, str) else None

    @property
    def suggested_display_precision(self) -> int | None:
        """Return the source sensor's suggested display precision."""
        precision = self.source_attributes.get("suggested_display_precision")
        return precision if isinstance(precision, int) else None


class HavrvTankLevelSensor(HavrvSensor):
    """Expose a selected tank-level source on its own tank device."""

    entity_description = SensorEntityDescription(
        key="tank_level",
        name="Level",
        translation_key="tank_level",
    )

    def __init__(
        self,
        entry: HavrvConfigEntry,
        tank: str,
        tank_name: str,
        source_entity_id: str | None,
    ) -> None:
        """Initialize a tank level sensor."""
        parent_device_id = entry.runtime_data.device_id
        if parent_device_id is None:
            raise RuntimeError("RV device must be registered before platform setup")
        super().__init__(entry, "water", source_entity_id, parent_device_id)
        self._profile_unit = (
            "L"
            if entry.runtime_data.measurement_system == UNIT_SYSTEM_METRIC
            else "gal"
        )
        self._attr_unique_id = f"{entry.entry_id}_tank_{tank}_level"
        self._attr_device_info = _tank_device_info(entry, tank, tank_name)

    @property
    def name(self) -> str | None:
        """Use the translated level name instead of the source entity name."""
        return None

    @property
    def native_value(self) -> float | str | None:
        """Return the level, converting volumes to the RV profile unit."""
        value = super().native_value
        source_unit = self.source_attributes.get("unit_of_measurement")
        if (
            isinstance(value, float)
            and source_unit in VolumeConverter.VALID_UNITS
            and self._profile_unit != source_unit
        ):
            return VolumeConverter.convert(value, source_unit, self._profile_unit)
        return value

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Report volumes in the RV profile unit; keep other units unchanged."""
        unit = super().native_unit_of_measurement
        return self._profile_unit if unit in VolumeConverter.VALID_UNITS else unit

    @property
    def suggested_unit_of_measurement(self) -> str | None:
        """Display volumes in the RV profile unit instead of the HA system unit."""
        unit = self.native_unit_of_measurement
        return unit if unit == self._profile_unit else None


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
        self._attr_suggested_unit_of_measurement = unit
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
        }

    @property
    def native_value(self) -> str | int | float | bool:
        """Return the configured profile value."""
        return self._native_value


class HavrvTankCapacitySensor(HavrvProfileSensor):
    """Expose an optional profile capacity on its corresponding tank device."""

    entity_description = SensorEntityDescription(
        key="tank_capacity",
        name="Capacity",
        translation_key="tank_capacity",
    )

    def __init__(
        self,
        entry: HavrvConfigEntry,
        tank: str,
        tank_name: str,
        capacity_key: str,
        capacity: float | int,
    ) -> None:
        """Initialize a tank capacity sensor."""
        super().__init__(
            entry,
            self.entity_description,
            capacity,
            _profile_sensor_unit(entry, capacity_key),
        )
        self._attr_unique_id = f"{entry.entry_id}_tank_{tank}_capacity"
        self._attr_device_info = _tank_device_info(entry, tank, tank_name)


class HavrvTankDerivedSensor(HavrvSourceEntity, SensorEntity):
    """Base for values derived from a tank-level source."""

    entity_description: SensorEntityDescription

    def __init__(
        self,
        entry: HavrvConfigEntry,
        tank: str,
        tank_name: str,
        capacity_key: str,
        source_entity_id: str | None,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize a derived tank sensor."""
        parent_device_id = entry.runtime_data.device_id
        if parent_device_id is None:
            raise RuntimeError("RV device must be registered before platform setup")
        super().__init__(entry, "water", source_entity_id, parent_device_id)
        self.entity_description = description
        self._tank = tank
        self._capacity = entry.data.get(capacity_key)
        self._capacity_unit = _profile_sensor_unit(entry, capacity_key)
        self._attr_unique_id = f"{entry.entry_id}_tank_{tank}_{description.key}"
        self._attr_device_info = _tank_device_info(entry, tank, tank_name)

    @property
    def available(self) -> bool:
        """Return whether a fill percentage can be derived."""
        return self._percent() is not None

    def _percent(self) -> float | None:
        """Return the fill percentage derived from the source, if possible."""
        state = self._source_state
        if state is None:
            return None
        try:
            value = float(state.state)
        except ValueError:
            return None
        if not math.isfinite(value):
            return None
        return tank_percent(
            value,
            state.attributes.get("unit_of_measurement"),
            self._capacity,
            self._capacity_unit,
        )


class HavrvTankPercentageSensor(HavrvTankDerivedSensor):
    """Expose a tank's fill percentage."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    @property
    def native_value(self) -> float | None:
        """Return the fill percentage."""
        return self._percent()


class HavrvTankStatusSensor(HavrvTankDerivedSensor):
    """Expose ok/warning/problem from user-configured thresholds."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(STATUS_OPTIONS)

    def __init__(
        self,
        entry: HavrvConfigEntry,
        tank: str,
        tank_name: str,
        capacity_key: str,
        source_entity_id: str | None,
        description: SensorEntityDescription,
        warning: float,
        problem: float,
    ) -> None:
        """Initialize a tank status sensor."""
        super().__init__(
            entry, tank, tank_name, capacity_key, source_entity_id, description
        )
        self._warning = warning
        self._problem = problem

    @property
    def native_value(self) -> str | None:
        """Return the status for the fill percentage and operation mode."""
        return tank_status(
            self._tank,
            self._percent(),
            self._warning,
            self._problem,
            self._entry.runtime_data.operation_mode,
        )

    async def async_added_to_hass(self) -> None:
        """Re-evaluate the status when the operation mode changes."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_OPERATION_MODE_CHANGED.format(self._entry.entry_id),
                self.async_write_ha_state,
            )
        )


class HavrvTankHistorySensor(HavrvTankDerivedSensor, RestoreEntity):
    """Record when a tank was last filled or emptied."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    _last_percent: float | None = None
    _last_event: datetime | None = None

    @property
    def available(self) -> bool:
        """Stay available so the last event is kept while the source is down."""
        return True

    @property
    def native_value(self) -> datetime | None:
        """Return the time of the last detected event."""
        return self._last_event

    def _observe(self) -> None:
        """Detect a fill or empty transition between consecutive readings."""
        percent = self._percent()
        if percent is None:
            return
        previous = self._last_percent
        self._last_percent = percent
        if previous is None:
            return
        if self._tank == TANK_FRESH_WATER:
            event = previous < TANK_FULL_PERCENT <= percent
        else:
            event = previous > TANK_EMPTY_PERCENT >= percent
        if event:
            self._last_event = dt_util.utcnow()

    @callback
    def async_on_source_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Track the transition, then write state."""
        self._observe()
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore the last event and seed the baseline reading."""
        await super().async_added_to_hass()
        if (last_state := await self.async_get_last_state()) is not None:
            self._last_event = dt_util.parse_datetime(last_state.state)
        self._last_percent = self._percent()


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
            "pressure": "tire_pressure",
            "temperature": "tire_temperature",
            "battery": "tire_battery",
        }
        self.entity_description = SensorEntityDescription(
            key=metric,
            translation_key=descriptions[metric],
        )
        self._metric = metric
        self._attr_unique_id = f"{entry.entry_id}_tire_{position.key}_{metric}"

    @property
    def native_value(self) -> float | None:
        """Return the source reading converted to the RV profile unit."""
        state = self._source_state(self._metric)
        if state is None or state.state in ("unknown", "unavailable"):
            return None
        try:
            value = float(state.state)
        except ValueError:
            return None
        if not math.isfinite(value):
            return None
        unit = state.attributes.get("unit_of_measurement")
        system = self._entry.runtime_data.measurement_system
        if self._metric == "pressure":
            return pressure_in_profile_units(value, unit, system)
        if self._metric == "temperature":
            return temperature_in_profile_units(value, unit, system)
        return value

    @property
    def available(self) -> bool:
        """Return whether the configured source has a usable numeric reading."""
        return self.native_value is not None

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the RV profile unit for pressure and temperature."""
        metric = self._entry.runtime_data.measurement_system == UNIT_SYSTEM_METRIC
        if self._metric == "pressure":
            return "kPa" if metric else "psi"
        if self._metric == "temperature":
            return "°C" if metric else "°F"
        return self._source_attributes(self._metric).get("unit_of_measurement")

    @property
    def suggested_unit_of_measurement(self) -> str | None:
        """Display pressure and temperature in the RV profile unit."""
        if self._metric in ("pressure", "temperature"):
            return self.native_unit_of_measurement
        return None

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
    """Analyze comparable tire readings on an axle or across the whole RV."""

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
        self._history = TireMonitorHistory()
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
    def async_on_source_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Record changed readings and recalculate the comparison."""
        entity_id = event.data["entity_id"]
        now = dt_util.utcnow()
        readings = dict(
            (position.key, value)
            for position, value in tire_monitor_readings(
                self.hass, self._entry, self._group, self._metric
            )
        )
        for position in self._group.positions:
            if (
                source_entity_id(self._entry, position, self._metric) == entity_id
                and position.key in readings
            ):
                self._history.record(position, now, readings[position.key])
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Seed histories from current readings and subscribe to source changes."""
        await super().async_added_to_hass()
        now = dt_util.utcnow()
        for position, value in tire_monitor_readings(
            self.hass, self._entry, self._group, self._metric
        ):
            self._history.record(position, now, value)
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
        """Return the minimum number of current peer readings."""
        return 2

    @property
    def _readings(self) -> list[tuple[TirePosition, float]]:
        """Return currently usable normalized readings."""
        return tire_monitor_readings(self.hass, self._entry, self._group, self._metric)

    @property
    def available(self) -> bool:
        """Require enough comparable readings and prior history if needed."""
        readings = self._readings
        if len(readings) < self._minimum_readings:
            return False
        return self._analysis == "spread" or self._history.can_analyze(
            readings, dt_util.utcnow()
        )

    @property
    def native_value(self) -> float | str | None:
        """Return a spread value or the unique tire identified as an outlier."""
        if not self.available:
            return None
        if self._analysis == "spread":
            return tire_monitor_spread(
                self.hass, self._entry, self._group, self._metric
            )
        return self._history.outlier(self._readings, dt_util.utcnow())

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
    def suggested_unit_of_measurement(self) -> str | None:
        """Keep spreads in the RV profile's unit instead of HA's display unit."""
        if self._analysis == "spread":
            return self.native_unit_of_measurement
        return None

    @property
    def extra_state_attributes(self) -> dict[str, int | str]:
        """Describe the usable and expected readings in this comparison."""
        attributes = {
            "valid_readings": len(self._readings),
            "compared_tires": len(self._group.positions),
            "minimum_readings": self._minimum_readings,
            "analysis": (
                "maximum minus minimum"
                if self._analysis == "spread"
                else "modified z-score greater than 3.5 against each tire's 12-hour "
                "median absolute deviation baseline"
            ),
        }
        if self._analysis == "outlier":
            attributes["minimum_history_readings"] = 3
            attributes["history_window_hours"] = 12
        return attributes


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


def _tank_device_info(entry: HavrvConfigEntry, tank: str, tank_name: str) -> DeviceInfo:
    """Return stable device information for a tank."""
    parent_device_id = entry.runtime_data.device_id
    if parent_device_id is None:
        raise RuntimeError("RV device must be registered before platform setup")
    return {
        "identifiers": {(DOMAIN, f"{entry.entry_id}_tank_{tank}")},
        "name": tank_name,
        "via_device_id": parent_device_id,
    }


def _tank_entities(entry: HavrvConfigEntry) -> list[Entity]:
    """Create tank devices from configured capacities and mapped level sources."""
    mappings = entry.options.get(CONF_TANK_ENTITY_MAPPINGS, {})
    entities: list[Entity] = []
    for tank in TANK_TYPES:
        name, capacity_key = TANK_DEFINITIONS[tank]
        capacity = entry.data.get(capacity_key)
        if capacity is not None:
            entities.append(
                HavrvTankCapacitySensor(entry, tank, name, capacity_key, capacity)
            )
        source_entity_id = mappings.get(tank)
        if capacity is None and source_entity_id is None:
            continue
        entities.append(HavrvTankLevelSensor(entry, tank, name, source_entity_id))

        def derived(key: str, translation_key: str) -> SensorEntityDescription:
            return SensorEntityDescription(
                key=key,
                name=key.replace("_", " ").capitalize(),
                translation_key=translation_key,
            )

        args = (entry, tank, name, capacity_key, source_entity_id)
        entities.append(
            HavrvTankPercentageSensor(*args, derived("percentage", "tank_percentage"))
        )
        thresholds = entry.options.get(CONF_TANK_THRESHOLDS, {}).get(tank)
        warning, problem = (
            (thresholds[TANK_WARNING], thresholds[TANK_PROBLEM])
            if thresholds is not None
            else DEFAULT_TANK_THRESHOLDS[tank]
        )
        entities.append(
            HavrvTankStatusSensor(
                *args, derived("status", "tank_status"), warning, problem
            )
        )
        history_key = "last_filled" if tank == TANK_FRESH_WATER else "last_emptied"
        entities.append(
            HavrvTankHistorySensor(*args, derived(history_key, f"tank_{history_key}"))
        )
    return entities


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
    async_add_entities(list(_profile_sensors(entry)))
    async_add_entities(_tank_entities(entry))
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
            for group in tire_monitor_groups(dict(entry.data), metric)
            for analysis in ("spread", "outlier")
        ]
    )
