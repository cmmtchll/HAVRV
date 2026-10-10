"""Config flow for HAVRV."""

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN


class HavrvConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HAVRV."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            if not name:
                errors["base"] = "name_required"
            else:
                await self.async_set_unique_id(name.casefold())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=name, data={CONF_NAME: name})

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default="My RV"): str,
                }
            ),
            errors=errors,
        )
