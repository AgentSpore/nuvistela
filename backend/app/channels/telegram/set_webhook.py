"""One-off: register the webhook with Telegram. `python -m app.channels.telegram.set_webhook`.

Reads TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET and TELEGRAM_WEBHOOK_URL through `Settings`.
Prints only success or failure; the token and the Telegram error text are never printed.
"""

import asyncio
import sys

from aiogram import Bot

from app.channels.telegram.secret import is_valid_webhook_secret
from app.core.config import Settings


async def register(token: str, secret: str, url: str) -> None:
    bot = Bot(token)
    try:
        await bot.set_webhook(url, secret_token=secret, allowed_updates=["message"])
    finally:
        await bot.session.close()


def main() -> int:
    try:
        settings = Settings()
        token, secret, url = (
            settings.telegram_bot_token,
            settings.telegram_webhook_secret,
            settings.telegram_webhook_url,
        )
        if not (token and secret and url):
            print("failure: set TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET, TELEGRAM_WEBHOOK_URL")
            return 2
        if not is_valid_webhook_secret(secret.get_secret_value()):
            print("failure: TELEGRAM_WEBHOOK_SECRET must match [A-Za-z0-9_-]{1,256}")
            return 2
        asyncio.run(register(token.get_secret_value(), secret.get_secret_value(), url))
    except Exception as exc:  # noqa: BLE001 (CLI boundary: print the class, never the message)
        print(f"failure: {type(exc).__name__}")
        return 1
    print("success")
    return 0


if __name__ == "__main__":
    sys.exit(main())
