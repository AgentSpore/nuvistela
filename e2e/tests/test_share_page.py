"""The public share card in a real browser against the real API and Postgres.

A world comes from the scripted model; its cover is inserted straight into `world_images`
(no image model runs in the suite), using a real picture from the landing gallery.
"""

import hashlib
import re
import time
from collections.abc import Callable
from uuid import UUID

import httpx
from playwright.sync_api import Page, ViewportSize, expect

from replies import WORLD_TITLE
from stack import ROOT, Stack, run_sql
from test_adventure_flow import wait_for_quest

Shot = Callable[[Page, str], None]
NewPage = Callable[..., Page]

PHONE = ViewportSize(width=390, height=844)
DESKTOP = ViewportSize(width=1280, height=800)
COVER = (ROOT / "frontend" / "public" / "examples" / "ship.webp").read_bytes()


def overflow(page: Page) -> int:
    return page.evaluate("document.documentElement.scrollWidth - window.innerWidth")


def seed_share(page: Page, stack: Stack) -> tuple[str, str]:
    """Family + ready pirate world + cover + share link; return (family id, token)."""
    api = page.context.request
    created = api.post(
        "/api/v1/families",
        data={"title": "Sharers", "locale": "ru", "display_name": "Anna", "privacy_consent": True, "interests": []},
    )
    assert created.ok, created.status
    family_id = created.json()["family_id"]
    assert api.post(f"/api/v1/families/{family_id}/adventure", data={"genre": "pirates"}).ok
    deadline = time.monotonic() + 30
    while True:
        rows = run_sql(
            stack.database_url,
            "SELECT job_id FROM worlds WHERE family_id = $1 AND status = 'ready'",
            UUID(family_id),
        )
        if rows:
            break
        assert time.monotonic() < deadline, "world not ready within 30 s"
        time.sleep(0.5)
    run_sql(
        stack.database_url,
        "INSERT INTO world_images (family_id, world_job_id, kind, prompt, status, sha256, bytes)"
        " VALUES ($1, $2, 'cover', 'p', 'ready', $3, $4)"
        " ON CONFLICT (family_id, world_job_id, kind, milestone_no) DO UPDATE"
        " SET status = 'ready', sha256 = $3, bytes = $4",
        UUID(family_id),
        rows[0]["job_id"],
        hashlib.sha256(COVER).hexdigest(),
        COVER,
    )
    shared = api.post(f"/api/v1/families/{family_id}/world/share")
    assert shared.ok, shared.status
    return family_id, shared.json()["token"]


def test_stranger_sees_cover_and_title_and_og_tags_without_js(
    new_page: NewPage, stack: Stack, shot: Shot
) -> None:
    owner = new_page()
    family_id, token = seed_share(owner, stack)
    stranger = new_page()  # fresh context: no cookies, no session
    stranger.set_viewport_size(PHONE)
    stranger.goto(f"/w/{token}")
    expect(stranger.get_by_role("heading", level=1)).to_have_text(WORLD_TITLE)
    cover = stranger.get_by_role("img")
    expect(cover).to_be_visible()
    assert cover.evaluate("img => img.complete && img.naturalWidth > 0")
    expect(stranger.get_by_role("navigation")).to_have_count(0)
    hrefs = stranger.locator("a").evaluate_all("els => els.map(e => e.getAttribute('href'))")
    assert not [h for h in hrefs if re.match(r"/(en/)?(play|adventure|family|new|join)\b", h or "")], hrefs
    cta = stranger.get_by_role("link", name="Создать свой мир")
    expect(cta).to_have_attribute("href", "/?source=share#demo")
    assert overflow(stranger) <= 0, f"horizontal scroll at 390: {overflow(stranger)}px"
    shot(stranger, "share-card-390")
    stranger.set_viewport_size(DESKTOP)
    assert overflow(stranger) <= 0, f"horizontal scroll at 1280: {overflow(stranger)}px"
    shot(stranger, "share-card-1280")

    html = httpx.get(f"{stack.site}/w/{token}", timeout=10)  # a bot: no scripts, no cookies
    assert html.status_code == 200
    body = html.text
    image = f"{stack.site}/api/v1/share/{token}/cover.webp"
    assert re.search(rf'<meta property="og:image" content="{re.escape(image)}"', body), body
    og_title = re.search(r'property="og:title" content="([^"]*)"', body)
    assert og_title and WORLD_TITLE in og_title[1]
    assert re.search(rf"<h1[^>]*>{re.escape(WORLD_TITLE)}</h1>", body), "title is not in the server HTML"
    assert re.search(rf'<img[^>]*src="/api/v1/share/{token}/cover\.webp"', body), "cover is not in the server HTML"
    assert 'name="twitter:card" content="summary_large_image"' in body
    assert re.search(r'name="robots" content="noindex, nofollow"', body)
    assert 'property="og:image:width" content="1024"' in body
    picture = httpx.get(image, timeout=10)
    assert picture.status_code == 200 and picture.headers["content-type"] == "image/webp"
    assert "Анна" not in body and "Anna" not in body and family_id not in body


