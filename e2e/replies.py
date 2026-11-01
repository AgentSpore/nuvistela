"""Text shared by the launcher (what the test model says) and the tests (what they expect)."""

REPLY = "Bumbli greets the family: the quest begins!"
ECHO = "You said: "


def scripted_reply(user_text: str) -> str:
    """The test model's answer: the fixed greeting plus the user's own words, echoed back."""
    return f"{REPLY} {ECHO}{user_text}"
