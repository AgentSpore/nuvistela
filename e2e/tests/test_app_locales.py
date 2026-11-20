"""The whole app in es and zh-CN at a phone: create family, own world, quest, done, reward."""

import json
import re
from collections.abc import Callable
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect
from test_adventure_flow import PHONE, overflow

Shot = Callable[[Page, str], None]
NewPage = Callable[..., Page]

MESSAGES = Path(__file__).resolve().parents[2] / "frontend" / "messages"
CYRILLIC = re.compile("[Ѐ-ӿ]")
WORLD = {
    "es": "Un faro en una isla que flota entre nubes, con gatos astronautas.",
    "zh-CN": "一座漂浮在云海中的灯塔岛，岛上住着会飞的猫。",
}
# What follows the quest title in the reward card: reward.done is "{title}: hecho" / "{title}：已完成".
DONE_WORD = {"es": "hecho", "zh-CN": "已完成"}


def messages(locale: str) -> dict:
    return json.loads((MESSAGES / f"{locale}.json").read_text(encoding="utf-8"))


def assert_clean(page: Page, locale: str, name: str) -> None:
    """Right language, no other script, no horizontal scroll."""
    expect(page.locator("html")).to_have_attribute("lang", locale)
    # The language switcher legitimately names «Русский» in its own script.
    text = page.evaluate(
        "() => { const b = document.body.cloneNode(true);"
        " b.querySelectorAll('select, script, style').forEach((s) => s.remove());"
        " return b.textContent; }"
    )
    leak = CYRILLIC.findall(text)
    assert not leak, (
        f"{name}: Cyrillic text leaked into the {locale} page: {''.join(leak[:20])}"
    )
    assert overflow(page) <= 0, f"{name}: horizontal scroll {overflow(page)}px"


@pytest.mark.parametrize("locale", ["es", "zh-CN"])
def test_family_to_reward_in_the_language(
    new_page: NewPage, shot: Shot, locale: str
) -> None:
    m = messages(locale)
    page = new_page()
    page.set_viewport_size(PHONE)

    page.goto(f"/{locale}/new")
    assert_clean(page, locale, "new")
    shot(page, f"locale-{locale}-1-new")
    page.get_by_label(m["new"]["title"]).fill("Smith")
    page.get_by_label(m["new"]["name"]).fill("Anna")
    page.get_by_role("checkbox").check()
    page.get_by_role("button", name=m["new"]["submit"], exact=True).click()
    expect(page.locator('#main a[href$="/adventure"]')).to_be_visible()
    assert_clean(page, locale, "new-created")
    shot(page, f"locale-{locale}-2-created")

    page.goto(f"/{locale}/adventure")
    field = page.get_by_label(m["adventure"]["customLabel"])
    expect(field).to_be_visible()
    assert_clean(page, locale, "adventure-start")
    shot(page, f"locale-{locale}-3-start")
    field.fill(WORLD[locale])
    page.get_by_role("button", name=m["adventure"]["start"], exact=True).click()
    quest = page.get_by_role(
        "region", name=re.compile(re.escape(m["adventure"]["questTitle"]))
    )
    expect(quest).to_be_visible(timeout=30_000)
    assert_clean(page, locale, "quest")
    shot(page, f"locale-{locale}-4-quest")
    title = quest.get_by_role("heading").inner_text()

    page.get_by_role("button", name=m["adventure"]["done"]).click()
    expect(page.get_by_role("dialog")).to_be_visible()
    shot(page, f"locale-{locale}-5-sheet")
    page.get_by_role("button", name=m["adventure"]["send"]).click()
    reward = page.get_by_role("status", name=re.compile(re.escape(DONE_WORD[locale])))
    expect(reward).to_be_visible()
    expect(reward).to_contain_text(title)
    assert_clean(page, locale, "reward")
    shot(page, f"locale-{locale}-6-reward")

    page.goto(f"/{locale}/family")
    expect(
        page.get_by_role("heading", name=m["family"]["title"], exact=True)
    ).to_be_visible()
    assert_clean(page, locale, "family")
    shot(page, f"locale-{locale}-7-family")
    page.goto(f"/{locale}/play")
    expect(
        page.get_by_role("heading", name=m["play"]["title"], exact=True)
    ).to_be_visible()
    assert_clean(page, locale, "play")
    shot(page, f"locale-{locale}-8-play")


@pytest.mark.parametrize("locale", ["es", "zh-CN"])
def test_landing_is_clean(new_page: NewPage, shot: Shot, locale: str) -> None:
    page = new_page()
    page.set_viewport_size(PHONE)
    page.goto(f"/{locale}")
    expect(page.get_by_role("heading", level=1)).to_have_text(
        messages(locale)["landing"]["title"]
    )
    assert_clean(page, locale, "landing")
    shot(page, f"locale-{locale}-0-landing")
