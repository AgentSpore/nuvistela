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

## World

`POST /api/v1/families/{id}/world` (adults) queues the family world, `POST .../world/regenerate` repeats it with the stored genre (3 requests per family per day), `GET .../world` returns `pending`, `ready` or `fallback` with the world. A background worker generates it over OpenRouter with zero data retention, with the model in `WORLD_MODEL` (default `deepseek/deepseek-v4.1-flash`, the chapter model). Without `OPENROUTER_API_KEY` (or with the worker disabled by its flag) the worker is off and every world stays `pending`; after 3 failed attempts a template world for the genre is stored (`fallback`).

`GET .../world` also carries `cover`: `null` when no cover was ordered for the current world, otherwise `{status: pending|ready|failed, url}` with `url` set only when ready. `GET /api/v1/media/{sha}.webp` serves a ready picture to the signed-in members of the family that owns it, cached privately and immutably (`ETag` is the sha, `If-None-Match` gives 304); anonymous callers, other families, malformed or unknown hashes and pictures that are not ready all get the same 404. Pictures are stored in Postgres (`world_images`); `cover` stays `null` while `IMAGE_MODEL` is empty and for a fallback world (see the world cover paragraph below).

`POST /api/v1/families/{id}/world/share` (adults) returns `{token, created}` for the current world's cover card: 409 until the world is `ready` with a `ready` cover, 429 for the 11th new link in 24 hours; a repeat gives the same token. `DELETE` on the same path turns off every active link of the family (204). `GET /api/v1/share/{token}` needs no session and returns exactly `{title, genre, cover_url}` (`title` is null when it held a member's name or an age; `genre` is a key, `custom` for a family's own text); `GET /api/v1/share/{token}/cover.webp` serves the cover with `Cache-Control: public, max-age=300`. Revoked, unknown and malformed tokens all give the same 404. A link keeps the world and cover of the moment it was made. Tokens are 128-bit HMACs of the link id under `SHARE_TOKEN_KEY` (unset = sharing answers 409; changing it turns every sent link off); the database keeps only their SHA-256 (`world_shares`).

