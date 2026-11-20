import pytest

from app.agent import world3d_client
from app.agent.world3d_client import SceneError
from tests.test_scene_worker import DONE, SPZ, Api, client, op


async def test_operation_404_before_it_appears_is_polled_again() -> None:
    api = Api(polls=[404, op(False, "IN_PROGRESS"), DONE])
    assert (await client(api).generate("A harbor.")).spz == SPZ
    polls = [r for r in api.requests if "/operations/" in str(r.url)]
    assert len(polls) == 3


async def test_operation_404_past_the_grace_window_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(world3d_client, "OPERATION_GRACE_S", 0.02)
    with pytest.raises(SceneError, match="404"):
        await client(Api(polls=[404]), world3d_timeout_s=1.0).generate("A harbor.")


async def test_operation_500_fails_at_once() -> None:
    api = Api(polls=[500, DONE])
    with pytest.raises(SceneError, match="HTTP 500"):
        await client(api).generate("A harbor.")
    assert sum("/operations/" in str(r.url) for r in api.requests) == 1
