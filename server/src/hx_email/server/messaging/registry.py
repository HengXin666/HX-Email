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
        "QQ 个人号第三方协议存在封号/风控风险,请使用专用小号;"
        "出站经路由层限流与风控熔断, 登录态由 NapCat 本地持久化。"
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
    # 只走消息路由, 没有旧 adapter 的平台 (QQ 官方机器人): 允许用通用接口建实例
    router_only: bool = False


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
            "基于 NapCat (OneBot 11) 独立容器,扫码登录,私聊/群聊收发与群管理,"
            "经消息路由统一 API 与 MCP 对外提供。"
        ),
    ),
    PluginKind(
        key="github",
        display_name="GitHub",
        available=True,
        capabilities=Capabilities(risk_level="official"),
        adapter_factory=None,
        description=(
            "GitHub App (官方 API): webhook 监听 issue/PR 评论, installation token 回帖与建 issue;"
            "用下方「一键创建 GitHub App」接入。"
        ),
    ),
    PluginKind(
        key="qqbot",
        display_name="QQ 频道 (官方机器人)",
        available=True,
        capabilities=Capabilities(
            risk_level="official",
            risk_notice="官方机器人身份, 不涉及个人号; 主动消息按子频道每天限量。",
        ),
        adapter_factory=None,
        description=(
            "QQ 开放平台机器人 (AppID + AppSecret): 子频道消息经 webhook 回调接收, "
            "OpenAPI 回复与推送; 回调地址 /api/v1/router/ingress/qqbot/{实例 id}。"
        ),
        router_only=True,
    ),
    PluginKind(
        key="github_user",
        display_name="GitHub 账号 (gh CLI)",
        available=True,
        capabilities=Capabilities(
            supports_groups=True,
            supports_history=True,
            risk_level="official",
            risk_notice="以真人或专用账号身份行动; token 只在 gh 包装脚本里, 本服务只记 CLI 路径。",
        ),
        adapter_factory=None,
        description=(
            "GitHub 用户账号 (官方 API, 经 gh CLI): 轮询本账号在一个仓库上的 notifications, "
            "以账号身份回帖, review 与 discussion; 用下方「GitHub 账号 (gh CLI)」接入, 仅管理员。"
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


def creation_error(key: str, config: dict[str, str]) -> str | None:
    """通用建实例接口拒绝的原因; ``None`` 表示可以建."""
    kind: PluginKind | None = get_kind(key)
    if kind is None or (kind.adapter_factory is None and not kind.router_only):
        return f"Messaging kind {key} cannot be created here"
    if kind.router_only and not (config.get("app_id") and config.get("app_secret")):
        return f"Messaging kind {key} needs app_id and app_secret"
    return None
