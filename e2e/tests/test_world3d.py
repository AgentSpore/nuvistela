"""The 3D world button in a real browser: nothing 3D loads before the tap, `?nogl` shows the panorama.

The WebGL test proves the lazy chunk loads and a canvas appears; frame rate is not asserted
(headless caps it, and it says nothing about a phone).
"""

import json
import re
import time
from collections.abc import Callable

import pytest
from playwright.sync_api import Browser, Page, Response, expect
from stack import ROOT, Stack
from test_adventure_cls import set_cover
from test_adventure_flow import PHONE

NewPage = Callable[..., Page]
WALK = re.compile(r"Пройтись по миру · (до )?\d+ МБ")
CORNER_WALK = re.compile(r"Пройтись по миру в 3D, (до )?\d+ МБ")
MAX_COVERED = 0.12
MIN_TARGET = 44
OWN_SHA = "c" * 64
OWN_PANO = f"/api/v1/media/pano/{OWN_SHA}.webp"
WORLDS = ROOT / "frontend" / "public" / "worlds"


def seed_pirate_world(page: Page, genre: str = "pirates") -> str:
    api = page.context.request
    created = api.post(
        "/api/v1/families",
        data={
            "title": "Walkers",
            "locale": "ru",
            "display_name": "Anna",
            "privacy_consent": True,
            "interests": [],
        },
    )
    assert created.ok, created.status
    family_id = created.json()["family_id"]
    assert api.post(
        f"/api/v1/families/{family_id}/adventure", data={"genre": genre, "custom_genre": "floating islands" if genre == "custom" else None}
    ).ok
    deadline = time.monotonic() + 30
    while api.get(f"/api/v1/families/{family_id}/adventure").json()["quest"] is None:
        assert time.monotonic() < deadline, "world not ready within 30 s"
        time.sleep(0.5)
    return family_id


def walk_button(page: Page):
    """The walk inside «О мире»: the cover may carry a second one."""
    summary = page.get_by_text("О мире", exact=True)
    expect(summary).to_be_visible()
    button = page.locator("details").filter(has=summary).get_by_role("button", name=WALK)
    if not button.is_visible():
        summary.click()
    return button


def test_page_load_requests_neither_spz_nor_spark(new_page: NewPage) -> None:
    page = new_page()
    seed_pirate_world(page)
    responses: list[Response] = []
    page.on("response", lambda r: responses.append(r))
    page.goto("/adventure")
    expect(walk_button(page)).to_be_visible()
    page.wait_for_load_state("networkidle")
    assert not [r.url for r in responses if r.url.endswith(".spz")]
    scripts = [r for r in responses if r.request.resource_type == "script"]
    assert scripts
    assert not [r.url for r in scripts if "SplatMesh" in r.text()], (
        "Spark is in an eager chunk"
    )


def test_cover_carries_the_walk_button_on_a_phone(
    new_page: NewPage, stack: Stack, shot: Callable[[Page, str], None]
) -> None:
    """With the family's own scene ready the walk sits on the picture, seen without unfolding «О мире»."""
    page = new_page()
    page.set_viewport_size(PHONE)
    family_id = seed_pirate_world(page)
    set_cover(stack, family_id, "ready")
    stub_scene(page, READY)
    page.goto("/adventure?nogl")
    cover = page.get_by_alt_text(re.compile("Обложка"))
    expect(cover).to_be_visible()
    button = cover.locator("xpath=..").get_by_role("button", name=CORNER_WALK)
    expect(button).to_be_in_viewport()
    picture, own = cover.bounding_box(), button.bounding_box()
    assert picture and own
    covered = own["width"] * own["height"] / (picture["width"] * picture["height"])
    print(f"covered share {covered:.3f} ({own['width']:.0f}x{own['height']:.0f})")
    assert covered <= MAX_COVERED, f"the button covers {covered:.1%} of the cover"
    assert own["width"] >= MIN_TARGET and own["height"] >= MIN_TARGET, own
    assert own["x"] + own["width"] <= picture["x"] + picture["width"] + 1
    assert own["y"] + own["height"] <= picture["y"] + picture["height"] + 1
    right_gap = picture["x"] + picture["width"] - (own["x"] + own["width"])
    assert right_gap <= 16, f"not at the right edge: {right_gap:.0f}px from it"
    shot(page, "fi-cover-3d-button-390")
    page.set_viewport_size({"width": 1440, "height": 900})
    expect(button).to_be_visible()
    shot(page, "fi-cover-3d-button-1440")
    page.set_viewport_size(PHONE)
    button.click()
    pano = page.get_by_role("img", name="Панорама мира")
    expect(pano).to_be_visible()
    assert pano.get_attribute("src") == OWN_PANO


