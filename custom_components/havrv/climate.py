"""Climate platform for mapped HAVRV source entities."""

from collections.abc import Callable
from typing import Any

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import ClimateEntityFeature, HVACMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity

from .entity import HavrvSourceEntity, async_add_source_entities

PARALLEL_UPDATES = 0


class HavrvClimate(HavrvSourceEntity, ClimateEntity):
    """Expose and control a mapped source climate entity."""

    @property
    def name(self) -> str | None:
        """Return the source climate name."""
        return self.source_name

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return the source HVAC mode."""
        state = self._source_state
        if state is None or not self.available:
            return None
        try:
            return HVACMode(state.state)
        except ValueError:
            return None

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return the source HVAC modes."""
        modes = self.source_attributes.get("hvac_modes", [])
        if not isinstance(modes, list):
            return []
        valid_modes = []
        for mode in modes:
            if isinstance(mode, str):
                try:
                    valid_modes.append(HVACMode(mode))
                except ValueError:
                    continue
        return valid_modes

    @property
    def current_temperature(self) -> float | None:
        """Return the current source temperature."""
        return self._float_attribute("current_temperature")

    @property
    def current_humidity(self) -> int | None:
        """Return the current source humidity."""
        value = self.source_attributes.get("current_humidity")
        return value if isinstance(value, int) else None

    @property
    def icon(self) -> str | None:
        """Return the source icon."""
        return self.source_icon

    @property
    def target_temperature(self) -> float | None:
        """Return the source target temperature."""
        return self._float_attribute("temperature")

    @property
    def target_temperature_high(self) -> float | None:
        """Return the source high target temperature."""
        return self._float_attribute("target_temp_high")

    @property
    def target_temperature_low(self) -> float | None:
        """Return the source low target temperature."""
        return self._float_attribute("target_temp_low")

    @property
    def fan_mode(self) -> str | None:
        """Return the source fan mode."""
        return self.source_attributes.get("fan_mode")

    @property
    def fan_modes(self) -> list[str] | None:
        """Return the source fan modes."""
        modes = self.source_attributes.get("fan_modes")
        return (
            [mode for mode in modes if isinstance(mode, str)]
            if isinstance(modes, list)
            else None
        )

    @property
    def min_temp(self) -> float:
        """Return the source minimum temperature."""
        value = self._float_attribute("min_temp")
        return 7 if value is None else value

    @property
    def max_temp(self) -> float:
        """Return the source maximum temperature."""
        value = self._float_attribute("max_temp")
        return 35 if value is None else value

    @property
    def target_temperature_step(self) -> float | None:
        """Return the source target temperature step."""
        return self._float_attribute("target_temp_step")

    @property
    def temperature_unit(self) -> str:
        """Return the source temperature unit."""
        unit = self.source_attributes.get("temperature_unit")
        return (
            unit if isinstance(unit, str) else self.hass.config.units.temperature_unit
        )

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Return the source climate features."""
        return ClimateEntityFeature(self.source_attributes.get("supported_features", 0))

    @property
    def preset_mode(self) -> str | None:
        """Return the source preset mode."""
        return self.source_attributes.get("preset_mode")

    @property
    def preset_modes(self) -> list[str] | None:
        """Return the source preset modes."""
        return self.source_attributes.get("preset_modes")

    @property
    def swing_mode(self) -> str | None:
        """Return the source swing mode."""
        return self.source_attributes.get("swing_mode")

    @property
    def swing_modes(self) -> list[str] | None:
        """Return the source swing modes."""
        return self.source_attributes.get("swing_modes")

    @property
    def target_humidity(self) -> int | None:
        """Return the source target humidity."""
        value = self.source_attributes.get("humidity")
        return value if isinstance(value, int) else None

    @property
    def min_humidity(self) -> int:
        """Return the source minimum humidity."""
        value = self.source_attributes.get("min_humidity")
        return value if isinstance(value, int) else 30

    @property
    def max_humidity(self) -> int:
        """Return the source maximum humidity."""
        value = self.source_attributes.get("max_humidity")
        return value if isinstance(value, int) else 99

    def _float_attribute(self, key: str) -> float | None:
        """Return a numeric source attribute, excluding booleans."""
        value = self.source_attributes.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return float(value)

    async def async_set_hvac_mode(self, hvac_mode: str) -> None:
        """Set the source HVAC mode."""
        await self._async_call("set_hvac_mode", {"hvac_mode": hvac_mode})

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the source target temperature."""
        await self._async_call("set_temperature", kwargs)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set the source fan mode."""
        await self._async_call("set_fan_mode", {"fan_mode": fan_mode})

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the source preset mode."""
        await self._async_call("set_preset_mode", {"preset_mode": preset_mode})

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set the source swing mode."""
        await self._async_call("set_swing_mode", {"swing_mode": swing_mode})

    async def async_set_humidity(self, humidity: int) -> None:
        """Set the source target humidity."""
        await self._async_call("set_humidity", {"humidity": humidity})

    async def _async_call(self, service: str, service_data: dict[str, Any]) -> None:
        await self.hass.services.async_call(
            "climate",
            service,
            {"entity_id": self._source_entity_id, **service_data},
            blocking=True,
        )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: Callable[[list[Entity]], None],
) -> None:
    """Set up mapped climate entities."""
    async_add_source_entities(entry, "climate", HavrvClimate, async_add_entities)
