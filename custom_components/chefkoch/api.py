"""Client for api.chefkoch.de (the API the Chefkoch website itself uses).

Unofficial. Public endpoints (search, recipe details) need no login. The
personal Kochbuch needs the ``x-chefkoch-api-token`` header that the website
sends after login; its first part is the user id. The token is never
generated here - it comes from a browser session (see README).
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

from .const import API_BASE, PAGE_SIZE

TIMEOUT = ClientTimeout(total=20)
HEADERS = {
    "accept": "application/json",
    "origin": "https://www.chefkoch.de",
    "referer": "https://www.chefkoch.de/",
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0 Safari/537.36",
}
RECIPE_ID_RE = re.compile(r"/rezepte/(\d+)")
# "50 bis 55 Minuten", "20 Min.", "1,5 Stunden", "1/2 Stunde", "½ Std.", "eine halbe Stunde"
_NUM = r"(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?|[½¼¾]|eine\s+halbe|einer\s+halben|anderthalb|eineinhalb)"
MINUTES_RE = re.compile(
    rf"({_NUM})(?:\s*(?:-|–|bis)\s*({_NUM}))?\s*(Minuten|Minute|Min\.?|Stunden|Stunde|Std\.?)(?![a-zäöü])",
    re.IGNORECASE,
)
_WORDS = {"½": 0.5, "¼": 0.25, "¾": 0.75, "anderthalb": 1.5, "eineinhalb": 1.5}


class ChefkochError(Exception):
    """API unreachable or unexpected answer."""


class ChefkochAuthError(ChefkochError):
    """Token missing, invalid or expired (HTTP 401/403)."""


@dataclass
class SavedRecipe:
    id: str
    title: str
    preparation_time: int | None
    rating: float | None
    note: str | None
    url: str | None
    image: str | None


@dataclass
class Recipe:
    id: str
    title: str
    url: str | None
    image: str | None
    servings: int | None
    preparation_time: int | None
    cooking_time: int | None
    total_time: int | None
    difficulty: int | None
    ingredients: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)


def user_id_from_token(token: str) -> str:
    return token.strip().split("-", 1)[0]


def recipe_id_from(value: str) -> str | None:
    """Accept a plain id or any Chefkoch recipe URL."""
    value = value.strip()
    if value.isdigit():
        return value
    match = RECIPE_ID_RE.search(value)
    return match.group(1) if match else None


def image_url(template: str | None, size: str = "crop-960x720") -> str | None:
    return template.replace("<format>", size) if template else None


def _number(text: str) -> float:
    text = re.sub(r"\s+", " ", text.strip().lower())
    if text in _WORDS:
        return _WORDS[text]
    if "halbe" in text:
        return 0.5
    if "/" in text:
        whole, _, frac = text.rpartition(" ")
        num, den = frac.split("/")
        return (float(whole) if whole else 0.0) + float(num) / float(den)
    return float(text.replace(",", "."))


def step_minutes(text: str) -> int | None:
    """Longest duration mentioned in a step, in minutes (for a timer)."""
    best = None
    for low, high, unit in MINUTES_RE.findall(text):
        try:
            value = _number(high or low)
        except (ValueError, ZeroDivisionError):
            continue
        if unit.lower().startswith(("stund", "std")):
            value *= 60
        minutes = round(value)
        if minutes > 0:
            best = max(best or 0, minutes)
    return best


def _format_amount(amount: float | None) -> str:
    if not amount:
        return ""
    if float(amount).is_integer():
        return str(int(amount))
    return f"{amount:g}".replace(".", ",")


def parse_recipe(data: dict[str, Any]) -> Recipe:
    ingredients: list[str] = []
    for group in data.get("ingredientGroups") or []:
        header = (group.get("header") or "").strip()
        if header:
            ingredients.append(f"— {header} —")
        for ing in group.get("ingredients") or []:
            # Chefkoch puts qualifiers into the unit ("EL, gestr.") - read as "EL gestr."
            unit = re.sub(r"\s*,\s*", " ", ing.get("unit") or "").strip()
            parts = [_format_amount(ing.get("amount")), unit, (ing.get("name") or "").strip()]
            line = " ".join(p for p in parts if p).strip()
            usage = (ing.get("usageInfo") or "").strip()
            if usage:
                line += usage if usage.startswith(",") else f" {usage}"
            line = line.strip(" ,")
            if line:
                ingredients.append(line)
    text = (data.get("instructions") or "").replace("\r", "")
    steps = [re.sub(r"\s+", " ", s).strip() for s in re.split(r"\n\s*\n", text)]
    steps = [s for s in steps if s]
    return Recipe(
        id=str(data["id"]),
        title=data.get("title", ""),
        url=data.get("siteUrl"),
        image=image_url(data.get("previewImageUrlTemplate")),
        servings=data.get("servings"),
        preparation_time=data.get("preparationTime"),
        cooking_time=data.get("cookingTime"),
        total_time=data.get("totalTime"),
        difficulty=data.get("difficulty"),
        ingredients=ingredients,
        steps=steps,
    )


class ChefkochClient:
    def __init__(self, session: ClientSession, token: str | None = None) -> None:
        self._session = session
        self._token = token.strip() if token else None

    async def _get(self, path: str, params: dict | None = None, auth: bool = False) -> Any:
        headers = dict(HEADERS)
        if auth:
            if not self._token:
                raise ChefkochAuthError("Kein Token")
            headers["x-chefkoch-api-token"] = self._token
        try:
            async with self._session.get(
                f"{API_BASE}{path}", params=params, headers=headers, timeout=TIMEOUT
            ) as resp:
                if resp.status in (401, 403):
                    raise ChefkochAuthError(f"HTTP {resp.status}")
                if resp.status >= 400:
                    raise ChefkochError(f"HTTP {resp.status} für {path}")
                return await resp.json(content_type=None)
        except (ClientError, TimeoutError, ValueError) as err:
            raise ChefkochError(f"Chefkoch nicht erreichbar: {err}") from err

    @property
    def user_id(self) -> str:
        return user_id_from_token(self._token or "")

    async def cookbook_page(self, offset: int = 0, limit: int = PAGE_SIZE) -> dict[str, Any]:
        return await self._get(
            f"/cookbooks/user-{self.user_id}/recipes",
            {"offset": offset, "limit": limit, "order": 0, "orderBy": 2},
            auth=True,
        )

    async def cookbook(self) -> list[SavedRecipe]:
        recipes: list[SavedRecipe] = []
        offset = 0
        while True:
            page = await self.cookbook_page(offset)
            results = page.get("results") or []
            for entry in results:
                rec = entry.get("recipe") or {}
                if not rec.get("id"):
                    continue
                recipes.append(
                    SavedRecipe(
                        id=str(rec["id"]),
                        title=rec.get("title", ""),
                        preparation_time=rec.get("preparationTime"),
                        rating=(rec.get("rating") or {}).get("rating"),
                        note=entry.get("note"),
                        url=rec.get("siteUrl"),
                        image=image_url(rec.get("previewImageUrlTemplate")),
                    )
                )
            offset += len(results)
            if not results or offset >= int(page.get("count") or 0):
                return recipes

    async def recipe(self, recipe_id: str) -> Recipe:
        return parse_recipe(await self._get(f"/recipes/{recipe_id}"))

    async def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        data = await self._get("/recipes", {"query": query, "limit": limit})
        out = []
        for entry in data.get("results") or []:
            rec = entry.get("recipe") or {}
            if not rec.get("id"):
                continue
            out.append(
                {
                    "id": str(rec.get("id")),
                    "title": rec.get("title"),
                    "rating": (rec.get("rating") or {}).get("rating"),
                    "preparation_time": rec.get("preparationTime"),
                    "url": rec.get("siteUrl"),
                }
            )
        return out
