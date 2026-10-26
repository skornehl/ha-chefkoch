"""Select a recipe from the Kochbuch; choosing one loads it for cooking."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ChefkochConfigEntry
from .coordinator import CookbookCoordinator, CookingSession


async def async_setup_entry(
    hass: HomeAssistant, entry: ChefkochConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = entry.runtime_data
    async_add_entities([RecipeSelect(data.coordinator, data.session)])


class RecipeSelect(CoordinatorEntity[CookbookCoordinator], SelectEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "kochbuch_auswahl"
    _attr_icon = "mdi:book-search"
    _unrecorded_attributes = frozenset({"options"})

    def __init__(self, coordinator: CookbookCoordinator, session: CookingSession) -> None:
        super().__init__(coordinator)
        self._session = session
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_auswahl"
        self._attr_device_info = coordinator.device_info

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._session.async_add_listener(self._session_changed))

    @callback
    def _session_changed(self) -> None:
        self.async_write_ha_state()

    @property
    def options(self) -> list[str]:
        return list(self.coordinator.titles())

    @property
    def current_option(self) -> str | None:
        if not self._session.recipe:
            return None
        for title, rid in self.coordinator.titles().items():
            if rid == self._session.recipe.id:
                return title
        return None

    async def async_select_option(self, option: str) -> None:
        await self._session.load(self.coordinator.titles()[option])
