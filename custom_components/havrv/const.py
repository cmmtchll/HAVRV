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
CONF_TIRE_ENTITY_MAPPINGS = "tire_entity_mappings"
CONF_TIRE_PRESSURE_THRESHOLDS = "tire_pressure_thresholds"
CONF_TIRE_TEMPERATURE_HIGH = "tire_temperature_high"
CONF_TIRE_BATTERY_LOW = "tire_battery_low"

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
TIRE_SUDDEN_DROP_WINDOW_SECONDS = 600
TIRE_SUDDEN_DROP_MIN_SPAN_SECONDS = 120
TIRE_SUDDEN_DROP_FRACTION = 0.08
TIRE_SLOW_LOSS_WINDOW_SECONDS = 43200
TIRE_SLOW_LOSS_MIN_SPAN_SECONDS = 14400
TIRE_SLOW_LOSS_MIN_SAMPLES = 3
TIRE_SLOW_LOSS_FRACTION = 0.03
