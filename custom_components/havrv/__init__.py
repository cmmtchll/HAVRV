"""Set up the HAVRV integration."""

from dataclasses import dataclass, field

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.typing import ConfigType
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM

from .const import (
    CONF_BLACK_WATER_TANK_CAPACITY,
    CONF_COACH_BUILDER,
    CONF_COACH_IDENTIFIER,
    CONF_COACH_YEAR,
    CONF_ENTITY_MAPPINGS,
    CONF_FRESH_WATER_TANK_CAPACITY,
    CONF_FUEL_TANK_CAPACITY,
    CONF_GRAY_WATER_TANK_CAPACITY,
    CONF_MAIN_REAR_WHEEL_CONFIGURATION,
    CONF_MAKE,
    CONF_MANUFACTURER,
    CONF_MEASUREMENT_SYSTEM,
    CONF_MODEL,
    CONF_OVERALL_HEIGHT,
    CONF_OVERALL_LENGTH,
    CONF_OVERALL_WIDTH,
    CONF_POWER_SOURCES,
    CONF_REAR_AXLE_COUNT,
    CONF_STORAGE_ZONE_ID,
    CONF_TAG_AXLE_PRESENT,
    CONF_TAG_AXLE_WHEEL_CONFIGURATION,
    CONF_TANK_ENTITY_MAPPINGS,
    DOMAIN,
    SUPPORTED_ENTITY_DOMAINS,
    SYSTEM_CATEGORIES,
    UNIT_SYSTEM_METRIC,
    UNIT_SYSTEM_US_CUSTOMARY,
)
from .dashboard import async_register_frontend
from .panel import async_register_management_panel
from .power import POWER_BINARY_METRICS, power_numeric_metrics, power_sources
from .tank import TANK_DEFINITIONS, defined_tanks
from .tire import tire_positions
from .websocket_api import async_register_commands, async_reload_profile


@dataclass
class HavrvRuntimeData:
    """Runtime data for an RV profile."""

    name: str
    coach_year: int | None = None
    manufacturer: str | None = None
    coach_builder: str | None = None
    make: str | None = None
    model: str | None = None
    coach_identifier: str | None = None
    storage_zone_id: str | None = None
    measurement_system: str = UNIT_SYSTEM_METRIC
    overall_height: float | None = None
    overall_length: float | None = None
    overall_width: float | None = None
    fuel_tank_capacity: float | None = None
    fresh_water_tank_capacity: float | None = None
    gray_water_tank_capacity: float | None = None
    black_water_tank_capacity: float | None = None
    rear_axle_count: int | None = None
    main_rear_wheel_configuration: str | None = None
    tag_axle_present: bool = False
    tag_axle_wheel_configuration: str | None = None
    operation_mode: str | None = field(default=None, compare=False)
    platforms: list[Platform] = field(default_factory=list, compare=False)
    device_id: str | None = field(default=None, compare=False)


type HavrvConfigEntry = ConfigEntry[HavrvRuntimeData]

