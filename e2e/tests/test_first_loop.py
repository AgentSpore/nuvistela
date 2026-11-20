"""First loop at a phone: the quest is on the first screen, the tabs fit one line, «Готово!» gets a reward moment."""

import re
import time
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

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

from stack import Stack, run_sql

Shot = Callable[[Page, str], None]
NewPage = Callable[..., Page]

SHOTS = Path(__file__).resolve().parents[1] / "artifacts" / "shots"
NARROW = ViewportSize(width=360, height=740)


def test_quest_card_is_on_the_first_screen_with_a_cover(
    new_page: NewPage, stack: Stack, shot: Shot
) -> None:
    page = new_page()
    family_id = start_adventure(page, stack)
    quest = page.get_by_role("region", name=re.compile("Ваше задание"))
    expect(quest).to_be_visible(timeout=30_000)
    set_cover(stack, family_id, "ready")  # the tallest case: a real picture is shown
    page.reload()
    expect(page.get_by_alt_text(re.compile("Обложка"))).to_be_visible()
    expect(quest).to_be_visible()
    box = quest.bounding_box()
    assert box is not None
    assert page.evaluate("window.scrollY") == 0
    assert box["y"] >= 0, box
    assert box["y"] + box["height"] <= PHONE["height"], (
        f"quest card below the fold: {box}"
    )
    about = page.get_by_text("О мире", exact=True)
    expect(about).to_be_visible()
    shot(page, "first-loop-1-quest-on-first-screen-390")
    page.screenshot(
        path=str(SHOTS / "first-loop-0-new-player-full-390.png"), full_page=True
    )
    assert page.locator(".min-h-80").count() == 0, "room reserved before any check-in"


CHAPTER_ONE = {
    "id": "00000000-0000-0000-0000-0000000000c1",
    "seq": 1,
    "status": "ready",
    "title": "Глава 1",
    "body": "Фонарь мигнул, и бухта ответила огнями.",
}


def with_chapter_one(page: Page) -> None:
    """A return visit: the adventure answer carries a written chapter next to the open quest."""

    def adventure(route: Route) -> None:
        body = route.fetch().json()
        route.fulfill(json={**body, "chapters": [CHAPTER_ONE]})

    page.route(re.compile(r".*/api/v1/families/[^/]+/adventure$"), adventure)


def test_return_visit_cover_is_2_to_1_and_quest_stays_on_the_first_screen(
    new_page: NewPage, stack: Stack, shot: Shot
) -> None:
    page = new_page()
    family_id = start_adventure(page, stack)
    expect(page.get_by_role("region", name=re.compile("Ваше задание"))).to_be_visible(
        timeout=30_000
    )
    set_cover(stack, family_id, "ready")
    with_chapter_one(page)
    page.goto("/adventure")
    cover = page.get_by_alt_text(re.compile("Обложка"))
    quest = page.get_by_role("region", name=re.compile("Ваше задание"))
    expect(cover).to_be_visible()
    expect(quest).to_be_visible()
    expect(page.get_by_text("Фонарь мигнул")).to_be_attached()
    expect(page.get_by_text("О мире", exact=True).locator("xpath=..")).not_to_have_attribute(
        "open", ""
    )
    settle(page)
    picture, card = cover.bounding_box(), quest.bounding_box()
    assert picture and card
    assert 1.95 <= picture["width"] / picture["height"] <= 2.02, f"cover not 2:1: {picture}"
    assert page.evaluate("window.scrollY") == 0
    assert card["y"] + card["height"] <= PHONE["height"], f"quest card below the fold: {card}"
    assert cls(page) < BUDGET, shifts(page)
    shot(page, "first-loop-5-return-visit-390")


LONG_QUEST = {
    "en": "Follow the path by the pier, count every lantern you meet and find the blue door that keeps the key to the bay. ",
    "es": "Sigan el sendero junto al muelle, cuenten los faroles que encuentren y "
    "busquen la puerta azul que guarda la llave de la bahía. ",
    "zh-CN": "沿着码头旁边的小路走，数一数你们遇到的灯笼，然后找到那扇守着海湾钥匙的蓝色小门。",
    "ru": "Пройдите по тропинке у причала, сосчитайте все фонари, которые встретите, "
    "и найдите синюю дверцу, за которой хранится ключ от бухты. ",
}
QUEST_LABEL = {
    "en": "Your quest",
    "es": "Su misión",
    "zh-CN": "您的任务",
    "ru": "Ваше задание",
}


