"""Independent RV power sources and their declared mappings."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo

from .const import (
    CONF_CHASSIS_BATTERY_BANK_COUNT,
    CONF_HOUSE_BATTERY_BANK_COUNT,
    CONF_POWER_SOURCES,
    DEFAULT_BATTERY_BANK_COUNT,
    DEFAULT_BATTERY_NOMINAL_VOLTAGE,
    DOMAIN,
)
from .entity import HavrvSourceEntity

NUMERIC_POWER_DOMAINS = ("sensor", "number", "input_number")
BINARY_POWER_DOMAINS = ("binary_sensor", "switch", "input_boolean")
POWER_BINARY_METRICS = ("enabled", "charging", "warning", "problem")


@dataclass(frozen=True)
class PowerSource:
    """One battery bank or AC source, independent of its source entity IDs."""

    key: str
    name: str
    battery: bool = False


def power_sources(profile: Mapping[str, Any]) -> list[PowerSource]:
    """Create stable bank identities, followed by the three AC sources."""
    sources: list[PowerSource] = []
    for kind, field, name in (
        ("house", CONF_HOUSE_BATTERY_BANK_COUNT, "House Batteries"),
        ("chassis", CONF_CHASSIS_BATTERY_BANK_COUNT, "Chassis Batteries"),
    ):
        count = profile.get(field, DEFAULT_BATTERY_BANK_COUNT)
        sources.extend(
            PowerSource(f"{kind}_bank_{index}", f"{name} Bank {index}", True)
            for index in range(1, count + 1)
        )
    sources.extend(
        PowerSource(key, name)
        for key, name in (
            ("inverter", "Inverter"),
            ("generator", "Generator"),
            ("shore_power", "Shore Power"),
        )
    )
    return sources


def power_settings(entry: ConfigEntry, source: PowerSource) -> dict[str, Any]:
    """Read declared settings, including defaults for legacy entries."""
    settings = dict(entry.options.get(CONF_POWER_SOURCES, {}).get(source.key, {}))
    settings.setdefault("location", "not_shown")
    if source.battery:
        settings.setdefault("nominal_voltage", DEFAULT_BATTERY_NOMINAL_VOLTAGE)
    return settings


def power_device_info(entry: ConfigEntry, source: PowerSource) -> DeviceInfo:
    """Return the child device identity without depending on entity mappings."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_source_{source.key}")},
        name=source.name,
        via_device_id=entry.runtime_data.device_id,
    )


class HavrvPowerSourceEntity(HavrvSourceEntity):
    """Listen to one explicitly declared power reading or binary status."""

    def __init__(self, entry: ConfigEntry, source: PowerSource, metric: str) -> None:
        """Initialize a source without inferring electrical connections."""
        parent_device_id = entry.runtime_data.device_id
        if parent_device_id is None:
            raise RuntimeError("RV device must be registered before platform setup")
        settings = power_settings(entry, source)
        super().__init__(entry, "power", settings.get(metric), parent_device_id)
        self._attr_unique_id = f"{entry.entry_id}_source_{source.key}_{metric}"
        self._attr_device_info = power_device_info(entry, source)
