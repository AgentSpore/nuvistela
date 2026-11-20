"""Two adults of one family: the second one's open choice form follows the first one's choice.

The form polls the adventure, so the second adult leaves it without a reload as soon as the
first adult has chosen the world.
"""

from collections.abc import Callable
import json

from playwright.sync_api import Page, Route, ViewportSize, expect

from replies import WORLD_GENRE

Shot = Callable[[Page, str], None]
NewPage = Callable[..., Page]

PHONE = ViewportSize(width=390, height=844)
FORM = "Придумайте свой мир"
POLL_WINDOW_MS = 15_000


def two_adults(new_page: NewPage) -> tuple[Page, Page, str]:
    owner = new_page()
    created = owner.context.request.post(
        "/api/v1/families",
        data={
            "title": "Pair",
            "locale": "ru",
            "display_name": "Anna",
            "privacy_consent": True,
            "interests": [],
        },
    )
    assert created.ok, created.status
    family_id = created.json()["family_id"]
    invited = owner.context.request.post(
        f"/api/v1/families/{family_id}/members",
        data={"display_name": "Boris", "age_band": "adult", "role": "adult", "interests": []},
    )
    assert invited.ok, invited.status
    second = new_page()
    token = invited.json()["invite_url"].split("#")[1]
    assert second.context.request.post("/api/v1/invite/accept", data={"token": token}).ok
    return owner, second, family_id


def test_second_adult_leaves_the_form_without_reload(new_page: NewPage) -> None:
    owner, second, family_id = two_adults(new_page)
    second.set_viewport_size(PHONE)
    second.goto("/adventure")
    expect(second.get_by_role("heading", name=FORM)).to_be_visible()
    second.evaluate("window.__sameDocument = true")

    started = owner.context.request.post(
        f"/api/v1/families/{family_id}/adventure", data={"genre": WORLD_GENRE}
    )
    assert started.ok, started.status

    expect(second.get_by_role("heading", name=FORM)).to_have_count(0, timeout=POLL_WINDOW_MS)
    assert second.evaluate("window.__sameDocument") is True, "the page was reloaded"


def test_waiting_screen_shows_the_steps(new_page: NewPage, shot: Shot) -> None:
    owner, second, family_id = two_adults(new_page)
    pending = {"world": {"status": "pending"}, "quest": None, "chapters": []}

    def hold_pending(route: Route) -> None:
        route.fulfill(status=200, content_type="application/json", body=json.dumps(pending))

    second.route(f"**/api/v1/families/{family_id}/adventure", hold_pending)
    second.set_viewport_size(PHONE)
    second.goto("/adventure")
    expect(second.get_by_text("Мир пишется")).to_be_visible()
    for step in ("Придумываем места", "Выбираем героев", "Готовим первое задание"):
        expect(second.get_by_text(step)).to_be_visible()
    shot(second, "world-wait-390")


def test_quote_is_not_clipped_in_the_waiting_card(new_page: NewPage, shot: Shot) -> None:
    owner, _second, family_id = two_adults(new_page)
    quote = "Город в облаках, где дома плавают на воздушных шарах и каждое утро приходит почтовый кит"
    owner.add_init_script(
        "sessionStorage.setItem("
        f"'bumbli.worldChoice.{family_id}', JSON.stringify({{kind: 'text', text: {json.dumps(quote)}}}))"
    )
    pending = {"world": {"status": "pending"}, "quest": None, "chapters": []}
    owner.route(
        f"**/api/v1/families/{family_id}/adventure",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(pending)
        ),
    )
    owner.set_viewport_size(PHONE)
    owner.goto("/adventure")
    card = owner.get_by_role("status").filter(has_text="Мир пишется")
    expect(card.get_by_text(quote[:20])).to_be_visible()
    box = card.bounding_box()
    bee = card.locator("span").first.bounding_box()
    last = card.get_by_text("Готовим первое задание").bounding_box()
    assert box and bee and last
    assert bee["y"] - box["y"] >= 16, f"bee too close to the top edge: {bee['y'] - box['y']}px"
    assert last["y"] + last["height"] <= box["y"] + box["height"], "last step clipped"
    shot(owner, "wait-fix1-390")
