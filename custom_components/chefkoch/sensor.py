"""Sensors: Kochbuch size, the loaded recipe, the current cooking step."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ChefkochConfigEntry
from .api import step_minutes
from .coordinator import CookbookCoordinator, CookingSession


async def async_setup_entry(
    hass: HomeAssistant, entry: ChefkochConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = entry.runtime_data
    async_add_entities(
        [
            CookbookSensor(data.coordinator),
            RecipeSensor(data.coordinator, data.session),
            StepSensor(data.coordinator, data.session),
        ]
    )


class CookbookSensor(CoordinatorEntity[CookbookCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "kochbuch"
    _attr_icon = "mdi:book-open-page-variant"
    _attr_native_unit_of_measurement = "Rezepte"
    # The full list is useful for templates but far too big for the recorder.
    _unrecorded_attributes = frozenset({"rezepte"})

    def __init__(self, coordinator: CookbookCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_kochbuch"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data or [])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"rezepte": [{"id": r.id, "title": r.title} for r in self.coordinator.data or []]}


class SessionEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: CookbookCoordinator, session: CookingSession, key: str) -> None:
        self._session = session
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{key}"
        self._attr_device_info = coordinator.device_info
        self._attr_translation_key = key

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._session.async_add_listener(self._update))

    @callback
    def _update(self) -> None:
        self.async_write_ha_state()


class RecipeSensor(SessionEntity, SensorEntity):
    _attr_icon = "mdi:chef-hat"
    _unrecorded_attributes = frozenset({"zutaten", "schritte"})

    def __init__(self, coordinator, session) -> None:
        super().__init__(coordinator, session, "rezept")

    @property
    def native_value(self) -> str | None:
        return self._session.recipe.title[:255] if self._session.recipe else None

    @property
    def entity_picture(self) -> str | None:
        return self._session.recipe.image if self._session.recipe else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        r = self._session.recipe
        if not r:
            return {}
        return {
            "rezept_id": r.id,
            "url": r.url,
            "bild": r.image,
            "portionen": r.servings,
            "arbeitszeit_min": r.preparation_time,
            "koch_backzeit_min": r.cooking_time,
            "gesamtzeit_min": r.total_time,
            "schwierigkeit": r.difficulty,
            "zutaten": r.ingredients,
            "schritte": r.steps,
            "anzahl_schritte": len(r.steps),
        }


class StepSensor(SessionEntity, SensorEntity):
    _attr_icon = "mdi:format-list-numbered"
    _unrecorded_attributes = frozenset({"text"})

    def __init__(self, coordinator, session) -> None:
        super().__init__(coordinator, session, "kochschritt")

    @property
    def native_value(self) -> str | None:
        return self._session.step_label()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        s = self._session
        if not s.recipe:
            return {}
        text = s.step_text()
        return {
            "rezept": s.recipe.title,
            "schritt": s.step,
            "schritte_gesamt": s.total,
            "text": text,
            "timer_minuten": step_minutes(text) if s.step else None,
            "letzter_schritt": s.step >= s.total,
        }
