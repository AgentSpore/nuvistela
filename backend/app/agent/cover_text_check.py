"""One cheap yes/no vision question about a finished cover: does it show any writing?

Image models often ignore "no text" in the prompt, so the picture itself is looked at. The same
OpenRouter key, model and zero-retention routing as the cover call; the picture is the only thing
sent, never a name or a family fact.
"""

import base64
from dataclasses import dataclass
from typing import Protocol

import httpx2

from app.agent.errors import AgentConfigError
from app.agent.image_client import ROUTING, URL, cost_micro
from app.core.config import Settings

QUESTION = (
    "Does this image contain any letters, words, writing, numbers or text-like glyphs, including "
    "invented or garbled letter-like marks on signs, walls, objects or in the corners? "
    "Answer with exactly one word: YES or NO."
)
MAX_ANSWER_TOKENS = 16
CHECK_RESERVE_MICRO = 2_000  # micro-USD kept back for the check; a cheap model costs ~100


class CheckError(Exception):
    """No usable answer; the message never carries provider text.

    `cost_micro` is what the failed check still cost: set when the provider answered (and billed)
    but the answer was unusable, None when nothing is known to have been charged.
    """

    def __init__(self, message: str, cost: int | None = None) -> None:
        super().__init__(message)
        self.cost_micro = cost


@dataclass(frozen=True)
class TextVerdict:
    has_text: bool
    cost_micro: int | None  # price the provider reported, None when it reported none


class TextChecker(Protocol):
    async def has_text(self, image: bytes) -> TextVerdict:
        """Raises `CheckError` when no answer could be had."""
        ...


class OpenRouterTextChecker:
    def __init__(
        self, settings: Settings, *, http_client: httpx2.AsyncClient | None = None
    ) -> None:
        key = settings.openrouter_api_key
        if key is None or not settings.image_model:
            raise AgentConfigError("IMAGE_MODEL and OPENROUTER_API_KEY must be set")
        self._model = settings.image_model
        self._headers = {"Authorization": f"Bearer {key.get_secret_value()}"}
        prices = (
            settings.image_max_price_in_usd_per_mtok,
            settings.image_max_price_out_usd_per_mtok,
        )
        self._provider = {
            **ROUTING,
            "max_price": dict(zip(("prompt", "completion"), prices, strict=True)),
        }
        self._http = http_client or httpx2.AsyncClient(timeout=settings.image_timeout_s)

    async def has_text(self, image: bytes) -> TextVerdict:
        """`image` is WebP bytes. Anything but a clear YES or NO is a `CheckError`."""
        url = "data:image/webp;base64," + base64.b64encode(image).decode()
        body = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": QUESTION},
                        {"type": "image_url", "image_url": {"url": url}},
                    ],
                }
            ],
            "max_tokens": MAX_ANSWER_TOKENS,
            "temperature": 0,
            "provider": self._provider,
        }
        try:
            response = await self._http.post(URL, json=body, headers=self._headers)
            response.raise_for_status()
        except httpx2.HTTPStatusError as exc:
            raise CheckError(f"HTTP {exc.response.status_code}") from None
        except httpx2.HTTPError as exc:
            raise CheckError(type(exc).__name__) from None
        return _verdict(response)


def _verdict(response: httpx2.Response) -> TextVerdict:
    """An answer on HTTP 200 was billed: an unusable one still carries its price or the reserve."""
    try:
        payload = response.json()
    except ValueError:
        raise CheckError("no answer in the response", CHECK_RESERVE_MICRO) from None
    price = cost_micro(payload)
    billed = CHECK_RESERVE_MICRO if price is None else price
    try:
        answer = str(payload["choices"][0]["message"]["content"]).strip().strip(".!").upper()
    except (KeyError, IndexError, TypeError):
        raise CheckError("no answer in the response", billed) from None
    if answer not in ("YES", "NO"):
        raise CheckError("answer is neither YES nor NO", billed)
    return TextVerdict(answer == "YES", price)
