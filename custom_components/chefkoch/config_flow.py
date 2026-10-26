"""Config flow: paste the x-chefkoch-api-token from a logged-in browser."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .api import ChefkochAuthError, ChefkochClient, ChefkochError, user_id_from_token
from .const import CONF_TOKEN, DOMAIN

SCHEMA = vol.Schema(
    {vol.Required(CONF_TOKEN): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))}
)


class ChefkochConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _check(self, token: str) -> tuple[dict[str, str], int]:
        client = ChefkochClient(async_get_clientsession(self.hass), token)
        try:
            page = await client.cookbook_page(0, 1)
        except ChefkochAuthError:
            return {"base": "invalid_auth"}, 0
        except ChefkochError:
            return {"base": "cannot_connect"}, 0
        return {}, int(page.get("count") or 0)

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            await self.async_set_unique_id(user_id_from_token(token))
            self._abort_if_unique_id_configured()
            errors, count = await self._check(token)
            if not errors:
                return self.async_create_entry(title=f"Chefkoch ({count} Rezepte)", data={CONF_TOKEN: token})
        return self.async_show_form(step_id="user", data_schema=SCHEMA, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            if user_id_from_token(token) != entry.unique_id:
                errors["base"] = "wrong_account"
            else:
                errors, _ = await self._check(token)
                if not errors:
                    return self.async_update_reload_and_abort(entry, data={CONF_TOKEN: token})
        return self.async_show_form(step_id="reauth_confirm", data_schema=SCHEMA, errors=errors)
