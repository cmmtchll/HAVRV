"""Strictly passthrough travel sources for the Operations device."""

import math
from typing import TYPE_CHECKING, Any

from homeassistant.const import EntityCategory
from homeassistant.core import Event, EventStateReportedData, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_state_report_event

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
    _unrecorded_attributes = frozenset({"source_reported"})

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
        if self._source_entity_id is not None:
            self.async_on_remove(
                async_track_state_report_event(
                    self.hass,
                    [self._source_entity_id],
                    self._source_reported,
                )
            )

    @callback
    def _source_reported(self, _event: Event[EventStateReportedData]) -> None:
        """Expose actual report freshness even for unchanged travel readings."""
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose source identity and report time without inventing a new reading."""
        state = self._source_state
        return {
            "source_entity_id": self._source_entity_id,
            "source_reported": state.last_reported.isoformat() if state else None,
        }

    @property
    def entity_category(self) -> EntityCategory | None:
        """Keep travel readings primary regardless of the source's category."""
        return None
