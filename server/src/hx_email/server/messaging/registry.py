"""Plugin catalog and runtime adapter registry for messaging platforms."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass

from hx_email.config import Settings
from hx_email.server.messaging.onebot import OneBotAdapter
from hx_email.server.messaging.types import (
    Capabilities,
    MessagingAdapter,
    MessagingInstance,
)

QQ_CAPABILITIES: Capabilities = Capabilities(
    supports_qr_login=True,
    supports_groups=True,
    supports_history=True,
    risk_level="third_party",
    risk_notice=(
        "QQ 个人号第三方协议存在封号/风控风险,请使用专用小号并控制消息频率;"
        "登录态由 lagrange-python 本地持久化。"
    ),
)


@dataclass(frozen=True)
class PluginKind:
    key: str
    display_name: str
    available: bool
    capabilities: Capabilities
    adapter_factory: Callable[[Settings, MessagingInstance], MessagingAdapter] | None
    description: str = ""


def create_qq_adapter(settings: Settings, instance: MessagingInstance) -> MessagingAdapter:
    return OneBotAdapter(settings, instance)


PLUGIN_KINDS: tuple[PluginKind, ...] = (
    PluginKind(
        key="qq",
        display_name="QQ",
        available=True,
        capabilities=QQ_CAPABILITIES,
        adapter_factory=create_qq_adapter,
        description=(
            "基于官方 lagrange-python (NTQQ 协议),进程内运行,支持扫码登录、私聊/群聊收发与群管理。"
        ),
    ),
    PluginKind(
        key="wechat",
        display_name="微信",
        available=False,
        capabilities=Capabilities(risk_notice="个人微信自动化封号风险高,推荐企业微信官方 API。"),
        adapter_factory=None,
        description="规划中:企业微信官方 API(低风险);个人微信方案需显著风险提示。",
    ),
    PluginKind(
        key="telegram",
        display_name="Telegram",
        available=False,
        capabilities=Capabilities(risk_level="official"),
        adapter_factory=None,
        description="规划中:官方 Bot API(python-telegram-bot),机器人账号零封禁风险。",
    ),
    PluginKind(
        key="discord",
        display_name="Discord",
        available=False,
        capabilities=Capabilities(risk_level="official"),
        adapter_factory=None,
        description="规划中:官方 Bot API(discord.py)。",
    ),
)

_RUNTIME: dict[int, MessagingAdapter] = {}


def catalog() -> list[dict[str, object]]:
    """Return public metadata for the messaging plugin catalog."""
    return [
        {
            "key": kind.key,
            "display_name": kind.display_name,
            "available": kind.available,
            "description": kind.description,
            "capabilities": {
                "supports_qr_login": kind.capabilities.supports_qr_login,
                "supports_groups": kind.capabilities.supports_groups,
                "supports_history": kind.capabilities.supports_history,
                "risk_level": kind.capabilities.risk_level,
                "risk_notice": kind.capabilities.risk_notice,
            },
        }
        for kind in PLUGIN_KINDS
    ]


def get_kind(key: str) -> PluginKind | None:
    for kind in PLUGIN_KINDS:
        if kind.key == key:
            return kind
    return None


def get_adapter(
    settings: Settings,
    instance: MessagingInstance,
    force_new: bool = False,
) -> MessagingAdapter:
    """Return a cached adapter for the instance, creating it on first use."""
    cached: MessagingAdapter | None = _RUNTIME.get(instance.id)
    if cached is not None and not force_new:
        return cached
    kind: PluginKind | None = get_kind(instance.kind)
    if kind is None or kind.adapter_factory is None:
        raise ValueError(f"Messaging kind '{instance.kind}' is not available yet")
    adapter: MessagingAdapter = kind.adapter_factory(settings, instance)
    _RUNTIME[instance.id] = adapter
    return adapter


def drop_adapter(instance_id: int) -> None:
    cached: MessagingAdapter | None = _RUNTIME.pop(instance_id, None)
    if cached is not None:
        with suppress(Exception):
            cached.stop()


def clear_runtime() -> None:
    """Drop all cached adapters (used by tests and instance deletion flows)."""
    for instance_id in list(_RUNTIME):
        drop_adapter(instance_id)
