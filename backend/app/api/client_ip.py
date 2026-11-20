from ipaddress import IPv6Address, IPv6Network, ip_address

from fastapi import Request

UNKNOWN = "-"


def _is_public(raw: str) -> bool:
    try:
        addr = ip_address(raw.strip())
    except ValueError:
        return False
    return not (addr.is_private or addr.is_loopback or addr.is_link_local)


def _bucket(raw: str) -> str:
    """An IPv6 client owns a whole /64, so one host cannot spread over its addresses."""
    try:
        addr = ip_address(raw.strip())
    except ValueError:
        return raw.strip()
    if isinstance(addr, IPv6Address) and addr.ipv4_mapped:
        return str(addr.ipv4_mapped)
    if isinstance(addr, IPv6Address):
        return str(IPv6Network(f"{addr}/64", strict=False))
    return str(addr)


def client_ip(request: Request) -> str:
    """The caller's address (an IPv6 one as its /64) for in-memory limits; never store or log it.

    Behind two Caddy hops each proxy appends the address it saw, so the entries to the left of
    the rightmost public one are client-supplied and ignored. Without a public entry the peer
    address is used.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    for entry in reversed(forwarded.split(",")):
        if _is_public(entry):
            return _bucket(entry)
    return _bucket(request.client.host) if request.client else UNKNOWN
