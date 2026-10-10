"""Set up the HAVRV integration."""

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant


@dataclass
class HavrvRuntimeData:
    """Runtime data for an RV profile."""

    name: str


type HavrvConfigEntry = ConfigEntry[HavrvRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: HavrvConfigEntry) -> bool:
    """Set up an RV profile from a config entry."""
    entry.runtime_data = HavrvRuntimeData(name=entry.data[CONF_NAME])
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HavrvConfigEntry) -> bool:
    """Unload an RV profile."""
    return True
