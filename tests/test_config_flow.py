"""Tests for the HAVRV config flow."""

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.havrv.const import DOMAIN


async def test_user_flow_creates_rv_profile(hass: HomeAssistant) -> None:
    """Create an RV profile from the user flow."""
    form = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    assert form["type"] is config_entries.FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        form["flow_id"], user_input={CONF_NAME: "Adventure RV"}
    )

    assert result["type"] is config_entries.FlowResultType.CREATE_ENTRY
    assert result["title"] == "Adventure RV"
    assert result["data"] == {CONF_NAME: "Adventure RV"}
    assert result["result"].unique_id == "adventure rv"


async def test_user_flow_rejects_duplicate_name(hass: HomeAssistant) -> None:
    """Reject duplicate RV profile names."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Adventure RV",
        data={CONF_NAME: "Adventure RV"},
        unique_id="adventure rv",
    )
    entry.add_to_hass(hass)

    form = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.flow.async_configure(
        form["flow_id"], user_input={CONF_NAME: "Adventure RV"}
    )

    assert result["type"] is config_entries.FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_flow_rejects_whitespace_name(hass: HomeAssistant) -> None:
    """Reject whitespace-only RV profile names."""
    form = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.flow.async_configure(
        form["flow_id"], user_input={CONF_NAME: "   "}
    )

    assert result["type"] is config_entries.FlowResultType.FORM
    assert result["errors"] == {"base": "name_required"}
