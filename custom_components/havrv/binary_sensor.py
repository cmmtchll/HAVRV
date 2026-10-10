"""Binary sensor platform for mapped HAVRV source entities."""

from collections.abc import Callable

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity

from . import HavrvConfigEntry
from .entity import HavrvSourceEntity, async_add_source_entities
from .tire import (
    HavrvTireEntity,
    TirePosition,
    overall_tire_problem,
    tire_data_present,
    tire_positions,
    tire_problem,
)

PARALLEL_UPDATES = 0


class HavrvBinarySensor(HavrvSourceEntity, BinarySensorEntity):
    """Expose a mapped source binary sensor."""

    @property
    def name(self) -> str | None:
        """Return the source sensor name."""
        return self.source_attributes.get("friendly_name", self._source_entity_id)

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
        return self.source_attributes.get("icon")

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
                "Pressure problem",
                "tire_pressure_problem",
                BinarySensorDeviceClass.PROBLEM,
            ),
            "temperature": (
                "Temperature problem",
                "tire_temperature_problem",
                BinarySensorDeviceClass.PROBLEM,
            ),
            "battery": (
                "Battery problem",
                "tire_battery_problem",
                BinarySensorDeviceClass.PROBLEM,
            ),
            "data_present": (
                "Data present",
                "tire_data_present",
                BinarySensorDeviceClass.CONNECTIVITY,
            ),
            "problem": (
                "Problem",
                "tire_problem",
                BinarySensorDeviceClass.PROBLEM,
            ),
        }
        name, translation_key, device_class = descriptions[problem]
        self.entity_description = BinarySensorEntityDescription(
            key=problem,
            name=name,
            translation_key=translation_key,
            device_class=device_class,
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
