"""Kochbuch coordinator and the cooking session (current recipe + step)."""
from __future__ import annotations

from dataclasses import asdict
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ChefkochAuthError, ChefkochClient, ChefkochError, Recipe, SavedRecipe, step_minutes
from .const import CONF_TOKEN, COOKBOOK_SCAN_HOURS, DOMAIN, EVENT_STEP

_LOGGER = logging.getLogger(__name__)


class CookbookCoordinator(DataUpdateCoordinator[list[SavedRecipe]]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_kochbuch",
            update_interval=timedelta(hours=COOKBOOK_SCAN_HOURS),
        )
        self.client = ChefkochClient(async_get_clientsession(hass), entry.data[CONF_TOKEN])
        self.device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Chefkoch",
            manufacturer="chefkoch.de",
            model="Kochbuch",
            configuration_url="https://www.chefkoch.de/benutzer/kochbuch",
        )

    async def _async_update_data(self) -> list[SavedRecipe]:
        try:
            return await self.client.cookbook()
        except ChefkochAuthError as err:
            raise ConfigEntryAuthFailed("Chefkoch-Token abgelaufen") from err
        except ChefkochError as err:
            raise UpdateFailed(str(err)) from err

    def titles(self) -> dict[str, str]:
        """Unique, sorted display title -> recipe id."""
        out: dict[str, str] = {}
        for rec in sorted(self.data or [], key=lambda r: r.title.casefold()):
            title = rec.title or rec.id
            if title in out:
                title = f"{title} ({rec.id})"
            out[title] = rec.id
        return out


class CookingSession:
    """The recipe on the stove: ingredients page (step 0), then steps 1..n.

    Survives restarts (Store). Every change fires ``chefkoch_step`` so an
    automation can put the step on a kitchen screen.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: ChefkochClient) -> None:
        self.hass = hass
        self.client = client
        self.recipe: Recipe | None = None
        self.step = 0
        self._store: Store[dict[str, Any]] = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.session")
        self._listeners: list = []

    async def async_load(self) -> None:
        data = await self._store.async_load()
        if data and data.get("recipe"):
            self.recipe = Recipe(**data["recipe"])
            self.step = int(data.get("step", 0))

    @callback
    def async_add_listener(self, update) -> callable:
        self._listeners.append(update)
        return lambda: self._listeners.remove(update)

    @property
    def total(self) -> int:
        return len(self.recipe.steps) if self.recipe else 0

    def step_text(self) -> str:
        if not self.recipe:
            return ""
        if self.step == 0:
            return "\n".join(self.recipe.ingredients)
        return self.recipe.steps[self.step - 1]

    def step_label(self) -> str | None:
        if not self.recipe:
            return None
        if self.step == 0:
            return f"Zutaten ({self.recipe.servings} Portion(en))" if self.recipe.servings else "Zutaten"
        return f"Schritt {self.step}/{self.total}"

    def as_event(self) -> dict[str, Any]:
        text = self.step_text()
        return {
            "recipe_id": self.recipe.id if self.recipe else None,
            "title": self.recipe.title if self.recipe else None,
            "label": self.step_label(),
            "step": self.step,
            "total": self.total,
            "text": text,
            "timer_minutes": step_minutes(text) if self.step else None,
            "last": bool(self.recipe) and self.step >= self.total,
        }

    async def _changed(self) -> None:
        await self._store.async_save(
            {"recipe": asdict(self.recipe) if self.recipe else None, "step": self.step}
        )
        self.hass.bus.async_fire(EVENT_STEP, self.as_event())
        for update in list(self._listeners):
            update()

    async def load(self, recipe_id: str) -> Recipe:
        try:
            self.recipe = await self.client.recipe(recipe_id)
        except ChefkochError as err:
            raise HomeAssistantError(f"Rezept {recipe_id} nicht ladbar: {err}") from err
        self.step = 0
        await self._changed()
        return self.recipe

    async def move(self, delta: int) -> None:
        if not self.recipe:
            raise HomeAssistantError("Kein Rezept geladen")
        self.step = max(0, min(self.total, self.step + delta))
        await self._changed()

    async def restart(self) -> None:
        if self.recipe:
            self.step = 0
            await self._changed()

    async def stop(self) -> None:
        self.recipe = None
        self.step = 0
        await self._changed()
