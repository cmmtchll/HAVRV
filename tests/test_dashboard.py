"""Tests for the HAVRV dashboard frontend module."""

import json
import re
from hashlib import sha256
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.havrv.const import (
    CONF_FRESH_WATER_TANK_CAPACITY,
    CONF_GRAY_WATER_TANK_CAPACITY,
    CONF_MAIN_REAR_WHEEL_CONFIGURATION,
    CONF_REAR_AXLE_COUNT,
    CONF_TAG_AXLE_PRESENT,
    CONF_TAG_AXLE_WHEEL_CONFIGURATION,
    DOMAIN,
)
from custom_components.havrv.dashboard import (
    DASHBOARD_MODULE,
    FRONTEND_DIRECTORY,
    FRONTEND_URL_PATH,
    async_register_frontend,
)

DASHBOARD_SOURCE = (FRONTEND_DIRECTORY / DASHBOARD_MODULE).read_text(encoding="utf-8")


def _js_object_keys(name: str) -> set[str]:
    """Return the keys of a top-level object literal in the dashboard module."""
    match = re.search(rf"const {name} = \{{(.*?)\n\}};", DASHBOARD_SOURCE, re.DOTALL)
    assert match, name
    return set(re.findall(r"^\s*(\w+):", match.group(1), re.MULTILINE))


def _js_tire_key() -> re.Pattern[str]:
    match = re.search(r"const TIRE_KEY = /(.+)/;", DASHBOARD_SOURCE)
    assert match
    return re.compile(match.group(1))


async def test_frontend_registration_skipped_without_frontend(
    hass: HomeAssistant,
) -> None:
    """Without the frontend component, nothing is registered."""
    with patch("custom_components.havrv.dashboard.add_extra_js_url") as add_url:
        assert not await async_register_frontend(hass)
    add_url.assert_not_called()


async def test_frontend_registration_serves_versioned_module(
    hass: HomeAssistant,
) -> None:
    """The bundled module is served and loaded with a cache-busting version."""
    hass.http = Mock(async_register_static_paths=AsyncMock())
    hass.config.components.add("frontend")
    with patch("custom_components.havrv.dashboard.add_extra_js_url") as add_url:
        assert await async_register_frontend(hass)

    (paths,) = hass.http.async_register_static_paths.call_args.args
    assert len(paths) == 1
    assert paths[0].url_path == FRONTEND_URL_PATH
    assert paths[0].path == str(FRONTEND_DIRECTORY)
    assert paths[0].cache_headers
    assert (FRONTEND_DIRECTORY / DASHBOARD_MODULE).is_file()
    add_url.assert_called_once()
    url = add_url.call_args.args[1]
    assert re.fullmatch(
        rf"{FRONTEND_URL_PATH}/{re.escape(DASHBOARD_MODULE)}"
        rf"\?v=\d+\.\d+\.\d+&rev=[a-f0-9]{{12}}",
        url,
    )
    revision = sha256((FRONTEND_DIRECTORY / DASHBOARD_MODULE).read_bytes()).hexdigest()[
        :12
    ]
    assert url.endswith(f"&rev={revision}")


async def test_frontend_revision_changes_without_version_change(
    hass: HomeAssistant,
) -> None:
    """A frontend-only update invalidates cached JavaScript at the same version."""
    hass.http = Mock(async_register_static_paths=AsyncMock())
    hass.config.components.add("frontend")
    with (
        patch("custom_components.havrv.dashboard.add_extra_js_url") as add_url,
        patch(
            "custom_components.havrv.dashboard.Path.read_bytes",
            side_effect=[b"old module", b"new module"],
        ),
    ):
        assert await async_register_frontend(hass)
        assert await async_register_frontend(hass)
    first, second = [call.args[1] for call in add_url.call_args_list]
    assert first.split("&rev=")[0] == second.split("&rev=")[0]
    assert first != second


def test_legacy_resource_loads_canonical_module() -> None:
    """Manual resources cannot register a stale duplicate card implementation."""
    loader = (FRONTEND_DIRECTORY.parents[2] / DASHBOARD_MODULE).read_text(
        encoding="utf-8"
    )
    assert "/havrv_frontend/havrv-dashboard.js?compat=" in loader
    assert "customElements.define" not in loader
    assert "class HavrvRvCard" not in loader


