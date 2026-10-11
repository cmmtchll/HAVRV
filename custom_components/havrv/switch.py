"""Switch platform for mapped HAVRV source entities."""

from collections.abc import Callable

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity

from .entity import HavrvSourceEntity, async_add_source_entities

PARALLEL_UPDATES = 0


class HavrvSwitch(HavrvSourceEntity, SwitchEntity):
    """Expose and control a mapped source switch."""

    @property
    def name(self) -> str | None:
        """Return the source switch name."""
        return self.source_name

    @property
    def is_on(self) -> bool | None:
        """Return whether the source switch is on."""
        state = self._source_state
        if state is None or not self.available:
            return None
        return state.state == "on"

    @property
    def icon(self) -> str | None:
        """Return the source icon."""
        return self.source_icon

    async def async_turn_on(self, **kwargs: object) -> None:
        """Turn on the source switch."""
        await self.hass.services.async_call(
            "switch", "turn_on", {"entity_id": self._source_entity_id}, blocking=True
        )

    async def async_turn_off(self, **kwargs: object) -> None:
        """Turn off the source switch."""
        await self.hass.services.async_call(
            "switch", "turn_off", {"entity_id": self._source_entity_id}, blocking=True
        )

    async def async_toggle(self, **kwargs: object) -> None:
        """Toggle the source switch."""
        await self.hass.services.async_call(
            "switch", "toggle", {"entity_id": self._source_entity_id}, blocking=True
        )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: Callable[[list[Entity]], None],
) -> None:
    """Set up mapped switch entities."""
    async_add_source_entities(entry, "switch", HavrvSwitch, async_add_entities)
