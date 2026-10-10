"""Config flow for HAVRV."""

import math
from datetime import date
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.util.unit_system import METRIC_SYSTEM, US_CUSTOMARY_SYSTEM

from .const import (
    AXLE_COUNT_ONE,
    AXLE_COUNT_TWO,
    CONF_BLACK_WATER_TANK_CAPACITY,
    CONF_COACH_BUILDER,
    CONF_COACH_IDENTIFIER,
    CONF_COACH_YEAR,
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
    DOMAIN,
    UNIT_SYSTEM_METRIC,
    UNIT_SYSTEM_US_CUSTOMARY,
    WHEEL_CONFIGURATION_DUAL,
    WHEEL_CONFIGURATION_SINGLE,
)

_PROFILE_TEXT_FIELDS = (
    CONF_MANUFACTURER,
    CONF_COACH_BUILDER,
    CONF_MAKE,
    CONF_MODEL,
    CONF_COACH_IDENTIFIER,
)
_MEASUREMENT_FIELDS = (
    CONF_OVERALL_HEIGHT,
    CONF_OVERALL_LENGTH,
    CONF_OVERALL_WIDTH,
    CONF_FUEL_TANK_CAPACITY,
    CONF_FRESH_WATER_TANK_CAPACITY,
    CONF_GRAY_WATER_TANK_CAPACITY,
    CONF_BLACK_WATER_TANK_CAPACITY,
)
_UNIT_SYSTEMS = {UNIT_SYSTEM_METRIC, UNIT_SYSTEM_US_CUSTOMARY}
_WHEEL_CONFIGURATIONS = {
    WHEEL_CONFIGURATION_SINGLE,
    WHEEL_CONFIGURATION_DUAL,
}


class HavrvConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HAVRV."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            raw_name = user_input[CONF_NAME]
            if not isinstance(raw_name, str) or not (name := raw_name.strip()):
                errors["base"] = "name_required"
            else:
                profile, error = _normalize_profile(
                    user_input,
                    default_measurement_system=_default_measurement_system(self.hass),
                )
                if error:
                    errors["base"] = error
                else:
                    await self.async_set_unique_id(name.casefold())
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(title=name, data=profile)

        return self.async_show_form(
            step_id="user",
            data_schema=_profile_schema(
                default_measurement_system=_default_measurement_system(self.hass)
            ),
            errors=errors,
        )


def _default_measurement_system(hass: HomeAssistant) -> str:
    """Use Home Assistant's configured unit system when it is supported."""
    if hass.config.units == METRIC_SYSTEM:
        return UNIT_SYSTEM_METRIC
    if hass.config.units == US_CUSTOMARY_SYSTEM:
        return UNIT_SYSTEM_US_CUSTOMARY
    return UNIT_SYSTEM_METRIC


def _profile_schema(*, default_measurement_system: str) -> vol.Schema:
    """Build the RV profile form schema."""
    numeric_selector = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0,
            step=0.1,
            mode=selector.NumberSelectorMode.BOX,
        )
    )
    wheel_selector = selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=sorted(_WHEEL_CONFIGURATIONS),
            mode=selector.SelectSelectorMode.DROPDOWN,
            translation_key="wheel_configuration",
        )
    )

    schema: dict[vol.Marker, Any] = {
        vol.Required(CONF_NAME, default="My RV"): selector.TextSelector(),
        vol.Optional(CONF_COACH_YEAR): selector.NumberSelector(
            selector.NumberSelectorConfig(
                step=1,
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
    }
    schema.update(
        {vol.Optional(field): selector.TextSelector() for field in _PROFILE_TEXT_FIELDS}
    )
    schema.update(
        {
            vol.Optional(
                CONF_MEASUREMENT_SYSTEM, default=default_measurement_system
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=sorted(_UNIT_SYSTEMS),
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    translation_key="measurement_system",
                )
            ),
            vol.Optional(CONF_STORAGE_ZONE_ID): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="zone")
            ),
        }
    )
    schema.update(
        {vol.Optional(field): numeric_selector for field in _MEASUREMENT_FIELDS}
    )
    schema.update(
        {
            vol.Optional(CONF_REAR_AXLE_COUNT): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[AXLE_COUNT_ONE, AXLE_COUNT_TWO],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    translation_key="rear_axle_count",
                )
            ),
            vol.Optional(CONF_MAIN_REAR_WHEEL_CONFIGURATION): wheel_selector,
            vol.Optional(
                CONF_TAG_AXLE_PRESENT, default=False
            ): selector.BooleanSelector(),
            vol.Optional(CONF_TAG_AXLE_WHEEL_CONFIGURATION): wheel_selector,
        }
    )
    return vol.Schema(schema)


def _normalize_profile(
    user_input: dict[str, Any], *, default_measurement_system: str
) -> tuple[dict[str, Any], str | None]:
    """Validate and normalize submitted RV profile values."""
    name = user_input[CONF_NAME].strip()
    data: dict[str, Any] = {CONF_NAME: name}

    measurement_system = user_input.get(
        CONF_MEASUREMENT_SYSTEM, default_measurement_system
    )
    data[CONF_MEASUREMENT_SYSTEM] = measurement_system

    coach_year = user_input.get(CONF_COACH_YEAR)
    if coach_year is not None:
        if (
            not math.isfinite(coach_year)
            or not float(coach_year).is_integer()
            or not 1900 <= coach_year <= date.today().year + 1
        ):
            return data, "invalid_coach_year"
        data[CONF_COACH_YEAR] = int(coach_year)

    for field in _PROFILE_TEXT_FIELDS:
        value = user_input.get(field)
        if value is not None:
            if clean_value := value.strip():
                data[field] = clean_value

    zone_id = user_input.get(CONF_STORAGE_ZONE_ID)
    if zone_id is not None:
        if clean_zone_id := zone_id.strip():
            data[CONF_STORAGE_ZONE_ID] = clean_zone_id

    for field in _MEASUREMENT_FIELDS:
        value = user_input.get(field)
        if value is not None:
            if not math.isfinite(value) or value <= 0:
                return data, "invalid_measurement"
            data[field] = float(value)

    rear_axle_count = user_input.get(CONF_REAR_AXLE_COUNT)
    if rear_axle_count is not None:
        data[CONF_REAR_AXLE_COUNT] = 1 if rear_axle_count == AXLE_COUNT_ONE else 2

    tag_axle_present = user_input.get(CONF_TAG_AXLE_PRESENT, False)
    data[CONF_TAG_AXLE_PRESENT] = tag_axle_present

    tag_wheel_configuration = user_input.get(CONF_TAG_AXLE_WHEEL_CONFIGURATION)
    if tag_axle_present:
        if tag_wheel_configuration is None:
            return data, "tag_axle_wheel_configuration_required"
        data[CONF_TAG_AXLE_WHEEL_CONFIGURATION] = tag_wheel_configuration
    elif tag_wheel_configuration is not None:
        return data, "tag_wheel_configuration_without_tag_axle"

    main_wheel_configuration = user_input.get(CONF_MAIN_REAR_WHEEL_CONFIGURATION)
    if main_wheel_configuration is not None:
        data[CONF_MAIN_REAR_WHEEL_CONFIGURATION] = main_wheel_configuration

    return data, None
