"""One-off: register the webhook with Telegram. `python -m app.channels.telegram.set_webhook`.

Reads TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET and TELEGRAM_WEBHOOK_URL from the environment.
Prints only success or failure; the token and the Telegram error text are never printed.
"""

import asyncio
import os
import sys

from aiogram import Bot

REQUIRED = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_WEBHOOK_SECRET", "TELEGRAM_WEBHOOK_URL")


async def register(token: str, secret: str, url: str) -> None:
    bot = Bot(token)
    try:
        await bot.set_webhook(url, secret_token=secret, allowed_updates=["message"])
    finally:
        await bot.session.close()


def main() -> int:
    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:
        print(f"failure: missing {', '.join(missing)}")
        return 2
    try:
        asyncio.run(
            register(
                os.environ["TELEGRAM_BOT_TOKEN"],
                os.environ["TELEGRAM_WEBHOOK_SECRET"],
                os.environ["TELEGRAM_WEBHOOK_URL"],
            )
        )
    except Exception as exc:  # noqa: BLE001 (CLI boundary: print the class, never the message)
        print(f"failure: {type(exc).__name__}")
        return 1
    print("success")
    return 0


if __name__ == "__main__":
    sys.exit(main())
