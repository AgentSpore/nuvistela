"""Bring up the whole stack for the suite: Postgres, backend launcher, Next.js production build."""

import asyncio
import os
import shutil
import socket
import subprocess
import time
from collections.abc import Generator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path

import asyncpg
import httpx
from testcontainers.community.postgres import PostgresContainer

ROOT = Path(__file__).resolve().parents[1]
E2E = Path(__file__).resolve().parent
LOGS = E2E / "artifacts" / "logs"
STANDALONE = ROOT / "frontend" / ".next" / "standalone"


@dataclass(frozen=True)
class Stack:
    site: str  # frontend origin; /api/* is rewritten to the backend
    backend: str  # backend origin, for /health only


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _migrate(url: str) -> None:
    conn = await asyncpg.connect(url)
    try:
        for sql in sorted((ROOT / "db" / "migrations").glob("V*.sql")):
            await conn.execute(sql.read_text())
    finally:
        await conn.close()


def _wait(url: str, proc: subprocess.Popen, timeout: float = 120) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"process for {url} exited with {proc.returncode}, see {LOGS}"
            )
        with suppress(httpx.HTTPError):
            if httpx.get(url, timeout=2).status_code == 200:
                return
        time.sleep(0.5)
    raise TimeoutError(f"{url} not ready in {timeout}s")


def _spawn(
    cmd: list[str], cwd: Path, env: dict[str, str], name: str
) -> subprocess.Popen:
    LOGS.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        stdout=(LOGS / f"{name}.log").open("w"),
        stderr=subprocess.STDOUT,
    )


def _stop(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def _compile_frontend(env: dict[str, str]) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    with (LOGS / "frontend-compile.log").open("w") as out:
        subprocess.run(
            ["pnpm", "build"],
            cwd=ROOT / "frontend",
            env=env,
            stdout=out,
            stderr=out,
            check=True,
        )
    # Same layout as frontend/Dockerfile: `next start` does not support `output: standalone`
    # (it redirects every page to itself), the deployed image runs `node server.js`.
    shutil.copytree(
        ROOT / "frontend" / ".next" / "static",
        STANDALONE / ".next" / "static",
        dirs_exist_ok=True,
    )


@contextmanager
def running_stack() -> Generator[Stack]:
    """Start everything, yield the origins, tear it all down."""
    base_env = {k: v for k, v in os.environ.items() if k != "OPENROUTER_API_KEY"}
    procs: list[subprocess.Popen] = []
    with PostgresContainer("postgres:17", driver=None) as pg:
        url = pg.get_connection_url()
        asyncio.run(_migrate(url))
        be_port, fe_port = free_port(), free_port()
        try:
            be_env = {
                **base_env,
                "DATABASE_URL": url.replace("postgresql://", "postgresql+asyncpg://"),
                "PORT": str(be_port),
                "PYTHONPATH": str(ROOT / "backend"),
            }
            cmd = [
                "uv",
                "run",
                "--project",
                str(ROOT / "backend"),
                "python",
                str(E2E / "launcher.py"),
            ]
            backend = _spawn(cmd, E2E, be_env, "backend")
            procs.append(backend)
            _wait(f"http://127.0.0.1:{be_port}/health", backend)
            fe_env = {**base_env, "API_ORIGIN": f"http://127.0.0.1:{be_port}"}
            _compile_frontend(fe_env)
            frontend = _spawn(
                ["node", "server.js"],
                STANDALONE,
                {**fe_env, "PORT": str(fe_port), "HOSTNAME": "0.0.0.0"},
                "frontend",
            )
            procs.append(frontend)
            _wait(f"http://127.0.0.1:{fe_port}/", frontend)
            yield Stack(f"http://127.0.0.1:{fe_port}", f"http://127.0.0.1:{be_port}")
        finally:
            for p in reversed(procs):
                _stop(p)
