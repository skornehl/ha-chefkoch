"""Cooking-mode buttons and a Kochbuch refresh."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ChefkochConfigEntry
from .coordinator import CookbookCoordinator, CookingSession

BUTTONS = {
    "weiter": ("mdi:arrow-right-bold", lambda s, c: s.move(1)),
    "zurueck": ("mdi:arrow-left-bold", lambda s, c: s.move(-1)),
    "von_vorn": ("mdi:restart", lambda s, c: s.restart()),
    "beenden": ("mdi:stop", lambda s, c: s.stop()),
    "kochbuch_aktualisieren": ("mdi:refresh", lambda s, c: c.async_request_refresh()),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ChefkochConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = entry.runtime_data
    async_add_entities(CookingButton(data.coordinator, data.session, key) for key in BUTTONS)


class CookingButton(ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: CookbookCoordinator, session: CookingSession, key: str) -> None:
        self._coordinator = coordinator
        self._session = session
        self._key = key
        self._attr_translation_key = key
        self._attr_icon = BUTTONS[key][0]
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{key}"
        self._attr_device_info = coordinator.device_info

    async def async_press(self) -> None:
        await BUTTONS[self._key][1](self._session, self._coordinator)
