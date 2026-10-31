# Kinsaga

A family story game: real chores, confirmed by another family member, unlock chapters of a shared story.

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
