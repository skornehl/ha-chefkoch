"""Constants for the Chefkoch integration."""
from __future__ import annotations

DOMAIN = "chefkoch"

CONF_TOKEN = "token"

API_BASE = "https://api.chefkoch.de/v2"
# Kochbuch does not change often; one full read is ~404 recipes in pages.
COOKBOOK_SCAN_HOURS = 6
PAGE_SIZE = 50

EVENT_STEP = "chefkoch_step"

ATTR_RECIPE_ID = "recipe_id"
ATTR_URL = "url"
ATTR_QUERY = "query"
ATTR_ENTITY_ID = "entity_id"
ATTR_LIMIT = "limit"
