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
