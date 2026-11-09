"""Shared helpers: instance resolution and dataclass -> dict serialization."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from hx_email.config import Settings
from hx_email.server.gateway.impl.github_adapter import GitHubAppAdapter
from hx_email.server.messaging.registry import get_adapter, get_kind
from hx_email.server.messaging.store import get_instance
from hx_email.server.messaging.types import (
    AdapterStatus,
    Capabilities,
    LoginState,
    LoginTicket,
    MessagingAdapter,
    MessagingConversation,
    MessagingGroup,
    MessagingInstance,
    MessagingMessage,
)
from hx_email.server.router.providers.impl.github.github_auth import SECRET_CONFIG_KEYS

# GitHub 私钥与 webhook secret 和 QQ 的 event_token 一样只写不读
MASKED_CONFIG_KEYS: frozenset[str] = frozenset({"event_token", "app_secret"}) | SECRET_CONFIG_KEYS
# 没有会话型 adapter, 但实例详情可直接由目录声明回答的平台
CATALOG_DETAIL_KINDS: frozenset[str] = frozenset({"github_user"})


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
        adapter: MessagingAdapter = adapter_for(settings, instance)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    return instance, adapter


def adapter_for(settings: Settings, instance: MessagingInstance) -> MessagingAdapter:
    """GitHub App instances get a status-only adapter; the rest come from the registry."""
    if instance.kind == "github":
        return GitHubAppAdapter(settings, instance)
    return get_adapter(settings, instance)


def safe_adapter(settings: Settings, instance: MessagingInstance) -> MessagingAdapter | None:
    try:
        return adapter_for(settings, instance)
    except ValueError:
        return None


# github_user 只经 gh CLI 轮询与路由网关工作, 没有 adapter; 详情的能力取目录声明, 配置照常脱敏
# (与 routes.py 的拆分同一条决策, 锚点在 routes.py)
def instance_detail(settings: Settings, instance: MessagingInstance) -> dict[str, Any]:
    """Serialize one instance for ``GET /messaging/instances/{id}``."""
    if instance.kind in CATALOG_DETAIL_KINDS:
        kind = get_kind(instance.kind)
        result: dict[str, Any] = instance_dict(instance)
        if kind is not None:
            result["capabilities"] = capabilities_dict(kind.capabilities)
        return result
    try:
        adapter: MessagingAdapter = adapter_for(settings, instance)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    return instance_dict(instance, adapter)


def capabilities_dict(capability: Capabilities) -> dict[str, Any]:
    return {
        "supports_qr_login": capability.supports_qr_login,
        "supports_groups": capability.supports_groups,
        "supports_history": capability.supports_history,
        "risk_level": capability.risk_level,
        "risk_notice": capability.risk_notice,
    }


def instance_dict(
    instance: MessagingInstance,
    adapter: MessagingAdapter | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": instance.id,
        "kind": instance.kind,
        "name": instance.name,
        "status": instance.status,
        "config": public_config(instance.config),
        "created_at": instance.created_at,
        "updated_at": instance.updated_at,
    }
    if adapter is not None:
        result["capabilities"] = capabilities_dict(adapter.capabilities)
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


# GitHub App 一键创建与秘密字段只写不读的决策
# 决策记录: .agents/notes/implemented/feature/2026-11-03-github-app-manifest-flow.md
def public_config(config: dict[str, str]) -> dict[str, str]:
    """Mask secrets before returning instance config to the browser."""
    return {
        key: ("***" if key in MASKED_CONFIG_KEYS and value else value)
        for key, value in config.items()
    }
