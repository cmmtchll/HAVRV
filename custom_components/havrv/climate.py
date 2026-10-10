"""Climate platform for mapped HAVRV source entities."""

from collections.abc import Callable
from typing import Any

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature
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
        return self.source_attributes.get("friendly_name", self._source_entity_id)

    @property
    def hvac_mode(self) -> str | None:
        """Return the source HVAC mode."""
        return self._source_state.state if self.available else None

    @property
    def hvac_modes(self) -> list[str]:
        """Return the source HVAC modes."""
        return self.source_attributes.get("hvac_modes", [])

    @property
    def current_temperature(self) -> float | None:
        """Return the current source temperature."""
        return self.source_attributes.get("current_temperature")

    @property
    def current_humidity(self) -> int | None:
        """Return the current source humidity."""
        return self.source_attributes.get("current_humidity")

    @property
    def icon(self) -> str | None:
        """Return the source icon."""
        return self.source_attributes.get("icon")

    @property
    def target_temperature(self) -> float | None:
        """Return the source target temperature."""
        return self.source_attributes.get("temperature")

    @property
    def target_temperature_high(self) -> float | None:
        """Return the source high target temperature."""
        return self.source_attributes.get("target_temp_high")

    @property
    def target_temperature_low(self) -> float | None:
        """Return the source low target temperature."""
        return self.source_attributes.get("target_temp_low")

    @property
    def fan_mode(self) -> str | None:
        """Return the source fan mode."""
        return self.source_attributes.get("fan_mode")

    @property
    def fan_modes(self) -> list[str] | None:
        """Return the source fan modes."""
        return self.source_attributes.get("fan_modes")

    @property
    def min_temp(self) -> float:
        """Return the source minimum temperature."""
        return self.source_attributes.get("min_temp", 7)

    @property
    def max_temp(self) -> float:
        """Return the source maximum temperature."""
        return self.source_attributes.get("max_temp", 35)

    @property
    def target_temperature_step(self) -> float | None:
        """Return the source target temperature step."""
        return self.source_attributes.get("target_temp_step")

    @property
    def temperature_unit(self) -> str | None:
        """Return the source temperature unit."""
        return self.source_attributes.get(
            "temperature_unit", self.hass.config.units.temperature_unit
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
        return self.source_attributes.get("humidity")

    @property
    def min_humidity(self) -> int:
        """Return the source minimum humidity."""
        return self.source_attributes.get("min_humidity", 30)

    @property
    def max_humidity(self) -> int:
        """Return the source maximum humidity."""
        return self.source_attributes.get("max_humidity", 99)

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
