"""Strictly passthrough travel sources for the Operations device."""

import math
from typing import TYPE_CHECKING, Any

from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo

from .const import CONF_OPERATIONS_SOURCES, DOMAIN
from .entity import HavrvSourceEntity

if TYPE_CHECKING:
    from . import HavrvConfigEntry


def operations_device_info(entry: HavrvConfigEntry) -> DeviceInfo:
    """Return stable device information for the Operations device."""
    parent_device_id = entry.runtime_data.device_id
    if parent_device_id is None:
        raise RuntimeError("RV device must be registered before platform setup")
    return {
        "identifiers": {(DOMAIN, f"{entry.entry_id}_operations")},
        "name": "Operations",
        "via_device_id": parent_device_id,
    }


def finite_number(value: Any) -> float | None:
    """Read finite source numbers, excluding booleans and non-numeric objects."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        number = float(value)
    except ValueError, OverflowError:
        return None
    return number if math.isfinite(number) else None


class HavrvOperationsSource(HavrvSourceEntity):
    """Subscribe to one optional source with an identity independent of mapping."""

    _attr_should_poll = False

    def __init__(self, entry: HavrvConfigEntry, metric: str) -> None:
        """Associate each mapped reading with Operations, not a generic system."""
        info = operations_device_info(entry)
        super().__init__(
            entry,
            "operations",
            entry.options[CONF_OPERATIONS_SOURCES][metric],
            info["via_device_id"],
        )
        self._attr_device_info = info
        self._attr_unique_id = f"{entry.entry_id}_operations_{metric}"

    async def async_added_to_hass(self) -> None:
        """Do not subscribe to our own output when a mapping points back to it."""
        if self._source_entity_id == self.entity_id:
            self._source_entity_id = None
        await super().async_added_to_hass()

    @property
    def entity_category(self) -> EntityCategory | None:
        """Keep travel readings primary regardless of the source's category."""
        return None
