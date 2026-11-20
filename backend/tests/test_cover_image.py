import base64
import io
import json
from typing import Any

import httpx2
import pytest
from PIL import Image, UnidentifiedImageError
from pydantic import SecretStr

from app.agent.errors import AgentConfigError
from app.agent.image_client import ImageError, OpenRouterImageClient
from app.agent.webp import encode_webp
from app.core.config import Settings
from app.services.cover_prompt import SAFETY_ENDING, YOUNG_CHILD_ENDING, cover_prompt


def settings(**extra) -> Settings:
    values: dict[str, Any] = {
        "database_url": "postgresql+asyncpg://u:p@localhost/x",
        "openrouter_api_key": SecretStr("k"),
        "image_model": "vendor/img",
        **extra,
    }
    return Settings(_env_file=None, **values)


def png(size: tuple[int, int]) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, (200, 120, 40)).save(out, "PNG")
    return out.getvalue()


def reply(raw: bytes, usage: dict | None) -> httpx2.Response:
    url = "data:image/png;base64," + base64.b64encode(raw).decode()
    body = {"choices": [{"message": {"images": [{"image_url": {"url": url}}]}}]}
    if usage is not None:
        body["usage"] = usage
    return httpx2.Response(200, json=body)


def client_with(handler, **extra: Any) -> OpenRouterImageClient:
    http = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    return OpenRouterImageClient(settings(**extra), http_client=http)


def test_webp_is_capped_to_1024_and_keeps_proportions() -> None:
    out = encode_webp(png((1264, 848)))
    img = Image.open(io.BytesIO(out))
    assert img.format == "WEBP"
    assert max(img.size) == 1024
    assert abs(img.size[0] / img.size[1] - 1264 / 848) < 0.01


def test_webp_small_picture_is_not_enlarged() -> None:
    assert Image.open(io.BytesIO(encode_webp(png((300, 200))))).size == (300, 200)


async def test_request_is_one_zdr_image_without_temperature() -> None:
    seen: list[dict] = []

    async def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(json.loads(request.content))
        return reply(png((8, 8)), {"cost": 0.0336})

    result = await client_with(handler).generate("a quiet harbor")
    body = seen[0]
    assert body["model"] == "vendor/img"
    assert body["modalities"] == ["image"]
    assert "temperature" not in body
    routing = {"zdr": True, "data_collection": "deny", "require_parameters": True}
    assert {k: v for k, v in body["provider"].items() if k != "max_price"} == routing
    assert body["messages"][0]["content"] == "a quiet harbor"
    assert body["image_config"] == {"aspect_ratio": "3:2"}
    assert result.cost_micro == 33600


async def test_request_caps_the_price_per_million_tokens() -> None:
    seen: list[dict] = []

    async def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(json.loads(request.content))
        return reply(png((8, 8)), None)

    await client_with(handler).generate("x")
    assert seen[0]["provider"]["max_price"] == {"prompt": 5, "completion": 200}
    await client_with(
        handler, image_max_price_in_usd_per_mtok=1.5, image_max_price_out_usd_per_mtok=40
    ).generate("x")
    assert seen[1]["provider"]["max_price"] == {"prompt": 1.5, "completion": 40}


async def test_missing_cost_is_unknown_not_zero() -> None:
    client = client_with(lambda r: reply(png((8, 8)), None))
    assert (await client.generate("x")).cost_micro is None


@pytest.mark.parametrize("status", [404, 500])
async def test_http_failure_is_an_error_without_provider_text(status: int) -> None:
    client = client_with(lambda r: httpx2.Response(status, json={"error": "secret detail"}))
    with pytest.raises(ImageError) as exc:
        await client.generate("x")
    assert "secret" not in str(exc.value)


async def test_response_without_an_image_is_an_error() -> None:
    client = client_with(lambda r: httpx2.Response(200, json={"choices": []}))
    with pytest.raises(ImageError):
        await client.generate("x")


def test_reserve_is_ceiling_plus_prompt_bytes_at_the_input_price() -> None:
    client = client_with(lambda r: reply(b"", None), image_price_in_usd_per_mtok=0.5)
    assert client.worst_case("a" * 1000) == 45_000 + 500


def test_client_needs_model_and_key() -> None:
    with pytest.raises(AgentConfigError):
        OpenRouterImageClient(settings(image_model=""))


def test_prompt_ends_with_the_safety_ending() -> None:
    got = cover_prompt("storybook, Moon Harbor", young_child=False)
    assert got.startswith("storybook, Moon Harbor")
    assert got.endswith(SAFETY_ENDING)
    for word in ("no people", "no characters", "no text"):
        assert word in got
    assert "daytime" not in got
    assert not any(ch.isdigit() for ch in got)


def test_prompt_for_a_young_child_requires_a_bright_daytime_scene() -> None:
    got = cover_prompt("storybook", young_child=True)
    assert got.endswith(YOUNG_CHILD_ENDING)
    assert "bright daytime" in got
    assert not any(ch.isdigit() for ch in got)


@pytest.mark.parametrize("cost", ["abc", "NaN", "Infinity", -0.01, {"x": 1}, [1], True])
async def test_unusable_cost_never_turns_a_delivered_image_into_an_error(cost) -> None:
    client = client_with(lambda r: reply(png((8, 8)), {"cost": cost}))
    result = await client.generate("x")
    assert result.data == png((8, 8)) and result.cost_micro is None


async def test_oversized_response_is_rejected_before_decoding() -> None:
    big = httpx2.Response(
        200,
        json={
            "choices": [
                {
                    "message": {
                        "images": [
                            {"image_url": {"url": "data:image/png;base64," + "A" * 12_000_000}}
                        ]
                    }
                }
            ]
        },
    )
    with pytest.raises(ImageError):
        await client_with(lambda r: big).generate("x")


def gif() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (8, 8)).save(out, "GIF")
    return out.getvalue()


def test_a_gif_is_rejected() -> None:
    with pytest.raises(UnidentifiedImageError):
        encode_webp(gif())


def test_an_oversized_header_is_rejected_without_decoding(monkeypatch: pytest.MonkeyPatch) -> None:
    wide = png((4097, 8))

    def forbidden(*args, **kwargs):
        raise AssertionError("decoded")

    monkeypatch.setattr(Image.Image, "convert", forbidden)
    monkeypatch.setattr(Image.Image, "load", forbidden)
    with pytest.raises(ValueError, match="too large"):
        encode_webp(wide)


def test_ending_forbids_writing_of_any_kind() -> None:
    for word in (
        "no writing of any kind",
        "labels",
        "captions",
        "signs",
        "numbers",
        "logos",
        "watermarks",
        "screens",
        "maps",
        "windows",
    ):
        assert word in SAFETY_ENDING


@pytest.mark.parametrize(
    ("world", "tidy"),
    [
        ("A vessel on a , looping passage", "A vessel on a, looping passage"),
        ("toys ,, and  more ..", "toys, and more"),
        ("one , , two", "one, two"),
        ("a ; b", "a; b"),
        ("a : b", "a: b"),
        ("a ! b", "a! b"),
        ("a ? b", "a? b"),
        ("a ;; b", "a; b"),
        ("a :: b", "a: b"),
        ("a !! b", "a! b"),
        ("a ?? b", "a? b"),
        ("lead ;: ", "lead"),
        ("plain text, kept. As is", "plain text, kept. As is"),
    ],
)
def test_scrub_debris_is_collapsed_but_words_are_kept(world: str, tidy: str) -> None:
    assert cover_prompt(world, young_child=False).startswith(tidy + ". ")
