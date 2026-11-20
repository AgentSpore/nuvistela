"""Layout shift on /adventure at 390x844: the world and first quest arrive by polling, the share sheet opens.

CLS counts only shifts without a tap in the previous 500 ms (`hadRecentInput`), so what is
measured here is what the page does to the reader on its own.
"""

import hashlib
import re
import time
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

from playwright.sync_api import Page, Route, expect
from test_adventure_flow import PHONE
from test_share_button import COPY_PATH
from test_share_page import COVER

from stack import Stack, run_sql

SHOTS = Path(__file__).resolve().parents[1] / "artifacts" / "shots"

NewPage = Callable[..., Page]

BUDGET = 0.1
OBSERVE = """
window.__shifts = [];
new PerformanceObserver((list) => {
  for (const e of list.getEntries()) {
    if (e.hadRecentInput) continue;
    const name = (n) => !n ? '?' : n.nodeType === 1
      ? n.tagName.toLowerCase() + (n.id ? '#' + n.id : '') + '.' + String(n.className).slice(0, 40)
      : '#text';
    window.__shifts.push({value: e.value, at: Math.round(e.startTime), sources: e.sources.map((s) => name(s.node))});
  }
}).observe({type: 'layout-shift', buffered: true});
"""


def late_answer(page: Page, url: str) -> None:
    """A phone on a slow network: the answer comes after the 500 ms grace that follows a tap."""

    def late(route: Route) -> None:
        page.wait_for_timeout(800)
        route.continue_()

    page.route(re.compile(url), late)


def settle(page: Page) -> None:
    """Two painted frames: any shift the last change caused has been reported."""
    page.evaluate(
        "new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))"
    )


def shifts(page: Page) -> list[dict]:
    return page.evaluate("window.__shifts")


def cls(page: Page) -> float:
    return sum(s["value"] for s in shifts(page))


def set_cover(stack: Stack, family_id: str, status: str) -> None:
    deadline = time.monotonic() + 30
    while not (
        rows := run_sql(
            stack.database_url,
            "SELECT job_id FROM worlds WHERE family_id = $1 AND status = 'ready'",
            UUID(family_id),
        )
    ):
        assert time.monotonic() < deadline, "world not ready within 30 s"
        time.sleep(0.3)
    run_sql(
        stack.database_url,
        "INSERT INTO world_images (family_id, world_job_id, kind, prompt, status, sha256, bytes)"
        " VALUES ($1, $2, 'cover', 'p', $3, $4, $5)"
        " ON CONFLICT (family_id, world_job_id, kind, milestone_no) DO UPDATE"
        " SET status = $3, sha256 = $4, bytes = $5",
        UUID(family_id),
        rows[0]["job_id"],
        status,
        hashlib.sha256(COVER).hexdigest() if status == "ready" else None,
        COVER if status == "ready" else None,
    )


def start_adventure(page: Page, stack: Stack) -> str:
    """Create a family and press «Начать»; return the family id."""
    created = page.context.request.post(
        "/api/v1/families",
        data={
            "title": "Shifters",
            "locale": "ru",
            "display_name": "Anna",
            "privacy_consent": True,
            "interests": [],
        },
    )
    assert created.ok, created.status
    page.add_init_script(OBSERVE)
    page.set_viewport_size(PHONE)
    page.goto("/adventure")
    page.get_by_role("radio", name="Пираты").check(force=True)
    page.get_by_role("button", name="Начать", exact=True).click()
    return created.json()["family_id"]


def test_world_and_first_quest_arrive_without_shifting_the_page(
    new_page: NewPage, stack: Stack
) -> None:
    page = new_page()
    late_answer(
        page, r"/api/v1/families/[^/]+/world$"
    )  # the world follows the poll that announced it
    family_id = start_adventure(page, stack)
    set_cover(
        stack, family_id, "pending"
    )  # the live picture is pending when the world lands
    quest = page.get_by_role("region", name=re.compile("Ваше задание"))
    expect(quest).to_be_visible(timeout=30_000)
    placeholder = page.get_by_test_id("world-cover-placeholder")
    expect(placeholder).to_have_text("Рисуем ваш мир…")  # never an empty box
    page.screenshot(path=SHOTS / "cover-placeholder-390.png")
    set_cover(stack, family_id, "ready")  # the picture finishes while the reader looks
    expect(page.get_by_alt_text(re.compile("Обложка"))).to_have_css(
        "opacity", "1", timeout=30_000
    )
    settle(page)
    assert cls(page) < BUDGET, f"CLS {cls(page):.3f}: {shifts(page)}"


def test_opening_the_share_sheet_does_not_shift_the_page(
    new_page: NewPage, stack: Stack
) -> None:
    page = new_page()
    family_id = start_adventure(page, stack)
    quest = page.get_by_role("region", name=re.compile("Ваше задание"))
    expect(quest).to_be_visible(timeout=30_000)
    set_cover(stack, family_id, "ready")
    page.add_init_script(COPY_PATH)
    page.reload()
    opener = page.get_by_role("button", name="Поделиться миром")
    expect(opener).to_be_visible()
    settle(page)
    page.evaluate(
        "window.__shifts.length = 0"
    )  # the sheet is under test, not the page load
    late_answer(page, r"/api/v1/families/[^/]+/world/share$")
    opener.click()
    sheet = page.get_by_role("dialog", name="Поделиться миром")
    expect(sheet).to_be_visible()
    expect(
        sheet.get_by_role("heading", level=1)
    ).to_be_visible()  # the preview data has landed
    expect(sheet.get_by_role("button", name="Создать ссылку")).to_be_enabled()
    settle(page)
    assert cls(page) < BUDGET, f"CLS {cls(page):.3f}: {shifts(page)}"
