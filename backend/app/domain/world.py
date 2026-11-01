"""The generated world and the rule that keeps user text out of image prompts (W-3)."""

import re
from collections.abc import Iterable
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

GENRES = ("fairy_tale", "space", "pirates", "custom")
_STYLE = {
    "fairy_tale": "storybook watercolor fairy tale",
    "space": "bright cartoon space adventure",
    "pirates": "bright cartoon pirate adventure",
    "custom": "storybook illustration",
}

Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Long = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)]


class Location(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Short
    description: Long
    image_prompt: str = Field(default="", description="Leave empty: the service fills it.")


class Hero(BaseModel):
    model_config = ConfigDict(extra="forbid")
    member_id: UUID
    hero_class: Short
    trait: Short
    skill: Short = Field(description="The hero's superpower: one everyday skill")
    image_prompt: str = Field(default="", description="Leave empty: the service fills it.")


class World(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Short
    setting: Long
    tone: Short
    locations: Annotated[list[Location], Field(min_length=4, max_length=6)]
    heroes: list[Hero]
    prologue: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1500)
    ]
    cover_image_prompt: str = Field(default="", description="Leave empty: the service fills it.")


def _is_same_word(token: str, banned: str) -> bool:
    """Exact match, or for a banned word of 4+ letters a declension: same stem, similar length."""
    if token == banned:
        return True
    return len(banned) >= 4 and token.startswith(banned[:-1]) and len(token) - len(banned) <= 3


def scrub(text: str, banned: Iterable[str]) -> str:
    """Remove banned words (also their declensions) and every digit run (ages).

    Matching is per word, never per substring, so a short name cannot mangle other words.
    """
    words = {w for b in banned for w in re.findall(r"\w+", b.lower())}

    def drop(m: re.Match[str]) -> str:
        return "" if any(_is_same_word(m.group().lower(), w) for w in words) else m.group()

    text = re.sub(r"\d+", "", re.sub(r"\w+", drop, text))
    text = re.sub(r"(?<!\w)-+(?!\w)", "", text)
    return re.sub(r"\s+([,.])", r"\1", re.sub(r"\s+", " ", text)).strip(" ,.")


def with_image_prompts(world: World, genre: str, banned: Iterable[str]) -> World:
    """Fill image prompts from the world's own text, minus names, interests and numbers.

    `banned` holds member names and interests; the model never sees names, but it may echo an
    interest or invent a name-like word, so the prompt is cleaned here rather than trusted.
    """
    style, words = _STYLE.get(genre, _STYLE["custom"]), tuple(banned)

    def prompt(*parts: str) -> str:
        return ", ".join([style, *filter(None, (scrub(p, words) for p in parts))])

    return world.model_copy(
        update={
            "cover_image_prompt": prompt(world.title, world.setting),
            "locations": [
                loc.model_copy(update={"image_prompt": prompt(loc.name, loc.description)})
                for loc in world.locations
            ],
            "heroes": [
                h.model_copy(update={"image_prompt": prompt(h.hero_class, h.trait, "portrait")})
                for h in world.heroes
            ],
        }
    )