def test_cover_has_no_walk_until_the_own_scene_is_ready(new_page: NewPage, stack: Stack) -> None:
    page = new_page()
    page.set_viewport_size(PHONE)
    family_id = seed_pirate_world(page)
    set_cover(stack, family_id, "ready")
    stub_scene(page, {"status": "pending", "url": None, "panorama_url": None})
    page.goto("/adventure?nogl")
    cover = page.get_by_alt_text(re.compile("Обложка"))
    expect(cover).to_be_visible()
    expect(walk_button(page)).to_be_visible()
    expect(
        cover.locator("xpath=..").get_by_role("button", name=re.compile("Пройтись по миру"))
    ).to_have_count(0)


def test_tap_with_nogl_shows_panorama_and_escape_closes(new_page: NewPage) -> None:
    page = new_page()
    seed_pirate_world(page)
    requested: list[str] = []
    page.on("request", lambda r: requested.append(r.url))
    page.goto("/adventure?nogl")
    button = walk_button(page)
    button.click()
    pano = page.get_by_role("img", name="Панорама мира")
    expect(pano).to_be_visible()
    assert pano.evaluate("img => img.complete && img.naturalWidth > 0")
    expect(page.get_by_role("dialog")).not_to_contain_text(
        re.compile("ошибк|не удалось", re.IGNORECASE)
    )
    assert not [u for u in requested if u.endswith(".spz")]
    page.keyboard.press("Escape")
    expect(page.get_by_role("dialog")).to_have_count(0)
    expect(button).to_be_focused()


def test_world_files_are_immutable(new_page: NewPage) -> None:
    page = new_page()
    spz = next((WORLDS / "seaside-lighthouse").glob("world-500k.*.spz"))
    response = page.context.request.head(f"/worlds/seaside-lighthouse/{spz.name}")
    assert response.ok, response.status
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"


GL_FLAGS = [
    "--use-angle=swiftshader",
    "--enable-unsafe-swiftshader",
    "--ignore-gpu-blocklist",
]


def test_tap_with_webgl_loads_spz_and_shows_canvas(
    new_page: NewPage, browser: Browser, stack: Stack
) -> None:
    seeder = new_page()
    seed_pirate_world(seeder)
    gl_browser = browser.browser_type.launch(headless=True, args=GL_FLAGS)
    try:
        context = gl_browser.new_context(
            base_url=stack.site, storage_state=seeder.context.storage_state()
        )
        page = context.new_page()
        if not page.evaluate("!!document.createElement('canvas').getContext('webgl2')"):
            pytest.skip("this Chromium has no WebGL2, even with the swiftshader flags")
        page.goto("/adventure")
        button = walk_button(page)
        with page.expect_response(
            lambda r: r.url.endswith(".spz"), timeout=60_000
        ) as spz:
            button.click()
        assert spz.value.ok, spz.value.status
        assert (
            spz.value.headers["cache-control"] == "public, max-age=31536000, immutable"
        )
        expect(page.get_by_role("dialog").locator("canvas")).to_be_visible(
            timeout=60_000
        )
        expect(page.get_by_role("img", name="Панорама мира")).to_have_count(0)
    finally:
        gl_browser.close()


def stub_scene(page: Page, scene: dict | None) -> None:
    """Add `scene` to the world response; serve a library panorama as the family's own picture."""

    def world(route) -> None:
        body = route.fetch().json()
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({**body, "scene": scene}),
        )

    page.route(re.compile(r".*/api/v1/families/[^/]+/world$"), world)
    pano = next((WORLDS / "sky-islands").glob("pano.*.webp"))
    page.route(
        re.compile(r".*/api/v1/media/pano/.*\.webp$"),
        lambda r: r.fulfill(status=200, path=str(pano), content_type="image/webp"),
    )


READY = {
    "status": "ready",
    "url": f"/api/v1/media/{OWN_SHA}.spz",
    "panorama_url": OWN_PANO,
}


@pytest.mark.parametrize(
    ("name", "scene", "own"),
    [
        ("library", None, False),
        ("pending", {"status": "pending", "url": None, "panorama_url": None}, False),
        ("failed", {"status": "failed", "url": None, "panorama_url": None}, False),
        ("own", READY, True),
    ],
)
def test_card_shows_own_scene_only_when_ready(
    new_page: NewPage, shot: Callable[[Page, str], None], name: str, scene, own: bool
) -> None:
    page = new_page()
    page.set_viewport_size({"width": 390, "height": 844})
    seed_pirate_world(page)
    stub_scene(page, scene)
    page.goto("/adventure?nogl")
    button = walk_button(page)
    shot(page, f"s4_card_{name}")
    assert not page.get_by_text(re.compile("строится|создаётся|генерир", re.I)).count()
    button.click()
    pano = page.get_by_role("img", name="Панорама мира")
    expect(pano).to_be_visible()
    assert pano.evaluate("img => img.complete && img.naturalWidth > 0")
    assert (pano.get_attribute("src") == OWN_PANO) is own
    shot(page, f"s4_dialog_{name}")