Paid model calls (world, chapter and chat) are capped before they are made: each call reserves its worst case (prompt plus `*_MAX_TOKENS` times the model's output price) in `llm_spend`, per family and globally per UTC day (`LLM_FAMILY_DAILY_CAP_USD`, `LLM_GLOBAL_DAILY_CAP_USD`). The `*_PRICE_*_USD_PER_MTOK` variables hold the prices of the configured model; they also become the OpenRouter `max_price` of the request, so change them together with `WORLD_MODEL` / `CHAPTER_MODEL`. The chat agent reserves every model request of a turn separately (its prompt plus `CHAT_MAX_TOKENS` of output) and settles it with the real usage; at the cap the caller gets the usual limit answer (429 on the web, the limit reply on Telegram) and no model call is made. Its prices are `CHAT_PRICE_IN_USD_PER_MTOK` and `CHAT_PRICE_OUT_USD_PER_MTOK`; the defaults match `deepseek/deepseek-v4.1-flash`, so they must be set to the prices of `FAMILY_LLM_MODEL`: a pricier model with the default prices is refused by the provider on every chat turn. A chapter that cannot be written is `delayed_model` or `delayed_budget`; a template quest keeps the game going and the chapter is retried automatically up to 3 times. At the default ceilings one chapter reserves 0.0076 to 0.0078 USD worst case by prompt size (two requests: the answer and one output retry) and the world 0.0049 to 0.0051 USD, so the 0.05 USD family cap covers at least 6 chapters per UTC day (5 on the day the world is generated). A chapter of a quest that a member aged 3-5 plays keeps model reasoning on with an 8000-token ceiling, so it reserves 0.0105 to 0.0110 USD by prompt size and the cap covers at least 4 such chapters per UTC day; reservations are settled to the real cost afterwards, so the actual count is higher. Paid image calls are counted and capped apart from text (`llm_spend.kind` is `text` or `image`): `IMAGE_FAMILY_DAILY_CAP_USD` (default 0.15: a first cover, one regeneration after the text check and one growth cover per UTC day; each picture reserves 0.045 USD plus its prompt, and the first one also 0.002 USD for the check that looks for writing) and `IMAGE_GLOBAL_DAILY_CAP_USD` (default 1.0), so an image reservation never reduces the text allowance and the reverse. A call that times out (`CHAPTER_TIMEOUT_S` 90 s, two requests, `WORLD_TIMEOUT_S` 75 s, whole run; the chat turn keeps `AGENT_TIMEOUT_S` 60 s) is retried after a flat pause (`CHAPTER_RETRY_DELAY_S` 5 s for a chapter, `WORLD_RETRY_DELAY_S` 30 s for a world); its reservation stays `reserved` with no actual cost, because the provider may still have billed the abandoned request, and keeps counting at the worst case until the UTC day ends. A `reserved` row older than the call timeout plus the job lease is an attempt of unknown outcome, never a measured cost.

New games are admitted in two steps before any paid call. A per-address limit kept in the memory of the backend process (never stored or logged, forgotten on restart): `POST /api/v1/families` 3 per hour and 10 per day, `POST /api/v1/invite/accept` 30 per hour; over it the answer is 429 `{"detail": {"code": "rate_limited"}}`. The address is the rightmost non-private entry of `X-Forwarded-For` (each proxy hop appends one, so entries a client forged on the left are ignored), else the peer address; the proxy in front of the backend must be the only way to reach it and must append the address it saw. `MAX_NEW_FAMILIES_PER_DAY` (default 60, `0` = unlimited) caps new games per UTC day across all callers (counted from `families.created_at`; the check and the insert are not locked together, so a burst may pass the cap by a few); past it the answer is 429 `{"detail": {"code": "daily_full"}}`. The `/new` page shows a warm text for each code. The per-address quota is spent before the request body is validated, on purpose: it also bounds probing of invite tokens. The daily cap counts live families plus those created and erased the same UTC day since the process started, so erasing a family does not free its place (a restart forgets that second part). IPv6 clients are keyed by their /64.

Quest 1 is written with the world: the world generator returns a required `first_quest`, and the world worker opens it (`quests.source = world`) in the same transaction that stores the world. Until then `GET /api/v1/families/{id}/adventure` reports `world.status = pending` with `quest = null`. A fallback world (three failed attempts, or no budget) opens the first template quest instead.

## Telegram

Set in `.env` (names only here): `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET` (1-256 characters of `A-Za-z0-9_-`), `TELEGRAM_WEBHOOK_URL` (public `https://.../api/v1/telegram/webhook`), optional `TELEGRAM_MAX_CONCURRENT_UPDATES` (default 8). Without the token and the secret the webhook answers 404 and the rest of the app runs normally; an invalid token is logged by class and Telegram stays off.

Register the webhook once, after the release is up: `python -m app.channels.telegram.set_webhook` (from `backend/`). It prints only `success` or `failure: <ErrorClass>`.

Group chats:
- Make the bot a group admin, or turn privacy off in BotFather (`/setprivacy`), so plain `@bot` mentions are delivered. With privacy on, only replies to the bot and commands reach it.
- An adult gets a code on the site (`POST /api/v1/families/{id}/telegram/link-code`, valid 10 minutes, single use). A chat creator or admin sends `/link@<bot> <code>` in the group; in a private chat plain `/link <code>` works.
- An admin who posts anonymously (as the group) must switch anonymity off to use `/link`: Telegram then reports the group, not the person, as the sender. A bad webhook secret format disables Telegram at startup (logged), like a bad token.
- Soft reminders: `/notify on` in a linked chat turns them on, `/notify off` turns them off, `/notify` shows the state. Off by default; in a group only the creator or an admin can switch it, in a private chat anyone. The bot writes when a chapter is ready (not while the game tab is open) and, 17:00-20:00 local, when a quest waits (at most once a day, silent after 3 unanswered). "Quest waiting" takes its time zone from the family's newest Web Push subscription: without one only "chapter ready" is sent. A blocked bot, a removed bot or a group that moved to a new id switches the reminders off. Optional `SITE_URL` (public origin, no secrets) adds a link `{SITE_URL}/{locale}/adventure` to each message.
- Bot replies come in the player's language: a linked chat uses the family's language; an unlinked sender gets their Telegram language for Russian, Spanish and Chinese, otherwise English.
- Ask the game master with `/ask@<bot> <question>`, by replying to the bot, or by mentioning `@<bot>`.

## Funnel

Public endpoints: `POST /api/v1/waitlist` (email, family size, kids' age bands; kept for earlier requests only, the landing no longer posts to it) and `POST /api/v1/events` (`landing_view` only). Funnel events live in the `events` table; they carry ids and coarse props, never email, names or message text.

Report: `python -m app.cli.funnel --days 30` (from `backend/`) prints counts per step and conversion. `return_d1`/`return_d7` are counted per family created in the window; the day is a UTC calendar day.

The app has no rate limiter: put a per-IP limit at the ingress before exposing these two endpoints publicly.

Pilot sources: the landing reads `?source=` once per browser session; `direct`, `share`, `community`, `newsletter`, `x`, `telegram`, `substack` and `youtube` are kept, anything else counts as `direct`. A lead (`lead_created`) is recorded by the server when a waitlist request or `POST /api/v1/families` carries that session's attribution; the pilot report (`python -m app.cli.pilot`) breaks sessions and leads down by source.

Share funnel: the same command ends with plain counts by kind (links created, sessions that opened the card, sessions that clicked «Создать свой мир», new leads with `source=share`); nothing per family or per link, and nothing shown to the sender. Link created/revoked are server events without a session, so internal links are not excluded from those counts; viewed, cta and new leads follow the internal flag below.

## Checking the pilot without polluting the report

The pilot report (`python -m app.cli.pilot --days 30`) leaves out sessions marked internal; add `--include-internal` to see them.

- Open the landing once with `?internal=1` in the browser you will use for your own checks: it stores `nuvistela-internal=1` in localStorage, and every pilot event and waitlist attribution from that browser is marked internal. `?internal=0` clears the mark.
- Browsers driven by automation (`navigator.webdriver`) send no pilot events, and their waitlist attribution is marked internal.
- The mark is first-touch per session and set by the client, so it keeps honest self-checks out of the numbers; it is not protection against a hostile client.
- Per-IP rate limiting of `POST /api/v1/pilot/events` is not done in the app (behind the Next rewrite and Caddy every visitor shares one peer address); configure it at the ingress, in Caddy on the server. The app only caps events per session (60).

The 3D scene (World Labs Marble) is ordered when a real world's cover is stored, only with `WORLD3D_MODEL` (`marble-1.0-draft` or `marble-1.1`) and `WORLDLABS_API_KEY` set; otherwise nothing is queued and no scene worker starts. A scene job reserves the table price (230 credits = 0.184 USD for the draft; 1 USD = 1250 credits) under the `world3d` caps, starts `worlds:generate` from the cover prompt without its ending plus a fixed daytime ending, polls the operation for up to `WORLD3D_TIMEOUT_S` (600), downloads the 500k SPZ and the panorama (stored as WebP, at most 4096 px) and settles the table price. At most 2 paid attempts, a failed attempt keeps its reservation; the second failure marks the scene `failed`. When a cap refuses the reservation the job waits for the next UTC day and uses no attempt. `WORLD3D_MODEL` is ignored (logged) when it has no known price or its price exceeds the smaller of `WORLD3D_FAMILY_DAILY_CAP_USD` and `WORLD3D_GLOBAL_DAILY_CAP_USD` (3D is then off); `WORLD3D_TIMEOUT_S` is at most 780. The request is sent with `permission.public = false`. `GET .../world` carries `scene`: `null` or `{status, url, panorama_url}`, the urls (`/api/v1/media/{sha}.spz`, `/api/v1/media/pano/{sha}.webp`) set only when ready.

The world cover is one picture of the place, bought after the world is stored `ready` (a fallback world gets none). With `IMAGE_MODEL` empty (the default) nothing is queued and the image worker does not start, so no paid image call can happen. A cover job reserves `IMAGE_PRICE_USD_PER_IMAGE` plus the prompt bytes at `IMAGE_PRICE_IN_USD_PER_MTOK` under the image caps, calls OpenRouter once (zero retention, `modalities: ["image"]`, `image_config.aspect_ratio` 3:2, `provider.max_price` from `IMAGE_MAX_PRICE_IN_USD_PER_MTOK` (5) and `IMAGE_MAX_PRICE_OUT_USD_PER_MTOK` (200), USD per million tokens; it does not bound this model's image price, the per-image limit is the reservation and the worker stop below; no `temperature`), settles the price the provider reports and stores a WebP of at most 1024 px in `world_images`. At most 2 attempts; a failed attempt keeps its reservation, and the second failure marks the cover `failed` while the world stays `ready`. If the reported price exceeds the reservation, the worker logs an error and stops. The prompt is the scrubbed `cover_image_prompt` plus a fixed ending (a place only, no people, no writing of any kind; a bright daytime scene when a member is aged 3-5). On every 2nd milestone chapter (milestones 2, 4, 6...) the chapter worker, in the transaction that stores the chapter, also queues a growth cover when `IMAGE_MODEL` is set: the same art style and place, plus the story summary and the milestone lines so far, with the newest milestone as the focus of the picture. It is bought under the same image caps and never touches the text cap; over the cap or after a failure the growth cover is marked `failed` and the chapter is unaffected. The newest ready cover is the current one (the world panel and new share links use it, existing links keep theirs); earlier covers stay in `world_images`, and the 3D scene is not regenerated. Its prompt lists only the milestones written since the current world became ready. `GET .../world` carries `cover_growing`: true while a growth cover of the current world is pending (`cover` is then still the previous one), so a client can poll until it turns false.
