import pytest

from app.channels.push.endpoints import is_allowed_push_endpoint


@pytest.mark.parametrize(
    "url",
    [
        "https://fcm.googleapis.com/fcm/send/x",
        "https://FCM.googleapis.com/fcm/send/x",
        "https://updates.push.services.mozilla.com/wpush/v2/x",
        "https://web.push.apple.com/x",
        "https://a1.push.apple.com/x",
        "https://db5p.notify.windows.com/?token=x",
        "https://fcm.googleapis.com:443/x",
    ],
)
def test_known_push_services_are_allowed(url: str) -> None:
    assert is_allowed_push_endpoint(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://fcm.googleapis.com/x",
        "https://evil.example/r",
        "https://evilnotify.windows.com/x",
        "https://notify.windows.com/x",
        "https://fcm.googleapis.com.evil.example/x",
        "https://user:pw@fcm.googleapis.com/x",
        "https://fcm.googleapis.com@evil.example/x",
        "https://fcm.googleapis.com:8443/x",
        "https://127.0.0.1/x",
        "https:///x",
        "not a url",
    ],
)
def test_everything_else_is_refused(url: str) -> None:
    assert not is_allowed_push_endpoint(url)
