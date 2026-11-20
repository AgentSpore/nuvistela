"""The cover prompt: the scrubbed world prompt plus an ending that keeps the picture safe."""

import re
from collections.abc import Iterable
from dataclasses import dataclass

from app.domain.world import scrub

SAFETY_ENDING = (
    "One single continuous scene: no collage, no grid, no panels, no split frames. "
    "A place only: no people, no characters, no writing of any kind, "
    "no writing of any script: no letters, no words, no labels, no captions, no signs, "
    "no shop signs, no numbers, no logos, no watermarks, no text on screens, maps, windows "
    "or star charts."
)
YOUNG_CHILD_ENDING = SAFETY_ENDING + " A bright daytime scene, cheerful and friendly."
RETRY_ENDING = (
    "IMPORTANT: the previous attempt showed writing. Every surface must stay plain: signs, "
    "banners, walls, shells, sails, books, doors and screens carry only pictures and patterns, "
    "never letters, never pseudo-letters, never any marks that look like writing."
)
_PUNCT = r"[,.;:!?]"


def tidy_debris(text: str) -> str:
    """Collapse what the scrub left behind: repeated spaces, a space before punctuation, doubled
    punctuation. Words are never added or repaired."""
    text = re.sub(r"\s+", " ", text)
    text = re.sub(rf"\s+({_PUNCT})", r"\1", text)
    return re.sub(rf"({_PUNCT})(?:\s*{_PUNCT})+", r"\1", text).strip(" ,.;:")


def cover_prompt(world_prompt: str, *, young_child: bool) -> str:
    """`world_prompt` already has names, interests, ages and digits removed (`scrub`)."""
    return f"{tidy_debris(world_prompt)}. {YOUNG_CHILD_ENDING if young_child else SAFETY_ENDING}"


def retry_prompt(prompt: str) -> str:
    """The prompt of the one regeneration after a picture showed writing: the same, stricter."""
    return f"{prompt} {RETRY_ENDING}"


MILESTONES_SHOWN = 6  # the latest milestone lines that go into a growth prompt
SUMMARY_MAX = 300


@dataclass(frozen=True)
class GrowthStory:
    """What the world has become: its tone, the latest chapter summary, the milestone lines."""

    tone: str
    summary: str
    milestones: list[str]


def growth_cover_prompt(
    world_prompt: str, story: GrowthStory, *, banned: Iterable[str], young_child: bool
) -> str:
    """The prompt of a growth cover: the world's own art style and place, then what changed.

    The newest milestone is the focus, so the picture shows a new place, object or creature rather
    than the same scene again. The story text is scrubbed like the world text: it may echo a name
    or an interest the model never saw.
    """
    banned = tuple(banned)
    shown = [m for m in (scrub(line, banned) for line in story.milestones[-MILESTONES_SHOWN:]) if m]
    summary = scrub(story.summary, banned)[:SUMMARY_MAX]
    parts = [tidy_debris(world_prompt), f"Tone: {scrub(story.tone, banned)}"]
    if summary:
        parts.append(f"The story so far: {summary}")
    if shown:
        parts.append(f"What has changed in this world, oldest first: {'; '.join(shown)}")
        parts.append(
            f"The newest change, {shown[-1]}, is the clear focus of the picture: draw that new"
            " place, object or creature large in the centre. Do not repaint the earlier scene;"
            " the older changes stay visible around it"
        )
    return cover_prompt(". ".join(parts), young_child=young_child)
