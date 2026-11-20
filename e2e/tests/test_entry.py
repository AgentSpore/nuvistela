"""Entry: an invited player lands on the adventure, waits for the world by name, gets the quest live."""

import re
from collections.abc import Callable

from playwright.sync_api import Page, expect

Shot = Callable[[Page, str], None]
NewPage = Callable[..., Page]


def test_invited_child_waits_for_the_world_then_gets_the_quest(
    new_page: NewPage, shot: Shot
) -> None:
    owner = new_page()
    api = owner.context.request
    created = api.post(
        "/api/v1/families",
        data={
            "title": "Bees",
            "locale": "ru",
            "display_name": "Вера",
            "privacy_consent": True,
            "interests": [],
        },
    )
    assert created.ok, created.status
    family_id = created.json()["family_id"]
    owner.goto("/family")
    owner.get_by_label("Имя", exact=True).fill("Тёма")
    owner.get_by_label("Возраст", exact=True).select_option("6-9")
    owner.get_by_role("button", name="Добавить", exact=True).click()
    link = owner.get_by_role("textbox", name="Ссылка для входа: Тёма")
    expect(link).to_be_visible()
    expect(owner.get_by_role("button", name="Поделиться")).to_be_visible()

    kid = new_page()
    kid.goto(link.input_value())
    kid.wait_for_url("**/adventure")
    expect(kid.get_by_text("Вера выбирает ваш мир — скоро начнём!")).to_be_visible()
    shot(kid, "entry-01-child-waits-for-world")

    assert api.post(
        f"/api/v1/families/{family_id}/adventure", data={"genre": "pirates"}
    ).ok
    quest = kid.get_by_role("region", name=re.compile("Ваше задание"))
    expect(quest).to_be_visible(timeout=60_000)
    shot(kid, "entry-02-child-got-quest")
