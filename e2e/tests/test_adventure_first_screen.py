"""/adventure at launch: every button is named, and the first visit shows the quest text and «Готово!» above the fold."""

import re
from collections.abc import Callable
from pathlib import Path

import pytest
from playwright.sync_api import Locator, Page, Route, ViewportSize, expect
from test_adventure_cls import (
    BUDGET,
    OBSERVE,
    cls,
    set_cover,
    settle,
    shifts,
    start_adventure,
)
from test_adventure_flow import PHONE, overflow, wait_for_quest
from test_first_loop import QUEST_LABEL, make_chapter_ready, with_chapter_one
from test_world3d import READY, stub_scene

from stack import Stack

NewPage = Callable[..., Page]
Shot = Callable[[Page, str], None]

DESKTOP = ViewportSize(width=1440, height=900)
FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "node_modules" / ".pnpm"


def unnamed_buttons(page: Page) -> list[str]:
    """Nodes axe's `button-name` rule rejects on the current DOM, open «О мире» and sheets included."""
    return page.evaluate(
        "window.axe.run(document, {runOnly: ['button-name']})"
        ".then((r) => r.violations.flatMap((v) => v.nodes.map((n) => n.html)))"
    )


def load_axe(page: Page) -> None:
    found = sorted(
        FRONTEND.glob("axe-core@*/node_modules/axe-core/axe.min.js"),
        key=lambda path: [int(n) for n in re.findall(r"\d+", path.parts[-4])],
    )
    assert found, "axe-core not found in frontend/node_modules/.pnpm — run pnpm install"
    script = found[-1]
    page.add_script_tag(path=str(script))


def check_buttons(page: Page, state: str) -> None:
    load_axe(page)
    page.evaluate(
        "document.querySelectorAll('details').forEach((d) => (d.open = true))"
    )
    assert unnamed_buttons(page) == [], f"unnamed buttons in state «{state}»"


def hold_world_pending(page: Page) -> Callable[[], None]:
    """Once the world exists, answer the adventure poll as still being written until released.

    Before the start the real (empty) state passes through, so the pre-start check sees no world.
    """
    held = {"on": True}

    def answer(route: Route) -> None:
        body = route.fetch().json()
        if held["on"] and body.get("world") is not None:
            body["world"] = {"status": "pending"}
            body["quest"], body["chapters"] = None, []
        route.fulfill(json=body)

    page.route(re.compile(r"/api/v1/families/[^/]+/adventure$"), answer)
    return lambda: held.update(on=False)


def test_no_unnamed_buttons_in_any_state_of_the_adventure(
    new_page: NewPage, stack: Stack
) -> None:
    page = new_page()
    page.set_viewport_size(PHONE)
    created = page.context.request.post(
        "/api/v1/families",
        data={
            "title": "Axe",
            "locale": "ru",
            "display_name": "Anna",
            "privacy_consent": True,
            "interests": [],
        },
    )
    assert created.ok, created.status
    family_id = created.json()["family_id"]
    page.goto("/adventure")
    page.get_by_role("radio", name="Пираты").check(force=True)
    check_buttons(page, "choose a world")
    release = hold_world_pending(page)
    page.get_by_role("button", name="Начать", exact=True).click()
    expect(page.get_by_text("Мир пишется", exact=False).first).to_be_visible(
        timeout=15_000
    )
    check_buttons(page, "the world is written")
    wait_for_quest(page, family_id)
    release()
    page.reload()
    quest = page.get_by_role("region", name=re.compile("Ваше задание"))
    expect(quest).to_be_visible(timeout=30_000)
    check_buttons(page, "the first quest")
    quest.get_by_role("button", name="Готово!").click()
    expect(page.get_by_role("dialog")).to_be_visible()
    check_buttons(page, "the check-in sheet")
    page.get_by_role("dialog").get_by_role("button", name="Отправить").click()
    expect(page.locator("#reward-title")).to_be_visible(timeout=15_000)
    check_buttons(page, "after «Готово!»: the reward")
    make_chapter_ready(stack, family_id)
    expect(page.get_by_role("heading", name="Фонарь бухты", exact=True)).to_be_visible(
        timeout=30_000
    )
    check_buttons(page, "after «Готово!»: the chapter")


