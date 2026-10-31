"""Pytest plugin (loaded with `-p harness`): the stack, browser and page fixtures."""

import re
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from stack import Stack, running_stack

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

    def make(state: dict | None = None) -> Page:
        ctx = browser.new_context(base_url=stack.site, storage_state=state)
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
