"""Notification texts. They show on a lock screen: world and quest titles only, no names."""

_CHAPTER_READY = {
    "ru": "глава готова",
    "en": "the chapter is ready",
    "es": "el capítulo está listo",
    "zh-CN": "章节已完成",
}
_CHAPTER_READY_BARE = {
    "ru": "Глава готова",
    "en": "The chapter is ready",
    "es": "El capítulo está listo",
    "zh-CN": "章节已完成",
}
_QUEST_WAITING = {
    "ru": "{world}: новое задание — «{quest}»",
    "en": "{world}: a new quest — “{quest}”",
    "es": "{world}: nueva misión — «{quest}»",
    "zh-CN": "{world}：新任务——「{quest}」",
}
_QUEST_WAITING_BARE = {
    "ru": "Новое задание — «{quest}»",
    "en": "A new quest — “{quest}”",
    "es": "Nueva misión — «{quest}»",
    "zh-CN": "新任务——「{quest}」",
}
_FALLBACK = "en"


def chapter_ready_text(locale: str, world_title: str | None) -> str:
    if world_title is None:
        return _CHAPTER_READY_BARE.get(locale, _CHAPTER_READY_BARE[_FALLBACK])
    sep = "：" if locale == "zh-CN" else ": "
    return f"{world_title}{sep}{_CHAPTER_READY.get(locale, _CHAPTER_READY[_FALLBACK])}"


def quest_waiting_text(locale: str, world_title: str | None, quest_title: str) -> str:
    table = _QUEST_WAITING_BARE if world_title is None else _QUEST_WAITING
    template = table.get(locale, table[_FALLBACK])
    return template.format(world=world_title, quest=quest_title)
