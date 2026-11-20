"""Which hosts may receive a push: browser vendors' push services only.

A subscription endpoint is client-supplied, so without this list the server would POST to any
address a member names (blind SSRF into the stand network).
"""

from urllib.parse import urlsplit

EXACT_HOSTS = frozenset(
    {"fcm.googleapis.com", "updates.push.services.mozilla.com", "web.push.apple.com"}
)
HOST_SUFFIXES = (".notify.windows.com", ".push.apple.com")


def is_allowed_push_endpoint(endpoint: str) -> bool:
    try:
        parts = urlsplit(endpoint)
        port = parts.port
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or parts.username is not None or port not in (None, 443):
        return False
    return host in EXACT_HOSTS or host.endswith(HOST_SUFFIXES)
