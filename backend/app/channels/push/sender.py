"""The only door to push services: tests replace `PushSender`, so the network is never touched.

A subscription's endpoint and keys are personal device data: nothing here logs or prints them.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

import requests
from pywebpush import WebPushException, webpush

from app.channels.push.endpoints import is_allowed_push_endpoint

CONNECT_TIMEOUT_S = 5.0
READ_TIMEOUT_S = 10.0
# The thread cannot be cancelled, only abandoned: connect and read bound each socket wait, not
# the total, so a slow host can outlive the deadline; the deadline frees the worker regardless.
TOTAL_DEADLINE_S = CONNECT_TIMEOUT_S + READ_TIMEOUT_S
GONE_STATUSES = frozenset({404, 410})


@dataclass(frozen=True, slots=True)
class PushSubscription:
    id: UUID
    tz: str
    endpoint: str = field(repr=False)
    p256dh: str = field(repr=False)
    auth: str = field(repr=False)


class SubscriptionGone(Exception):
    """The push service no longer knows this subscription (404/410): delete it."""


class PushFailed(Exception):
    """Any other failure; the message names the class or status only, never the subscription."""


class PushSender(Protocol):
    async def send(self, sub: PushSubscription, payload: str, ttl: int) -> None: ...


class WebPushSender:
    def __init__(self, private_key: str, subject: str) -> None:
        self._private_key, self._subject = private_key, subject

    async def send(self, sub: PushSubscription, payload: str, ttl: int) -> None:
        if not is_allowed_push_endpoint(sub.endpoint):
            raise SubscriptionGone  # stored before the allow-list existed: drop the row
        try:
            async with asyncio.timeout(TOTAL_DEADLINE_S):
                await asyncio.to_thread(self._send_blocking, sub, payload, ttl)
        except WebPushException as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status in GONE_STATUSES:
                raise SubscriptionGone from None
            raise PushFailed(f"push service answered {status}") from None
        except Exception as exc:  # noqa: BLE001 (library boundary: key, network, TLS errors)
            raise PushFailed(type(exc).__name__) from None

    def _send_blocking(self, sub: PushSubscription, payload: str, ttl: int) -> None:
        with requests.Session() as session:
            session.max_redirects = 0
            webpush(
                {"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
                data=payload,
                vapid_private_key=self._private_key,
                vapid_claims={"sub": self._subject},  # the library adds `aud` to this dict
                ttl=ttl,
                # pywebpush types timeout as float but forwards it verbatim to requests.post
                timeout=(CONNECT_TIMEOUT_S, READ_TIMEOUT_S),  # ty: ignore[invalid-argument-type]
                requests_session=session,
            )
