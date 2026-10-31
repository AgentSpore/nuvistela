"""Bring up the whole stack for the suite: Postgres, backend launcher, Next.js production build."""

import asyncio
import os
import re
import shutil
import socket
import subprocess
import time
from collections.abc import Generator
from contextlib import contextmanager, suppress
from typing import IO
from dataclasses import dataclass
from pathlib import Path

import asyncpg
import httpx
from testcontainers.community.postgres import PostgresContainer

ROOT = Path(__file__).resolve().parents[1]
E2E = Path(__file__).resolve().parent
LOGS = E2E / "artifacts" / "logs"
STANDALONE = ROOT / "frontend" / ".next" / "standalone"
# The only variables a child process inherits; the stack adds its own on top.
INHERITED_ENV = ("PATH", "HOME", "LANG", "TMPDIR")
_VERSIONED = re.compile(r"V(\d+)__.*\.sql")


@dataclass
class Service:
    proc: subprocess.Popen
    log: IO[str]


@dataclass(frozen=True)
class Stack:
    site: str  # frontend origin; /api/* is rewritten to the backend
    backend: str  # backend origin, for /health only


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _migration_files(directory: Path) -> list[Path]:
    """Flyway order: V files by numeric version (V10 after V2), then R__ files by name."""
    versioned = [
        (int(m[1]), f)
        for f in directory.glob("V*.sql")
        if (m := _VERSIONED.fullmatch(f.name))
    ]
    repeatable = sorted(directory.glob("R__*.sql"))
    return [f for _, f in sorted(versioned)] + repeatable


async def _migrate(url: str) -> None:
    conn = await asyncpg.connect(url)
    try:
        for sql in _migration_files(ROOT / "db" / "migrations"):
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


def _spawn(cmd: list[str], cwd: Path, env: dict[str, str], name: str) -> Service:
    LOGS.mkdir(parents=True, exist_ok=True)
    log = (LOGS / f"{name}.log").open("w")
    try:
        proc = subprocess.Popen(
            cmd, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT
        )
    except BaseException:
        log.close()
        raise
    return Service(proc, log)


def _stop(svc: Service) -> None:
    try:
        svc.proc.terminate()
        try:
            svc.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            svc.proc.kill()
            svc.proc.wait(timeout=10)
    finally:
        svc.log.close()


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
    base_env = {k: os.environ[k] for k in INHERITED_ENV if k in os.environ}
    services: list[Service] = []
    with PostgresContainer("postgres:17", driver=None) as pg:
        url = pg.get_connection_url()
        asyncio.run(_migrate(url))
        be_port = free_port()
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
            services.append(backend)
            _wait(f"http://127.0.0.1:{be_port}/health", backend.proc)
            fe_env = {**base_env, "API_ORIGIN": f"http://127.0.0.1:{be_port}"}
            _compile_frontend(fe_env)
            fe_port = (
                free_port()
            )  # picked last: the longest wait (build) must not hold it
            frontend = _spawn(
                ["node", "server.js"],
                STANDALONE,
                {**fe_env, "PORT": str(fe_port), "HOSTNAME": "0.0.0.0"},
                "frontend",
            )
            services.append(frontend)
            _wait(f"http://127.0.0.1:{fe_port}/", frontend.proc)
            yield Stack(f"http://127.0.0.1:{fe_port}", f"http://127.0.0.1:{be_port}")
        finally:
            for svc in reversed(services):
                _stop(svc)
