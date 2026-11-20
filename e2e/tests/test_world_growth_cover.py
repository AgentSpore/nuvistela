"""Growth cover: the new picture replaces the old one on the open card, no reload, no layout shift."""

import json
import re

from playwright.sync_api import Page, Route, expect
from stack import ROOT
from test_adventure_cls import OBSERVE, cls, settle, shifts
from test_adventure_flow import PHONE
from test_world_chronicle import seed

OLD = f"/api/v1/media/{'a1' * 32}.webp"
NEW = f"/api/v1/media/{'b2' * 32}.webp"
PICTURE = next((ROOT / "frontend" / "public" / "worlds" / "sky-islands").glob("pano.*.webp"))


def serve_growth(page: Page, growing_reads: int) -> None:
    """The world answer: the old ready cover while growing, the new one after `growing_reads` reads."""
    reads = {"n": 0}

    def world(route: Route) -> None:
        body = route.fetch().json()
        reads["n"] += 1
        growing = reads["n"] <= growing_reads
        body["cover"] = {"status": "ready", "url": OLD if growing else NEW}
        body["cover_growing"] = growing
        route.fulfill(
            status=200, content_type="application/json", body=json.dumps(body)
        )

    page.route(re.compile(r".*/api/v1/families/[^/]+/world$"), world)
    page.route(
        re.compile(r".*/api/v1/media/[0-9a-f]{64}\.webp$"),
        lambda r: r.fulfill(status=200, path=str(PICTURE), content_type="image/webp"),
    )


def test_new_cover_replaces_the_old_one_without_reload(new_page, shot) -> None:
    page = new_page()
    page.add_init_script(OBSERVE)
    seed(page, "ru")
    serve_growth(page, growing_reads=2)
    page.set_viewport_size(PHONE)
    page.goto("/adventure")

    cover = page.get_by_role("img", name=re.compile("Обложка"))
    expect(cover).to_have_attribute("src", OLD)
    expect(page.get_by_text("Мир меняется…")).to_be_visible()
    page.evaluate("window.__probe = 1")  # a reload would wipe it
    shot(page, "g3b-world-growing-ru-390")

    expect(cover).to_have_attribute("src", NEW, timeout=30_000)  # no reload
    expect(page.get_by_text("Мир вырос")).to_be_visible()
    expect(page.get_by_text("Мир меняется…")).to_have_count(0)
    assert page.evaluate("window.__probe") == 1, "the page reloaded"
    box = cover.locator("xpath=..")
    assert not re.search(r"\d", box.inner_text()), "the cover box shows a number"
    shot(page, "g3b-world-grown-ru-390")
    settle(page)
    assert cls(page) < 0.1, f"CLS {cls(page):.3f}: {shifts(page)}"
