import time
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pywebpush import WebPushException

from app.channels.push import sender as sender_module
from app.channels.push.sender import PushFailed, PushSubscription, SubscriptionGone, WebPushSender

SUB = PushSubscription(
    uuid4(), "UTC", "https://fcm.googleapis.com/fcm/send/secret-endpoint", "pk", "ak"
)


def raising(status: int | None):
    def webpush(*_args, **_kwargs):
        response = None if status is None else SimpleNamespace(status_code=status)
        raise WebPushException(
            "boom with https://fcm.googleapis.com/fcm/send/secret-endpoint", response
        )

    return webpush


async def test_send_passes_the_subscription_payload_and_ttl(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(sender_module, "webpush", lambda *a, **kw: calls.append((a, kw)))
    await WebPushSender("private", "mailto:ops@example.test").send(SUB, '{"body": "x"}', 600)
    (info,), kwargs = calls[0]
    assert info == {
        "endpoint": SUB.endpoint,
        "keys": {"p256dh": "pk", "auth": "ak"},
    }
    assert kwargs["data"] == '{"body": "x"}' and kwargs["ttl"] == 600
    assert kwargs["vapid_claims"] == {"sub": "mailto:ops@example.test"}


@pytest.mark.parametrize("status", [404, 410])
async def test_a_gone_subscription_is_reported(monkeypatch, status: int) -> None:
    monkeypatch.setattr(sender_module, "webpush", raising(status))
    with pytest.raises(SubscriptionGone):
        await WebPushSender("k", "mailto:a@b.test").send(SUB, "{}", 60)


@pytest.mark.parametrize("status", [None, 500, 429])
async def test_other_failures_never_carry_the_endpoint(monkeypatch, status: int | None) -> None:
    monkeypatch.setattr(sender_module, "webpush", raising(status))
    with pytest.raises(PushFailed) as err:
        await WebPushSender("k", "mailto:a@b.test").send(SUB, "{}", 60)
    assert "secret-endpoint" not in str(err.value) and "secret-endpoint" not in repr(SUB)


async def test_a_disallowed_endpoint_is_never_contacted(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(sender_module, "webpush", lambda *a, **kw: calls.append(a))
    evil = PushSubscription(uuid4(), "UTC", "https://evil.example/r", "pk", "ak")
    with pytest.raises(SubscriptionGone):
        await WebPushSender("k", "mailto:a@b.test").send(evil, "{}", 60)
    assert calls == []


async def test_send_follows_no_redirects(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(sender_module, "webpush", lambda *a, **kw: calls.append(kw))
    await WebPushSender("k", "mailto:a@b.test").send(SUB, "{}", 60)
    assert calls[0]["requests_session"].max_redirects == 0


async def test_a_stuck_send_is_cut_at_the_deadline(monkeypatch) -> None:
    monkeypatch.setattr(sender_module, "TOTAL_DEADLINE_S", 0.05)
    monkeypatch.setattr(sender_module, "webpush", lambda *a, **kw: time.sleep(0.3))
    with pytest.raises(PushFailed):
        await WebPushSender("k", "mailto:a@b.test").send(SUB, "{}", 60)


async def test_the_deadline_covers_one_connect_and_one_read_wait(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(sender_module, "webpush", lambda *a, **kw: calls.append(kw))
    await WebPushSender("k", "mailto:a@b.test").send(SUB, "{}", 60)
    connect, read = calls[0]["timeout"]
    assert connect + read == sender_module.TOTAL_DEADLINE_S