def test_no_unnamed_buttons_on_a_return_visit_with_cover_scene_and_share(
    new_page: NewPage, stack: Stack
) -> None:
    page = new_page()
    page.set_viewport_size(PHONE)
    family_id = start_adventure(page, stack)
    expect(page.get_by_role("region", name=re.compile("Ваше задание"))).to_be_visible(
        timeout=30_000
    )
    set_cover(stack, family_id, "ready")
    with_chapter_one(page)
    stub_scene(page, READY)
    page.reload()
    expect(page.get_by_alt_text(re.compile("Обложка"))).to_be_visible()
    check_buttons(page, "a return visit")
    page.get_by_role("button", name=re.compile("Пройтись по миру в 3D")).click()
    expect(page.get_by_role("dialog")).to_be_visible()
    check_buttons(page, "the 3D dialog")
    page.keyboard.press("Escape")
    page.get_by_role("button", name=re.compile("Поделиться")).first.click()
    check_buttons(page, "the share sheet")


# Two sentences, the worst case the quest prompt allows, and a long world title.
TWO_SENTENCES = {
    "ru": "Пройдите по тропинке у причала и сосчитайте все фонари, которые встретите по пути. "
    "Потом найдите синюю дверцу, за которой хранится ключ от бухты, и нарисуйте её вместе.",
    "zh-CN": "沿着码头旁边的小路走，数一数你们遇到的所有灯笼，看看谁数得最准确。"
    "然后一起找到那扇守着海湾钥匙的蓝色小门，并把它的样子认真地画下来给大家看。",
}
LONG_TITLE = {
    "ru": "Маяк дождливой гавани и таинственные огни над самым дальним островом",
    "zh-CN": "雨港灯塔和远方小岛上神秘闪烁的灯火之谜",
}


def open_first_visit(
    new_page: NewPage, stack: Stack, locale: str, size: ViewportSize
) -> tuple[Page, Locator]:
    """A first visit (no chapter yet), cover ready, two-sentence quest, long world title."""
    page = new_page()
    api = page.context.request
    created = api.post(
        "/api/v1/families",
        data={
            "title": "Firsts",
            "locale": locale,
            "display_name": "Anna",
            "privacy_consent": True,
            "interests": [],
        },
    )
    assert created.ok, created.status
    family_id = created.json()["family_id"]
    assert api.post(
        f"/api/v1/families/{family_id}/adventure", data={"genre": "pirates"}
    ).ok
    wait_for_quest(page, family_id)
    set_cover(stack, family_id, "ready")

    def quest(route: Route) -> None:
        body = route.fetch().json()
        if body.get("quest"):
            body["quest"]["description"] = TWO_SENTENCES[locale]
        route.fulfill(json=body)

    def world(route: Route) -> None:
        body = route.fetch().json()
        if body.get("world"):
            body["world"]["title"] = LONG_TITLE[locale]
        route.fulfill(json=body)

    page.route(re.compile(r"/api/v1/families/[^/]+/adventure$"), quest)
    page.route(re.compile(r"/api/v1/families/[^/]+/world$"), world)
    page.add_init_script(OBSERVE)
    page.set_viewport_size(size)
    page.goto("/adventure" if locale == "ru" else f"/{locale}/adventure")
    card = page.get_by_role("region", name=re.compile(QUEST_LABEL[locale]))
    expect(card).to_be_visible(timeout=30_000)
    expect(card.get_by_text(TWO_SENTENCES[locale])).to_be_visible()
    settle(page)
    return page, card


@pytest.mark.parametrize("locale", ["ru", "zh-CN"])
def test_first_visit_shows_quest_text_and_done_above_the_fold_at_390(
    new_page: NewPage, stack: Stack, shot: Shot, locale: str
) -> None:
    page, card = open_first_visit(new_page, stack, locale, PHONE)
    shot(page, f"ol-polish-first-screen-{locale}-390")
    bar = page.get_by_test_id("quest-action-bar")
    visible_to = PHONE["height"]
    if bar.count():
        bar_box = bar.bounding_box()
        assert bar_box is not None
        visible_to = bar_box["y"]  # the pinned bar covers what is below its top edge
    text = card.get_by_text(TWO_SENTENCES[locale]).bounding_box()
    assert text is not None
    assert text["y"] + text["height"] <= visible_to, (
        f"{locale} text {text}, visible to {visible_to}"
    )
    done = card.get_by_role(
        "button", name=re.compile("Готово|完成")
    ).last.bounding_box()
    assert done is not None and done["y"] + done["height"] <= PHONE["height"], done
    assert cls(page) < BUDGET, shifts(page)


def test_first_visit_on_desktop_keeps_its_layout(
    new_page: NewPage, stack: Stack, shot: Shot
) -> None:
    page, card = open_first_visit(new_page, stack, "ru", DESKTOP)
    shot(page, "ol-polish-first-screen-ru-1440")
    box = card.bounding_box()
    assert box is not None and box["y"] < DESKTOP["height"], box
    assert overflow(page) <= 0
    assert cls(page) < BUDGET, shifts(page)
