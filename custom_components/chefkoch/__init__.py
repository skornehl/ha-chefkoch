"""Chefkoch: your saved recipes (Kochbuch) and a step-by-step cooking mode."""
from __future__ import annotations

from dataclasses import dataclass

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
import homeassistant.helpers.config_validation as cv

from .api import ChefkochError, recipe_id_from
from .const import ATTR_ENTITY_ID, ATTR_LIMIT, ATTR_QUERY, ATTR_RECIPE_ID, ATTR_URL, DOMAIN
from .coordinator import CookbookCoordinator, CookingSession

PLATFORMS = [Platform.BUTTON, Platform.SELECT, Platform.SENSOR]


@dataclass
class ChefkochData:
    coordinator: CookbookCoordinator
    session: CookingSession


type ChefkochConfigEntry = ConfigEntry[ChefkochData]


async def async_setup_entry(hass: HomeAssistant, entry: ChefkochConfigEntry) -> bool:
    coordinator = CookbookCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    session = CookingSession(hass, entry, coordinator.client)
    await session.async_load()
    entry.runtime_data = ChefkochData(coordinator, session)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ChefkochConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


def _data(hass: HomeAssistant) -> ChefkochData:
    entries = [e for e in hass.config_entries.async_loaded_entries(DOMAIN)]
    if not entries:
        raise ServiceValidationError("Chefkoch ist nicht eingerichtet")
    return entries[0].runtime_data


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, "load_recipe"):
        return

    async def load_recipe(call: ServiceCall) -> ServiceResponse:
        data = _data(hass)
        recipe_id = call.data.get(ATTR_RECIPE_ID) or (
            recipe_id_from(call.data[ATTR_URL]) if call.data.get(ATTR_URL) else None
        )
        if not recipe_id and call.data.get(ATTR_QUERY):
            query = call.data[ATTR_QUERY].casefold()
            # Own Kochbuch first, then the whole of Chefkoch.
            own = [r for r in data.coordinator.data or [] if query in r.title.casefold()]
            if own:
                recipe_id = own[0].id
            else:
                try:
                    found = await data.coordinator.client.search(call.data[ATTR_QUERY], 1)
                except ChefkochError as err:
                    raise HomeAssistantError(str(err)) from err
                recipe_id = found[0]["id"] if found else None
        if not recipe_id:
            raise ServiceValidationError("Kein Rezept gefunden (recipe_id, url oder query angeben)")
        recipe = await data.session.load(str(recipe_id))
        return {"id": recipe.id, "title": recipe.title, "steps": len(recipe.steps)}

    async def search(call: ServiceCall) -> ServiceResponse:
        data = _data(hass)
        try:
            results = await data.coordinator.client.search(call.data[ATTR_QUERY], call.data[ATTR_LIMIT])
        except ChefkochError as err:
            raise HomeAssistantError(str(err)) from err
        own = {r.id for r in data.coordinator.data or []}
        for r in results:
            r["im_kochbuch"] = r["id"] in own
        return {"results": results}

    async def add_ingredients(call: ServiceCall) -> None:
        data = _data(hass)
        recipe = data.session.recipe
        if not recipe:
            raise ServiceValidationError("Kein Rezept geladen")
        for item in recipe.ingredients:
            if not item.strip() or item.startswith("—"):
                continue
            await hass.services.async_call(
                "todo", "add_item", {"item": item}, target={"entity_id": call.data[ATTR_ENTITY_ID]}, blocking=True
            )

    hass.services.async_register(
        DOMAIN,
        "load_recipe",
        load_recipe,
        schema=vol.Schema(
            {
                vol.Optional(ATTR_RECIPE_ID): cv.string,
                vol.Optional(ATTR_URL): cv.string,
                vol.Optional(ATTR_QUERY): cv.string,
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        "search",
        search,
        schema=vol.Schema(
            {vol.Required(ATTR_QUERY): cv.string, vol.Optional(ATTR_LIMIT, default=10): vol.All(int, vol.Range(1, 50))}
        ),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        "add_ingredients_to_list",
        add_ingredients,
        schema=vol.Schema({vol.Required(ATTR_ENTITY_ID): cv.entity_ids}),
    )
