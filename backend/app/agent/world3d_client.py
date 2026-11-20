"""One 3D scene from World Labs Marble (docs.worldlabs.ai/api): generate, poll, download."""

import asyncio
from dataclasses import dataclass
from typing import Any, Protocol

import httpx2

from app.agent.errors import AgentConfigError
from app.agent.webp import encode_webp
from app.core.config import Settings

BASE_URL = "https://api.worldlabs.ai/marble/v1"
DISPLAY_NAME = "Nuvistela world"  # World Labs may show it to others: it names nothing of a family
SPLAT_QUALITY = "500k"
MAX_ASSET_BYTES = 30_000_000
PANORAMA_MAX_SIDE = 4096
PANORAMA_MAX_SOURCE_SIDE = 8192  # marble-1.1 panoramas are 4608x2304
OPERATION_GRACE_S = 60.0  # a fresh operation answers 404 for ~3 s (measured 19.11.2026)


class SceneError(Exception):
    """The scene was not produced; the message never carries provider text."""


class _NotFound(SceneError):
    """HTTP 404; the operation poll treats it as "not visible yet" for a while."""


@dataclass(frozen=True)
class SceneAssets:
    spz: bytes
    panorama_webp: bytes


class SceneGenerator(Protocol):
    """What the worker needs; tests replace the network."""

    @property
    def price_micro(self) -> int: ...

    async def generate(self, prompt: str) -> SceneAssets: ...


def _dig(data: object, *keys: str) -> Any:
    """Nested dict lookup; None when any level is missing or not a dict."""
    for key in keys:
        data = data.get(key) if isinstance(data, dict) else None
    return data


class WorldLabsClient:
    def __init__(self, settings: Settings, *, http_client: httpx2.AsyncClient | None = None):
        if not settings.world3d_model or settings.worldlabs_api_key is None:
            raise AgentConfigError("WORLD3D_MODEL and WORLDLABS_API_KEY must be set")
        if (price := settings.world3d_price_micro) is None:
            raise AgentConfigError("WORLD3D_MODEL has no known price")
        self._model, self._price_micro = settings.world3d_model, price
        self._headers = {"WLT-Api-Key": settings.worldlabs_api_key.get_secret_value()}
        self._poll_s, self._timeout_s = settings.world3d_poll_s, settings.world3d_timeout_s
        self._http = http_client or httpx2.AsyncClient(timeout=60.0)

    @property
    def price_micro(self) -> int:
        return self._price_micro

    async def generate(self, prompt: str) -> SceneAssets:
        try:
            async with asyncio.timeout(self._timeout_s):
                world = await self._finished_world(await self._start(prompt))
                spz = await self._download(world["spz"], MAX_ASSET_BYTES)
                pano = await self._download(world["pano"], MAX_ASSET_BYTES)
        except TimeoutError:
            raise SceneError("Timeout") from None
        except httpx2.HTTPError as exc:
            raise SceneError(type(exc).__name__) from None
        try:
            webp = await asyncio.to_thread(
                encode_webp, pano, PANORAMA_MAX_SIDE, PANORAMA_MAX_SOURCE_SIDE
            )
            return SceneAssets(spz, webp)
        except (OSError, ValueError):
            raise SceneError("bad panorama") from None

    async def _start(self, prompt: str) -> str:
        body = {
            "display_name": DISPLAY_NAME,
            "model": self._model,
            "permission": {"public": False},
            "world_prompt": {"type": "text", "text_prompt": prompt},
        }
        data = await self._call("POST", f"{BASE_URL}/worlds:generate", json=body)
        try:
            return str(data["operation_id"])
        except (KeyError, TypeError):
            raise SceneError("no operation in the response") from None

    async def _finished_world(self, operation_id: str) -> dict[str, str]:
        grace_ends = asyncio.get_running_loop().time() + OPERATION_GRACE_S
        while True:
            try:
                op = await self._call("GET", f"{BASE_URL}/operations/{operation_id}")
            except _NotFound:
                if asyncio.get_running_loop().time() >= grace_ends:
                    raise
                await asyncio.sleep(self._poll_s)
                continue
            status = ((op.get("metadata") or {}).get("progress") or {}).get("status")
            if op.get("error") or status == "FAILED":
                raise SceneError("FAILED")
            if op.get("done"):
                return await self._world_urls(op)
            await asyncio.sleep(self._poll_s)

    async def _world_urls(self, op: dict) -> dict[str, str]:
        # INVARIANT(world3d-pano): the finished operation carries pano_url=null (measured
        # 18.11.2026, still null 240 s later); only GET /worlds/{world_id} has it. Reading
        # the panorama from the operation again fails every scene with
        # "no scene in the response". An unknown /worlds shape now waits out the timeout
        # and is logged as Timeout (accepted trade-off).
        world_id = _dig(op, "response", "world_id")
        if not isinstance(world_id, str) or not world_id:
            raise SceneError("no scene in the response")
        while True:
            data = await self._call("GET", f"{BASE_URL}/worlds/{world_id}")
            wrapped = data.get("world")
            if (
                urls := self._asset_urls(wrapped if isinstance(wrapped, dict) else data)
            ) is not None:
                return urls
            await asyncio.sleep(self._poll_s)

    @staticmethod
    def _asset_urls(world: dict) -> dict[str, str] | None:
        """None while the splat or the panorama is not ready yet."""
        urls = {
            "spz": _dig(world, "assets", "splats", "spz_urls", SPLAT_QUALITY),
            "pano": _dig(world, "assets", "imagery", "pano_url"),
        }
        if None in urls.values():
            return None
        if not all(isinstance(u, str) and u.startswith("https://") for u in urls.values()):
            raise SceneError("no scene in the response")
        return urls

    async def _call(self, method: str, url: str, **kwargs) -> dict:
        response = await self._http.request(method, url, headers=self._headers, **kwargs)
        if response.status_code == 404:
            raise _NotFound("HTTP 404")
        if response.status_code != 200:
            raise SceneError(f"HTTP {response.status_code}")
        try:
            data = response.json()
        except ValueError:
            raise SceneError("bad response") from None
        if not isinstance(data, dict):
            raise SceneError("bad response")
        return data

    async def _download(self, url: str, limit: int) -> bytes:
        """Pre-signed asset URL: fetched without the API key, aborted once past `limit`."""
        async with self._http.stream("GET", url) as response:
            declared = response.headers.get("content-length", "")
            if response.status_code != 200:
                raise SceneError(f"asset HTTP {response.status_code}")
            if declared.isdigit() and int(declared) > limit:
                raise SceneError("asset too large")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body += chunk
                if len(body) > limit:
                    raise SceneError("asset too large")
        return bytes(body)
