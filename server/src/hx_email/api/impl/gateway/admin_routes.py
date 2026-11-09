"""Session-only gateway routes: router API keys and outbound hold / resume (spec 6, 8.2).

These accept the web console session and refuse router keys, so a leaked key cannot
lift a breaker or mint more keys.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from hx_email.api.impl.gateway.auth import session_user_id
from hx_email.config import Settings
from hx_email.server.access.key_scopes import update_scopes
from hx_email.server.access.scopes import ALL_SCOPES, LEGACY_SCOPES
from hx_email.server.gateway.api_keys import (
    IssuedKey,
    KeyLimitError,
    issue_key,
    list_keys,
    revoke_key,
)
from hx_email.server.gateway.sending import hold_outbound, resume_outbound

PREFIX: str = "/router"


class KeyCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(default="default", max_length=64)
    # 缺省 None = 引入 scope 之前的能力集, 老脚本只传 name 时行为不变
    scopes: list[str] | None = Field(default=None, max_length=16)


class KeyScopesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scopes: list[str] = Field(min_length=1, max_length=16)


def register_gateway_admin_routes(router: APIRouter, settings: Settings) -> None:
    @router.post(f"{PREFIX}/api-keys", status_code=status.HTTP_201_CREATED)
    def create_key(
        payload: KeyCreateRequest, authorization: Annotated[str | None, Header()] = None
    ) -> dict[str, object]:
        user_id: int = session_user_id(settings, authorization)
        try:
            issued: IssuedKey = issue_key(settings, user_id, payload.name, payload.scopes)
        except KeyLimitError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        return {
            "id": issued.id,
            "name": issued.name,
            "key": issued.key,
            "key_prefix": issued.key_prefix,
            "created_at": issued.created_at,
            "scopes": issued.scopes,
        }

    @router.get(f"{PREFIX}/api-keys/scopes")
    def key_scopes(authorization: Annotated[str | None, Header()] = None) -> dict[str, object]:
        session_user_id(settings, authorization)
        return {"scopes": list(ALL_SCOPES), "default": list(LEGACY_SCOPES)}

    @router.patch(f"{PREFIX}/api-keys/{{key_id}}")
    def patch_key(
        key_id: int,
        payload: KeyScopesRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user_id: int = session_user_id(settings, authorization)
        updated: dict[str, object] | None = update_scopes(settings, user_id, key_id, payload.scopes)
        if updated is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Key not found or already revoked")
        return updated

    @router.get(f"{PREFIX}/api-keys")
    def get_keys(authorization: Annotated[str | None, Header()] = None) -> dict[str, object]:
        return {"keys": list_keys(settings, session_user_id(settings, authorization))}

    @router.delete(f"{PREFIX}/api-keys/{{key_id}}")
    def delete_key(
        key_id: int, authorization: Annotated[str | None, Header()] = None
    ) -> dict[str, object]:
        if not revoke_key(settings, session_user_id(settings, authorization), key_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Key not found or already revoked")
        return {"id": key_id, "revoked": True}

    @router.post(f"{PREFIX}/instances/{{instance_id}}/outbound/hold")
    def hold(
        instance_id: int, authorization: Annotated[str | None, Header()] = None
    ) -> dict[str, object]:
        return hold_outbound(settings, session_user_id(settings, authorization), instance_id)

    @router.post(f"{PREFIX}/instances/{{instance_id}}/outbound/resume")
    def resume(
        instance_id: int, authorization: Annotated[str | None, Header()] = None
    ) -> dict[str, object]:
        return resume_outbound(settings, session_user_id(settings, authorization), instance_id)
