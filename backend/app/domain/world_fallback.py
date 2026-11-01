"""Template worlds shown when generation fails three times (W-1). Texts per genre and locale."""

from uuid import UUID

from app.domain.world import Hero, Location, World

_CLASSES = {"ru": ("Разведчик", "Мастер", "Хранитель"), "en": ("Scout", "Maker", "Keeper")}
_TRAITS = {"ru": ("смелый", "добрый", "выдумщик"), "en": ("brave", "kind", "inventive")}
_SKILLS = {"ru": ("уборка", "забота", "готовка"), "en": ("tidying", "caring", "cooking")}
_PLACES = {
    "ru": ("Главная площадь", "Тихая гавань", "Старый мост", "Тайный сад"),
    "en": ("Main Square", "Quiet Harbor", "Old Bridge", "Secret Garden"),
}
# (title, setting, prologue) by genre, then locale.
_TEXT = {
    "fairy_tale": {
        "ru": ("Сказочная долина", "Долина, где живут добрые чудеса", "Долина ждёт вашу семью."),
        "en": (
            "Fairy Valley",
            "A valley where kind wonders live",
            "The valley awaits your family.",
        ),
    },
    "space": {
        "ru": ("Звёздный дом", "Станция среди дружелюбных звёзд", "Станция зовёт ваш экипаж."),
        "en": ("Star Home", "A station among friendly stars", "The station calls your crew."),
    },
    "pirates": {
        "ru": ("Бухта Ветров", "Бухта, где паруса хранят тайны", "Бухта ждёт ваш экипаж."),
        "en": ("Windy Cove", "A cove where sails keep secrets", "The cove awaits your crew."),
    },
}


def fallback_world(genre: str, locale: str, member_ids: list[UUID]) -> World:
    """A valid World for the genre ('custom' uses the fairy tale) with one hero per member."""
    lang = locale if locale in _CLASSES else "en"
    title, setting, prologue = _TEXT.get(genre, _TEXT["fairy_tale"])[lang]
    n = len(_CLASSES[lang])
    return World(
        title=title,
        setting=setting,
        tone="warm" if lang == "en" else "тёплый",
        locations=[Location(name=p, description=f"{p}: {setting}") for p in _PLACES[lang]],
        heroes=[
            Hero(
                member_id=m,
                hero_class=_CLASSES[lang][i % n],
                trait=_TRAITS[lang][i % n],
                skill=_SKILLS[lang][i % n],
            )
            for i, m in enumerate(member_ids)
        ],
        prologue=prologue,
    )
