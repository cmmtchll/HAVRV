"""Tests for HAVRV config-entry setup."""

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import CONF_NAME, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.icon import async_get_icons
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.havrv import HavrvRuntimeData, async_migrate_entry
from custom_components.havrv.const import (
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
    CONF_REAR_AXLE_COUNT,
    CONF_STORAGE_ZONE_ID,
    CONF_TAG_AXLE_PRESENT,
    CONF_TAG_AXLE_WHEEL_CONFIGURATION,
    CONF_TANK_ENTITY_MAPPINGS,
    CONF_TIRE_BATTERY_LOW,
    CONF_TIRE_ENTITY_MAPPINGS,
    CONF_TIRE_PRESSURE_THRESHOLDS,
    CONF_TIRE_TEMPERATURE_HIGH,
    DOMAIN,
    UNIT_SYSTEM_METRIC,
    UNIT_SYSTEM_US_CUSTOMARY,
)


async def test_setup_and_unload_name_only_profile(hass: HomeAssistant) -> None:
    """A profile with only its name remains set-up and unloadable."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Adventure RV",
        data={CONF_NAME: "Adventure RV"},
        unique_id="adventure rv",
        version=3,
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    assert entry.runtime_data == HavrvRuntimeData(
        name="Adventure RV",
        measurement_system=(
            UNIT_SYSTEM_US_CUSTOMARY
            if hass.config.units == US_CUSTOMARY_SYSTEM
            else UNIT_SYSTEM_METRIC
        ),
    )

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_migration_requires_new_profile_configuration(
    hass: HomeAssistant,
) -> None:
    """Block older profiles that use the previous axle configuration model."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Adventure RV",
        data={
            CONF_NAME: "Adventure RV",
            CONF_REAR_AXLE_COUNT: 2,
            CONF_TAG_AXLE_PRESENT: True,
        },
        unique_id="adventure rv",
        version=2,
    )
    entry.add_to_hass(hass)

    assert not await async_migrate_entry(hass, entry)
    assert entry.version == 2
    assert entry.data[CONF_REAR_AXLE_COUNT] == 2


async def test_setup_uses_home_assistant_units_when_profile_omits_units(
    hass: HomeAssistant,
) -> None:
    """Default profile units to Home Assistant's unit system when omitted."""
    hass.config.units = US_CUSTOMARY_SYSTEM
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Adventure RV",
        data={CONF_NAME: "Adventure RV"},
        unique_id="adventure rv",
        version=3,
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    assert entry.runtime_data.measurement_system == UNIT_SYSTEM_US_CUSTOMARY
    assert len(entry.runtime_data.platforms) == 1
    assert entry.runtime_data.platforms[0].value == "sensor"
    profile_entities = {
        entity.unique_id.removeprefix(f"{entry.entry_id}_profile_"): entity
        for entity in er.async_entries_for_config_entry(
            er.async_get(hass), entry.entry_id
        )
        if entity.unique_id.startswith(f"{entry.entry_id}_profile_")
    }
    assert set(profile_entities) == {
        CONF_MEASUREMENT_SYSTEM,
        CONF_TAG_AXLE_PRESENT,
    }


