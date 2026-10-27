"""GPS passthrough for an explicitly selected RV location source."""

from collections.abc import Callable

from homeassistant.components.device_tracker.const import SourceType
from homeassistant.components.device_tracker.entity import TrackerEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity

from . import HavrvConfigEntry
from .const import CONF_OPERATIONS_SOURCES
from .operations import HavrvOperationsSource, finite_number

PARALLEL_UPDATES = 0


class HavrvLocationTracker(HavrvOperationsSource, TrackerEntity):
    """Expose valid mapped coordinates using Home Assistant's GPS/zone handling."""

    _attr_translation_key = "rv_location"
    _attr_source_type = SourceType.GPS

    def __init__(self, entry: HavrvConfigEntry) -> None:
        """Initialize the optional location tracker."""
        super().__init__(entry, "location")

    @property
    def _coordinates(self) -> tuple[float, float] | None:
        """Reject unavailable, missing, non-finite, or out-of-range coordinates."""
        if not super().available:
            return None
        latitude = finite_number(self.source_attributes.get("latitude"))
        longitude = finite_number(self.source_attributes.get("longitude"))
        if (
            latitude is None
            or longitude is None
            or not -90 <= latitude <= 90
            or not -180 <= longitude <= 180
        ):
            return None
        return latitude, longitude

    @property
    def available(self) -> bool:
        """Require a complete valid GPS fix, not merely a home/away source state."""
        return self._coordinates is not None

    @property
    def latitude(self) -> float | None:
        """Return the mapped latitude without retaining stale fixes."""
        return coords[0] if (coords := self._coordinates) else None

    @property
    def longitude(self) -> float | None:
        """Return the mapped longitude without retaining stale fixes."""
        return coords[1] if (coords := self._coordinates) else None

    @property
    def location_accuracy(self) -> float:
        """Pass through valid accuracy in metres, otherwise use HA's default."""
        accuracy = finite_number(self.source_attributes.get("gps_accuracy"))
        return accuracy if accuracy is not None and accuracy >= 0 else 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HavrvConfigEntry,
    async_add_entities: Callable[[list[Entity]], None],
) -> None:
    """Set up the location tracker only when explicitly mapped."""
    if entry.options.get(CONF_OPERATIONS_SOURCES, {}).get("location"):
        async_add_entities([HavrvLocationTracker(entry)])
