"""Re-encode a generated picture as the small WebP that is stored and served."""

import io

from PIL import Image

QUALITY = 80
MAX_SIDE = 1024
MAX_SOURCE_SIDE = 4096  # a header claiming more is refused before any pixel is decoded
FORMATS = ("PNG", "JPEG", "WEBP")


def encode_webp(
    raw: bytes, max_side: int = MAX_SIDE, max_source_side: int = MAX_SOURCE_SIDE
) -> bytes:
    """WebP of the picture, long side at most `max_side`; never enlarged."""
    with Image.open(io.BytesIO(raw), formats=FORMATS) as src:
        if max(src.size) > max_source_side:
            raise ValueError("picture too large")
        img = src.convert("RGB")
    img.thumbnail((max_side, max_side))
    out = io.BytesIO()
    img.save(out, "WEBP", quality=QUALITY)
    return out.getvalue()
