# Bumbli

A family story game: real chores, confirmed by another family member, unlock chapters of a shared story.

## Why "Bumbli"

Bumbli comes from *bumblebee* and *to bumble* (to potter about, busy and a little clumsy). A family is like a hive: everyone brings their own drop, and the shared honey becomes chapters of the family's story. Bumbli the bumblebee is the narrator who writes those chapters and sums up the week.

По-русски: Bumbli — «маленький шмель». Семья как улей: каждый вносит свою каплю, общий мёд превращается в главы истории, а шмель Бамбли её рассказывает.

## Run

Copy `.env.example` to `.env`, fill in the values, then:

```bash
docker compose up --build
```

## Develop

```bash
cd backend
uv sync
uv run ruff check . && uv run ruff format --check . && uv run ty check app tests
uv run pytest -q
```

Tests start Postgres through Testcontainers and need a running Docker. On colima set
`TESTCONTAINERS_RYUK_DISABLED=true`.

## Telegram

Set in `.env` (names only here): `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET` (1-256 characters of `A-Za-z0-9_-`), `TELEGRAM_WEBHOOK_URL` (public `https://.../api/v1/telegram/webhook`), optional `TELEGRAM_MAX_CONCURRENT_UPDATES` (default 8). Without the token and the secret the webhook answers 404 and the rest of the app runs normally; an invalid token is logged by class and Telegram stays off.

Register the webhook once, after the release is up: `python -m app.channels.telegram.set_webhook` (from `backend/`). It prints only `success` or `failure: <ErrorClass>`.

Group chats:
- Make the bot a group admin, or turn privacy off in BotFather (`/setprivacy`), so plain `@bot` mentions are delivered. With privacy on, only replies to the bot and commands reach it.
- An adult gets a code on the site (`POST /api/v1/families/{id}/telegram/link-code`, valid 10 minutes, single use). A chat creator or admin sends `/link@<bot> <code>` in the group; in a private chat plain `/link <code>` works.
- An admin who posts anonymously (as the group) must switch anonymity off to use `/link`: Telegram then reports the group, not the person, as the sender. A bad webhook secret format disables Telegram at startup (logged), like a bad token.
- Ask the game master with `/ask@<bot> <question>`, by replying to the bot, or by mentioning `@<bot>`.
