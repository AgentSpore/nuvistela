"""World card: chronicle and "what we learned" at 390x844, the new milestone marked once, no layout shift."""

import json
import re
from collections.abc import Callable

import pytest
from playwright.sync_api import Page, Route, expect
from test_adventure_cls import OBSERVE, cls, settle, shifts
from test_adventure_flow import PHONE, seed_adventure, wait_for_quest

NewPage = Callable[..., Page]

TEXTS = {
    "ru": (
        "Хроника мира",
        "Чему учились",
        "Станция получила вывеску",
        "Зажёгся маяк",
        "наблюдательность",
    ),
    "zh-CN": ("世界编年史", "我们学到了什么", "车站挂上了招牌", "灯塔亮了", "观察力"),
}


def seed(page: Page, locale: str) -> str:
    api = page.context.request
    created = api.post(
        "/api/v1/families",
        data={
            "title": "Adventurers",
            "locale": locale,
            "display_name": "Anna",
            "privacy_consent": True,
            "interests": [],
        },
    )
    assert created.ok, created.status
    family_id = created.json()["family_id"]
    assert api.post(
        f"/api/v1/families/{family_id}/adventure", data={"genre": "space"}
    ).ok
    wait_for_quest(page, family_id)
    return family_id


def with_chronicle(page: Page, entries: list[dict], skills: list[str]) -> None:
    """The backend G1 fields on top of the real adventure answer (milestones need the model)."""

    def patch(route: Route) -> None:
        resp = route.fetch()
        body = resp.json()
        body["chronicle"], body["skills"] = entries, skills
        route.fulfill(response=resp, body=json.dumps(body))

    page.route(re.compile(r"/api/v1/families/[^/]+/adventure$"), patch)


@pytest.mark.parametrize("locale", ["ru", "zh-CN"])
def test_chronicle_and_skills_on_the_world_card(
    new_page: NewPage, shot, locale: str
) -> None:
    head, learned, first, second, skill = TEXTS[locale]
    page = new_page()
    page.add_init_script(OBSERVE)
    seed(page, locale)
    entries = [{"chapter": 1, "text": first}, {"chapter": 3, "text": second}]
    with_chronicle(page, entries, [skill])
    page.set_viewport_size(PHONE)
    page.goto("/adventure" if locale == "ru" else f"/{locale}/adventure")

    chronicle = page.get_by_role("list", name=head)
    expect(chronicle.get_by_role("listitem")).to_have_text(
        [re.compile(first), re.compile(second)]
    )
    expect(page.get_by_role("list", name=learned).get_by_role("listitem")).to_have_text(
        [skill]
    )
    assert not re.search(r"\d", chronicle.inner_text()), "the chronicle shows a number"
    expect(chronicle.locator("li.bg-honey-soft")).to_have_count(2)
    chronicle.scroll_into_view_if_needed()
    shot(page, f"g2-chronicle-new-{locale}-390")

    page.reload()  # seen: the same lines are ordinary now
    expect(page.get_by_role("list", name=head).get_by_role("listitem")).to_have_count(2)
    expect(page.locator("li.bg-honey-soft", has_text=first)).to_have_count(0)
    page.get_by_role("list", name=head).scroll_into_view_if_needed()
    shot(page, f"g2-chronicle-card-{locale}-390")
    settle(page)
    assert cls(page) < 0.1, f"CLS {cls(page):.3f}: {shifts(page)}"


def test_a_return_visit_opens_the_card_for_a_new_milestone_only(
    new_page: NewPage, shot
) -> None:
    """A done chapter means a return visit: the card is closed unless a milestone is new."""
    page = new_page()
    page.add_init_script(OBSERVE)
    seed_adventure(page)
    with_chronicle(
        page, [{"chapter": 1, "text": "Станция получила вывеску"}], ["наблюдательность"]
    )
    page.set_viewport_size(PHONE)
    page.goto("/adventure")
    chronicle = page.get_by_role("list", name="Хроника мира")
    expect(chronicle).to_be_visible()
    chronicle.scroll_into_view_if_needed()
    expect(chronicle.locator("li.bg-honey-soft")).to_have_count(1)
    shot(page, "g2-chronicle-return-ru-390")

    page.wait_for_function(
        "() => Object.keys(localStorage).some(k => k.startsWith('nuvistela-milestones-seen:'))"
    )
    page.reload()  # it was on screen, so it is seen: the card is closed again
    expect(page.get_by_text("О мире")).to_be_visible()
    expect(chronicle).to_be_hidden()
    settle(page)
    assert cls(page) < 0.1, f"CLS {cls(page):.3f}: {shifts(page)}"