_DOMAIN_PLATFORMS = {
    "sensor": Platform.SENSOR,
    "number": Platform.SENSOR,
    "input_number": Platform.SENSOR,
    "binary_sensor": Platform.BINARY_SENSOR,
    "switch": Platform.SWITCH,
    "light": Platform.LIGHT,
    "climate": Platform.CLIMATE,
}

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, _config: ConfigType) -> bool:
    """Set up HAVRV services shared by every RV profile."""
    await async_register_frontend(hass)
    async_register_commands(hass)
    await async_register_management_panel(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: HavrvConfigEntry) -> bool:
    """Set up an RV profile from a config entry."""
    data = entry.data
    if hass.config.units == US_CUSTOMARY_SYSTEM:
        configured_measurement_system = UNIT_SYSTEM_US_CUSTOMARY
    else:
        configured_measurement_system = UNIT_SYSTEM_METRIC

    entry.runtime_data = HavrvRuntimeData(
        name=data[CONF_NAME],
        coach_year=data.get(CONF_COACH_YEAR),
        manufacturer=data.get(CONF_MANUFACTURER),
        coach_builder=data.get(CONF_COACH_BUILDER),
        make=data.get(CONF_MAKE),
        model=data.get(CONF_MODEL),
        coach_identifier=data.get(CONF_COACH_IDENTIFIER),
        storage_zone_id=data.get(CONF_STORAGE_ZONE_ID),
        measurement_system=data.get(
            CONF_MEASUREMENT_SYSTEM, configured_measurement_system
        ),
        overall_height=data.get(CONF_OVERALL_HEIGHT),
        overall_length=data.get(CONF_OVERALL_LENGTH),
        overall_width=data.get(CONF_OVERALL_WIDTH),
        fuel_tank_capacity=data.get(CONF_FUEL_TANK_CAPACITY),
        fresh_water_tank_capacity=data.get(CONF_FRESH_WATER_TANK_CAPACITY),
        gray_water_tank_capacity=data.get(CONF_GRAY_WATER_TANK_CAPACITY),
        black_water_tank_capacity=data.get(CONF_BLACK_WATER_TANK_CAPACITY),
        rear_axle_count=data.get(CONF_REAR_AXLE_COUNT),
        main_rear_wheel_configuration=data.get(CONF_MAIN_REAR_WHEEL_CONFIGURATION),
        tag_axle_present=data.get(CONF_TAG_AXLE_PRESENT, False),
        tag_axle_wheel_configuration=data.get(CONF_TAG_AXLE_WHEEL_CONFIGURATION),
    )
    device_registry = dr.async_get(hass)
    rv_device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.runtime_data.name,
        manufacturer=entry.runtime_data.manufacturer or "HAVRV",
        model=entry.runtime_data.model or "RV",
    )
    entry.runtime_data.device_id = rv_device.id
    for source in power_sources(data):
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, f"{entry.entry_id}_source_{source.key}")},
            name=source.name,
            via_device_id=rv_device.id,
        )
    tank_mappings = entry.options.get(CONF_TANK_ENTITY_MAPPINGS, {})
    active_tanks = defined_tanks(data, tank_mappings)
    for tank, (tank_name, _capacity_key) in TANK_DEFINITIONS.items():
        if tank in active_tanks:
            device_registry.async_get_or_create(
                config_entry_id=entry.entry_id,
                identifiers={(DOMAIN, f"{entry.entry_id}_tank_{tank}")},
                name=tank_name,
                via_device_id=rv_device.id,
            )
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    mappings = _entry_entity_mappings(entry)
    positions = tire_positions(data)
    _remove_stale_entities_and_devices(
        hass,
        entry,
        active_categories={
            category for category, entities in mappings.items() if entities
        },
        active_mapping_ids={
            f"{entry.entry_id}_{category}_{entity_id}"
            for category, entities in mappings.items()
            for entity_id in entities
        },
        active_tire_keys={position.key for position in positions},
    )
    platforms = {
        _DOMAIN_PLATFORMS[entity_id.split(".", maxsplit=1)[0]]
        for entities in mappings.values()
        for entity_id in entities
        if entity_id.split(".", maxsplit=1)[0] in SUPPORTED_ENTITY_DOMAINS
    }
    platforms.add(Platform.SENSOR)
    platforms.add(Platform.SWITCH)
    if positions or any(
        settings.get(metric)
        for settings in entry.options.get(CONF_POWER_SOURCES, {}).values()
        for metric in POWER_BINARY_METRICS
    ):
        platforms.add(Platform.BINARY_SENSOR)
    entry.runtime_data.platforms = [Platform.SELECT, Platform.NUMBER, *platforms]
    await hass.config_entries.async_forward_entry_setups(
        entry, entry.runtime_data.platforms
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HavrvConfigEntry) -> bool:
    """Unload an RV profile."""
    platforms = entry.runtime_data.platforms
    if not platforms:
        return True
    return await hass.config_entries.async_unload_platforms(entry, list(platforms))


