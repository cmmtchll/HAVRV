"""Select platform for the HAVRV Operations device."""

from collections.abc import Callable

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.restore_state import RestoreEntity

from . import HavrvConfigEntry
from .const import DOMAIN, OPERATION_MODES, SIGNAL_OPERATION_MODE_CHANGED

PARALLEL_UPDATES = 0


def operations_device_info(entry: HavrvConfigEntry) -> DeviceInfo:
    """Return stable device information for the Operations device."""
    parent_device_id = entry.runtime_data.device_id
    if parent_device_id is None:
        raise RuntimeError("RV device must be registered before platform setup")
    return {
        "identifiers": {(DOMAIN, f"{entry.entry_id}_operations")},
        "name": "Operations",
        "via_device_id": parent_device_id,
    }


class HavrvOperationModeSelect(SelectEntity, RestoreEntity):
    """Let the user choose the RV's current operation mode."""

    _attr_has_entity_name = True
    entity_description = SelectEntityDescription(
        key="operation_mode",
        translation_key="operation_mode",
        options=list(OPERATION_MODES),
    )

    def __init__(self, entry: HavrvConfigEntry) -> None:
        """Initialize the operation-mode selector."""
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_operations_mode"
        self._attr_device_info = operations_device_info(entry)

    @property
    def current_option(self) -> str | None:
        """Return the selected operation mode, or None until one is chosen."""
        return self._entry.runtime_data.operation_mode

    async def async_select_option(self, option: str) -> None:
        """Change the operation mode and notify mode-aware entities."""
        self._set_mode(option)
        self.async_write_ha_state()

    def _set_mode(self, option: str | None) -> None:
        """Store the mode and signal entities that depend on it."""
        self._entry.runtime_data.operation_mode = option
        async_dispatcher_send(
            self.hass, SIGNAL_OPERATION_MODE_CHANGED.format(self._entry.entry_id)
        )

    async def async_added_to_hass(self) -> None:
        """Restore the last selected operation mode."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state in OPERATION_MODES:
            self._set_mode(last_state.state)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HavrvConfigEntry,
    async_add_entities: Callable[[list[Entity]], None],
) -> None:
    """Set up the Operations device entities."""
    async_add_entities([HavrvOperationModeSelect(entry)])
