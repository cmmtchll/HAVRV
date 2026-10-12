"""Constants for the HAVRV integration."""

DOMAIN = "havrv"

CONF_COACH_YEAR = "coach_year"
CONF_MANUFACTURER = "manufacturer"
CONF_COACH_BUILDER = "coach_builder"
CONF_MAKE = "make"
CONF_MODEL = "model"
CONF_COACH_IDENTIFIER = "coach_identifier"
CONF_STORAGE_ZONE_ID = "storage_zone_id"
CONF_MEASUREMENT_SYSTEM = "measurement_system"
CONF_OVERALL_HEIGHT = "overall_height"
CONF_OVERALL_LENGTH = "overall_length"
CONF_OVERALL_WIDTH = "overall_width"
CONF_FUEL_TANK_CAPACITY = "fuel_tank_capacity"
CONF_FRESH_WATER_TANK_CAPACITY = "fresh_water_tank_capacity"
CONF_GRAY_WATER_TANK_CAPACITY = "gray_water_tank_capacity"
CONF_BLACK_WATER_TANK_CAPACITY = "black_water_tank_capacity"
CONF_TANK_ENTITY_MAPPINGS = "tank_entity_mappings"
CONF_TANK_THRESHOLDS = "tank_thresholds"
CONF_REAR_AXLE_COUNT = "rear_axle_count"
CONF_MAIN_REAR_WHEEL_CONFIGURATION = "main_rear_wheel_configuration"
CONF_TAG_AXLE_PRESENT = "tag_axle_present"
CONF_TAG_AXLE_WHEEL_CONFIGURATION = "tag_axle_wheel_configuration"
CONF_ENTITY_MAPPINGS = "entity_mappings"
CONF_TIRE_ENTITY_MAPPINGS = "tire_entity_mappings"
CONF_TIRE_PRESSURE_THRESHOLDS = "tire_pressure_thresholds"
CONF_TIRE_TEMPERATURE_HIGH = "tire_temperature_high"
CONF_TIRE_BATTERY_LOW = "tire_battery_low"
CONF_HOUSE_BATTERY_BANK_COUNT = "house_battery_bank_count"
CONF_CHASSIS_BATTERY_BANK_COUNT = "chassis_battery_bank_count"
CONF_POWER_SOURCES = "power_sources"
CONF_CONFIGURE_POWER_SOURCES = "configure_power_sources"
DEFAULT_BATTERY_BANK_COUNT = 1
DEFAULT_BATTERY_NOMINAL_VOLTAGE = 24
POWER_LOCATIONS = (
    "not_shown",
    "left_front",
    "left_mid",
    "left_rear",
    "right_front",
    "right_mid",
    "right_rear",
)
SHORE_LOCATIONS = ("not_shown", "left", "right")

TANK_FRESH_WATER = "fresh_water"
TANK_GRAY_WATER = "gray_water"
TANK_BLACK_WATER = "black_water"
TANK_TYPES = (TANK_FRESH_WATER, TANK_GRAY_WATER, TANK_BLACK_WATER)
TANK_WARNING = "warning"
TANK_PROBLEM = "problem"
# Percent levels used to recognize a tank having been emptied or filled.
TANK_EMPTY_PERCENT = 5.0
TANK_FULL_PERCENT = 95.0

OPERATION_MODE_STORAGE = "storage"
OPERATION_MODE_DRIVING = "driving"
OPERATION_MODE_CAMPSITE_FULL_SERVICE = "campsite_full_service"
OPERATION_MODE_CAMPSITE_MINIMAL = "campsite_minimal"
OPERATION_MODE_MAINTENANCE = "maintenance"
OPERATION_MODES = (
    OPERATION_MODE_STORAGE,
    OPERATION_MODE_DRIVING,
    OPERATION_MODE_CAMPSITE_FULL_SERVICE,
    OPERATION_MODE_CAMPSITE_MINIMAL,
    OPERATION_MODE_MAINTENANCE,
)

UNIT_SYSTEM_METRIC = "metric"
UNIT_SYSTEM_US_CUSTOMARY = "us_customary"

SYSTEM_POWER = "power"
SYSTEM_WATER = "water"
SYSTEM_CHASSIS = "chassis"
SYSTEM_CLIMATE = "climate"
SYSTEM_LOCATION = "location"
SYSTEM_OTHER = "other"
SYSTEM_CATEGORIES = (
    SYSTEM_POWER,
    SYSTEM_WATER,
    SYSTEM_CHASSIS,
    SYSTEM_CLIMATE,
    SYSTEM_LOCATION,
    SYSTEM_OTHER,
)

SUPPORTED_ENTITY_DOMAINS = ("sensor", "binary_sensor", "switch", "light", "climate")

AXLE_COUNT_ONE = "one"
AXLE_COUNT_TWO = "two"
AXLE_COUNT_THREE = "three"

WHEEL_CONFIGURATION_SINGLE = "single"
WHEEL_CONFIGURATION_DUAL = "dual"

TIRE_FRONT = "front"
TIRE_AXLE = "axle"
TIRE_TAG = "tag"
TIRE_PRESSURE = "pressure"
TIRE_TEMPERATURE = "temperature"
TIRE_BATTERY = "battery"
TIRE_METRICS = (TIRE_PRESSURE, TIRE_TEMPERATURE, TIRE_BATTERY)
TIRE_PRESSURE_LOW = "low"
TIRE_PRESSURE_HIGH = "high"
CONF_TIRE_PRESSURE_LOW = TIRE_PRESSURE_LOW
CONF_TIRE_PRESSURE_HIGH = TIRE_PRESSURE_HIGH

TIRE_SUDDEN_DROP = "pressure_sudden_drop"
TIRE_SLOW_LOSS = "pressure_slow_loss"
# Built-in trend limits are intentionally conservative and not user-configurable.
TIRE_SUDDEN_DROP_WINDOW_SECONDS = 300
TIRE_SUDDEN_DROP_MIN_SPAN_SECONDS = 120
TIRE_SUDDEN_DROP_FRACTION = 0.08
TIRE_SLOW_LOSS_WINDOW_SECONDS = 43200
TIRE_SLOW_LOSS_MIN_SPAN_SECONDS = 14400
TIRE_SLOW_LOSS_MIN_SAMPLES = 3
TIRE_SLOW_LOSS_FRACTION = 0.03

# Default alert thresholds as (warning, problem) percent per tank type.
DEFAULT_TANK_THRESHOLDS = {
    TANK_FRESH_WATER: (50.0, 25.0),
    TANK_GRAY_WATER: (50.0, 75.0),
    TANK_BLACK_WATER: (50.0, 75.0),
}
# Tire defaults are 100/150 psi and 150 F, in each profile unit system.
DEFAULT_TIRE_PRESSURE = {
    UNIT_SYSTEM_US_CUSTOMARY: (100.0, 150.0),
    UNIT_SYSTEM_METRIC: (689.5, 1034.2),
}
DEFAULT_TIRE_TEMPERATURE_HIGH = {
    UNIT_SYSTEM_US_CUSTOMARY: 150.0,
    UNIT_SYSTEM_METRIC: 65.6,
}
DEFAULT_TIRE_BATTERY_LOW = 20.0
