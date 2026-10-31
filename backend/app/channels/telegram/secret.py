import re

# https://core.telegram.org/bots/api#setwebhook : secret_token is 1-256 of A-Z a-z 0-9 _ -
_SECRET_RE = re.compile(r"[A-Za-z0-9_-]{1,256}")


def is_valid_webhook_secret(secret: str) -> bool:
    return _SECRET_RE.fullmatch(secret) is not None
