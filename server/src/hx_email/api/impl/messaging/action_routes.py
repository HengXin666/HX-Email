"""REST routes: conversations, messages, sending and group operations.

Conversations, messages and sending go through the router gateway for every platform,
so the web console shares the shaper, breaker and dedup with MCP and REST callers. The
response shapes stay the legacy ones the console renders (``chat_id`` is the bare peer).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query, status

from hx_email.api.dependencies import require_user
from hx_email.api.impl.messaging.schemas import (
    MessagingGroupActionRequest,
    MessagingSendRequest,
)
from hx_email.api.impl.messaging.serializers import group_dict, require_instance
from hx_email.config import Settings
from hx_email.server.gateway.catalog import collect_sessions
from hx_email.server.gateway.listen import recent_messages
from hx_email.server.gateway.providers import InstanceRow, require_owned
from hx_email.server.gateway.sending import send_message
from hx_email.server.messaging.types import (
    GroupAction,
    MessagingError,
    MessagingGroup,
)
from hx_email.server.router.envelope import Envelope
from hx_email.server.router.errors import RouterError

LEGACY_GROUP_TYPES: frozenset[str] = frozenset({"group", "repo", "issue"})
FAILED_STATUSES: frozenset[str] = frozenset({"failed", "dead"})


def legacy_type(session_type: str) -> str:
    return "group" if session_type in LEGACY_GROUP_TYPES else "private"


def session_address(instance: InstanceRow, chat_id: str, chat_type: str) -> str:
    """Accept a full address or the console's bare peer plus chat_type."""
    if chat_id.startswith(f"{instance.kind}:"):
        return chat_id
    if instance.kind == "github":
        return f"github:{instance.id}:{'issue' if '#' in chat_id else 'repo'}:{chat_id}"
    kind: str = "group" if chat_type == "group" else "private"
    return f"qq:{instance.id}:{kind}:{chat_id}"


def legacy_message(item: Envelope) -> dict[str, object]:
    return {
        "direction": item.direction,
        "chat_id": item.session.split(":", 3)[3],
        "chat_type": legacy_type(item.session_type),
        "sender_id": item.sender.id,
        "sender_name": item.sender.name or ("我" if item.sender.is_self else ""),
        "text": item.text,
        "message_id": item.platform_message_id,
        "created_at": item.received_at,
    }


def gateway_http_error(error: RouterError) -> HTTPException:
    code: int = status.HTTP_404_NOT_FOUND if error.code == "session_not_found" else 400
    return HTTPException(status_code=code, detail=f"{error.code}: {error.message}")


# 前端会话, 消息与发送统一走路由网关, 与 MCP/REST 共享整形, 熔断与去重, 不再直调适配器
# 决策记录: .agents/notes/implemented/feature/2026-11-06-router-gateway-facade.md
def register_messaging_action_routes(router: APIRouter, settings: Settings) -> None:
    @router.get("/messaging/instances/{instance_id}/conversations")
    def conversations(
        instance_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        require_instance(settings, user.id, instance_id)
        try:
            instance: InstanceRow = require_owned(settings, user.id, instance_id)
        except RouterError as error:
            raise gateway_http_error(error) from error
        items: list[dict[str, object]] = [
            {
                "chat_id": ref.session_id,
                "chat_type": legacy_type(ref.session_type),
                "name": ref.title,
                "session": ref.address,
            }
            for ref in collect_sessions(settings, instance)
        ]
        return {"success": True, "conversations": items}

    @router.get("/messaging/instances/{instance_id}/messages")
    def messages(
        instance_id: int,
        chat_id: str = "",
        chat_type: str = "",
        limit: int = Query(default=50, ge=1, le=100),
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        require_instance(settings, user.id, instance_id)
        if not chat_id:
            return {"success": True, "messages": []}
        try:
            instance: InstanceRow = require_owned(settings, user.id, instance_id)
        except RouterError as error:
            raise gateway_http_error(error) from error
        address: str = (
            chat_id
            if not chat_type and instance.kind == "qq" and ":" not in chat_id
            else session_address(instance, chat_id, chat_type)
        )
        stored: list[Envelope] = recent_messages(settings, instance.id, address, limit)
        newest_first: list[dict[str, object]] = [legacy_message(item) for item in reversed(stored)]
        return {"success": True, "messages": newest_first}

    @router.post("/messaging/instances/{instance_id}/send")
    def send(
        instance_id: int,
        payload: MessagingSendRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        require_instance(settings, user.id, instance_id)
        try:
            instance: InstanceRow = require_owned(settings, user.id, instance_id)
            result: dict[str, object] = send_message(
                settings,
                user.id,
                session_address(instance, payload.chat_id, payload.chat_type),
                payload.text,
                f"web-{uuid.uuid4().hex}",
            )
        except RouterError as error:
            raise gateway_http_error(error) from error
        if result["status"] in FAILED_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"发送失败: {result['last_error']}",
            )
        return {
            "success": True,
            "message_id": result["platform_message_id"],
            "delivery_id": result["delivery_id"],
            "status": result["status"],
            "queued_until": result["queued_until"],
        }

    @router.get("/messaging/instances/{instance_id}/groups")
    def groups(
        instance_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        _instance, adapter = require_instance(settings, user.id, instance_id)
        if not adapter.capabilities.supports_groups or adapter.kind == "github":
            return {"success": True, "groups": []}
        try:
            items: list[MessagingGroup] = adapter.list_groups()
        except MessagingError as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)
            ) from error
        return {"success": True, "groups": [group_dict(item) for item in items]}

    @router.post("/messaging/instances/{instance_id}/groups/{group_id}/action")
    def group_action(
        instance_id: int,
        group_id: str,
        payload: MessagingGroupActionRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        _instance, adapter = require_instance(settings, user.id, instance_id)
        if not adapter.capabilities.supports_groups or adapter.kind == "github":
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail=f"{adapter.display_name} 不支持群组能力",
            )
        try:
            ok: bool = adapter.group_action(
                group_id,
                GroupAction(
                    action=payload.action,
                    member_id=payload.member_id,
                    duration_seconds=payload.duration_seconds,
                ),
            )
        except MessagingError as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        return {"success": True, "applied": ok}
