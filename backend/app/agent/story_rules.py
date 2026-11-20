"""The rules for the task `kind` and the story `beat`, shared by the world and chapter prompts."""

from app.domain.adventure import MILESTONE_MAX

KIND_RULES = (
    "A quest kind is one of: say (name, tell or write), make (make or draw), move (body "
    "movement at home, or outdoors with an adult in the text when a child plays; never "
    "climbing or water), care (look after a place, plant or thing), find (find or "
    "notice), gift (something kind for another person, never asking for data about them). "
)

BEAT_RULES = (
    "The data field beat sets the chapter: opening begins the story; turn brings exactly one new "
    "named character, place or object, or one small never-scary mystery, named in the summary; "
    "milestone shows something visibly opened, built or saved by the player's deeds, and the "
    f"field milestone is one short sentence of at most {MILESTONE_MAX} characters (about ten "
    "words) saying what changed in the world, never a bare name; develop deepens what exists. "
    "On every other beat milestone is null. The kind of next_quest "
    "is next_quest_kind. "
)
