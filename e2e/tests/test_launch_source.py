"""A visitor from a launch post (`/?source=telegram`) who creates a game is a lead for that source.

Playwright sets navigator.webdriver, which the client treats as a bot and does not report, so the
page hides it, as a real visitor's browser would.
"""

import json
from collections.abc import Callable

from playwright.sync_api import Page
from stack import Stack, run_sql
from test_family_flow import fill_family_form

NewPage = Callable[..., Page]


def test_game_created_after_a_telegram_post_is_a_telegram_lead(
    new_page: NewPage, stack: Stack
) -> None:
    page = new_page()
    page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => false})")
    with page.expect_response("**/api/v1/pilot/events") as landed:
        page.goto("/?source=telegram&utm_source=telegram&utm_campaign=launch")
    assert landed.value.status == 204
    session = json.loads(page.evaluate("sessionStorage.getItem('bumbli-pilot-session')"))
    assert session["source"] == "telegram"

    page.goto("/new")
    with page.expect_response("**/api/v1/families") as created:
        fill_family_form(page, ("Название игры", "Ваше имя", "Продолжить"), "Launch")
    assert created.value.status == 201
    sent = json.loads(created.value.request.post_data or "{}")
    assert sent["attribution"]["session_id"] == session["session_id"]

    rows = run_sql(
        stack.database_url,
        "SELECT e.kind, e.source, s.source AS first_touch"
        " FROM pilot_events e JOIN pilot_sessions s USING (session_id)"
        " WHERE session_id = $1::uuid ORDER BY e.at",
        session["session_id"],
    )
    assert [dict(r) for r in rows] == [
        {"kind": "landing_view", "source": "telegram", "first_touch": "telegram"},
        {"kind": "lead_created", "source": "telegram", "first_touch": "telegram"},
    ]
