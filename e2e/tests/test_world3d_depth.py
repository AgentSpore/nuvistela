"""First frame of the 3D walk in each library world: a screenshot per world for a human to read.

`WORLD3D_TAG` names the run (`before` / `after` a change to the aiming) in the file name.
The `close` case serves the nook a panorama whose liveliest stretch lies straight at the
nearest wall, so the aim by colour alone looks right into it.
"""

import math
import os
import re
import struct
import zlib
from collections.abc import Callable

import pytest
from playwright.sync_api import Browser, Page, Route, expect
from stack import E2E, Stack
from test_world3d import GL_FLAGS, seed_pirate_world, walk_button

NewPage = Callable[..., Page]
TAG = os.environ.get("WORLD3D_TAG", "after")
ARTIFACTS = E2E / "artifacts"
W, H = 256, 128
VIEWPORT = {  # `WORLD3D_VIEWPORT=390x844` for a phone
    k: int(v)
    for k, v in zip(
        ("width", "height"), os.environ.get("WORLD3D_VIEWPORT", "1280x800").split("x")
    )
}


def busy_panorama(yaw_deg: float) -> bytes:
    """Grey equirect PNG with a colourful chequered stretch on the horizon around `yaw_deg`."""
    centre = round((0.5 - yaw_deg / 360) * W) % W
    rows = []
    for y in range(H):
        row = bytearray([0])
        for x in range(W):
            near = min((x - centre) % W, (centre - x) % W) < 18 and 40 <= y < 88
            row += bytes(
                (250, 140, 20)
                if near and (x + y) % 2
                else (40, 90, 200)
                if near
                else (120, 120, 120)
            )
        rows.append(bytes(row))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data))
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"".join(rows)))
        + chunk(b"IEND", b"")
    )


@pytest.mark.parametrize(
    ("name", "genre", "close_yaw"),
    [
        ("sky-islands", "custom", None),
        ("seaside-lighthouse", "pirates", None),
        ("library-nook", "fairy_tale", None),
        ("library-nook-close", "fairy_tale", -175.0),
    ],
)
def test_first_frame_screenshot(
    new_page: NewPage,
    browser: Browser,
    stack: Stack,
    name: str,
    genre: str,
    close_yaw: float | None,
) -> None:
    seeder = new_page()
    seed_pirate_world(seeder, genre)
    gl_browser = browser.browser_type.launch(headless=True, args=GL_FLAGS)
    try:
        context = gl_browser.new_context(
            base_url=stack.site,
            storage_state=seeder.context.storage_state(),
            viewport=VIEWPORT,
        )
        page = context.new_page()
        panorama_hits: list[str] = []
        if close_yaw is not None:
            png = busy_panorama(close_yaw)

            def serve(route: Route) -> None:
                panorama_hits.append(route.request.url)
                route.fulfill(status=200, body=png, content_type="image/png")

            page.route(
                re.compile(r".*/worlds/library-nook-full/pano\..*\.webp$"), serve
            )
        page.goto("/adventure")
        walk_button(page).click()
        canvas = page.get_by_role("dialog").locator("canvas")
        expect(canvas).to_be_visible(timeout=60_000)
        expect(canvas).to_have_attribute(
            "data-initial-yaw", re.compile(r"^-?\d"), timeout=60_000
        )
        if close_yaw is None:  # a library world is open enough to need no step back
            expect(canvas).to_have_attribute("data-initial-back", "0")
        else:
            yaw = math.degrees(float(canvas.get_attribute("data-initial-yaw") or "nan"))
            away = abs((yaw - close_yaw + 180) % 360 - 180)
            assert panorama_hits, "the busy panorama was never requested"
            assert away > 60, (
                f"walk opens {away:.0f} deg from the close wall, yaw {yaw:.0f}"
            )
        page.wait_for_timeout(
            3_000
        )  # screenshot only: swiftshader sorts the splats over a few frames
        ARTIFACTS.mkdir(exist_ok=True)
        page.screenshot(
            path=str(ARTIFACTS / f"world3d-{TAG}-{VIEWPORT['width']}-{name}.png")
        )
    finally:
        gl_browser.close()
