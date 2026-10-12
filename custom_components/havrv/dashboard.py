"""Serve the HAVRV dashboard card and strategies to the Home Assistant frontend."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http.server import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

FRONTEND_DIRECTORY = Path(__file__).parent / "frontend"
FRONTEND_URL_PATH = f"/{DOMAIN}_frontend"
DASHBOARD_MODULE = "havrv-dashboard.js"


def _asset_stamp() -> str:
    """Return a cache-busting stamp that changes whenever the module changes."""
    return str((FRONTEND_DIRECTORY / DASHBOARD_MODULE).stat().st_mtime_ns)


async def async_register_frontend(hass: HomeAssistant) -> bool:
    """Register the dashboard module when the Home Assistant frontend is loaded."""
    if hass.http is None or "frontend" not in hass.config.components:
        _LOGGER.debug("Frontend is not loaded; skipping HAVRV dashboard registration")
        return False

    integration = await async_get_integration(hass, DOMAIN)
    await hass.http.async_register_static_paths(
        [StaticPathConfig(FRONTEND_URL_PATH, str(FRONTEND_DIRECTORY), True)]
    )
    version = f"{integration.version}-{_asset_stamp()}"
    add_extra_js_url(hass, f"{FRONTEND_URL_PATH}/{DASHBOARD_MODULE}?v={version}")
    return True
