"""Landing link preview: Open Graph and Twitter tags in the served HTML, picture reachable."""

import re
from collections.abc import Callable
from urllib.parse import urlparse

import pytest
from playwright.sync_api import Page

NewPage = Callable[..., Page]


def tags(html: str) -> dict[str, str]:
    found = re.findall(
        r'<meta[^>]+(?:property|name)="((?:og|twitter):[a-z:_]+)"[^>]+content="([^"]*)"', html
    )
    return dict(found)


@pytest.mark.parametrize(
    ("path", "locale", "picture"),
    [("/", "ru_RU", "og-ru.jpg"), ("/en", "en_US", "og-en.jpg")],
)
def test_landing_html_carries_preview_tags_and_the_picture_loads(
    new_page: NewPage, path: str, locale: str, picture: str
) -> None:
    request = new_page().context.request
    html = request.get(path).text()
    meta = tags(html)
    assert meta["twitter:card"] == "summary_large_image"
    assert meta["og:type"] == "website"
    assert meta["og:locale"] == locale
    for key in ("og:title", "og:description", "twitter:title", "twitter:description"):
        assert meta[key].strip(), key
    image = meta["og:image"]
    assert image.startswith("https://"), image
    assert meta["twitter:image"] == image
    assert image.endswith(f"/og/{picture}"), image
    response = request.get(urlparse(image).path)
    assert response.status == 200
    assert response.headers["content-type"].startswith("image/")