def test_english_card_and_locale_switcher(new_page: NewPage, stack: Stack) -> None:
    _, token = seed_share(new_page(), stack)
    page = new_page()
    page.goto(f"/en/w/{token}")
    expect(page.get_by_role("link", name="Create your own world")).to_have_attribute(
        "href", "/en?source=share#demo"
    )
    page.get_by_label("Язык").or_(page.get_by_label("Language")).select_option("ru")
    page.wait_for_url(f"**/w/{token}")
    expect(page.get_by_role("heading", level=1)).to_have_text(WORLD_TITLE)


def test_revoked_and_unknown_links_are_one_404_card(
    new_page: NewPage, stack: Stack, shot: Shot
) -> None:
    owner = new_page()
    family_id, token = seed_share(owner, stack)
    assert owner.context.request.delete(f"/api/v1/families/{family_id}/world/share").ok
    for path in (f"/w/{token}", "/w/AbCdEfGhIjKlMnOpQrStUv", "/w/short"):
        gone = httpx.get(f"{stack.site}{path}", timeout=10)
        assert gone.status_code == 404, (path, gone.status_code)
        assert "noindex" in gone.text and "og:image" not in gone.text
    page = new_page()
    page.set_viewport_size(PHONE)
    response = page.goto(f"/w/{token}")
    assert response is not None and response.status == 404
    expect(page.get_by_role("heading", name="Открытка недоступна")).to_be_visible()
    expect(page.get_by_role("link", name="Создать свой мир")).to_have_attribute(
        "href", "/?source=share#demo"
    )
    assert overflow(page) <= 0
    shot(page, "share-unavailable-390")


def test_card_counts_done_quests_without_any_story_text(new_page: NewPage, stack: Stack) -> None:
    owner = new_page()
    family_id, token = seed_share(owner, stack)
    quest = wait_for_quest(owner, family_id)
    done = owner.context.request.post(
        f"/api/v1/quests/{quest['id']}/done",
        data={"note": "Мы справились с Anna"},
        headers={"Idempotency-Key": "e2e-share-count"},
    )
    assert done.ok, done.status
    card = httpx.get(f"{stack.site}/api/v1/share/{token}", timeout=10).json()
    assert card["quests_done"] == 1 and card["chapters"] in (0, 1), card
    page = new_page()
    page.set_viewport_size(PHONE)
    page.goto(f"/w/{token}")
    counts = page.locator("[data-share-counts]")
    expect(counts).to_have_text(re.compile(r"^1 дело выполнено · [01] глав[аы]?$"))
    text = page.locator("body").inner_text()
    assert "справились" not in text and "Anna" not in text and quest["title"] not in text
    assert overflow(page) <= 0, f"horizontal scroll at 390: {overflow(page)}px"
