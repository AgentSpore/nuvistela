"""Privacy policy page, links to it, consent on /new, and owner-only family deletion."""

import json
import re
from collections.abc import Callable
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect
from test_adventure_flow import PHONE, overflow
from test_family_flow import fill_family_form

Shot = Callable[[Page, str], None]
NewPage = Callable[..., Page]

MESSAGES = Path(__file__).resolve().parents[2] / "frontend" / "messages"
LOCALES = {"ru": "", "en": "/en", "es": "/es", "zh-CN": "/zh-CN"}


def messages(locale: str) -> dict:
    return json.loads((MESSAGES / f"{locale}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("locale", list(LOCALES))
def test_policy_page_in_every_locale(new_page: NewPage, shot: Shot, locale: str) -> None:
    m = messages(locale)["privacy"]
    page = new_page()
    page.set_viewport_size(PHONE)
    response = page.goto(f"{LOCALES[locale]}/privacy")
    assert response is not None and response.status == 200
    expect(page.locator("html")).to_have_attribute("lang", locale)
    expect(page.get_by_role("heading", level=1, name=m["title"])).to_be_visible()
    expect(page.get_by_text(m["effective"])).to_be_visible()
    expect(page.get_by_text(m["version"])).to_be_visible()
    for section in m["sections"]:
        expect(page.get_by_role("heading", level=2, name=section["h"])).to_be_visible()
    assert overflow(page) <= 0, f"horizontal scroll {overflow(page)}px"
    assert re.search(m["title"].split()[0], page.title()), page.title()
    shot(page, f"privacy-{locale}")


@pytest.mark.parametrize("path", ["/", "/new", "/family", "/join", "/privacy"])
def test_footer_links_the_policy_on_site_pages(new_page: NewPage, path: str) -> None:
    page = new_page()
    page.goto(path)
    link = page.get_by_role("contentinfo").get_by_role(
        "link", name=messages("ru")["footer"]["privacy"]
    )
    expect(link).to_be_visible()
    link.click()
    page.wait_for_url("**/privacy")
    expect(page.get_by_role("heading", level=1)).to_have_text(messages("ru")["privacy"]["title"])


def test_new_family_requires_consent(new_page: NewPage, shot: Shot) -> None:
    page = new_page()
    page.set_viewport_size(PHONE)
    page.goto("/new")
    page.get_by_label("Название игры").fill("Consent")
    page.get_by_label("Ваше имя").fill("Anna")
    submit = page.get_by_role("button", name="Продолжить", exact=True)
    expect(submit).to_be_disabled()
    shot(page, "privacy-new-consent")
    with page.expect_popup() as popup:
        page.get_by_role("link", name="политику конфиденциальности").click()
    expect(popup.value.get_by_role("heading", level=1)).to_have_text(
        messages("ru")["privacy"]["title"]
    )
    page.get_by_role("checkbox").check()
    expect(submit).to_be_enabled()


def test_join_states_acceptance_with_policy_link(new_page: NewPage) -> None:
    page = new_page()
    page.goto("/join#nonsense")
    expect(page.get_by_text("Продолжая, вы принимаете")).to_be_visible()
    expect(page.get_by_role("link", name="политику конфиденциальности")).to_be_visible()


def test_owner_deletes_family_and_session_ends(new_page: NewPage, shot: Shot) -> None:
    """Needs feature/privacy-backend (DELETE /families/{id}); run after it is merged."""
    page = new_page()
    page.set_viewport_size(PHONE)
    page.goto("/new")
    fill_family_form(page, ("Название игры", "Ваше имя", "Продолжить"), "Doomed")
    page.goto("/family")
    page.get_by_role("button", name="Удалить семью и все данные").click()
    confirm = page.get_by_role("button", name="Удалить навсегда")
    expect(confirm).to_be_disabled()
    page.get_by_label("Подтверждение").fill("удалить")
    expect(confirm).to_be_disabled()
    page.get_by_label("Подтверждение").fill("УДАЛИТЬ")
    confirm.scroll_into_view_if_needed()
    shot(page, "privacy-family-delete-confirm")
    confirm.click()
    page.wait_for_url(re.compile(r"/$"))
    assert page.request.get("/api/v1/me").status == 401
    page.goto("/family")
    expect(page.get_by_role("heading", name="Сначала войдите")).to_be_visible()
