# Nuvistela

A real-life adventure: complete a small activity and unlock the next chapter of an AI-assisted story, on your own or with people you care about.

**Status: concept validation / early prototype · 2026-11-06.** Maintained by AgentSpore. Review by 2026-12-06.

## The idea in one example

A fox wants to reach a library. You build a tower with real blocks and mark the activity complete. In the story, the blocks become a path. The fox finds a book; a bird flies out. Your next activity is to draw a friend for that bird.

The intended reward is a personal story that gives you a reason to do something creative away from the screen. This is the proposed experience, not a claim that every step is implemented.

## What is available today

This repository contains the earlier **Bumbli** family-oriented prototype: chore confirmation, shared story mechanics, world-generation integration, Telegram integration, and a landing page with a waitlist. Existing source names and interface copy still use Bumbli.

The Nuvistela name, solo mode, and the complete activity-to-personalized-chapter experience shown in the concept video are product direction. The video uses mockups; it is not a recording of a released application. This publication is not a production-readiness certification. Local work in progress is not included.

## Give feedback

[Open an issue](https://github.com/AgentSpore/nuvistela/issues/new) and tell us:

- What do you think you would actually do in this product?
- Would you use it alone or with someone? Give one real situation.
- What would make you return for a second chapter, or stop after the first?

Please do not post names, photos of children, emails, or other private information. No live public service or waitlist is advertised yet.

## Development

The setup notes below describe the existing Bumbli prototype and are retained from its source repository. They have not been revalidated as part of this documentation-only publication.

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

## World

`POST /api/v1/families/{id}/world` (adults) queues the family world, `POST .../world/regenerate` repeats it with the stored genre (3 requests per family per day), `GET .../world` returns `pending`, `ready` or `fallback` with the world. A background worker generates it with `WORLD_MODEL` over OpenRouter with zero data retention. Without `WORLD_MODEL` (or the API key) the worker is off and every world stays `pending`; after 3 failed attempts a template world for the genre is stored (`fallback`).

## Telegram

Set in `.env` (names only here): `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET` (1-256 characters of `A-Za-z0-9_-`), `TELEGRAM_WEBHOOK_URL` (public `https://.../api/v1/telegram/webhook`), optional `TELEGRAM_MAX_CONCURRENT_UPDATES` (default 8). Without the token and the secret the webhook answers 404 and the rest of the app runs normally; an invalid token is logged by class and Telegram stays off.

Register the webhook once, after the release is up: `python -m app.channels.telegram.set_webhook` (from `backend/`). It prints only `success` or `failure: <ErrorClass>`.

Group chats:
- Make the bot a group admin, or turn privacy off in BotFather (`/setprivacy`), so plain `@bot` mentions are delivered. With privacy on, only replies to the bot and commands reach it.
- An adult gets a code on the site (`POST /api/v1/families/{id}/telegram/link-code`, valid 10 minutes, single use). A chat creator or admin sends `/link@<bot> <code>` in the group; in a private chat plain `/link <code>` works.
- An admin who posts anonymously (as the group) must switch anonymity off to use `/link`: Telegram then reports the group, not the person, as the sender. A bad webhook secret format disables Telegram at startup (logged), like a bad token.
- Ask the game master with `/ask@<bot> <question>`, by replying to the bot, or by mentioning `@<bot>`.

## Funnel

Public endpoints: `POST /api/v1/waitlist` (email, family size, kids' age bands) and `POST /api/v1/events` (`landing_view` only). Funnel events live in the `events` table; they carry ids and coarse props, never email, names or message text.

Report: `python -m app.cli.funnel --days 30` (from `backend/`) prints counts per step and conversion. `return_d1`/`return_d7` are counted per family created in the window; the day is a UTC calendar day.

The app has no rate limiter: put a per-IP limit at the ingress before exposing these two endpoints publicly.
