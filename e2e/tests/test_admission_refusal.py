"""/new shows a warm answer when the server refuses a new game (429 with a reason code)."""

import json
from collections.abc import Callable

import pytest
from playwright.sync_api import Page, Route, expect

NewPage = Callable[..., Page]


def refuse(code: str) -> Callable[[Route], None]:
    def handler(route: Route) -> None:
        route.fulfill(
            status=429,
            content_type="application/json",
            body=json.dumps({"detail": {"code": code}}),
        )

    return handler


@pytest.mark.parametrize(
    ("code", "text"),
    [
        ("rate_limited", "Слишком много попыток, попробуйте через час"),
        ("daily_full", "Сегодня все места заняты — приходите завтра"),
    ],
)
def test_new_page_explains_the_refusal(new_page: NewPage, code: str, text: str) -> None:
    page = new_page()
    page.route("**/api/v1/families", refuse(code))
    page.goto("/new")
    page.get_by_label("Название игры").fill("Smith")
    page.get_by_label("Ваше имя").fill("Anna")
    page.get_by_role("checkbox").check()
    page.get_by_role("button", name="Продолжить", exact=True).click()
    expect(page.get_by_text(text)).to_be_visible()


def test_limit_is_per_browser_through_the_site_proxy(new_page: NewPage) -> None:
    """X-Forwarded-For survives the Next rewrite: one context is refused, another is not."""
    body = {"title": "Bees", "locale": "ru", "display_name": "Вера", "privacy_consent": True}
    first, second = new_page().context.request, new_page().context.request
    statuses = [first.post("/api/v1/families", data=body).status for _ in range(4)]
    assert statuses == [201, 201, 201, 429]
    assert first.post("/api/v1/families", data=body).json() == {"detail": {"code": "rate_limited"}}
    assert second.post("/api/v1/families", data=body).status == 201
