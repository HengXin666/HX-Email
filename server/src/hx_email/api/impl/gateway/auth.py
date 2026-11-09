"""Caller identity for the gateway: a router API key or a web console session.

Machine callers (MCP clients, scripts) use ``hxr_`` keys bound to one user; the web
console keeps its session token. Hold/resume and key management accept only the
session, so a leaked key can neither lift a breaker nor mint more keys.

Every gateway entry names the scope it needs (``server/access/scopes.py``); a key
without it gets ``insufficient_scope`` (REST 403, MCP JSON-RPC error). The console
session holds every scope.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from fastapi import HTTPException, status

from hx_email.api.dependencies import bearer_token, require_user
from hx_email.config import Settings
from hx_email.server.access.scopes import EVERYTHING, READ, require_scope
from hx_email.server.auth import authenticate_token
from hx_email.server.gateway.api_keys import KEY_PREFIX, KeyRecord, verify_key_record


@dataclass(frozen=True)
class Caller:
    """Who is calling: owner, key row (None for the console), scopes, credential hash."""

    user_id: int
    key_id: int | None
    scopes: frozenset[str]
    principal: str


def unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def resolve_caller(settings: Settings, authorization: str | None) -> Caller:
    """Identity from ``Authorization: Bearer <hxr_ key | session token>``."""
    token: str = bearer_token(authorization)
    principal: str = hashlib.sha256(token.encode("utf-8")).hexdigest()
    if token.startswith(KEY_PREFIX):
        record: KeyRecord | None = verify_key_record(settings, token)
        if record is None:
            raise unauthorized("Invalid or revoked router API key")
        return Caller(record.user_id, record.key_id, record.scopes, principal)
    user = authenticate_token(settings, token)
    if user is None:
        raise unauthorized("Invalid token")
    return Caller(int(user.id), None, EVERYTHING, principal)


# 每个入口显式声明所需 scope, 缺省是只读; 不足时抛 insufficient_scope 由错误处理映射成 403
# 决策记录: .agents/notes/implemented/feature/2026-11-09-mcp-completion.md
def caller_user_id(settings: Settings, authorization: str | None, scope: str = READ) -> int:
    """User id of a caller that holds ``scope``."""
    caller: Caller = resolve_caller(settings, authorization)
    require_scope(caller.scopes, scope)
    return caller.user_id


def session_user_id(settings: Settings, authorization: str | None) -> int:
    """Web console session only; router keys are refused here on purpose."""
    token: str = bearer_token(authorization)
    if token.startswith(KEY_PREFIX):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint needs the web console session, not a router API key",
        )
    return int(require_user(settings, authorization).id)
