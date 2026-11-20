import re

from fastapi import APIRouter, Header, Response

from app.api.v1.deps import ImageRepositoryDep, OptionalMember, WorldSceneRepositoryDep
from app.domain.errors import NotFound

router = APIRouter(prefix="/api/v1")

# `private`: the answer is per family. `immutable`: the name is the hash of the bytes.
CACHE_CONTROL = "private, max-age=31536000, immutable"
_SHA = re.compile(r"[0-9a-f]{64}")


def _matches(if_none_match: str | None, etag: str) -> bool:
    if not if_none_match:
        return False
    tags = [t.strip().removeprefix("W/") for t in if_none_match.split(",")]
    return "*" in tags or etag in tags


@router.get(
    "/media/{sha}.webp", response_class=Response, responses={200: {"content": {"image/webp": {}}}}
)
async def get_media(
    sha: str,
    member: OptionalMember,
    images: ImageRepositoryDep,
    if_none_match: str | None = Header(default=None),
) -> Response:
    """Serve a ready picture to its own family; every other case is the same 404."""
    data = None
    if member is not None and _SHA.fullmatch(sha):
        data = await images.ready_bytes(member.family_id, sha)
    if data is None:
        raise NotFound("not found")
    return _immutable(data, sha, "image/webp", if_none_match)


@router.get(
    "/media/{sha}.spz",
    response_class=Response,
    responses={200: {"content": {"application/octet-stream": {}}}},
)
async def get_scene_spz(
    sha: str,
    member: OptionalMember,
    scenes: WorldSceneRepositoryDep,
    if_none_match: str | None = Header(default=None),
) -> Response:
    """Serve a ready 3D scene to its own family; every other case is the same 404."""
    data = None
    if member is not None and _SHA.fullmatch(sha):
        data = await scenes.ready_spz(member.family_id, sha)
    if data is None:
        raise NotFound("not found")
    return _immutable(data, sha, "application/octet-stream", if_none_match)


@router.get(
    "/media/pano/{sha}.webp",
    response_class=Response,
    responses={200: {"content": {"image/webp": {}}}},
)
async def get_scene_panorama(
    sha: str,
    member: OptionalMember,
    scenes: WorldSceneRepositoryDep,
    if_none_match: str | None = Header(default=None),
) -> Response:
    """Serve the panorama of a ready scene (named by the scene's spz sha); else the same 404."""
    data = None
    if member is not None and _SHA.fullmatch(sha):
        data = await scenes.ready_panorama(member.family_id, sha)
    if data is None:
        raise NotFound("not found")
    return _immutable(data, f"pano-{sha}", "image/webp", if_none_match)


def _immutable(data: bytes, sha: str, media_type: str, if_none_match: str | None) -> Response:
    etag = f'"{sha}"'
    headers = {"Cache-Control": CACHE_CONTROL, "ETag": etag}
    if _matches(if_none_match, etag):
        return Response(status_code=304, headers=headers)
    return Response(data, media_type=media_type, headers=headers)
