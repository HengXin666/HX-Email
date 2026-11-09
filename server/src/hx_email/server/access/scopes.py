"""Scopes of router API keys (docs/messaging-router.md section 8.3).

A scope names a capability, not a transport: ``router:send`` covers both
``POST /api/v1/router/messages`` and the MCP tool ``message_send``. ``mcp`` only gates
the ``/mcp`` endpoint itself, so a REST-only key can be minted. ``admin`` implies
every scope, including ones added later. The web console session holds every scope.

Keys issued before scopes existed carry ``LEGACY_SCOPES`` (every scope but ``admin``),
which is exactly what a key could do before: key management and outbound hold/resume
stay console-session-only whatever the scopes say.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

from hx_email.server.router.errors import InsufficientScopeError, RouteInvalidError

READ: Final[str] = "router:read"
SEND: Final[str] = "router:send"
ACTIONS: Final[str] = "router:actions"
SUBSCRIPTIONS: Final[str] = "subscriptions"
RESOURCES_SUBSCRIBE: Final[str] = "resources:subscribe"
MCP: Final[str] = "mcp"
ADMIN: Final[str] = "admin"
ALL_SCOPES: Final[tuple[str, ...]] = (
    READ,
    SEND,
    ACTIONS,
    SUBSCRIPTIONS,
    RESOURCES_SUBSCRIBE,
    MCP,
    ADMIN,
)
LEGACY_SCOPES: Final[tuple[str, ...]] = tuple(scope for scope in ALL_SCOPES if scope != ADMIN)
LEGACY_TEXT: Final[str] = " ".join(LEGACY_SCOPES)
EVERYTHING: Final[frozenset[str]] = frozenset(ALL_SCOPES)


def normalize_scopes(values: Iterable[str]) -> tuple[str, ...]:
    """Known scopes in canonical order; unknown or empty raises ``RouteInvalidError``."""
    wanted: set[str] = {str(value).strip() for value in values if str(value).strip()}
    unknown: list[str] = sorted(wanted - EVERYTHING)
    if unknown:
        raise RouteInvalidError(f"unknown scopes: {', '.join(unknown)}")
    if not wanted:
        raise RouteInvalidError("a key needs at least one scope")
    return tuple(scope for scope in ALL_SCOPES if scope in wanted)


def parse_stored(text: str) -> frozenset[str]:
    """Column value to a set; unknown words are dropped, never widened."""
    return frozenset(word for word in text.split() if word in EVERYTHING)


def granted(scopes: frozenset[str], needed: str) -> bool:
    return ADMIN in scopes or needed in scopes


# scope 按能力命名而不是按入口: REST 与 MCP 的同一能力共用一个 scope, admin 蕴含全部
# 决策记录: .agents/notes/implemented/feature/2026-11-09-mcp-completion.md
def require_scope(scopes: frozenset[str], needed: str) -> None:
    """Raise ``InsufficientScopeError`` unless ``scopes`` grants ``needed``."""
    if not granted(scopes, needed):
        raise InsufficientScopeError(needed)
