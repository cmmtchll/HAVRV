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
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

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
    DOMAIN,
    TANK_BLACK_WATER,
    TANK_EMPTY_PERCENT,
    TANK_FRESH_WATER,
    TANK_FULL_PERCENT,
    TANK_GRAY_WATER,
    TANK_PROBLEM,
    TANK_TYPES,
    TANK_WARNING,
    UNIT_SYSTEM_METRIC,
)
from .entity import HavrvSourceEntity, async_add_source_entities
from .tank import STATUS_OPTIONS, tank_percent, tank_status
from .tire import HavrvTireEntity, TirePosition, tire_positions

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
            value = float(state.state)
        except ValueError:
            return state.state
        return value if math.isfinite(value) else None

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
        source_entity_id: str,
    ) -> None:
        """Initialize a tank level sensor."""
        parent_device_id = entry.runtime_data.device_id
        if parent_device_id is None:
            raise RuntimeError("RV device must be registered before platform setup")
        super().__init__(entry, "water", source_entity_id, parent_device_id)
        self._attr_unique_id = f"{entry.entry_id}_tank_{tank}_level"
        self._attr_device_info = _tank_device_info(entry, tank, tank_name)

    @property
    def name(self) -> str | None:
        """Use the translated level name instead of the source entity name."""
        return None


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
        source_entity_id: str,
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
        source_entity_id: str,
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
        """Return the status for the current fill percentage."""
        return tank_status(self._tank, self._percent(), self._warning, self._problem)


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
    def async_on_source_state_changed(self, event: Event) -> None:
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


def _tank_device_info(
    entry: HavrvConfigEntry, tank: str, tank_name: str
) -> dict[str, object]:
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
    """Create entities for explicitly mapped tank-level sources."""
    mappings = entry.options.get(CONF_TANK_ENTITY_MAPPINGS, {})
    entities: list[Entity] = []
    tank_names = {
        TANK_FRESH_WATER: ("Fresh-water tank", CONF_FRESH_WATER_TANK_CAPACITY),
        TANK_GRAY_WATER: ("Gray-water tank", CONF_GRAY_WATER_TANK_CAPACITY),
        TANK_BLACK_WATER: ("Black-water tank", CONF_BLACK_WATER_TANK_CAPACITY),
    }
    for tank in TANK_TYPES:
        source_entity_id = mappings.get(tank)
        if source_entity_id is None:
            continue
        name, capacity_key = tank_names[tank]
        entities.append(HavrvTankLevelSensor(entry, tank, name, source_entity_id))
        capacity = entry.data.get(capacity_key)
        if capacity is not None:
            entities.append(
                HavrvTankCapacitySensor(entry, tank, name, capacity_key, capacity)
            )

        def derived(key: str, **kwargs: object) -> SensorEntityDescription:
            return SensorEntityDescription(
                key=key, name=key.replace("_", " ").capitalize(), **kwargs
            )

        args = (entry, tank, name, capacity_key, source_entity_id)
        entities.append(
            HavrvTankPercentageSensor(
                *args, derived("percentage", translation_key="tank_percentage")
            )
        )
        thresholds = entry.options.get(CONF_TANK_THRESHOLDS, {}).get(tank)
        if thresholds is not None:
            entities.append(
                HavrvTankStatusSensor(
                    *args,
                    derived("status", translation_key="tank_status"),
                    thresholds[TANK_WARNING],
                    thresholds[TANK_PROBLEM],
                )
            )
        history_key = "last_filled" if tank == TANK_FRESH_WATER else "last_emptied"
        entities.append(
            HavrvTankHistorySensor(
                *args, derived(history_key, translation_key=f"tank_{history_key}")
            )
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
    async_add_entities(_profile_sensors(entry))
    async_add_entities(_tank_entities(entry))
    async_add_entities(
        [
            HavrvTireSensor(entry, position, metric)
            for position in tire_positions(entry.data)
            for metric in ("pressure", "temperature", "battery")
        ]
    )