def long_text(locale: str) -> str:
    """Exactly QUEST_DESCRIPTION_MAX (400) characters of realistic text."""
    unit = LONG_QUEST[locale]
    return (unit * (400 // len(unit) + 1))[:400]


def open_long_quest(
    new_page: NewPage, stack: Stack, locale: str, size: ViewportSize
) -> tuple[Page, Locator]:
    """A family in `locale` whose first quest has a 400-character description, cover ready."""
    page = new_page()
    api = page.context.request
    created = api.post(
        "/api/v1/families",
        data={
            "title": "Longs",
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
    set_cover(stack, family_id, "ready")  # the tallest case: a real picture is shown

    def long_quest(route: Route) -> None:
        body = route.fetch().json()
        if body.get("quest"):
            body["quest"]["description"] = long_text(locale)
        route.fulfill(json=body)

    page.route(re.compile(r"/api/v1/families/[^/]+/adventure$"), long_quest)
    page.add_init_script(OBSERVE)
    page.set_viewport_size(size)
    prefix = "" if locale == "ru" else f"/{locale}"
    page.goto(f"{prefix}/adventure")
    quest = page.get_by_role("region", name=re.compile(QUEST_LABEL[locale]))
    expect(quest).to_be_visible(timeout=30_000)
    expect(quest.get_by_text(long_text(locale))).to_be_visible()
    settle(page)
    return page, quest


@pytest.mark.parametrize("locale", ["es", "zh-CN", "ru"])
def test_main_action_is_reachable_with_the_longest_quest(
    new_page: NewPage, stack: Stack, shot: Shot, locale: str
) -> None:
    page, quest = open_long_quest(new_page, stack, locale, PHONE)
    assert page.evaluate("window.scrollY") == 0
    card = quest.bounding_box()
    assert card is not None and card["y"] < PHONE["height"], f"{locale} card: {card}"
    bar = page.get_by_test_id("quest-action-bar")
    expect(bar).to_be_visible()
    action = bar.get_by_role("button").bounding_box()
    assert action is not None
    assert action["y"] + action["height"] <= PHONE["height"], f"{locale}: {action}"
    expect(bar).to_have_css("opacity", "1")
    bar_box = bar.bounding_box()
    assert bar_box is not None
    bar_height = bar_box["height"]
    padding = page.evaluate(
        "parseFloat(getComputedStyle(document.querySelector('main > div')).paddingBottom)"
    )
    assert padding >= bar_height, f"page padding {padding} hides content under the bar"
    shot(page, f"s6b-{locale}-1-load")
    bar.get_by_role("button").click()
    expect(page.get_by_role("dialog")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.get_by_role("dialog")).to_be_hidden()
    expect(bar.get_by_role("button")).to_be_focused()
    quest.get_by_role("button").first.scroll_into_view_if_needed()
    expect(bar).to_have_count(0)
    shot(page, f"s6b-{locale}-2-scrolled")
    settle(page)
    assert cls(page) < BUDGET, f"CLS {cls(page):.3f}: {shifts(page)}"


@pytest.mark.parametrize("locale", ["ru", "en", "es", "zh-CN"])
def test_action_bar_label_is_one_line_at_360(
    new_page: NewPage, stack: Stack, shot: Shot, locale: str
) -> None:
    page, _ = open_long_quest(new_page, stack, locale, NARROW)
    bar = page.get_by_test_id("quest-action-bar")
    expect(bar).to_be_visible()
    button = bar.get_by_role("button")
    box = button.bounding_box()
    assert box is not None and box["y"] + box["height"] <= NARROW["height"], box
    assert box["height"] <= 52, f"{locale}: label wraps, button {box}"
    assert overflow(page) <= 0, f"{locale}: horizontal scroll {overflow(page)}px"
    expect(bar).to_have_css("opacity", "1")
    shot(page, f"s6b-{locale}-3-bar-360")


@pytest.mark.parametrize(
    ("path", "more", "fresh"),
    [
        ("/play", "Ещё", "Новая игра"),
        ("/en/play", "More", "New game"),
        ("/es/play", "Más", "Nueva partida"),
        ("/zh-CN/play", "更多", "新游戏"),
    ],
)
def test_tabs_share_one_line_at_360(
    new_page: NewPage, shot: Shot, path: str, more: str, fresh: str
) -> None:
    page = new_page()
    page.set_viewport_size(NARROW)
    page.goto(path)
    links = page.get_by_role("navigation").first.get_by_role("list").get_by_role("link")
    expect(links).to_have_count(3)
    boxes = [links.nth(i).bounding_box() for i in range(3)]
    tops = {round(b["y"]) for b in boxes if b}
    assert len(tops) == 1, f"tabs wrap onto several lines: {tops}"
    assert overflow(page) <= 0, f"horizontal scroll at 360: {overflow(page)}px"
    page.get_by_role("button", name=more).click()
    expect(page.get_by_role("link", name=fresh)).to_be_visible()
    shot(
        page, f"first-loop-2-nav-360-{path.split('/')[1] if path != '/play' else 'ru'}"
    )
    page.mouse.click(180, 600)  # a tap outside the menu
    expect(page.get_by_role("link", name=fresh)).to_be_hidden()
    page.get_by_role("button", name=more).click()
    expect(page.get_by_role("link", name=fresh)).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.get_by_role("link", name=fresh)).to_be_hidden()


def slow_chapter_after_done(page: Page) -> dict[str, bool]:
    """A phone on a slow network, a storyteller that is not done yet.

    The tap is answered a second late (past the 500 ms grace that follows input) and every
    adventure read after it answers late too. Until `state["written"]` flips, the chapter is
    reported as being written, so the page keeps polling while the stand has no model.
    """
    state = {"armed": False, "written": False}

    def adventure(route: Route) -> None:
        if not state["armed"]:
            return route.continue_()
        page.wait_for_timeout(1500)
        if state["written"]:
            return route.continue_()
        body = route.fetch().json()
        for chapter in body.get("chapters", []):
            chapter["status"] = "writing"
        route.fulfill(json=body)

    def done(route: Route) -> None:
        state["armed"] = True
        page.wait_for_timeout(1000)
        route.continue_()

    page.route(re.compile(r"/api/v1/families/[^/]+/adventure$"), adventure)
    page.route(re.compile(r"/api/v1/quests/[^/]+/done$"), done)
    return state


CHAPTER_BODY = "\n\n".join(
    ["Фонарь загорелся, и бухта вдруг стала видна до самого горизонта."] * 4
)


def make_chapter_ready(stack: Stack, family_id: str) -> None:
    """The stand has no storyteller model: once the worker gave up, the chapter is written by hand."""
    deadline = time.monotonic() + 30
    while not (
        rows := run_sql(
            stack.database_url,
            "SELECT 1 FROM chapters WHERE family_id = $1"
            " AND status NOT IN ('queued', 'writing')",
            UUID(family_id),
        )
    ):
        assert time.monotonic() < deadline, "chapter never left the queue within 30 s"
        time.sleep(0.3)
    assert rows
    run_sql(
        stack.database_url,
        "UPDATE chapters SET status = 'ready', title = $2, body = $3, next_run_at = NULL"
        " WHERE family_id = $1",
        UUID(family_id),
        "Фонарь бухты",
        CHAPTER_BODY,
    )


def scroll_settled(page: Page, timeout_ms: int = 5_000) -> float:
    """scrollY once two reads 200 ms apart agree: a smooth scroll in flight is not a position."""
    last = page.evaluate("window.scrollY")
    for _ in range(timeout_ms // 200):
        page.wait_for_timeout(200)
        now = page.evaluate("window.scrollY")
        if now == last:
            return now
        last = now
    raise AssertionError(f"scroll never settled, last scrollY={last}")


@pytest.mark.parametrize("motion", ["no-preference", "reduce"])
def test_done_shows_the_reward_then_the_chapter_in_view_without_shifting(
    new_page: NewPage, stack: Stack, shot: Shot, motion: str
) -> None:
    page = new_page()
    page.emulate_media(
        reduced_motion="reduce" if motion == "reduce" else "no-preference"
    )
    chapter_state = slow_chapter_after_done(page)
    family_id = start_adventure(page, stack)
    quest = page.get_by_role("region", name=re.compile("Ваше задание"))
    expect(quest).to_be_visible(timeout=30_000)
    set_cover(stack, family_id, "ready")
    page.reload()
    expect(page.get_by_alt_text(re.compile("Обложка"))).to_be_visible()
    skill = quest.locator("span.font-semibold").inner_text()
    page.get_by_role("button", name="Готово!").click()
    cover = page.get_by_alt_text(re.compile("Обложка"))
    scroll_before = page.evaluate("window.scrollY")
    box = cover.bounding_box()
    assert box is not None
    cover_top = box["y"]
    outgoing = quest.bounding_box()
    assert outgoing is not None
    cut_off_top = max(0.0, -outgoing["y"])
    # Slow CSS animations so the shot below catches the celebration mid-burst.
    cdp = page.context.new_cdp_session(page)
    cdp.send("Animation.enable")
    cdp.send("Animation.setPlaybackRate", {"playbackRate": 0.4})
    page.get_by_role("button", name="Отправить отметку").click()
    reward = page.get_by_role("status", name=re.compile("выполнено"))
    expect(reward).to_be_visible()
    expect(reward).to_contain_text(skill)
    expect(reward.get_by_role("heading")).to_be_focused()
    # The one deliberate move: a reward with a reaction brings itself into view (block "nearest"):
    # up only by what its top was cut off, down only by what hung below the fold; then it stays put.
    scrolled = scroll_settled(page)
    moved = scrolled - scroll_before
    card = reward.bounding_box()
    assert card is not None
    # The reward takes the quest card's place but may grow past it; its own bottom is what counts.
    overflow_below = max(0.0, outgoing["y"] + card["height"] - PHONE["height"])
    assert -cut_off_top - 2 <= moved <= overflow_below + 2, (
        f"scrolled {moved:+.0f}px; allowed -{cut_off_top:.0f}..+{overflow_below:.0f}"
    )
    assert -2 <= card["y"] and card["y"] + card["height"] <= PHONE["height"] + 2, (
        f"the reward is not fully in view: {card}"
    )
    box = cover.bounding_box()
    assert box is not None
    assert abs(box["y"] - (cover_top - (scrolled - scroll_before))) <= 2, (
        "the cover moved beyond the reward's own scroll"
    )
    shot(page, f"first-loop-3-reward-390-{motion}")
    cdp.send("Animation.setPlaybackRate", {"playbackRate": 1})
    settle(page)
    # A reaction shows before the send is answered; route callbacks run only inside page calls.
    page.wait_for_timeout(1500)
    assert page.evaluate("window.scrollY") == scrolled, (
        "the page jumped after the reward"
    )
    make_chapter_ready(stack, family_id)
    chapter_state["written"] = True
    chapter = page.get_by_role("listitem").filter(has_text="Фонарь бухты")
    expect(chapter).to_have_attribute("data-fresh", "true", timeout=30_000)
    expect(chapter).to_be_in_viewport(ratio=1, timeout=5_000)
    box = chapter.bounding_box()
    assert box is not None
    assert 0 <= box["y"] and box["y"] + box["height"] <= PHONE["height"], box
    expect(reward).to_have_count(0)
    shot(page, f"first-loop-4-chapter-390-{motion}")
    settle(page)
    assert cls(page) < BUDGET, f"CLS {cls(page):.3f}: {shifts(page)}"


REACTION = {
    "es": "La linterna del muelle parpadeó y, uno a uno, los faroles del sendero se "
    "encendieron como si la bahía hubiera estado esperando justo esta señal. ",
    "zh-CN": "码头的灯塔闪了一下，沿着小路的灯笼一盏接一盏地亮起来，仿佛整个海湾都在等待这个信号。",
    "ru": "Фонарь на причале мигнул, и вдоль тропинки один за другим загорелись огни, "
    "словно вся бухта ждала именно этого знака. ",
}


def reaction_text(locale: str) -> str:
    """Exactly 280 characters, the longest reaction the schema allows."""
    unit = REACTION[locale]
    return (unit * (280 // len(unit) + 1))[:280]


@pytest.mark.parametrize(
    ("locale", "motion"),
    [
        ("es", "no-preference"),
        ("zh-CN", "no-preference"),
        ("ru", "no-preference"),
        ("zh-CN", "reduce"),
    ],
)
def test_reaction_shows_in_the_first_screen_before_done_is_answered(
    new_page: NewPage, stack: Stack, shot: Shot, locale: str, motion: str
) -> None:
    page, _ = open_long_quest(new_page, stack, locale, PHONE)
    page.emulate_media(
        reduced_motion="reduce" if motion == "reduce" else "no-preference"
    )
    seen = {"family": "", "answered": False}

    def adventure(route: Route) -> None:
        seen["family"] = route.request.url.split("/families/")[1].split("/")[0]
        body = route.fetch().json()
        if body.get("quest"):
            body["quest"]["description"] = long_text(locale)
            body["quest"]["reaction"] = reaction_text(locale)
        route.fulfill(json=body)

    def done(route: Route) -> None:
        page.wait_for_timeout(2500)
        seen["answered"] = True
        route.continue_()

    page.route(re.compile(r"/api/v1/families/[^/]+/adventure$"), adventure)
    page.route(re.compile(r"/api/v1/quests/[^/]+/done$"), done)
    page.reload()
    quest = page.get_by_role("region", name=re.compile(QUEST_LABEL[locale]))
    expect(quest).to_be_visible(timeout=30_000)
    settle(page)
    assert page.evaluate("window.scrollY") == 0
    page.get_by_test_id("quest-action-bar").get_by_role("button").click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible()
    dialog.get_by_role("button").last.click()
    reward = page.get_by_role("status").filter(has_text=reaction_text(locale))
    expect(reward).to_be_visible(timeout=1500)
    assert not seen["answered"], "the reaction waited for the server"
    expect(dialog).to_be_hidden()
    page.wait_for_timeout(900)  # the smooth scroll that brings the card up
    box = reward.bounding_box()
    assert box is not None
    assert box["y"] >= 0 and box["y"] + box["height"] <= PHONE["height"] + 1, box
    expect(reward.locator("p.rise")).to_have_css("opacity", "1")
    shot(page, f"r2-reaction-{locale}-{motion}-390")
    while not seen["answered"]:  # route callbacks only run while a page call is waiting
        page.wait_for_timeout(200)
    make_chapter_ready(stack, seen["family"])
    chapter = page.get_by_role("listitem").filter(has_text="Фонарь бухты")
    expect(chapter).to_have_attribute("data-fresh", "true", timeout=30_000)
    expect(reward).to_have_count(0)
    settle(page)
    assert cls(page) < BUDGET, f"CLS {cls(page):.3f}: {shifts(page)}"


def test_failed_send_with_a_reaction_takes_it_back_and_reopens_the_sheet(
    new_page: NewPage, stack: Stack, shot: Shot
) -> None:
    page, _ = open_long_quest(new_page, stack, "ru", PHONE)

    def adventure(route: Route) -> None:
        body = route.fetch().json()
        if body.get("quest"):
            body["quest"]["description"] = long_text("ru")
            body["quest"]["reaction"] = reaction_text("ru")
        route.fulfill(json=body)

    page.route(re.compile(r"/api/v1/families/[^/]+/adventure$"), adventure)
    page.route(
        re.compile(r"/api/v1/quests/[^/]+/done$"),
        lambda route: route.fulfill(status=500, json={"detail": "boom"}),
    )
    page.reload()
    expect(page.get_by_role("region", name=re.compile("Ваше задание"))).to_be_visible(
        timeout=30_000
    )
    page.get_by_test_id("quest-action-bar").get_by_role("button").click()
    dialog = page.get_by_role("dialog")
    dialog.get_by_role("button").last.click()
    expect(dialog.get_by_role("alert")).to_be_visible()
    expect(dialog).to_be_visible()
    assert page.evaluate("document.activeElement?.closest('dialog') !== null"), (
        "focus left the reopened sheet"
    )
    expect(
        page.get_by_role("status").filter(has_text=reaction_text("ru"))
    ).to_have_count(0)
    shot(page, "r2-reaction-failed-send-390")
