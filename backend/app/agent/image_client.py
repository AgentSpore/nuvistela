"""One cover picture from OpenRouter chat completions (`modalities`), zero-retention routing."""

import base64
import binascii
import math
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import httpx2

from app.agent.errors import AgentConfigError
from app.core.config import Settings

URL = "https://openrouter.ai/api/v1/chat/completions"
# Same data policy as the text calls (`ModelPrice.zdr_routing`); the price cap is added per client.
ROUTING = {"zdr": True, "data_collection": "deny", "require_parameters": True}
_MICRO = 1_000_000
ASPECT_RATIO = "3:2"  # the card field's shape
MAX_IMAGE_BYTES = 8_000_000  # decoded size cap of the provider's picture


class ImageError(Exception):
    """The picture was not produced; the message never carries provider text."""


@dataclass(frozen=True)
class ImageResult:
    data: bytes
    cost_micro: int | None  # price the provider reported, None when it reported none


class OpenRouterImageClient:
    def __init__(self, settings: Settings, *, http_client: httpx2.AsyncClient | None = None):
        if not settings.image_model or settings.openrouter_api_key is None:
            raise AgentConfigError("IMAGE_MODEL and OPENROUTER_API_KEY must be set")
        self._model = settings.image_model
        self._key = settings.openrouter_api_key.get_secret_value()
        self._ceiling_micro = round(settings.image_price_usd_per_image * _MICRO)
        self._in_price = settings.image_price_in_usd_per_mtok
        self._max_price = {
            "prompt": settings.image_max_price_in_usd_per_mtok,
            "completion": settings.image_max_price_out_usd_per_mtok,
        }
        self._http = http_client or httpx2.AsyncClient(timeout=settings.image_timeout_s)

    def worst_case(self, prompt: str) -> int:
        """Micro-USD to reserve: the ceiling of one image plus the prompt at the input price."""
        return self._ceiling_micro + math.ceil(len(prompt.encode()) * self._in_price)

    async def generate(self, prompt: str) -> ImageResult:
        body = {
            "model": self._model,
            "modalities": ["image"],
            "messages": [{"role": "user", "content": prompt}],
            "image_config": {"aspect_ratio": ASPECT_RATIO},
            "provider": {**ROUTING, "max_price": self._max_price},
        }
        try:
            response = await self._http.post(
                URL, json=body, headers={"Authorization": f"Bearer {self._key}"}
            )
        except httpx2.HTTPError as exc:
            raise ImageError(type(exc).__name__) from None
        if response.status_code != 200:
            raise ImageError(f"HTTP {response.status_code}")
        return self._decode(response)

    @staticmethod
    def _decode(response: httpx2.Response) -> ImageResult:
        try:
            payload = response.json()
            url: str = payload["choices"][0]["message"]["images"][0]["image_url"]["url"]
            head, data = url.split(",", 1)
            if not head.startswith("data:image/"):
                raise ValueError(head)
            if len(data) > MAX_IMAGE_BYTES * 4 // 3 + 4:
                raise ValueError("too large")
            raw = base64.b64decode(data, validate=True)
        except (KeyError, IndexError, TypeError, ValueError, binascii.Error):
            raise ImageError("no image in the response") from None
        return ImageResult(raw, cost_micro(payload))


def cost_micro(payload: dict) -> int | None:
    """The reported price in micro-USD; None when absent or unusable (the reserve is charged)."""
    try:
        cost = Decimal(str(payload["usage"]["cost"]))
    except (KeyError, TypeError, InvalidOperation):
        return None
    return math.ceil(cost * _MICRO) if cost.is_finite() and cost >= 0 else None
