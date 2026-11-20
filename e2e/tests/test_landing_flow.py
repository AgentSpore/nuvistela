"""Landing signup through the real browser, API and migrated Postgres database."""

import asyncio
import json
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qs, urlparse

import asyncpg
import pytest
from playwright.sync_api import Page, expect

from stack import ROOT, Stack

NewPage = Callable[..., Page]
SHOTS = Path(__file__).resolve().parents[1] / "artifacts" / "shots"


def _open_landing(page: Page, locale: str, source: str | None = None) -> dict:
    path = "/" if locale == "ru" else f"/{locale}"
    if source:
        path += f"?source={source}"
    # Playwright sets navigator.webdriver, which the client treats as a bot and does not report.
    page.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => false})"
    )
    with (
        page.expect_response("**/api/v1/events") as legacy,
        page.expect_response("**/api/v1/pilot/events") as event,
    ):
        response = page.goto(path)
    assert legacy.value.status == 204
    assert response is not None and response.status == 200
    assert event.value.status == 204
    expect(page.get_by_role("heading", level=1)).to_be_visible()
    payload = event.value.request.post_data_json
    assert isinstance(payload, dict)
    return payload


def _landing_labels(locale: str) -> dict:
    return json.loads((ROOT / "frontend" / "messages" / f"{locale}.json").read_text())[
        "landing"
    ]


WAITLIST_WORDS = ("waitlist", "список ожидания", "lista de espera", "等候名单")


@pytest.mark.parametrize(
    "locale,viewport",
    [
        ("ru", (390, 844)),
        ("en", (390, 844)),
        ("es", (390, 844)),
        ("zh-CN", (390, 844)),
        ("ru", (1440, 900)),
    ],
)
def test_landing_start_button_opens_the_game_without_a_waitlist(
    new_page: NewPage, locale: str, viewport: tuple[int, int]
) -> None:
    page = new_page()
    page.set_viewport_size({"width": viewport[0], "height": viewport[1]})
    _open_landing(page, locale)
    start = (
        page.locator("main")
        .get_by_role("link", name=_landing_labels(locale)["ctaTry"], exact=True)
        .first
    )
    expect(start).to_be_in_viewport()
    text = page.locator("body").inner_text().lower()
    assert not [word for word in WAITLIST_WORDS if word in text]
    assert page.locator("#waitlist").count() == 0
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(
        path=str(SHOTS / f"landing-open-{locale}-{viewport[0]}.png"), full_page=True
    )
    start.click()
    prefix = "" if locale == "ru" else f"/{locale}"
    expect(page).to_have_url(re.compile(rf"{prefix}/new/?$"))


@pytest.mark.parametrize("locale", ["ru", "en", "es", "zh-CN"])
@pytest.mark.parametrize("width", [390, 1280])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_landing_illustrations_are_served_by_production_build(
    new_page: NewPage, locale: str, width: int, scheme: Literal["light", "dark"]
) -> None:
    page = new_page()
    page.set_viewport_size({"width": width, "height": 844})
    page.emulate_media(color_scheme=scheme)
    _open_landing(page, locale)
    images = page.locator("main img")
    expect(images).to_have_count(5)
    for image in images.all():
        source = image.get_attribute("src")
        assert source is not None
        assert page.request.get(source).status == 200
        expect(image).to_have_js_property("complete", True)
        assert image.evaluate("image => image.naturalWidth") > 0
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(
        path=str(SHOTS / f"landing-{locale}-{width}-{scheme}.png"), full_page=True
    )


def _pilot_stages_match(stack: Stack, landing: dict, intent: str) -> bool:
    async def check() -> bool:
        conn = await asyncpg.connect(stack.database_url)
        try:
            rows = await conn.fetch(
                "SELECT kind, intent FROM pilot_events WHERE session_id = $1::uuid",
                landing["session_id"],
            )
            session = await conn.fetchrow(
                "SELECT source, locale FROM pilot_sessions WHERE session_id = $1::uuid",
                landing["session_id"],
            )
            expected = {
                "landing_view",
                "demo_start",
                "demo_complete",
                "cta_click",
                "share_click",
            }
            return (
                len(rows) == 5
                and {row["kind"] for row in rows} == expected
                and all(
                    row["intent"] == (None if row["kind"] == "landing_view" else intent)
                    for row in rows
                )
                and session is not None
                and session["source"] == "share"
                and session["locale"] == landing["locale"]
            )
        finally:
            await conn.close()

    with ThreadPoolExecutor(1) as pool:
        return pool.submit(lambda: asyncio.run(check())).result()


@pytest.mark.parametrize(
    "locale,intent",
    [("ru", "family"), ("en", "solo"), ("es", "solo"), ("zh-CN", "family")],
)
def test_pilot_demo_share_and_signup_use_one_real_session(
    new_page: NewPage, stack: Stack, locale: str, intent: str
) -> None:
    page = new_page()
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    page.set_viewport_size(
        {"width": 390 if locale in ("ru", "es") else 1280, "height": 844}
    )
    landing = _open_landing(page, locale, "share")
    assert page.request.post("/api/v1/pilot/events", data=landing).status == 204
    labels = json.loads((ROOT / "frontend/messages" / f"{locale}.json").read_text())[
        "landing"
    ]["demo"]
    demo = page.locator("#demo")
    demo.get_by_role("button", name=labels[intent], exact=True).click()
    for action in ("start", "complete"):
        with page.expect_response("**/api/v1/pilot/events") as recorded:
            demo.get_by_role("button", name=labels[action], exact=True).click()
        assert recorded.value.status == 204
    expect(
        demo.get_by_role("heading", name=labels["chapterTitle"], exact=True)
    ).to_be_focused()
    with page.expect_response("**/api/v1/pilot/events") as shared:
        demo.get_by_role("button", name=labels["share"], exact=True).click()
    assert shared.value.status == 204
    expect(
        demo.get_by_text(labels["shareStatus"]["copied"], exact=True)
    ).to_be_visible()
    link = urlparse(page.evaluate("navigator.clipboard.readText()"))
    assert parse_qs(link.query) == {"source": ["share"]} and link.fragment == "demo"
    assert link.path == ("/" if locale == "ru" else f"/{locale}")
    with page.expect_response("**/api/v1/pilot/events") as cta:
        demo.get_by_role("link", name=labels["signup"], exact=True).click()
    assert cta.value.status == 204
    expect(page).to_have_url(re.compile(r"/new/?$"))
    assert _pilot_stages_match(stack, landing, intent)
    page.screenshot(path=str(SHOTS / f"pilot-{locale}-{intent}.png"), full_page=True)


@pytest.mark.parametrize("cookie", ["es", None])
def test_app_route_opens_for_a_visitor_with_a_landing_locale(
    new_page: NewPage, stack: Stack, cookie: str | None
) -> None:
    """A parent who previewed the Spanish landing must still reach the app routes."""
    page = new_page()
    if cookie:
        page.context.add_cookies(
            [{"name": "NEXT_LOCALE", "value": cookie, "url": stack.site}]
        )
    page.context.set_extra_http_headers({"Accept-Language": "es-ES,es;q=0.9"})
    response = page.goto("/new")
    assert response is not None and response.status == 200
    assert page.url.rstrip("/").endswith("/new")
