"""Text shared by the launcher (what the test model says) and the tests (what they expect)."""

REPLY = "Bumbli greets the family: the quest begins!"
ECHO = "You said: "


def scripted_reply(user_text: str) -> str:
    """The test model's answer: the fixed greeting plus the user's own words, echoed back."""
    return f"{REPLY} {ECHO}{user_text}"


# The scripted world model writes a world only for this genre; every other genre gets no world,
# so the stored fallback (and the template quest) stay what the other scenarios rely on.
WORLD_GENRE = "pirates"
WORLD_TITLE = "Бухта Скриптов"
WORLD_QUEST_TITLE = "Зажечь фонарь бухты"
WORLD_QUEST_DESCRIPTION = "Нарисуйте фонарь на листе бумаги и поставьте его на подоконник."
WORLD_QUEST_REACTION = (
    "Фонарь на причале мигнул, и вдоль тропинки один за другим загорелись огни."
)
