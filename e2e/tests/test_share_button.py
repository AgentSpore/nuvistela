"""The «Поделиться миром» sheet in a real browser: create the link, see it, turn it off.

The world and its cover are seeded like in test_share_page; no image model runs.
"""

import re
from collections.abc import Callable

import httpx
from playwright.sync_api import Page, ViewportSize, expect
from stack import Stack
from test_share_page import PHONE, overflow, seed_share

Shot = Callable[[Page, str], None]
NewPage = Callable[..., Page]

# Headless Chromium differs from a phone: no share window, clipboard behind a permission.
# Fix both so the copy path is the one under test, and record what was copied.
COPY_PATH = """
Object.defineProperty(navigator, 'share', {value: undefined, configurable: true});
window.__copied = [];
Object.defineProperty(navigator, 'clipboard', {
  value: {writeText: (text) => { window.__copied.push(text); return Promise.resolve(); }},
  configurable: true,
});
"""


def open_sheet(page: Page, viewport: ViewportSize) -> None:
    page.add_init_script(COPY_PATH)
    page.set_viewport_size(viewport)
    page.goto("/adventure")
    page.get_by_role("button", name="Поделиться миром").click()
    expect(page.get_by_role("dialog", name="Поделиться миром")).to_be_visible()


def test_adult_creates_link_and_turns_it_off(
    new_page: NewPage, stack: Stack, shot: Shot
) -> None:
    owner = new_page()
    _, token = seed_share(
        owner, stack
    )  # a link already exists: the sheet shows it on open
    open_sheet(owner, PHONE)
    sheet = owner.get_by_role("dialog")
    link = sheet.get_by_label("Ссылка на открытку")
    # The active link is there on open, without pressing «Создать ссылку».
    expect(link).to_have_value(re.compile(rf"^http://[^/]+/ru/w/{token}$"))
    expect(sheet.get_by_role("button", name="Создать ссылку")).to_have_count(0)
    expect(sheet.locator("main")).to_have_count(0)
    assert overflow(owner) <= 0, f"horizontal scroll at 390: {overflow(owner)}px"
    shot(owner, "share-sheet-390")

    sheet.get_by_role("button", name="Отключить ссылку").click()
    expect(sheet.get_by_text("Отключить ссылку? Открытка перестанет")).to_be_visible()
    sheet.get_by_role("button", name="Да, отключить").click()
    expect(sheet.get_by_text("Ссылка отключена")).to_be_visible()
    expect(link).to_have_count(0)
    shot(owner, "share-sheet-revoked-390")
    assert httpx.get(f"{stack.site}/w/{token}", timeout=10).status_code == 404

    sheet.get_by_role("button", name="Создать ссылку").click()
    expect(link).to_have_value(re.compile(r"^http://[^/]+/ru/w/[A-Za-z0-9_-]{22}$"))
    assert token not in link.input_value(), "a new link after revoke is a new token"
    expect(sheet.get_by_text("Ссылка скопирована")).to_be_visible()
    assert owner.evaluate("window.__copied") == [link.input_value()]
    assert sheet.evaluate("el => el.scrollWidth - el.clientWidth") <= 0
    assert overflow(owner) <= 0, "sheet overflows at 390"
    shot(owner, "share-sheet-created-390")

    owner.keyboard.press("Escape")
    expect(owner.get_by_role("dialog")).to_have_count(0)
