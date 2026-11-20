"""Adventure in a real browser: the story seeded through the API survives a reload.

The chapter worker may or may not have answered by the time the page loads, so the
chapter is checked against every honest status text, never against a fixed one.
"""

import re
import time
from collections.abc import Callable

from playwright.sync_api import Page, ViewportSize, expect

from replies import WORLD_QUEST_DESCRIPTION, WORLD_QUEST_TITLE

Shot = Callable[[Page, str], None]
NewPage = Callable[..., Page]

PHONE = ViewportSize(width=390, height=844)
DESKTOP = ViewportSize(width=1280, height=800)
HONEST_STATUSES = re.compile(
    "Глава ждёт своей очереди|Рассказчик пишет главу|Рассказчик сейчас недоступен"
    "|На сегодня лимит историй исчерпан"
)


def overflow(page: Page) -> int:
    return page.evaluate("document.documentElement.scrollWidth - window.innerWidth")


def wait_for_quest(page: Page, family_id: str) -> dict:
    """Poll the adventure like the client does: quest 1 appears once the world worker stored the world."""
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        body = page.context.request.get(f"/api/v1/families/{family_id}/adventure").json()
        if body["quest"] is not None:
            return body["quest"]
        time.sleep(0.5)
    raise AssertionError("no quest within 30 s of the start")


def seed_adventure(page: Page) -> str:
    """Create a family, start the adventure and mark its first quest done; return the quest title."""
    api = page.context.request
    created = api.post(
        "/api/v1/families",
        data={
            "title": "Adventurers",
            "locale": "ru",
            "display_name": "Anna",
            "privacy_consent": True,
            "interests": [],
        },
    )
    assert created.ok, created.status
    family_id = created.json()["family_id"]
    started = api.post(f"/api/v1/families/{family_id}/adventure", data={"genre": "space"})
    assert started.ok, started.status
    quest = wait_for_quest(page, family_id)
    done = api.post(
        f"/api/v1/quests/{quest['id']}/done",
        data={"note": "Мы справились"},
        headers={"Idempotency-Key": "e2e-seed-1"},
    )
    assert done.ok, done.status
    return quest["title"]


def test_seeded_story_survives_reload(new_page: NewPage, shot: Shot) -> None:
    page = new_page()
    seed_adventure(page)
    page.set_viewport_size(PHONE)
    page.goto("/adventure")
    chapter = page.get_by_role("listitem").filter(has_text="Глава 1")
    expect(chapter).to_be_visible()
    expect(chapter).to_contain_text(HONEST_STATUSES)
    assert overflow(page) <= 0, f"horizontal scroll at 390: {overflow(page)}px"
    shot(page, "adventure-1-story-390")

    page.reload()  # R8: the page is rebuilt from the server alone
    expect(page.get_by_role("heading", name="Ваша история")).to_be_visible()
    expect(chapter).to_be_visible()
    expect(chapter).to_contain_text(HONEST_STATUSES)
    shot(page, "adventure-2-reloaded-390")

    page.set_viewport_size(DESKTOP)
    expect(chapter).to_be_visible()
    assert overflow(page) <= 0, f"horizontal scroll at 1280: {overflow(page)}px"
    shot(page, "adventure-3-reloaded-1280")


def test_start_by_genre_and_mark_done_in_the_browser(new_page: NewPage, shot: Shot) -> None:
    page = new_page()
    created = page.context.request.post(
        "/api/v1/families",
        data={
            "title": "Players",
            "locale": "ru",
            "display_name": "Anna",
            "privacy_consent": True,
            "interests": [],
        },
    )
    assert created.ok, created.status
    page.set_viewport_size(PHONE)
    page.goto("/adventure")
    expect(page.get_by_role("heading", name="Придумайте свой мир")).to_be_visible()
    expect(page.get_by_role("group", name="или выберите готовый")).to_be_visible()
    assert overflow(page) <= 0, f"horizontal scroll at 390 (start): {overflow(page)}px"
    shot(page, "adventure-ui-1-start-390")

    page.get_by_role("radio", name="Космос").check(force=True)
    page.get_by_role("button", name="Начать", exact=True).click()
    quest = page.get_by_role("region", name=re.compile("Ваше задание"))
    # World worker poll (2 s) + fallback write + the page's own 3 s poll sit near the 5 s default.
    expect(quest).to_be_visible(timeout=30_000)
    title = quest.get_by_role("heading").inner_text()
    shot(page, "adventure-ui-2-quest-390")

    page.reload()  # the open quest comes back from the server alone
    expect(page.get_by_role("heading", name=title)).to_be_visible()

    trigger = page.get_by_role("button", name="Готово!")
    trigger.click()
    page.get_by_role("button", name="Закрыть").click()
    expect(page.get_by_role("dialog")).to_have_count(0)
    expect(trigger).to_be_focused()  # a real browser: not <body>, the trigger was inert while modal
    trigger.click()
    page.get_by_label("Заметка (необязательно)").fill("Мы справились")
    expect(page.get_by_text("13 из 280")).to_be_visible()
    assert overflow(page) <= 0, f"horizontal scroll at 390 (sheet): {overflow(page)}px"
    shot(page, "adventure-ui-3-sheet-390")
    page.evaluate(
        "window.__focused = []; document.addEventListener('focusin', "
        "(e) => window.__focused.push(e.target.textContent))"
    )
    page.get_by_role("button", name="Отправить отметку").click()
    chapter = page.get_by_role("listitem").filter(has_text="Глава 1")
    expect(chapter).to_be_visible()
    expect(chapter).to_contain_text(HONEST_STATUSES)
    # The done card goes away once the quest is done, so focus is read from its focusin event.
    assert "Готово!" in page.evaluate("window.__focused"), "focus never reached the trigger"
    shot(page, "adventure-ui-4-chapter-390")

    page.reload()
    expect(page.get_by_role("heading", name="Ваша история")).to_be_visible()
    expect(chapter).to_be_visible()
    expect(chapter).to_contain_text(HONEST_STATUSES)
    assert overflow(page) <= 0, f"horizontal scroll at 390: {overflow(page)}px"
    shot(page, "adventure-ui-5-reloaded-390")

    page.set_viewport_size(DESKTOP)
    expect(chapter).to_be_visible()
    assert overflow(page) <= 0, f"horizontal scroll at 1280: {overflow(page)}px"
    shot(page, "adventure-ui-6-reloaded-1280")


