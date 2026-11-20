"""The generated world and the rule that keeps user text out of image prompts (W-3)."""

import re
from collections.abc import Iterable
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.domain.adventure import NextQuest, StoredQuest

GENRES = ("fairy_tale", "space", "pirates", "custom")
_STYLE = {
    "fairy_tale": "storybook watercolor fairy tale",
    "space": "bright cartoon space adventure",
    "pirates": "bright cartoon pirate adventure",
    "custom": "storybook illustration",
}

SHORT_MAX = 60
LONG_MAX = 600
PROLOGUE_MAX = 1500
LOCATIONS_MIN, LOCATIONS_MAX = 4, 6

Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=SHORT_MAX)]
Long = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=LONG_MAX)]


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
    locations: Annotated[list[Location], Field(min_length=LOCATIONS_MIN, max_length=LOCATIONS_MAX)]
    heroes: list[Hero]
    prologue: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=PROLOGUE_MAX)
    ]
    cover_image_prompt: str = Field(default="", description="Leave empty: the service fills it.")
    first_quest: StoredQuest | None = (
        None  # None in fallback worlds and in worlds stored before V10; no reaction before V19
    )


class GeneratedWorld(World):
    """What the model must return: the same world with its first quest required."""

    first_quest: NextQuest  # ty: ignore[invalid-mutable-override]  # narrowing: never None here


_CASE_ENDINGS = frozenset(
    "а я у ю е и ы о ой ей ом ем ам ям ах ях ами ями ов ев ью ею ою ёй ём".split()
)
_VOWEL_ENDINGS = "аяыиеёуюоэьй"
_CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
_SENTENCE_END = re.compile(r"(?:^|[.!?…\n])\s*$")


def _is_same_word(token: str, banned: str) -> bool:
    """Exact match; for Cyrillic also the name's stem plus a real Russian case or number ending."""
    if token == banned:
        return True
    stem = banned[:-1] if banned[-1] in _VOWEL_ENDINGS else banned
    return token.startswith(stem) and token[len(stem) :] in _CASE_ENDINGS


def _cjk_names(banned: Iterable[str]) -> list[str]:
    """Chinese runs of at least two characters inside the banned strings: they are matched as
    substrings, since Chinese has no spaces to split words on."""
    return [run for b in banned for run in _CJK_RUN.findall(b) if len(run) >= 2]


def _cjk_bigrams(text: str) -> set[str]:
    return {run[i : i + 2] for run in _CJK_RUN.findall(text) for i in range(len(run) - 1)}


def scrub(text: str, banned: Iterable[str]) -> str:
    """Remove banned words (also their declensions) and every digit run (ages).

    Matching is per word, never per substring, so a short name cannot mangle other words;
    Chinese names are the exception and are removed as substrings.
    """
    banned = tuple(banned)
    for name in _cjk_names(banned):
        text = text.replace(name, " ")
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


def title_names_nobody(title: str, banned: Iterable[str], description: str = "") -> bool:
    """True when the title has no member name (also declined) and no digit run (an age).

    Chinese names are not found by `description_names`, so a title is also refused when it shares
    any two-character Chinese run with the player's own `description`.
    """
    banned = tuple(banned)
    if any(name in title for name in _cjk_names(banned)):
        return False
    if _cjk_bigrams(title) & _cjk_bigrams(description):
        return False
    return re.findall(r"\w+", scrub(title, banned)) == re.findall(r"\w+", title)


def _base_form(word: str) -> str:
    """The word without its longest case ending, keeping three letters (two after "-ей"/"-ой").

    Banning the stem also bans the base form ("Барсиком" -> "Барсик"): `scrub` matches the stem
    plus any case ending. After "-ей"/"-ой" the nominative is returned instead ("Зоей" -> "Зоя",
    "Машей" -> "Маша"): a bare short stem would be cut again and ban "За", "Мы".
    """
    low = word.lower()
    cut = max(
        (
            e
            for e in _CASE_ENDINGS
            if low.endswith(e) and len(word) - len(e) >= (2 if e in {"ей", "ой"} else 3)
        ),
        key=len,
        default="",
    )
    stem = word[: len(word) - len(cut)]
    if cut in {"ей", "ой"}:
        return stem + ("а" if stem[-1] in "шжчщцШЖЧЩЦ" else "я")
    return stem


def description_names(text: str) -> list[str]:
    """Name-like words of a player's own description: capitalised and not opening a sentence.

    Names, pet names and places follow this shape; the plain words that describe the world
    do not, so banning only these keeps the world visible in titles and pictures. A name that
    only opens a sentence is not recognised, unless it also stands elsewhere mid-sentence.
    """
    found = [
        m.group()
        for m in re.finditer(r"\w+", text)
        if len(m.group()) > 1
        and m.group()[0].isupper()
        and not _SENTENCE_END.search(text[: m.start()])
    ]
    # Both forms: the stem catches case forms the word's own stem would miss, the word itself
    # keeps names ending in -ия/-ей matching in their exact form.
    return list(dict.fromkeys([*found, *map(_base_form, found)]))
