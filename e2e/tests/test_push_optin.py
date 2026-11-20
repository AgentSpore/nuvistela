"""Web Push opt-in in a real browser: the card after the first chapter, the family toggle.

Headless Chromium has no push service and always reports notifications as denied, so
`Notification` and `PushManager.subscribe` are replaced by stubs that keep the state in the page; the service worker, the permission prompt and the
requests to `/api/v1/push/*` are the real ones (routes answer for the backend).
"""

import base64
import json
import time
from collections.abc import Callable

import pytest
from playwright.sync_api import Page, Route, expect
from test_adventure_cls import BUDGET, OBSERVE, cls, settle, shifts
from test_adventure_flow import PHONE, wait_for_quest
from test_first_loop import make_chapter_ready

from stack import Stack

Shot = Callable[[Page, str], None]
NewPage = Callable[..., Page]

KEY = base64.urlsafe_b64encode(b"\x04" + bytes(range(64))).rstrip(b"=").decode()
STUB = """
window.__sub = null;
window.__asked = 0;
let perm = 'default';
Object.defineProperty(Notification, 'permission', {get: () => perm, configurable: true});
Notification.requestPermission = async () => { window.__asked += 1; perm = 'granted'; return perm; };
PushManager.prototype.subscribe = async function () {
  window.__sub = {
    endpoint: 'https://fcm.googleapis.com/fcm/send/device-1',
    toJSON() { return {endpoint: this.endpoint, keys: {p256dh: 'p256dh-key', auth: 'auth-key'}}; },
    unsubscribe: async () => { window.__sub = null; return true; },
  };
  return window.__sub;
};
PushManager.prototype.getSubscription = async () => window.__sub;
"""
CARD = "Сообщить, когда будет готово следующее задание?"


def stub_backend(
    page: Page, key_status: int = 200, post_status: int = 201
) -> dict[str, list]:
    """Answer /api/v1/push/*; return what the page sent."""
    seen: dict[str, list] = {"key": [], "POST": [], "DELETE": []}

    def answer(route: Route) -> None:
        req = route.request
        if req.url.endswith("/push/key"):
            seen["key"].append(1)
            body = {"public_key": KEY} if key_status == 200 else None
            route.fulfill(status=key_status, json=body)
            return
        seen[req.method].append(json.loads(req.post_data or "{}"))
        route.fulfill(status=post_status if req.method == "POST" else 204)

    page.route("**/api/v1/push/**", answer)
    page.add_init_script(STUB)
    return seen