def test_own_world_from_an_example_at_390(new_page: NewPage, shot: Shot) -> None:
    """Own text is the main path: an example fills the field and takes focus, then a custom world starts."""
    page = new_page()
    created = page.context.request.post(
        "/api/v1/families",
        data={
            "title": "Dreamers",
            "locale": "ru",
            "display_name": "Anna",
            "privacy_consent": True,
            "interests": [],
        },
    )
    assert created.ok, created.status
    page.set_viewport_size(PHONE)
    page.goto("/adventure")
    field = page.get_by_label("Опишите свой мир")
    expect(field).to_be_visible()
    expect(page.get_by_role("button", name="Начать", exact=True)).to_be_disabled()
    page.get_by_role("button", name=re.compile("^Лесная школа")).click()
    expect(field).to_have_value(re.compile("^Лесная школа"))
    expect(field).to_be_focused()
    expect(page.get_by_text(re.compile(r"^\d+ из 300$"))).to_be_visible()
    assert overflow(page) <= 0, f"horizontal scroll at 390 (example): {overflow(page)}px"
    shot(page, "adventure-own-world-1-example-390")

    page.get_by_role("button", name="Начать", exact=True).click()
    quest = page.get_by_role("region", name=re.compile("Ваше задание"))
    alert = page.locator("#a-custom-err")
    # A limit mismatch (422) shows the alert instead of the quest: fail on it, not on a timeout.
    expect(quest.or_(alert)).to_be_visible(timeout=30_000)
    expect(alert).to_have_count(0)
    expect(quest).to_be_visible()
    shot(page, "adventure-own-world-2-quest-390")


def test_world_title_and_prologue_are_shown(new_page: NewPage, shot: Shot) -> None:
    """The generated world (the scripted model falls back to the stored one) is on screen."""
    page = new_page()
    created = page.context.request.post(
        "/api/v1/families",
        data={
            "title": "Worlds",
            "locale": "ru",
            "display_name": "Anna",
            "privacy_consent": True,
            "interests": [],
        },
    )
    assert created.ok, created.status
    family_id = created.json()["family_id"]
    started = page.context.request.post(
        f"/api/v1/families/{family_id}/adventure", data={"genre": "space"}
    )
    assert started.ok, started.status
    for name, viewport in (("390", PHONE), ("1280", DESKTOP)):
        page.set_viewport_size(viewport)
        page.goto("/adventure")
        expect(page.get_by_text("Звёздный дом")).to_be_visible(timeout=30_000)
        expect(page.get_by_text("Станция проснулась среди звёзд и ждёт вас.")).to_be_visible()
        assert overflow(page) <= 0, f"horizontal scroll at {name}: {overflow(page)}px"
        shot(page, f"adventure-world-{name}")


def test_quest_one_on_screen_is_the_generated_worlds_quest(new_page: NewPage, shot: Shot) -> None:
    """The world model writes a world: quest 1 is its first_quest (source 'world'), not a template."""
    page = new_page()
    created = page.context.request.post(
        "/api/v1/families",
        data={
            "title": "Pirates",
            "locale": "ru",
            "display_name": "Anna",
            "privacy_consent": True,
            "interests": [],
        },
    )
    assert created.ok, created.status
    page.set_viewport_size(PHONE)
    page.goto("/adventure")
    page.get_by_role("radio", name="Пираты").check(force=True)
    page.get_by_role("button", name="Начать", exact=True).click()
    quest = page.get_by_role("region", name=re.compile("Ваше задание"))
    expect(quest.get_by_role("heading", name=WORLD_QUEST_TITLE)).to_be_visible(timeout=30_000)
    expect(quest).to_contain_text(WORLD_QUEST_DESCRIPTION)
    assert overflow(page) <= 0, f"horizontal scroll at 390: {overflow(page)}px"
    shot(page, "adventure-world-quest-390")
