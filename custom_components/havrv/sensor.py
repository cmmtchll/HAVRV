"""Sensor platform for mapped HAVRV source entities."""

import math
from collections.abc import Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity

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
    UNIT_SYSTEM_METRIC,
)
from .entity import HavrvSourceEntity, async_add_source_entities
from .tire import HavrvTireEntity, TirePosition, tire_positions

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
            return float(state.state)
        except ValueError:
            return state.state

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
    async_add_entities(
        [
            HavrvTireSensor(entry, position, metric)
            for position in tire_positions(entry.data)
            for metric in ("pressure", "temperature", "battery")
        ]
    )
