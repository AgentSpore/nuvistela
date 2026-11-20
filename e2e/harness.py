"""Pytest plugin (loaded with `-p harness`): the stack, browser and page fixtures."""

import itertools
import re
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    StorageState,
    sync_playwright,
)

from stack import Stack, running_stack

# One address per context from 100.64.0.0/10 (carrier-grade NAT): never public, yet not private,
# loopback or link-local for the backend's rightmost-non-private parser, so each browser gets its
# own admission bucket instead of all sharing 127.0.0.1.
_CLIENT_IPS = (f"100.64.{n // 250}.{n % 250 + 1}" for n in itertools.count())

SHOTS = Path(__file__).resolve().parent / "artifacts" / "shots"


@pytest.fixture(scope="session")
def stack() -> Iterator[Stack]:
    with running_stack() as s:
        yield s


@pytest.fixture(scope="session")
def browser(
    stack: Stack,
) -> Iterator[Browser]:  # stack first: its asyncio.run must precede Playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture
def new_page(browser: Browser, stack: Stack) -> Iterator[Callable[..., Page]]:
    """Each call opens a page in a fresh context: own cookies, like another person's device."""
    contexts: list[BrowserContext] = []

    def make(state: StorageState | None = None) -> Page:
        ctx = browser.new_context(
            base_url=stack.site,
            storage_state=state,
            extra_http_headers={"X-Forwarded-For": next(_CLIENT_IPS)},
        )
        contexts.append(ctx)
        return ctx.new_page()

    yield make
    for ctx in contexts:
        ctx.close()


@pytest.fixture
def shot() -> Callable[[Page, str], None]:
    SHOTS.mkdir(parents=True, exist_ok=True)

    def take(page: Page, name: str) -> None:
        page.screenshot(path=str(SHOTS / f"{re.sub(r'[^a-z0-9_-]', '_', name)}.png"))

    return take
