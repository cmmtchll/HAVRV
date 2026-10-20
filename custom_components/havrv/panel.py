"""Register HAVRV's packaged management panel as the integration gear destination."""

from hashlib import sha256

from homeassistant.components.panel_custom import async_register_panel
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .dashboard import FRONTEND_DIRECTORY, FRONTEND_URL_PATH

PANEL_PATH = "havrv-config"
PANEL_MODULE = "havrv-config-panel.js"


async def async_register_management_panel(hass: HomeAssistant) -> None:
    """Register the hidden admin-only management page once per HA instance."""
    if (
        hass.http is None
        or "frontend" not in hass.config.components
        or hass.data.get(f"{DOMAIN}_management_panel")
    ):
        return

    def read_modules() -> bytes:
        """Invalidate sibling module imports together with the panel."""
        return b"".join(
            (FRONTEND_DIRECTORY / name).read_bytes()
            for name in (PANEL_MODULE, "havrv-config-model.js", "havrv-config-en.js")
        )

    content = await hass.async_add_executor_job(read_modules)
    revision = sha256(content).hexdigest()[:12]
    await async_register_panel(
        hass,
        frontend_url_path=PANEL_PATH,
        webcomponent_name="havrv-config-panel",
        sidebar_title=None,
        module_url=f"{FRONTEND_URL_PATH}/{PANEL_MODULE}?rev={revision}",
        require_admin=True,
        config_panel_domain=DOMAIN,
    )
    hass.data[f"{DOMAIN}_management_panel"] = True
