"""Fixed quests used without a model call: the first one, and the stand-in for a delayed chapter."""

import json
from pathlib import Path

from app.domain.adventure import QuestDraft

# {locale: [[title, description, skill], ...]} in the order a family meets them.
_TEMPLATES: dict[str, list[list[str]]] = json.loads(
    Path(__file__).with_name("quest_templates.json").read_text(encoding="utf-8")
)


def template_quest(locale: str, seq: int) -> QuestDraft:
    """The template for the family's `seq`-th quest (1-based); the pool repeats after the last."""
    pool = _TEMPLATES.get(locale, _TEMPLATES["en"])
    title, description, skill = pool[(seq - 1) % len(pool)]
    return QuestDraft(title, description, skill, "template")