async def async_migrate_entry(_hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Require existing profiles to be recreated with the current axle model."""
    return entry.version == 3


async def _async_update_listener(hass: HomeAssistant, entry: HavrvConfigEntry) -> None:
    """Reload an RV profile when its settings or mappings change."""
    await async_reload_profile(hass, entry)


def _entry_entity_mappings(entry: HavrvConfigEntry) -> dict[str, list[str]]:
    """Get configured mappings, preferring options for edited profiles."""
    mappings = entry.options.get(CONF_ENTITY_MAPPINGS)
    if mappings is None:
        mappings = entry.data.get(CONF_ENTITY_MAPPINGS, {})
    return {
        category: list(entities)
        for category, entities in mappings.items()
        if category in SYSTEM_CATEGORIES
    }


def _remove_stale_entities_and_devices(
    hass: HomeAssistant,
    entry: HavrvConfigEntry,
    *,
    active_categories: set[str],
    active_mapping_ids: set[str],
    active_tire_keys: set[str],
) -> None:
    """Remove registry entries and child devices no longer in the profile."""
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    active_tanks = defined_tanks(
        entry.data, entry.options.get(CONF_TANK_ENTITY_MAPPINGS, {})
    )
    active_tank_ids = {
        f"{entry.entry_id}_tank_{tank}_{metric}"
        for tank in active_tanks
        for metric in (
            "level",
            "percentage",
            "status",
            "last_filled" if tank == "fresh_water" else "last_emptied",
            *(
                ["capacity"]
                if entry.data.get(TANK_DEFINITIONS[tank][1]) is not None
                else []
            ),
        )
    }
    active_power_sources = {
        source.key: entry.options.get(CONF_POWER_SOURCES, {}).get(source.key, {})
        for source in power_sources(entry.data)
    }
    source_definitions = {source.key: source for source in power_sources(entry.data)}
    active_power_ids = {
        f"{entry.entry_id}_source_{key}_{metric}"
        for key, settings in active_power_sources.items()
        for metric in (
            "location",
            "nominal_voltage",
            *(
                ["nominal_capacity"]
                if settings.get("nominal_capacity") is not None
                else []
            ),
            *(
                metric
                for metric in (
                    *power_numeric_metrics(source_definitions[key], settings),
                    *POWER_BINARY_METRICS,
                )
                if settings.get(metric)
            ),
        )
    }

    for registry_entry in er.async_entries_for_config_entry(
        entity_registry, entry.entry_id
    ):
        if registry_entry.platform != DOMAIN:
            continue
        is_stale_tank = (
            registry_entry.unique_id.startswith(f"{entry.entry_id}_tank_")
            and registry_entry.unique_id not in active_tank_ids
        )
        is_stale_mapping = any(
            registry_entry.unique_id.startswith(f"{entry.entry_id}_{category}_")
            and registry_entry.unique_id not in active_mapping_ids
            for category in SYSTEM_CATEGORIES
        )
        is_stale_power = (
            registry_entry.unique_id.startswith(f"{entry.entry_id}_source_")
            and registry_entry.unique_id not in active_power_ids
        )
        tire_key = registry_entry.unique_id.removeprefix(f"{entry.entry_id}_tire_")
        is_tire_entity = tire_key != registry_entry.unique_id
        is_stale_tire = is_tire_entity and not any(
            tire_key.startswith(f"{key}_") for key in active_tire_keys
        )
        is_moved_capacity = (
            registry_entry.domain == "sensor"
            and registry_entry.unique_id
            in {
                f"{entry.entry_id}_profile_{key}"
                for key in (
                    CONF_FRESH_WATER_TANK_CAPACITY,
                    CONF_GRAY_WATER_TANK_CAPACITY,
                    CONF_BLACK_WATER_TANK_CAPACITY,
                )
            }
        )
        is_replaced_specification = (
            registry_entry.domain == "sensor"
            and registry_entry.unique_id
            in {
                f"{entry.entry_id}_profile_{key}"
                for key in (
                    CONF_OVERALL_HEIGHT,
                    CONF_OVERALL_LENGTH,
                    CONF_OVERALL_WIDTH,
                    CONF_FUEL_TANK_CAPACITY,
                )
            }
        )
        is_stale_limit = registry_entry.unique_id.startswith(
            f"{entry.entry_id}_configuration_tire_"
        ) and (
            not active_tire_keys
            or any(
                registry_entry.unique_id.startswith(
                    f"{entry.entry_id}_configuration_tire_{group}_pressure_"
                )
                and not any(key.startswith(prefix) for key in active_tire_keys)
                for group, prefix in (("axle", "rear_axle_"), ("tag", "tag_axle_"))
            )
        )
        if (
            is_stale_mapping
            or is_stale_power
            or is_stale_tire
            or is_moved_capacity
            or is_replaced_specification
            or is_stale_limit
            or is_stale_tank
        ):
            entity_registry.async_remove(registry_entry.entity_id)

    for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
        for domain, identifier in device.identifiers:
            if domain != DOMAIN:
                continue
            if identifier.startswith(f"{entry.entry_id}_source_"):
                if (
                    identifier.removeprefix(f"{entry.entry_id}_source_")
                    in active_power_sources
                ):
                    continue
            elif identifier.startswith(f"{entry.entry_id}_tank_"):
                if (
                    identifier.removeprefix(f"{entry.entry_id}_tank_") in active_tanks
                    or device.config_entry_id != entry.entry_id
                ):
                    continue
            elif identifier.startswith(f"{entry.entry_id}_tire_"):
                tire_key = identifier.removeprefix(f"{entry.entry_id}_tire_")
                if tire_key in active_tire_keys:
                    continue
            elif identifier.startswith(f"{entry.entry_id}_"):
                category = identifier.removeprefix(f"{entry.entry_id}_")
                if category not in SYSTEM_CATEGORIES or category in active_categories:
                    continue
            else:
                continue
            if not er.async_entries_for_device(entity_registry, device.id):
                device_registry.async_remove_device(device.id)
            break
