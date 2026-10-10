"""Binary sensor platform for mapped HAVRV source entities."""

from collections.abc import Callable

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity

from .entity import HavrvSourceEntity, async_add_source_entities


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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: Callable[[list[Entity]], None],
) -> None:
    """Set up mapped binary sensor entities."""
    async_add_source_entities(
        entry, "binary_sensor", HavrvBinarySensor, async_add_entities
    )
