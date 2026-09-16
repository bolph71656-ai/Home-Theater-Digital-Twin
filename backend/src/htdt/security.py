from __future__ import annotations

from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse, Response


LOOPBACK_HOSTS = frozenset({'127.0.0.1', 'localhost', '::1'})
UNSAFE_METHODS = frozenset({'POST', 'PUT', 'PATCH', 'DELETE'})


def _hostname_from_authority(authority: str) -> str | None:
    if not authority or any(character in authority for character in '\r\n'):
        return None
    try:
        return urlsplit(f'//{authority}').hostname
    except ValueError:
        return None


def is_allowed_host(authority: str | None, *, allow_testserver: bool = False) -> bool:
    if authority is None:
        return False
    hostname = _hostname_from_authority(authority)
    if hostname is None:
        return False
    hostname = hostname.lower()
    return hostname in LOOPBACK_HOSTS or (allow_testserver and hostname == 'testserver')


def is_allowed_origin(origin: str | None) -> bool:
    if origin is None:
        return True
    try:
        parsed = urlsplit(origin)
    except ValueError:
        return False
    if parsed.scheme != 'http' or parsed.username or parsed.password or parsed.query or parsed.fragment:
        return False
    hostname = parsed.hostname.lower() if parsed.hostname else None
    return hostname in LOOPBACK_HOSTS


def install_local_request_boundary(app: object, *, allow_testserver: bool = False) -> None:
    # FastAPI exposes `middleware` dynamically; keeping the dependency surface here small
    # makes the policy functions independently testable.
    middleware = getattr(app, 'middleware')

    @middleware('http')
    async def local_request_boundary(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if not is_allowed_host(request.headers.get('host'), allow_testserver=allow_testserver):
            return JSONResponse({'detail': 'Host must be localhost or loopback'}, status_code=400)

        if request.method.upper() in UNSAFE_METHODS and not is_allowed_origin(request.headers.get('origin')):
            return JSONResponse({'detail': 'Origin must be localhost or loopback'}, status_code=403)

        return await call_next(request)
