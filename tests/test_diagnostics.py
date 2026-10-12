"""Tests for redacted HAVRV diagnostics."""

from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.redact import REDACTED
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.havrv.const import (
    CONF_ENTITY_MAPPINGS,
    CONF_STORAGE_ZONE_ID,
    CONF_TIRE_ENTITY_MAPPINGS,
    DOMAIN,
)
from custom_components.havrv.diagnostics import async_get_config_entry_diagnostics


async def test_diagnostics_redact_profile_and_entity_mapping_values(
    hass: HomeAssistant,
) -> None:
    """Never disclose profile identity, location, or selected entity IDs."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Private RV",
        unique_id="private rv",
        data={
            CONF_NAME: "Private RV",
            CONF_STORAGE_ZONE_ID: "zone.private_storage",
            CONF_ENTITY_MAPPINGS: {"power": ["sensor.private_voltage"]},
        },
        options={
            CONF_TIRE_ENTITY_MAPPINGS: {
                "front_left_pressure": "sensor.private_tire_pressure"
            }
        },
        version=3,
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["entry_data"][CONF_NAME] == REDACTED
    assert diagnostics["entry_data"][CONF_STORAGE_ZONE_ID] == REDACTED
    assert diagnostics["entry_data"][CONF_ENTITY_MAPPINGS] == REDACTED
    assert diagnostics["entry_options"][CONF_TIRE_ENTITY_MAPPINGS] == REDACTED
    assert diagnostics["platforms"] == ["select", "number", "sensor"]
    assert "private_voltage" not in str(diagnostics)
    assert "private_tire_pressure" not in str(diagnostics)
    assert await hass.config_entries.async_unload(entry.entry_id)
