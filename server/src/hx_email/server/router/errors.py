"""Domain errors of the router layer, one class per code in docs/messaging-router.md 9.4.

The API layer maps ``RouterError.code`` to an HTTP status (mostly 4xx), so callers never
see a blanket 502 for a problem that is theirs to fix.
"""

from __future__ import annotations

from typing import ClassVar, Final


class RouterError(Exception):
    """Base error carrying the spec's ``{code, message, retryable}`` triple."""

    code: ClassVar[str] = "provider_error"
    default_retryable: ClassVar[bool] = False

    def __init__(self, message: str = "", *, retryable: bool | None = None) -> None:
        text: str = message or self.code
        super().__init__(text)
        self.message: str = text
        self.retryable: bool = self.default_retryable if retryable is None else retryable

    def to_dict(self) -> dict[str, object]:
        return {"code": self.code, "message": self.message, "retryable": self.retryable}


class SessionNotFoundError(RouterError):
    """Address is invalid or does not belong to the current user."""

    code = "session_not_found"


class SessionNotSendableError(RouterError):
    """Repo address without title, QQ target not a friend or group, cold private message."""

    code = "session_not_sendable"


class TextTooLongError(RouterError):
    """Text exceeds the platform ``max_text_length``."""

    code = "text_too_long"


class RateLimitedError(RouterError):
    """Local shaper refused within ``wait_seconds``; the message is already queued."""

    code = "rate_limited"


class OutboundHeldError(RouterError):
    """Instance is ``held`` or ``manual_hold``; the message is queued as ``held``."""

    code = "outbound_held"


class ProviderOfflineError(RouterError):
    """The account instance is offline."""

    code = "provider_offline"
    default_retryable = True


class ProviderError(RouterError):
    """Platform returned an error; ``retryable`` comes from ``SendResult.retryable``."""

    code = "provider_error"


class DeliveryUnknownError(RouterError):
    """Platform call outcome unknown, row is ``unknown`` (spec 7.3)."""

    code = "delivery_unknown"


class CursorInvalidError(RouterError):
    """Cursor cannot be parsed, is out of range, or belongs to another instance."""

    code = "cursor_invalid"


class RouteNotFoundError(RouterError):
    """Subscription id does not exist or belongs to another user."""

    code = "route_not_found"


class RouteInvalidError(RouterError):
    """Subscription filter, status or start value is not accepted."""

    code = "route_invalid"


class RouteLimitError(RouterError):
    """The account already holds the maximum number of subscriptions."""

    code = "route_limit"


class ActionNotSupportedError(RouterError):
    """The platform declares no such action, or not on this address kind."""

    code = "action_not_supported"


class InvalidPayloadError(RouterError):
    """Action parameters are missing, unknown, or outside what the declaration allows."""

    code = "invalid_payload"


ERROR_TYPES: Final[dict[str, type[RouterError]]] = {
    error_type.code: error_type
    for error_type in (
        SessionNotFoundError,
        SessionNotSendableError,
        TextTooLongError,
        RateLimitedError,
        OutboundHeldError,
        ProviderOfflineError,
        ProviderError,
        DeliveryUnknownError,
        CursorInvalidError,
        RouteNotFoundError,
        RouteInvalidError,
        RouteLimitError,
        ActionNotSupportedError,
        InvalidPayloadError,
    )
}


def error_from_code(code: str, message: str = "", retryable: bool | None = None) -> RouterError:
    """Rebuild a typed error from its code; unknown codes become ``ProviderError``."""
    error_type: type[RouterError] = ERROR_TYPES.get(code, ProviderError)
    return error_type(message, retryable=retryable)
