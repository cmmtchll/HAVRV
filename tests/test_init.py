"""Tests for HAVRV config-entry setup."""

from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.havrv import HavrvRuntimeData
from custom_components.havrv.const import DOMAIN


async def test_setup_and_unload_entry(hass: HomeAssistant) -> None:
    """An RV profile can be set up and unloaded."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Adventure RV",
        data={CONF_NAME: "Adventure RV"},
        unique_id="adventure rv",
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    assert entry.runtime_data == HavrvRuntimeData(name="Adventure RV")

    assert await hass.config_entries.async_unload(entry.entry_id)
