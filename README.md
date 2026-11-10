# Chefkoch for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5?style=for-the-badge&logo=homeassistantcommunitystore&logoColor=white)](https://hacs.xyz/docs/faq/custom_repositories/)
[![Release](https://img.shields.io/github/v/release/skornehl/ha-chefkoch?style=for-the-badge&color=6366F1)](https://github.com/skornehl/ha-chefkoch/releases)
[![Home Assistant 2026.1+](https://img.shields.io/badge/Home%20Assistant-2026.1%2B-18BCF2?style=for-the-badge&logo=homeassistant&logoColor=white)](https://www.home-assistant.io/)
[![Checks](https://img.shields.io/github/actions/workflow/status/skornehl/ha-chefkoch/validate.yml?branch=main&style=for-the-badge&label=checks)](https://github.com/skornehl/ha-chefkoch/actions/workflows/validate.yml)
[![License](https://img.shields.io/github/license/skornehl/ha-chefkoch?style=for-the-badge&color=9333EA)](LICENSE)

Your saved [chefkoch.de](https://www.chefkoch.de) recipes (Kochbuch) in Home
Assistant, plus a **cooking mode**: ingredients first, then one step at a
time - made for a small kitchen touch screen.

Unofficial. Uses the same JSON API the Chefkoch website uses
(`api.chefkoch.de/v2`). Search and recipe details are public; your Kochbuch
needs the token the website sends after you log in.

## What you get

| Entity | |
| --- | --- |
| `sensor.chefkoch_kochbuch` | number of saved recipes (attribute `rezepte`: id + title, not recorded) |
| `select.chefkoch_rezept_auswahlen` | pick a saved recipe → it is loaded for cooking |
| `sensor.chefkoch_rezept` | loaded recipe: portions, times, `zutaten`, `schritte`, picture |
| `sensor.chefkoch_kochschritt` | `Zutaten` or `Schritt 2/6`, attribute `text`, `timer_minuten` (longest duration mentioned) |
| buttons | Weiter, Zurück, Zu den Zutaten, Kochen beenden, Kochbuch aktualisieren |

Services: `chefkoch.load_recipe` (id, Chefkoch link or search term - own
Kochbuch first), `chefkoch.search` (returns results, marks `im_kochbuch`),
`chefkoch.add_ingredients_to_list` (to any to-do list).

Every step change fires the event **`chefkoch_step`** with `title`, `label`,
`text`, `step`, `total`, `timer_minutes`, `last` - use it to show the step on
a screen (e.g. a Tessera alert with "Weiter"/"Zurück" buttons) or to start a
timer.

## Setup: the token

Chefkoch protects its login form with bot detection, so this integration
does **not** log in itself. You log in in your own browser and hand over the
session token:

1. Log in on chefkoch.de, open your Kochbuch.
2. F12 → *Network* → filter *Fetch/XHR* → pick a request to `api.chefkoch.de`.
3. Copy the request header **`x-chefkoch-api-token`** into the integration's
   setup dialog.

When the token expires, Home Assistant asks you to re-authenticate (same
steps). The token is stored in the config entry only.

## License

MIT
