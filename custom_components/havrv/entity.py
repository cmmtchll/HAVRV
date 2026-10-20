"""Shared source-entity behavior for HAVRV platforms."""

from collections.abc import Callable
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import Event, EventStateChangedData, State, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_state_change_event

from .const import CONF_ENTITY_MAPPINGS, DOMAIN, SYSTEM_CATEGORIES

type EntityAddedCallback = Callable[[list[Entity]], None]


class HavrvSourceEntity(Entity):
    """Represent an existing Home Assistant entity on an RV system device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        category: str,
        source_entity_id: str | None,
        parent_device_id: str,
    ) -> None:
        """Initialize a mapped entity; the source may be attached later."""
        self._entry = entry
        self._category = category
        self._source_entity_id = source_entity_id
        self._attr_unique_id = f"{entry.entry_id}_{category}_{source_entity_id}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{entry.entry_id}_{category}")},
            "name": category.replace("_", " ").title(),
            "via_device_id": parent_device_id,
        }

    @property
    def available(self) -> bool:
        """Return whether the source entity has a usable state."""
        state = self._source_state
        return state is not None and state.state not in ("unknown", "unavailable")

    @property
    def _source_state(self) -> State | None:
        """Return the current source state, if it exists."""
        if self._source_entity_id is None:
            return None
        if self._source_entity_id is None:
            return None
        return self.hass.states.get(self._source_entity_id)

    @callback
    def async_on_source_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Write the proxy state when the source changes."""
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Subscribe to source state changes."""
        await super().async_added_to_hass()
        if self._source_entity_id is None:
            return
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._source_entity_id], self.async_on_source_state_changed
            )
        )

    @property
    def source_attributes(self) -> dict[str, Any]:
        """Return source attributes for platform-specific entity metadata."""
        state = self._source_state
        return {} if state is None else state.attributes

    @property
    def source_name(self) -> str:
        """Return a valid display name from the source or its entity ID."""
        name = self.source_attributes.get("friendly_name")
        return name if isinstance(name, str) else str(self._source_entity_id)

    @property
    def source_icon(self) -> str | None:
        """Return a valid icon from the source."""
        icon = self.source_attributes.get("icon")
        return icon if isinstance(icon, str) else None

    @property
    def entity_category(self) -> EntityCategory | None:
        """Preserve the source entity's configuration/diagnostic category."""
        if self._source_entity_id is None:
            return None
        source = er.async_get(self.hass).async_get(self._source_entity_id)
        return None if source is None else source.entity_category


def source_entities(
    entry: ConfigEntry,
    domain: str,
) -> list[tuple[str, str]]:
    """Get category and entity ID pairs for one source platform."""
    mappings = entry.options.get(CONF_ENTITY_MAPPINGS)
    if mappings is None:
        mappings = entry.data.get(CONF_ENTITY_MAPPINGS, {})
    return [
        (category, entity_id)
        for category, entity_ids in mappings.items()
        if category in SYSTEM_CATEGORIES
        for entity_id in entity_ids
        if entity_id.split(".", maxsplit=1)[0]
        in (("sensor", "number", "input_number") if domain == "sensor" else (domain,))
    ]


@callback
def async_add_source_entities(
    entry: ConfigEntry,
    domain: str,
    entity_class: type[HavrvSourceEntity],
    async_add_entities: EntityAddedCallback,
) -> None:
    """Add mapped sources for the platform."""
    parent_device_id = entry.runtime_data.device_id
    if parent_device_id is None:
        raise RuntimeError("RV device must be registered before platform setup")
    async_add_entities(
        [
            entity_class(entry, category, entity_id, parent_device_id)
            for category, entity_id in source_entities(entry, domain)
        ]
    )
