"""The URL locale decides the UI language, whatever the browser prefers or keeps.

The browser here drops every Set-Cookie (blocked cookies, a proxy that follows redirects),
so only the URL and Accept-Language are left to choose the locale. A server that picked a
language the page's own URL did not name once rendered English chrome at /ru/adventure and
React logged hydration error #418.
"""

import re

import pytest
from playwright.sync_api import Browser, Route, expect

from stack import Stack


def drop_set_cookie(route: Route) -> None:
    response = route.fetch(max_redirects=0)
    route.request.frame.page.context.clear_cookies()  # fetch() stores Set-Cookie in the jar
    headers = {k: v for k, v in response.headers.items() if k != "set-cookie"}
    route.fulfill(response=response, headers=headers)


# React sets this root marker when it starts hydrating; the probe below proves it finished.
HYDRATING = "Object.keys(document).some(k => k.startsWith('__reactContainer'))"


@pytest.mark.parametrize(
    ("browser_language", "path", "lang", "nav_item", "next_item"),
    [
        ("en-US", "/ru/adventure", "ru", "Приключение", "Участники"),
        ("ru-RU", "/en/adventure", "en", "Adventure", "Players"),
    ],
)
def test_url_locale_wins_without_cookies(
    browser: Browser,
    stack: Stack,
    browser_language: str,
    path: str,
    lang: str,
    nav_item: str,
    next_item: str,
) -> None:
    context = browser.new_context(
        base_url=stack.site,
        locale=browser_language,
        extra_http_headers={"Accept-Language": browser_language},
    )
    context.route("**/*", drop_set_cookie)
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    try:
        page.goto(path)
        expect(page.get_by_role("link", name=nav_item)).to_have_attribute(
            "aria-current", "page"
        )
        expect(page.locator("html")).to_have_attribute("lang", lang)
        page.wait_for_function(HYDRATING)
        page.evaluate("window.__probe = 1")
        page.get_by_role("link", name=next_item).click()
        expect(page.get_by_role("link", name=next_item)).to_have_attribute(
            "aria-current", "page"
        )
        expect(page.locator("html")).to_have_attribute("lang", lang)
        # A soft navigation only happens on a hydrated tree; a full reload drops the probe.
        assert page.evaluate("window.__probe") == 1
        assert [e for e in errors if "418" in e or "ydrat" in e] == []
    finally:
        context.unroute_all(behavior="ignoreErrors")
        context.close()


def test_client_sent_locale_header_does_not_pick_the_language(
    browser: Browser, stack: Stack
) -> None:
    context = browser.new_context(
        base_url=stack.site,
        extra_http_headers={"x-next-intl-locale": "en"},
    )
    page = context.new_page()
    try:
        page.goto("/ru/w/" + "a" * 22)
        expect(page.locator("html")).to_have_attribute("lang", "ru")
        expect(page.get_by_text("Could not")).to_have_count(0)
        expect(page.get_by_role("heading", level=1)).to_contain_text(
            re.compile("[А-Яа-я]")
        )
    finally:
        context.close()
