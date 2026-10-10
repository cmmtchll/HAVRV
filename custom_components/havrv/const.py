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
CONF_REAR_AXLE_COUNT = "rear_axle_count"
CONF_MAIN_REAR_WHEEL_CONFIGURATION = "main_rear_wheel_configuration"
CONF_TAG_AXLE_PRESENT = "tag_axle_present"
CONF_TAG_AXLE_WHEEL_CONFIGURATION = "tag_axle_wheel_configuration"
CONF_ENTITY_MAPPINGS = "entity_mappings"

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

WHEEL_CONFIGURATION_SINGLE = "single"
WHEEL_CONFIGURATION_DUAL = "dual"
