"""Main path in a real browser: create family, invite a child, play, see the roster.

The tests share one family and run in file order (each builds on the previous one).
"""

import re
from collections.abc import Callable
from typing import Any

import httpx
from playwright.sync_api import Page, expect

from replies import ECHO, REPLY
from stack import Stack, count_rows

Shot = Callable[[Page, str], None]
NewPage = Callable[..., Page]

ADULT, CHILD = "Anna", "Misha"
flow: dict[str, Any] = {}


def fill_family_form(page: Page, labels: tuple[str, str, str], title: str) -> str:
    """Fill the /new form and return the creator's invite link as shown on the page."""
    family_label, name_label, submit = labels
    page.get_by_label(family_label).fill(title)
    page.get_by_label(name_label).fill(ADULT)
    page.get_by_role("button", name=submit, exact=True).click()
    link = page.get_by_role("textbox", name=ADULT)
    expect(link).to_be_visible()
    return link.input_value()


def test_health_reports_ready_agent(stack: Stack) -> None:
    r = httpx.get(f"{stack.backend}/health", timeout=5)
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "db": "ok", "agent": "ready"}


def test_create_family_shows_creator_link_and_session(
    new_page: NewPage, shot: Shot
) -> None:
    page = new_page()
    page.goto("/new")
    link = fill_family_form(
        page, ("Название семьи", "Ваше имя", "Создать семью"), "Smith"
    )
    assert "/join#" in link and "/en/" not in link, link
    shot(page, "01-new-family-created")
    cookies = page.context.cookies()
    assert [c for c in cookies if c["httpOnly"]], f"no session cookie in {cookies}"
    flow["creator"] = page.context.storage_state()
    page.goto("/play")  # the session works: the roster is behind it
    expect(page.get_by_role("list", name="Семья").get_by_text(ADULT)).to_be_visible()


def test_add_child_shows_child_invite_link(new_page: NewPage, shot: Shot) -> None:
    page = new_page(flow["creator"])
    page.goto("/family")
    expect(page.get_by_role("heading", name="Добавить участника")).to_be_visible()
    page.get_by_label("Имя", exact=True).fill(CHILD)
    page.get_by_role("button", name="Добавить", exact=True).click()
    link = page.get_by_role("textbox", name=f"Ссылка для входа: {CHILD}")
    expect(link).to_be_visible()
    flow["child_link"] = link.input_value()
    assert "/join#" in flow["child_link"]
    shot(page, "02-child-invite-link")


def test_child_opens_link_once_then_it_is_invalid(
    new_page: NewPage, shot: Shot
) -> None:
    page = new_page()
    page.goto(flow["child_link"])
    page.wait_for_url("**/play")
    assert "#" not in page.url, page.url
    expect(page.get_by_role("list", name="Семья").get_by_text(CHILD)).to_be_visible()
    flow["child"] = page.context.storage_state()
    shot(page, "03-child-landed-on-play")

    again = new_page()
    again.goto(flow["child_link"])
    expect(
        again.get_by_text("Ссылка недействительна или уже использована")
    ).to_be_visible()
    assert "#" not in again.url, again.url
    shot(again, "04-join-invalid")


def test_message_gets_game_master_reply(
    new_page: NewPage, shot: Shot, stack: Stack
) -> None:
    page = new_page(flow["child"])
    page.goto("/play")
    page.get_by_label("Сообщение ведущему").fill("Hello, game master!")
    page.get_by_role("button", name="Отправить").click()
    log = page.get_by_role("log")
    # the scripted model echoes the last user text: the reply proves the message reached it
    echo = re.compile(re.escape(f"{REPLY} {ECHO}Hello, game master!") + "$")
    expect(log.get_by_role("listitem")).to_have_text(
        [re.compile("Hello, game master!$"), echo]
    )
    shot(page, "05-play-with-reply")
    # the turn went through the real PostgresSpendStore, not an in-memory one
    assert count_rows(stack.database_url, "spend_counters") > 0


def test_family_roster_lists_both_and_adult_controls(
    new_page: NewPage, shot: Shot
) -> None:
    page = new_page(flow["creator"])
    page.goto("/family")
    expect(page.get_by_role("heading", name="Семья", exact=True)).to_be_visible()
    for name in (ADULT, CHILD):
        expect(page.get_by_role("listitem").filter(has_text=name).first).to_be_visible()
    expect(page.get_by_role("button", name=f"Новая ссылка: {CHILD}")).to_be_visible()
    expect(page.get_by_role("heading", name="Добавить участника")).to_be_visible()
    shot(page, "06-family-adult-view")


def test_child_cannot_add_members_or_reissue(new_page: NewPage, shot: Shot) -> None:
    page = new_page(flow["child"])
    page.goto("/family")
    for name in (ADULT, CHILD):
        expect(page.get_by_role("listitem").filter(has_text=name).first).to_be_visible()
    assert page.get_by_role("heading", name="Добавить участника").count() == 0
    assert page.get_by_role("button", name="Новая ссылка").count() == 0
    assert page.get_by_label("Имя", exact=True).count() == 0
    shot(page, "07-family-child-view")

    # the UI hides the controls; the API must refuse them too
    api = page.context.request
    me = api.get("/api/v1/me").json()
    add = api.post(
        f"/api/v1/families/{me['family_id']}/members",
        data={"display_name": "Intruder", "age_band": "6-9", "role": "child"},
    )
    assert add.status == 403, add.status
    reissue = api.post(f"/api/v1/members/{me['id']}/invite")
    assert reissue.status == 403, reissue.status


def test_english_family_gets_english_invite_and_pages(
    new_page: NewPage, shot: Shot
) -> None:
    page = new_page()
    page.goto("/en/new")
    link = fill_family_form(
        page, ("Family name", "Your name", "Create family"), "Jones"
    )
    assert "/en/join#" in link, link
    page.get_by_label("Name", exact=True).fill("Sam")
    page.get_by_role("button", name="Add", exact=True).click()
    child_link = page.get_by_role("textbox", name="Sign-in link for Sam")
    expect(child_link).to_be_visible()
    url = child_link.input_value()
    assert "/en/join#" in url, url
    shot(page, "08-en-new-family-links")

    kid = new_page()
    kid.goto(url)
    kid.wait_for_url("**/en/play")
    expect(kid.get_by_label("Message to the game master")).to_be_visible()
    expect(kid.get_by_text("Write the game master your first message.")).to_be_visible()
    shot(kid, "09-en-play")

    stale = new_page()
    stale.goto(url)
    expect(stale.get_by_text("This link is invalid or already used")).to_be_visible()
    shot(stale, "10-en-join-invalid")