async def test_component_setup_registers_frontend(hass: HomeAssistant) -> None:
    """Component setup registers the dashboard once for every profile."""
    with patch(
        "custom_components.havrv.async_register_frontend", return_value=True
    ) as register:
        assert await async_setup_component(hass, DOMAIN, {})
    register.assert_awaited_once_with(hass)


def test_module_registers_card_and_strategies() -> None:
    """The module defines the card and both custom strategy elements."""
    for tag in (
        '"havrv-rv-card"',
        "`ll-strategy-dashboard-${STRATEGY_TYPE}`",
        "`ll-strategy-view-${STRATEGY_TYPE}`",
    ):
        assert tag in DASHBOARD_SOURCE
    assert 'const STRATEGY_TYPE = "havrv";' in DASHBOARD_SOURCE


def test_dashboard_translation_keys_exist() -> None:
    """Every entity translation key the dashboard reads is defined by HAVRV."""
    strings = json.loads(
        (FRONTEND_DIRECTORY.parent / "strings.json").read_text(encoding="utf-8")
    )
    defined = {key for platform in strings["entity"].values() for key in platform}
    used = (
        _js_object_keys("TIRE_ROLES")
        | _js_object_keys("TANK_ROLES")
        | _js_object_keys("POWER_ROLES")
    )
    used |= set(
        re.findall(r'(\w+): "(?:year|manufacturer|make|model)"', DASHBOARD_SOURCE)
    )
    used.add("operation_mode")
    assert {"coach_year", "manufacturer", "make", "model"} <= used
    assert used <= defined


@pytest.mark.parametrize(
    ("rear_axles", "rear_wheels", "tag_wheels"),
    [
        (1, "single", None),
        (2, "dual", None),
        (3, "dual", "single"),
        (2, "single", "dual"),
    ],
)
async def test_registry_layout_matches_dashboard_discovery(
    hass: HomeAssistant,
    rear_axles: int,
    rear_wheels: str,
    tag_wheels: str | None,
) -> None:
    """Every device and entity the dashboard reads is discoverable by its rules."""
    data = {
        CONF_NAME: "Layout RV",
        CONF_REAR_AXLE_COUNT: rear_axles,
        CONF_MAIN_REAR_WHEEL_CONFIGURATION: rear_wheels,
        CONF_FRESH_WATER_TANK_CAPACITY: 300.0,
        CONF_GRAY_WATER_TANK_CAPACITY: 200.0,
    }
    if tag_wheels:
        data[CONF_TAG_AXLE_PRESENT] = True
        data[CONF_TAG_AXLE_WHEEL_CONFIGURATION] = tag_wheels
    entry = MockConfigEntry(
        domain=DOMAIN, title="Layout RV", unique_id="layout rv", data=data, version=3
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    tire_key = _js_tire_key()
    tire_roles = _js_object_keys("TIRE_ROLES")
    tank_roles = _js_object_keys("TANK_ROLES")
    entity_registry = er.async_get(hass)
    tires: dict[str, set[str]] = {}
    tanks: dict[str, set[str]] = {}
    found_rv = found_operations = found_monitor = False
    for device in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id):
        identifier = next(
            value for domain, value in device.identifiers if domain == DOMAIN
        )
        keys = {
            entity.translation_key
            for entity in er.async_entries_for_device(entity_registry, device.id)
            if entity.platform == DOMAIN
        }
        if identifier == entry.entry_id:
            found_rv = True
            continue
        assert identifier.startswith(f"{entry.entry_id}_")
        part = identifier.removeprefix(f"{entry.entry_id}_")
        if part == "tire_monitor":
            found_monitor = True
        elif part.startswith("tire_"):
            assert tire_key.fullmatch(part.removeprefix("tire_")), part
            tires[part] = keys
        elif part.startswith("tank_"):
            tanks[part] = keys
        elif part == "operations":
            found_operations = True
            assert keys == {"operation_mode"}

    assert found_rv and found_operations and found_monitor
    wheels_per_side = {"single": 1, "dual": 2}
    expected_tires = (
        2 + 2 * (rear_axles - bool(tag_wheels)) * wheels_per_side[rear_wheels]
    )
    if tag_wheels:
        expected_tires += 2 * wheels_per_side[tag_wheels]
    assert len(tires) == expected_tires
    for keys in tires.values():
        assert tire_roles <= keys
    assert set(tanks) == {"tank_fresh_water", "tank_gray_water"}
    for keys in tanks.values():
        assert {"tank_percentage", "tank_status", "tank_level"} <= keys
        assert keys <= tank_roles
