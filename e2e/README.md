# Bumbli e2e

Browser suite (Python + Playwright) against the real stack: Postgres testcontainer, the
backend app with a scripted test model (no LLM call), and the Next.js standalone build.

## Prerequisites

- Docker running (Postgres testcontainer)
- `pnpm` with `frontend/` dependencies installed
- `uv` with `backend/` synced (`uv sync --project backend`): the launcher runs in its venv
- Chromium: `uv run --project e2e playwright install chromium`

## Run

```bash
TESTCONTAINERS_RYUK_DISABLED=true uv run --project e2e pytest e2e
```

The first run builds the frontend (about a minute). `-p harness` is set in `pyproject.toml`.
The tests share one family and run in file order.

## Artifacts (git-ignored)

- `e2e/artifacts/logs/` - `backend.log`, `frontend.log`, `frontend-compile.log`
- `e2e/artifacts/shots/` - one screenshot per step

## Type check

ty takes one interpreter per run, so the launcher (backend venv) is checked apart:

```bash
cd e2e && uv run ty check . && uv run ty check --python ../backend/.venv launcher.py
```
