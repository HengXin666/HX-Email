"""Shared helpers: instance resolution and dataclass -> dict serialization."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from hx_email.config import Settings
from hx_email.server.messaging.registry import get_adapter
from hx_email.server.messaging.store import get_instance
from hx_email.server.messaging.types import (
    AdapterStatus,
    LoginState,
    LoginTicket,
    MessagingAdapter,
    MessagingConversation,
    MessagingGroup,
    MessagingInstance,
    MessagingMessage,
)


def require_instance(
    settings: Settings,
    user_id: int,
    instance_id: int,
) -> tuple[MessagingInstance, MessagingAdapter]:
    instance: MessagingInstance | None = get_instance(settings, user_id, instance_id)
    if instance is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Messaging instance not found",
        )
    try:
        adapter: MessagingAdapter = get_adapter(settings, instance)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    return instance, adapter


def safe_adapter(settings: Settings, instance: MessagingInstance) -> MessagingAdapter | None:
    try:
        return get_adapter(settings, instance)
    except ValueError:
        return None


def instance_dict(
    instance: MessagingInstance,
    adapter: MessagingAdapter | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": instance.id,
        "kind": instance.kind,
        "name": instance.name,
        "status": instance.status,
        "config": instance.config,
        "created_at": instance.created_at,
        "updated_at": instance.updated_at,
    }
    if adapter is not None:
        capability = adapter.capabilities
        result["capabilities"] = {
            "supports_qr_login": capability.supports_qr_login,
            "supports_groups": capability.supports_groups,
            "supports_history": capability.supports_history,
            "risk_level": capability.risk_level,
            "risk_notice": capability.risk_notice,
        }
    return result


def status_dict(value: AdapterStatus) -> dict[str, str]:
    return {
        "state": value.state,
        "account_id": value.account_id,
        "account_name": value.account_name,
        "message": value.message,
    }


def login_ticket_dict(value: LoginTicket) -> dict[str, object]:
    return {
        "mode": value.mode,
        "url": value.url,
        "qr_image_url": value.qr_image_url,
        "instructions": value.instructions,
        "expires_in": value.expires_in,
    }


def login_state_dict(value: LoginState) -> dict[str, object]:
    return {
        "logged_in": value.logged_in,
        "account_id": value.account_id,
        "account_name": value.account_name,
        "message": value.message,
    }


def conversation_dict(value: MessagingConversation) -> dict[str, object]:
    return {
        "chat_id": value.chat_id,
        "chat_type": value.chat_type,
        "name": value.name,
    }


def message_dict(value: MessagingMessage) -> dict[str, object]:
    return {
        "direction": value.direction,
        "chat_id": value.chat_id,
        "chat_type": value.chat_type,
        "sender_id": value.sender_id,
        "sender_name": value.sender_name,
        "text": value.text,
        "message_id": value.message_id,
        "created_at": value.created_at,
    }


def group_dict(value: MessagingGroup) -> dict[str, object]:
    return {
        "group_id": value.group_id,
        "name": value.name,
        "member_count": value.member_count,
    }
