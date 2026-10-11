"""Light platform for mapped HAVRV source entities."""

from collections.abc import Callable
from typing import Any

from homeassistant.components.light import LightEntity
from homeassistant.components.light.const import ColorMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity

from .entity import HavrvSourceEntity, async_add_source_entities

PARALLEL_UPDATES = 0


class HavrvLight(HavrvSourceEntity, LightEntity):
    """Expose and control a mapped source light."""

    @property
    def name(self) -> str | None:
        """Return the source light name."""
        return self.source_name

    @property
    def is_on(self) -> bool | None:
        """Return whether the source light is on."""
        state = self._source_state
        if state is None or not self.available:
            return None
        return state.state == "on"

    @property
    def icon(self) -> str | None:
        """Return the source icon."""
        return self.source_icon

    @property
    def supported_color_modes(self) -> set[ColorMode]:
        """Return the source light's color modes."""
        modes = self.source_attributes.get("supported_color_modes", [])
        return {ColorMode(mode) for mode in modes}

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the source light."""
        await self.hass.services.async_call(
            "light",
            "turn_on",
            {"entity_id": self._source_entity_id, **kwargs},
            blocking=True,
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the source light."""
        await self.hass.services.async_call(
            "light",
            "turn_off",
            {"entity_id": self._source_entity_id, **kwargs},
            blocking=True,
        )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: Callable[[list[Entity]], None],
) -> None:
    """Set up mapped light entities."""
    async_add_source_entities(entry, "light", HavrvLight, async_add_entities)