def seed_ready_chapter(page: Page, stack: Stack, locale: str = "ru") -> str:
    """Family with a done first quest and a ready first chapter; return the family id."""
    api = page.context.request
    created = api.post(
        "/api/v1/families",
        data={
            "title": "Pushers",
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
    quest = wait_for_quest(page, family_id)
    done = api.post(
        f"/api/v1/quests/{quest['id']}/done",
        data={"note": "Мы справились"},
        headers={"Idempotency-Key": "e2e-push-1"},
    )
    assert done.ok, done.status
    make_chapter_ready(stack, family_id)
    return family_id


def adult_page(new_page: NewPage, stack: Stack, locale: str = "ru") -> Page:
    page = new_page()
    page.set_viewport_size(PHONE)
    seed_ready_chapter(page, stack, locale)
    return page


def prefix(locale: str) -> str:
    return "" if locale == "ru" else f"/{locale}"


def test_manifest_and_service_worker_are_served(new_page: NewPage) -> None:
    page = new_page()
    page.goto("/")
    href = page.locator("link[rel=manifest]").get_attribute("href")
    assert href == "/manifest.webmanifest"
    manifest = page.context.request.get(href)
    assert manifest.ok and manifest.json()["display"] == "standalone"
    assert manifest.json()["start_url"] == "/"
    sw = page.context.request.get("/sw.js")
    assert sw.ok and "javascript" in sw.headers["content-type"]
    assert page.context.request.get("/icon.svg").ok


@pytest.mark.parametrize(
    ("locale", "question", "yes"),
    [
        ("ru", CARD, "Да, сообщать"),
        (
            "es",
            "¿Quieren que avisemos cuando la próxima misión esté lista?",
            "Sí, avisar",
        ),
        ("zh-CN", "下一个任务准备好时，要通知您吗？", "好，通知我"),
    ],
)
def test_adult_turns_reminders_on_from_the_card(
    new_page: NewPage, stack: Stack, shot: Shot, locale: str, question: str, yes: str
) -> None:
    page = adult_page(new_page, stack, locale)
    page.add_init_script(OBSERVE)
    seen = stub_backend(page)
    page.goto(f"{prefix(locale)}/adventure")
    card = page.get_by_role("region", name=question)
    expect(card).to_be_visible(timeout=30_000)
    settle(page)
    assert cls(page) < BUDGET, f"CLS {cls(page):.3f}: {shifts(page)}"
    assert seen["POST"] == [] and page.evaluate("window.__asked") == 0, (
        "permission and subscription only after the tap"
    )
    card.scroll_into_view_if_needed()
    shot(page, f"push-card-{locale.lower().replace('-', '_')}-390")
    card.get_by_role("button", name=yes).click()
    expect(card).to_have_count(0)
    tz = page.evaluate("Intl.DateTimeFormat().resolvedOptions().timeZone")
    assert seen["POST"] == [
        {
            "endpoint": "https://fcm.googleapis.com/fcm/send/device-1",
            "keys": {"p256dh": "p256dh-key", "auth": "auth-key"},
            "tz": tz,
        }
    ]
    assert page.evaluate("window.__asked") == 1
    registration = page.evaluate(
        "navigator.serviceWorker.getRegistration('/sw.js').then((r) => !!r)"
    )
    assert registration, "the service worker is registered"


def test_not_now_is_never_offered_again_on_this_device(
    new_page: NewPage, stack: Stack
) -> None:
    page = adult_page(new_page, stack)
    seen = stub_backend(page)
    page.goto("/adventure")
    card = page.get_by_role("region", name=CARD)
    expect(card).to_be_visible(timeout=30_000)
    card.get_by_role("button", name="Не сейчас").click()
    expect(card).to_have_count(0)
    page.reload()
    expect(page.get_by_role("heading", name="Ваша история")).to_be_visible()
    deadline = time.monotonic() + 5
    while len(seen["key"]) < 2 and time.monotonic() < deadline:
        page.wait_for_timeout(100)
    page.wait_for_timeout(500)
    expect(page.get_by_role("region", name=CARD)).to_have_count(0)
    assert seen["POST"] == []


def test_no_card_when_the_server_has_no_keys(new_page: NewPage, stack: Stack) -> None:
    page = adult_page(new_page, stack)
    seen = stub_backend(page, key_status=404)
    page.goto("/adventure")
    expect(page.get_by_role("heading", name="Ваша история")).to_be_visible()
    page.wait_for_timeout(1000)
    assert seen["key"], "the key was asked for"
    expect(page.get_by_role("region", name=CARD)).to_have_count(0)


def test_child_is_not_offered_reminders(new_page: NewPage, stack: Stack) -> None:
    adult = adult_page(new_page, stack)
    me = adult.context.request.get("/api/v1/me").json()
    invited = adult.context.request.post(
        f"/api/v1/families/{me['family_id']}/members",
        data={
            "display_name": "Sam",
            "age_band": "6-9",
            "role": "child",
            "interests": [],
        },
    )
    assert invited.ok, invited.status
    token = invited.json()["invite_url"].split("#")[1]
    child = new_page()
    assert child.context.request.post("/api/v1/invite/accept", data={"token": token}).ok
    seen = stub_backend(child)
    child.set_viewport_size(PHONE)
    child.goto("/adventure")
    expect(child.get_by_role("heading", name="Ваша история")).to_be_visible(
        timeout=30_000
    )
    child.wait_for_timeout(1000)
    assert seen["POST"] == [] and seen["DELETE"] == []
    expect(child.get_by_role("region", name=CARD)).to_have_count(0)


def test_family_toggle_follows_this_device(
    new_page: NewPage, stack: Stack, shot: Shot
) -> None:
    page = adult_page(new_page, stack)
    seen = stub_backend(page)
    page.goto("/family")
    toggle = page.get_by_role(
        "switch", name="Сообщать на этом устройстве, когда будет готово новое задание"
    )
    expect(toggle).to_be_visible(timeout=30_000)
    expect(toggle).to_have_attribute("aria-checked", "false")
    toggle.click()
    expect(toggle).to_have_attribute("aria-checked", "true")
    assert len(seen["POST"]) == 1
    toggle.scroll_into_view_if_needed()
    shot(page, "push-toggle-on-390")
    toggle.click()
    expect(toggle).to_have_attribute("aria-checked", "false")
    assert seen["DELETE"] == [
        {"endpoint": "https://fcm.googleapis.com/fcm/send/device-1"}
    ]
    shot(page, "push-toggle-off-390")


def test_family_toggle_shows_off_and_a_note_when_another_adult_owns_the_device(
    new_page: NewPage, stack: Stack, shot: Shot
) -> None:
    page = adult_page(new_page, stack)
    seen = stub_backend(page, post_status=409)
    page.add_init_script(
        """
        Notification.requestPermission();
        window.__sub = {
          endpoint: 'https://fcm.googleapis.com/fcm/send/device-1',
          toJSON() { return {endpoint: this.endpoint, keys: {p256dh: 'p', auth: 'a'}}; },
          unsubscribe: async () => { window.__sub = null; return true; },
        };
        """
    )
    page.goto("/family")
    page.evaluate(
        "navigator.serviceWorker.register('/sw.js').then(() => navigator.serviceWorker.ready)"
    )
    page.reload()
    toggle = page.get_by_role(
        "switch", name="Сообщать на этом устройстве, когда будет готово новое задание"
    )
    expect(toggle).to_be_visible(timeout=30_000)
    expect(page.get_by_text("для другой семьи")).to_be_visible(timeout=10_000)
    expect(toggle).to_have_attribute("aria-checked", "false")
    toggle.scroll_into_view_if_needed()
    shot(page, "push-toggle-taken-390")
    toggle.click()
    expect(toggle).to_have_attribute("aria-checked", "false")
    assert seen["DELETE"] == []
    assert page.evaluate("window.__sub !== null"), (
        "the other member's subscription stays"
    )
