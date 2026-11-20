"""The whole share path in a real browser: create, open as a stranger, follow the CTA, revoke.

Events are read back from Postgres. Playwright sets navigator.webdriver, which the client treats
as a bot and does not report, so the stranger's context hides it.
"""

import time
from collections.abc import Callable

import httpx
from playwright.sync_api import Page, expect
from replies import WORLD_TITLE
from stack import Stack, run_sql
from test_share_page import PHONE, seed_share

NewPage = Callable[..., Page]
KINDS = ("share_created", "share_viewed", "share_cta", "share_revoked")


def counts(stack: Stack) -> dict[str, int]:
    rows = run_sql(
        stack.database_url,
        "SELECT kind, count(*) AS n FROM pilot_events WHERE kind = ANY($1::text[]) GROUP BY kind",
        list(KINDS),
    )
    return {
        kind: next((r["n"] for r in rows if r["kind"] == kind), 0) for kind in KINDS
    }


def wait_for_delta(
    stack: Stack, before: dict[str, int], kind: str, expected: int
) -> None:
    deadline = time.monotonic() + 10
    while counts(stack)[kind] - before[kind] != expected:
        assert time.monotonic() < deadline, (
            f"{kind}: {counts(stack)[kind] - before[kind]} != {expected}"
        )
        time.sleep(0.2)


def test_full_share_path_and_its_events(new_page: NewPage, stack: Stack) -> None:
    before = counts(stack)
    owner = new_page()
    family_id, token = seed_share(
        owner, stack
    )  # adult with a ready cover creates the link

    stranger = new_page()
    stranger.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => false})"
    )
    stranger.set_viewport_size(PHONE)
    posted: list[str] = []
    stranger.on(
        "request",
        lambda r: (
            posted.append(r.post_data or "")
            if r.url.endswith("/api/v1/pilot/events")
            else None
        ),
    )
    stranger.goto(f"/w/{token}")
    expect(stranger.get_by_role("heading", level=1)).to_have_text(WORLD_TITLE)
    assert stranger.get_by_role("img").evaluate(
        "img => img.complete && img.naturalWidth > 0"
    )
    assert "Анна" not in stranger.content() and "Anna" not in stranger.content()
    wait_for_delta(stack, before, "share_viewed", 1)
    stranger.reload()
    stranger.wait_for_load_state("networkidle")
    time.sleep(1)
    assert counts(stack)["share_viewed"] - before["share_viewed"] == 1, (
        "a reload counted again"
    )
    assert not any(token in body or family_id in body for body in posted), posted

    cta = stranger.get_by_role("link", name="Создать свой мир")
    expect(cta).to_have_attribute("href", "/?source=share#demo")
    cta.click()
    stranger.wait_for_url("**/?source=share*")
    wait_for_delta(stack, before, "share_cta", 1)

    assert owner.context.request.delete(f"/api/v1/families/{family_id}/world/share").ok
    gone = new_page()
    response = gone.goto(f"/w/{token}")
    assert response is not None and response.status == 404
    expect(gone.get_by_role("heading", name="Открытка недоступна")).to_be_visible()
    assert (
        httpx.get(
            f"{stack.site}/api/v1/share/{token}/cover.webp", timeout=10
        ).status_code
        == 404
    )

    after = counts(stack)
    assert {k: after[k] - before[k] for k in KINDS} == {
        "share_created": 1,
        "share_viewed": 1,
        "share_cta": 1,
        "share_revoked": 1,
    }
    sessions = run_sql(
        stack.database_url,
        "SELECT s.source FROM pilot_events e JOIN pilot_sessions s USING (session_id)"
        " WHERE e.kind = 'share_viewed' ORDER BY e.at DESC LIMIT 1",
    )
    assert sessions[0]["source"] == "share"
