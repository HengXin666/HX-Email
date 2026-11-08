"""Map router domain errors to HTTP responses, so client mistakes are 4xx, not 502."""

from __future__ import annotations

from typing import Final

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from hx_email.server.router.errors import RouterError

HTTP_STATUS_BY_CODE: Final[dict[str, int]] = {
    "session_not_found": 404,
    "session_not_sendable": 422,
    "text_too_long": 422,
    "rate_limited": 429,
    "outbound_held": 423,
    "provider_offline": 503,
    "provider_error": 502,
    "delivery_unknown": 409,
    "cursor_invalid": 400,
    "route_not_found": 404,
    "route_invalid": 422,
    "route_limit": 409,
    "action_not_supported": 422,
    "invalid_payload": 422,
}
DEFAULT_STATUS: Final[int] = 502


def http_status_for(error: RouterError) -> int:
    return HTTP_STATUS_BY_CODE.get(error.code, DEFAULT_STATUS)


def router_error_response(error: RouterError) -> JSONResponse:
    """Body is ``{"error": {code, message, retryable}}``, same triple as MCP isError."""
    return JSONResponse(status_code=http_status_for(error), content={"error": error.to_dict()})


async def handle_router_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RouterError):
        raise exc
    return router_error_response(exc)


def install_router_error_handler(app: FastAPI) -> None:
    """Register once when the router is mounted (``router_enabled``)."""
    app.add_exception_handler(RouterError, handle_router_error)