async def test_profile_sensors_use_metric_units(hass: HomeAssistant) -> None:
    """Expose metric dimensions and capacities in their configured units."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Metric RV",
        unique_id="metric rv",
        data={
            CONF_NAME: "Metric RV",
            CONF_MEASUREMENT_SYSTEM: UNIT_SYSTEM_METRIC,
            CONF_OVERALL_HEIGHT: 3.8,
            CONF_FRESH_WATER_TANK_CAPACITY: 500.0,
        },
        version=3,
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    entities = {
        entity.unique_id.removeprefix(f"{entry.entry_id}_profile_"): entity
        for entity in er.async_entries_for_config_entry(
            er.async_get(hass), entry.entry_id
        )
        if entity.unique_id.startswith(f"{entry.entry_id}_profile_")
    }
    height = hass.states.get(entities[CONF_OVERALL_HEIGHT].entity_id)
    capacity = hass.states.get(entities[CONF_FRESH_WATER_TANK_CAPACITY].entity_id)
    assert height.state == "3.8"
    assert height.attributes["unit_of_measurement"] == "m"
    assert capacity.state == "500.0"
    assert capacity.attributes["unit_of_measurement"] == "L"
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_setup_populates_typed_runtime_profile(hass: HomeAssistant) -> None:
    """Expose saved RV profile values as typed runtime data."""
    hass.config.units = US_CUSTOMARY_SYSTEM
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Liberty",
        unique_id="liberty",
        data={
            CONF_NAME: "Liberty",
            CONF_COACH_YEAR: 2003,
            CONF_MANUFACTURER: "Prevost",
            CONF_COACH_BUILDER: "Liberty",
            CONF_MAKE: "H3-45",
            CONF_MODEL: "Elegant Lady",
            CONF_COACH_IDENTIFIER: "1234",
            CONF_MEASUREMENT_SYSTEM: UNIT_SYSTEM_US_CUSTOMARY,
            CONF_STORAGE_ZONE_ID: "zone.rv_storage",
            CONF_OVERALL_HEIGHT: 12.5,
            CONF_OVERALL_LENGTH: 45.0,
            CONF_OVERALL_WIDTH: 8.5,
            CONF_FUEL_TANK_CAPACITY: 250.0,
            CONF_FRESH_WATER_TANK_CAPACITY: 160.0,
            CONF_GRAY_WATER_TANK_CAPACITY: 100.0,
            CONF_BLACK_WATER_TANK_CAPACITY: 80.0,
            CONF_REAR_AXLE_COUNT: 2,
            CONF_MAIN_REAR_WHEEL_CONFIGURATION: "dual",
            CONF_TAG_AXLE_PRESENT: True,
            CONF_TAG_AXLE_WHEEL_CONFIGURATION: "single",
        },
        version=3,
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    assert entry.runtime_data == HavrvRuntimeData(
        name="Liberty",
        coach_year=2003,
        manufacturer="Prevost",
        coach_builder="Liberty",
        make="H3-45",
        model="Elegant Lady",
        coach_identifier="1234",
        storage_zone_id="zone.rv_storage",
        measurement_system=UNIT_SYSTEM_US_CUSTOMARY,
        overall_height=12.5,
        overall_length=45.0,
        overall_width=8.5,
        fuel_tank_capacity=250.0,
        fresh_water_tank_capacity=160.0,
        gray_water_tank_capacity=100.0,
        black_water_tank_capacity=80.0,
        rear_axle_count=2,
        main_rear_wheel_configuration="dual",
        tag_axle_present=True,
        tag_axle_wheel_configuration="single",
    )
    profile_entities = {
        entity.unique_id.removeprefix(f"{entry.entry_id}_profile_"): entity
        for entity in er.async_entries_for_config_entry(
            er.async_get(hass), entry.entry_id
        )
        if entity.unique_id.startswith(f"{entry.entry_id}_profile_")
    }
    rear_axles = hass.states.get(profile_entities[CONF_REAR_AXLE_COUNT].entity_id)
    assert rear_axles.state == "2"
    assert entry.version == 3
    assert entry.data[CONF_REAR_AXLE_COUNT] == 2
    assert rear_axles.attributes["friendly_name"].endswith(
        "Number of rear axle assemblies"
    ), rear_axles.attributes["friendly_name"]
    assert profile_entities[CONF_REAR_AXLE_COUNT].entity_category is None
    assert (
        hass.states.get(profile_entities[CONF_OVERALL_HEIGHT].entity_id).attributes[
            "device_class"
        ]
        == SensorDeviceClass.DISTANCE
    )
    assert (
        hass.states.get(profile_entities[CONF_FUEL_TANK_CAPACITY].entity_id).attributes[
            "device_class"
        ]
        == SensorDeviceClass.VOLUME_STORAGE
    )
    profile_names = [
        hass.states.get(entity.entity_id).attributes["friendly_name"]
        for entity in profile_entities.values()
    ]
    assert len(profile_names) == len(set(profile_names))
    icon_translations = await async_get_icons(hass, "entity", {DOMAIN})
    profile_icons = icon_translations[DOMAIN]["sensor"]
    assert profile_icons[CONF_COACH_YEAR]["default"] == "mdi:calendar"
    assert (
        profile_icons[CONF_MAIN_REAR_WHEEL_CONFIGURATION]["default"]
        == "mdi:circle-multiple"
    )
    assert CONF_OVERALL_HEIGHT not in profile_icons
    assert CONF_FUEL_TANK_CAPACITY not in profile_icons
    assert (
        hass.states.get(
            profile_entities[CONF_MAIN_REAR_WHEEL_CONFIGURATION].entity_id
        ).state
        == "dual"
    )
    assert (
        hass.states.get(profile_entities[CONF_TAG_AXLE_PRESENT].entity_id).state
        == "Yes"
    )
    assert (
        hass.states.get(
            profile_entities[CONF_TAG_AXLE_WHEEL_CONFIGURATION].entity_id
        ).state
        == "single"
    )
    assert (
        hass.states.get(profile_entities[CONF_FUEL_TANK_CAPACITY].entity_id).attributes[
            "unit_of_measurement"
        ]
        == "gal"
    )
    assert (
        hass.states.get(profile_entities[CONF_OVERALL_LENGTH].entity_id).attributes[
            "unit_of_measurement"
        ]
        == "ft"
    )
    assert (
        hass.states.get(profile_entities[CONF_MANUFACTURER].entity_id).state
        == "Prevost"
    )


async def test_setup_creates_system_device_and_mirrors_source_sensor(
    hass: HomeAssistant,
) -> None:
    """Create a grouped system device and mirror source sensor state."""
    hass.states.async_set(
        "sensor.house_battery_voltage",
        "13.4",
        {"friendly_name": "House Battery Voltage", "unit_of_measurement": "V"},
    )
    hass.states.async_set("binary_sensor.fresh_water_low", "off")
    hass.states.async_set("switch.water_pump", "off")
    hass.states.async_set(
        "light.patio",
        "off",
        {"supported_color_modes": ["onoff"]},
    )
    hass.states.async_set(
        "climate.cabin",
        "off",
        {"hvac_modes": ["off", "heat"], "supported_features": 0},
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Adventure RV",
        unique_id="adventure rv",
        data={
            CONF_NAME: "Adventure RV",
            CONF_ENTITY_MAPPINGS: {
                "power": ["sensor.house_battery_voltage"],
                "water": [
                    "binary_sensor.fresh_water_low",
                    "switch.water_pump",
                ],
                "chassis": ["light.patio"],
                "climate": ["climate.cabin"],
            },
        },
        version=3,
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    mapped_entities = er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    assert len(mapped_entities) == 7
    mapped_entity = next(
        entity
        for entity in mapped_entities
        if entity.unique_id.endswith("sensor.house_battery_voltage")
    )
    assert hass.states.get(mapped_entity.entity_id).state == "13.4"

    device_registry = dr.async_get(hass)
    devices = dr.async_entries_for_config_entry(device_registry, entry.entry_id)
    assert {device.name for device in devices} == {
        "Adventure RV",
        "Power",
        "Water",
        "Chassis",
        "Climate",
    }
    system_device = next(device for device in devices if device.name == "Power")
    parent_device = next(device for device in devices if device.name == "Adventure RV")
    assert system_device.via_device_id == parent_device.id

    hass.states.async_set(
        "sensor.house_battery_voltage",
        "13.6",
        {"friendly_name": "House Battery Voltage", "unit_of_measurement": "V"},
    )
    await hass.async_block_till_done()
    assert hass.states.get(mapped_entity.entity_id).state == "13.6"
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_removed_system_mapping_removes_its_stale_device(
    hass: HomeAssistant,
) -> None:
    """Remove a child device and mapped entity when its group is deselected."""
    hass.states.async_set("sensor.house_battery_voltage", "13.4")
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Adventure RV",
        unique_id="adventure rv",
        data={
            CONF_NAME: "Adventure RV",
            CONF_ENTITY_MAPPINGS: {"power": ["sensor.house_battery_voltage"]},
        },
        version=3,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)

    form = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        form["flow_id"], user_input={"power_entities": []}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert {device.name for device in devices} == {"Adventure RV"}
    assert not any(
        entity.unique_id.endswith("sensor.house_battery_voltage")
        for entity in er.async_entries_for_config_entry(
            er.async_get(hass), entry.entry_id
        )
    )
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_reconfigure_removes_obsolete_tire_devices(
    hass: HomeAssistant,
) -> None:
    """Remove tire registry entries and devices when axle topology shrinks."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Adventure RV",
        unique_id="adventure rv",
        data={
            CONF_NAME: "Adventure RV",
            CONF_REAR_AXLE_COUNT: 2,
            CONF_MAIN_REAR_WHEEL_CONFIGURATION: "single",
            CONF_TAG_AXLE_PRESENT: True,
            CONF_TAG_AXLE_WHEEL_CONFIGURATION: "single",
        },
        version=3,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    form = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": "reconfigure",
            "entry_id": entry.entry_id,
        },
    )
    result = await hass.config_entries.flow.async_configure(
        form["flow_id"],
        user_input={
            CONF_REAR_AXLE_COUNT: "one",
            CONF_MAIN_REAR_WHEEL_CONFIGURATION: "single",
        },
    )
    assert result["type"] is FlowResultType.ABORT, result
    await hass.async_block_till_done()

    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert {device.name for device in devices} == {
        "Adventure RV",
        "All Tire Monitor",
        "Front Left Tire",
        "Front Right Tire",
        "Rear Axle 1 Left Tire",
        "Rear Axle 1 Right Tire",
    }
    assert not any(
        entity.unique_id.startswith(f"{entry.entry_id}_tire_tag_axle_")
        for entity in er.async_entries_for_config_entry(
            er.async_get(hass), entry.entry_id
        )
    )
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_setup_creates_tire_devices_readings_and_problem_sensors(
    hass: HomeAssistant,
) -> None:
    """Expose each tire position with mirrored readings and diagnostics."""
    hass.states.async_set(
        "sensor.front_left_pressure",
        "35",
        {"unit_of_measurement": "psi", "device_class": "pressure"},
    )
    hass.states.async_set(
        "sensor.front_left_temperature",
        "110",
        {"unit_of_measurement": "°F", "device_class": "temperature"},
    )
    hass.states.async_set(
        "sensor.front_left_battery",
        "15",
        {"unit_of_measurement": "%", "device_class": "battery"},
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Tire RV",
        unique_id="tire rv",
        data={
            CONF_NAME: "Tire RV",
            CONF_MEASUREMENT_SYSTEM: UNIT_SYSTEM_METRIC,
            CONF_REAR_AXLE_COUNT: 1,
            CONF_MAIN_REAR_WHEEL_CONFIGURATION: "single",
        },
        options={
            CONF_TIRE_ENTITY_MAPPINGS: {
                "front_left_pressure": "sensor.front_left_pressure",
                "front_left_temperature": "sensor.front_left_temperature",
                "front_left_battery": "sensor.front_left_battery",
            },
            CONF_TIRE_PRESSURE_THRESHOLDS: {
                "front": {"low": 300, "high": 800},
            },
            CONF_TIRE_TEMPERATURE_HIGH: 40,
            CONF_TIRE_BATTERY_LOW: 20,
        },
        version=3,
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    entities = {
        f"{entity.entity_id.split('.')[0]}:{entity.unique_id}": entity
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    pressure = entities[f"sensor:{entry.entry_id}_tire_front_left_pressure"]
    temperature = entities[f"sensor:{entry.entry_id}_tire_front_left_temperature"]
    battery = entities[f"sensor:{entry.entry_id}_tire_front_left_battery"]
    assert round(float(hass.states.get(pressure.entity_id).state)) == 241
    assert round(float(hass.states.get(temperature.entity_id).state)) == 43
    assert hass.states.get(battery.entity_id).state == "15.0"

    expected_problems = {
        "pressure": True,
        "temperature": True,
        "battery": True,
        "data_present": True,
        "problem": True,
    }
    for problem, expected in expected_problems.items():
        entity = entities[f"binary_sensor:{entry.entry_id}_tire_front_left_{problem}"]
        assert hass.states.get(entity.entity_id).state == ("on" if expected else "off")
        assert entity.entity_category is EntityCategory.DIAGNOSTIC

    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert {device.name for device in devices} == {
        "Tire RV",
        "All Tire Monitor",
        "Front Left Tire",
        "Front Right Tire",
        "Rear Axle 1 Left Tire",
        "Rear Axle 1 Right Tire",
    }
    front_tire = next(device for device in devices if device.name == "Front Left Tire")
    rv_device = next(device for device in devices if device.name == "Tire RV")
    assert front_tire.via_device_id == rv_device.id
    assert await hass.config_entries.async_unload(entry.entry_id)

    assert await hass.config_entries.async_setup(entry.entry_id)
    hass.states.async_set(
        "sensor.front_left_pressure", "60", {"unit_of_measurement": "psi"}
    )
    hass.states.async_set(
        "sensor.front_left_temperature", "100", {"unit_of_measurement": "°F"}
    )
    hass.states.async_set(
        "sensor.front_left_battery", "50", {"unit_of_measurement": "%"}
    )
    await hass.async_block_till_done()
    assert (
        hass.states.get(
            entities[
                f"binary_sensor:{entry.entry_id}_tire_front_left_problem"
            ].entity_id
        ).state
        == "off"
    )
    hass.states.async_set("sensor.front_left_pressure", "unavailable")
    await hass.async_block_till_done()
    assert (
        hass.states.get(
            entities[
                f"binary_sensor:{entry.entry_id}_tire_front_left_data_present"
            ].entity_id
        ).state
        == "off"
    )
    assert hass.states.get(pressure.entity_id).state == "unavailable"
    assert (
        hass.states.get(
            entities[
                f"binary_sensor:{entry.entry_id}_tire_front_left_problem"
            ].entity_id
        ).state
        == "on"
    )
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_tire_sources_and_threshold_changes_reload_and_follow_state(
    hass: HomeAssistant,
) -> None:
    """Apply edited source selections and limits, then follow each new source."""
    hass.states.async_set("sensor.old_pressure", "60", {"unit_of_measurement": "psi"})
    hass.states.async_set(
        "sensor.template_temperature", "30", {"unit_of_measurement": "°C"}
    )
    hass.states.async_set("input_number.tire_battery", "50")
    hass.states.async_set("number.new_pressure", "60", {"unit_of_measurement": "psi"})
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Tire RV",
        unique_id="tire rv",
        data={
            CONF_NAME: "Tire RV",
            CONF_MEASUREMENT_SYSTEM: UNIT_SYSTEM_METRIC,
            CONF_REAR_AXLE_COUNT: 1,
            CONF_MAIN_REAR_WHEEL_CONFIGURATION: "single",
        },
        options={
            CONF_TIRE_ENTITY_MAPPINGS: {
                "front_left_pressure": "sensor.old_pressure",
                "front_left_temperature": "sensor.template_temperature",
                "front_left_battery": "input_number.tire_battery",
            },
            CONF_TIRE_PRESSURE_THRESHOLDS: {
                "front": {"low": 300, "high": 800},
            },
            CONF_TIRE_TEMPERATURE_HIGH: 40,
            CONF_TIRE_BATTERY_LOW: 20,
        },
        version=3,
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)

    def registered_entity(domain: str, unique_id: str) -> er.RegistryEntry:
        return next(
            entity
            for entity in er.async_entries_for_config_entry(registry, entry.entry_id)
            if entity.entity_id.startswith(f"{domain}.")
            and entity.unique_id == unique_id
        )

    pressure = registered_entity("sensor", f"{entry.entry_id}_tire_front_left_pressure")
    temperature_problem = registered_entity(
        "binary_sensor", f"{entry.entry_id}_tire_front_left_temperature"
    )
    battery_problem = registered_entity(
        "binary_sensor", f"{entry.entry_id}_tire_front_left_battery"
    )
    tire_problem = registered_entity(
        "binary_sensor", f"{entry.entry_id}_tire_front_left_problem"
    )
    assert hass.states.get(tire_problem.entity_id).state == "off"

    form = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        form["flow_id"],
        user_input={
            "tire_front_left_pressure": "number.new_pressure",
            "tire_front_pressure_low": 450,
        },
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    assert hass.states.get(tire_problem.entity_id).state == "on"

    hass.states.async_set("number.new_pressure", "70", {"unit_of_measurement": "psi"})
    await hass.async_block_till_done()
    assert hass.states.get(pressure.entity_id).state == "70.0"
    assert hass.states.get(tire_problem.entity_id).state == "off"

    hass.states.async_set("sensor.old_pressure", "10")
    await hass.async_block_till_done()
    assert hass.states.get(pressure.entity_id).state == "70.0"
    assert hass.states.get(tire_problem.entity_id).state == "off"

    hass.states.async_set(
        "sensor.template_temperature", "50", {"unit_of_measurement": "°C"}
    )
    await hass.async_block_till_done()
    assert hass.states.get(tire_problem.entity_id).state == "on"
    assert hass.states.get(temperature_problem.entity_id).state == "on"

    hass.states.async_set("input_number.tire_battery", "10")
    await hass.async_block_till_done()
    assert hass.states.get(battery_problem.entity_id).state == "on"
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_options_reload_adds_platform_to_existing_entry(
    hass: HomeAssistant,
) -> None:
    """Reload a configured profile when a platform is mapped later."""
    hass.states.async_set("sensor.rv_battery", "12.8")
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Adventure RV",
        unique_id="adventure rv",
        data={CONF_NAME: "Adventure RV"},
        version=3,
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    assert len(entry.runtime_data.platforms) == 1
    assert entry.runtime_data.platforms[0].value == "sensor"

    form = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        form["flow_id"],
        user_input={"power_entities": ["sensor.rv_battery"]},
    )
    await hass.async_block_till_done()

    assert entry.runtime_data.platforms
    mapped_entities = er.async_entries_for_config_entry(
        er.async_get(hass), entry.entry_id
    )
    mapped_source_sensor = next(
        entity
        for entity in mapped_entities
        if entity.unique_id.endswith("sensor.rv_battery")
    )
    assert hass.states.get(mapped_source_sensor.entity_id).state == "12.8"
    assert {
        device.name
        for device in dr.async_entries_for_config_entry(
            dr.async_get(hass), entry.entry_id
        )
    } == {"Adventure RV", "Power"}
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_setup_creates_only_selected_tank_devices_and_optional_capacities(
    hass: HomeAssistant,
) -> None:
    """Create configured tank devices without assuming every tank exists."""
    hass.states.async_set(
        "sensor.fresh_water_level",
        "72",
        {"friendly_name": "Fresh water", "unit_of_measurement": "%"},
    )
    hass.states.async_set(
        "sensor.gray_water_level",
        "35",
        {"unit_of_measurement": "%"},
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Adventure RV",
        unique_id="adventure rv",
        data={
            CONF_NAME: "Adventure RV",
            CONF_MEASUREMENT_SYSTEM: UNIT_SYSTEM_METRIC,
            CONF_ENTITY_MAPPINGS: {
                "water": ["sensor.fresh_water_level"],
            },
            CONF_FRESH_WATER_TANK_CAPACITY: 400.0,
            CONF_BLACK_WATER_TANK_CAPACITY: 120.0,
        },
        options={
            CONF_TANK_ENTITY_MAPPINGS: {
                "fresh_water": "sensor.fresh_water_level",
                "gray_water": "sensor.gray_water_level",
            },
        },
        version=3,
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    level_entities = {
        entity.unique_id: entity
        for entity in entities
        if "_tank_" in entity.unique_id and entity.unique_id.endswith("_level")
    }
    assert set(level_entities) == {
        f"{entry.entry_id}_tank_fresh_water_level",
        f"{entry.entry_id}_tank_gray_water_level",
    }
    fresh_level = level_entities[f"{entry.entry_id}_tank_fresh_water_level"]
    assert hass.states.get(fresh_level.entity_id).state == "72.0"
    assert (
        hass.states.get(fresh_level.entity_id).attributes["unit_of_measurement"] == "%"
    )

    capacity = next(
        entity
        for entity in entities
        if entity.unique_id == f"{entry.entry_id}_tank_fresh_water_capacity"
    )
    capacity_state = hass.states.get(capacity.entity_id)
    assert capacity_state.state == "400.0"
    assert capacity_state.attributes["unit_of_measurement"] == "L"
    assert not any(
        entity.unique_id == f"{entry.entry_id}_tank_gray_water_capacity"
        for entity in entities
    )
    assert not any(
        entity.unique_id == f"{entry.entry_id}_tank_black_water_level"
        for entity in entities
    )

    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert {device.name for device in devices} == {
        "Adventure RV",
        "Fresh-water tank",
        "Gray-water tank",
        "Water",
    }
    rv_device = next(device for device in devices if device.name == "Adventure RV")
    assert all(
        device.via_device_id == rv_device.id
        for device in devices
        if device.name != "Adventure RV"
    )
    assert fresh_level.device_id == next(
        device.id for device in devices if device.name == "Fresh-water tank"
    )
    assert any(
        entity.unique_id == f"{entry.entry_id}_water_sensor.fresh_water_level"
        for entity in entities
    )

    hass.states.async_set("sensor.fresh_water_level", "68")
    await hass.async_block_till_done()
    assert hass.states.get(fresh_level.entity_id).state == "68.0"
    assert await hass.config_entries.async_unload(entry.entry_id)
