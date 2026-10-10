"""Sensor platform for mapped HAVRV source entities."""

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

_PROFILE_SENSOR_DESCRIPTIONS = (
    SensorEntityDescription(
        key=CONF_COACH_YEAR,
        name="Coach year",
        translation_key=CONF_COACH_YEAR,
    ),
    SensorEntityDescription(
        key=CONF_MANUFACTURER,
        name="Chassis manufacturer",
        translation_key=CONF_MANUFACTURER,
    ),
    SensorEntityDescription(
        key=CONF_COACH_BUILDER,
        name="Coach builder",
        translation_key=CONF_COACH_BUILDER,
    ),
    SensorEntityDescription(
        key=CONF_MAKE,
        name="Chassis make",
        translation_key=CONF_MAKE,
    ),
    SensorEntityDescription(
        key=CONF_MODEL,
        name="Coach model",
        translation_key=CONF_MODEL,
    ),
    SensorEntityDescription(
        key=CONF_COACH_IDENTIFIER,
        name="Coach identifier",
        translation_key=CONF_COACH_IDENTIFIER,
    ),
    SensorEntityDescription(
        key=CONF_STORAGE_ZONE_ID,
        name="Storage zone",
        translation_key=CONF_STORAGE_ZONE_ID,
    ),
    SensorEntityDescription(
        key=CONF_MEASUREMENT_SYSTEM,
        name="Measurement system",
        translation_key=CONF_MEASUREMENT_SYSTEM,
    ),
    SensorEntityDescription(
        key=CONF_OVERALL_HEIGHT,
        name="Overall height",
        translation_key=CONF_OVERALL_HEIGHT,
    ),
    SensorEntityDescription(
        key=CONF_OVERALL_LENGTH,
        name="Overall length",
        translation_key=CONF_OVERALL_LENGTH,
    ),
    SensorEntityDescription(
        key=CONF_OVERALL_WIDTH,
        name="Overall width",
        translation_key=CONF_OVERALL_WIDTH,
    ),
    SensorEntityDescription(
        key=CONF_FUEL_TANK_CAPACITY,
        name="Fuel tank capacity",
        translation_key=CONF_FUEL_TANK_CAPACITY,
    ),
    SensorEntityDescription(
        name="Fresh-water tank capacity",
        key=CONF_FRESH_WATER_TANK_CAPACITY,
        translation_key=CONF_FRESH_WATER_TANK_CAPACITY,
    ),
    SensorEntityDescription(
        name="Gray-water tank capacity",
        key=CONF_GRAY_WATER_TANK_CAPACITY,
        translation_key=CONF_GRAY_WATER_TANK_CAPACITY,
    ),
    SensorEntityDescription(
        name="Black-water tank capacity",
        key=CONF_BLACK_WATER_TANK_CAPACITY,
        translation_key=CONF_BLACK_WATER_TANK_CAPACITY,
    ),
    SensorEntityDescription(
        key=CONF_REAR_AXLE_COUNT,
        name="Number of rear axles",
        translation_key=CONF_REAR_AXLE_COUNT,
    ),
    SensorEntityDescription(
        name="Main rear axle wheel configuration",
        key=CONF_MAIN_REAR_WHEEL_CONFIGURATION,
        translation_key=CONF_MAIN_REAR_WHEEL_CONFIGURATION,
    ),
    SensorEntityDescription(
        key=CONF_TAG_AXLE_PRESENT,
        name="Tag axle present",
        translation_key=CONF_TAG_AXLE_PRESENT,
    ),
    SensorEntityDescription(
        name="Tag axle wheel configuration",
        key=CONF_TAG_AXLE_WHEEL_CONFIGURATION,
        translation_key=CONF_TAG_AXLE_WHEEL_CONFIGURATION,
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
