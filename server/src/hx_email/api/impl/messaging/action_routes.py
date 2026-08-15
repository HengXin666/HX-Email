"""REST routes: conversations, messages, sending and group operations."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query, status

from hx_email.api.dependencies import require_user
from hx_email.api.impl.messaging.schemas import (
    MessagingGroupActionRequest,
    MessagingSendRequest,
)
from hx_email.api.impl.messaging.serializers import (
    conversation_dict,
    group_dict,
    message_dict,
    require_instance,
)
from hx_email.config import Settings
from hx_email.server.messaging.store import list_messages
from hx_email.server.messaging.types import (
    GroupAction,
    MessageTarget,
    MessagingConversation,
    MessagingError,
    MessagingGroup,
    MessagingMessage,
)


def register_messaging_action_routes(router: APIRouter, settings: Settings) -> None:
    @router.get("/messaging/instances/{instance_id}/conversations")
    def conversations(
        instance_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        _instance, adapter = require_instance(settings, user.id, instance_id)
        items: list[MessagingConversation] = adapter.list_conversations()
        return {
            "success": True,
            "conversations": [conversation_dict(item) for item in items],
        }

    @router.get("/messaging/instances/{instance_id}/messages")
    def messages(
        instance_id: int,
        chat_id: str = "",
        limit: int = Query(default=50, ge=1, le=100),
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        instance, adapter = require_instance(settings, user.id, instance_id)
        remote: list[MessagingMessage] = []
        if chat_id and adapter.capabilities.supports_history:
            try:
                remote = adapter.list_messages(chat_id, limit)
            except MessagingError:
                remote = []
        stored: list[MessagingMessage] = list_messages(
            settings, user.id, instance.id, chat_id, limit
        )
        merged: dict[str, MessagingMessage] = {
            msg.message_id or str(id(msg)): msg for msg in [*remote, *stored]
        }
        ordered: list[MessagingMessage] = sorted(
            merged.values(), key=lambda m: m.created_at, reverse=True
        )
        return {
            "success": True,
            "messages": [message_dict(item) for item in ordered[:limit]],
        }

    @router.post("/messaging/instances/{instance_id}/send")
    def send(
        instance_id: int,
        payload: MessagingSendRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        _instance, adapter = require_instance(settings, user.id, instance_id)
        try:
            message_id: str = adapter.send_message(
                MessageTarget(chat_id=payload.chat_id, chat_type=payload.chat_type),
                payload.text,
            )
        except MessagingError as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        return {"success": True, "message_id": message_id}

    @router.get("/messaging/instances/{instance_id}/groups")
    def groups(
        instance_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        _instance, adapter = require_instance(settings, user.id, instance_id)
        if not adapter.capabilities.supports_groups:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail=f"{adapter.display_name} 不支持群组能力",
            )
        items: list[MessagingGroup] = adapter.list_groups()
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
        if not adapter.capabilities.supports_groups:
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
