"""Provider resolution for the router gateway: one live provider object per instance.

The router layer (``server/router``) holds the building blocks: providers, shaper,
outbox, reader. Nothing in production built those objects before this module, so every
send went straight to ``OneBotAdapter.send_message`` with no rate shaping at all. This
module is the single place that turns a ``messaging_instances`` row into the provider
the gateway calls, and that owns the process-wide shaper.

Memory: providers are cached per instance id and hold no message data; a QQ provider
wraps the adapter the registry already caches, so the gateway adds no second HTTP
session. GitHub shares one provider for every instance (its token cache is keyed by
instance internally).
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from dataclasses import dataclass
from typing import cast

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.messaging.registry import get_adapter
from hx_email.server.messaging.store import get_instance_by_id
from hx_email.server.messaging.types import MessagingAdapter, MessagingInstance
from hx_email.server.router.errors import SessionNotFoundError
from hx_email.server.router.impl.shaper import (
    QQ_CONSERVATIVE,
    QQ_DEFAULT,
    RateProfile,
    Shaper,
    from_provider_limits,
)
from hx_email.server.router.provider import MessagingProvider
from hx_email.server.router.providers.github import GitHubAppProvider
from hx_email.server.router.providers.impl.github.github_auth import (
    GitHubAppConfig,
    open_app_config,
)
from hx_email.server.router.providers.impl.github.github_contract import GITHUB_LIMITS
from hx_email.server.router.providers.impl.qqbot.qqbot_contract import QQBOT_PROFILE
from hx_email.server.router.providers.impl.qqbot.qqbot_http import API_BASE, BotConfig
from hx_email.server.router.providers.impl.qzone.qzone_contract import (
    QZONE_CONSERVATIVE,
    QZONE_DEFAULT,
)
from hx_email.server.router.providers.qq import QQNapCatProvider
from hx_email.server.router.providers.qqbot import QQBotProvider
from hx_email.server.router.providers.qzone import QzoneProvider

LOGGER: logging.Logger = logging.getLogger("hx_email.gateway.providers")
SUPPORTED_KINDS: tuple[str, ...] = ("qq", "github", "qqbot")
QZONE_TYPES: frozenset[str] = frozenset({"qzonepost"})
EMPTY_GITHUB: GitHubAppConfig = GitHubAppConfig("", "", "", "", "")
# 实例配置里逗号分隔的关闭动作名; 默认空, 即声明的动作全部开启, 新动作上线也默认开启
DISABLED_ACTIONS_KEY: str = "disabled_actions"
GITHUB_PROFILE: RateProfile = from_provider_limits("github", GITHUB_LIMITS)

# 整形器是进程级单例: REST, MCP, 前端发送与出站分发共用同一个桶, 否则各走各的桶就等于没限流
SHAPER: Shaper = Shaper()
# QQ 空间与聊天同号不同风控档: 独立的桶, 空间评论再多也不占聊天的配额, 反之亦然
QZONE_SHAPER: Shaper = Shaper(QZONE_DEFAULT)


@dataclass(frozen=True)
class InstanceRow:
    """The few instance fields the gateway needs, read without decrypting twice."""

    id: int
    user_id: int
    kind: str
    name: str
    status: str
    config: dict[str, str]

    def disabled_actions(self) -> frozenset[str]:
        """Actions the owner turned off for this instance; empty means all declared are on."""
        raw: str = self.config.get(DISABLED_ACTIONS_KEY, "")
        return frozenset(name.strip() for name in raw.split(",") if name.strip())


class ProviderHub:
    """Caches one provider per instance and configures its shaper profile once."""

    def __init__(self) -> None:
        self.lock: threading.Lock = threading.Lock()
        self.providers: dict[int, MessagingProvider] = {}
        self.github: GitHubAppProvider | None = None
        self.qzones: dict[int, QzoneProvider] = {}

    def provider_for(self, settings: Settings, instance: InstanceRow) -> MessagingProvider:
        with self.lock:
            cached: MessagingProvider | None = self.providers.get(instance.id)
            if cached is not None:
                return cached
            provider: MessagingProvider = self.build(settings, instance)
            self.providers[instance.id] = provider
            SHAPER.configure(instance.id, profile_for(instance))
            return provider

    def build(self, settings: Settings, instance: InstanceRow) -> MessagingProvider:
        if instance.kind == "qq":
            record: MessagingInstance | None = get_instance_by_id(settings, instance.id)
            if record is None:
                raise SessionNotFoundError(f"instance {instance.id} not found")
            adapter: MessagingAdapter = get_adapter(settings, record)
            profile: str = instance.config.get("rate_profile", "default")
            qq = QQNapCatProvider(
                instance.id,
                adapter,  # type: ignore[arg-type]  # OneBotAdapter implements call_action
                instance.config.get("event_token", ""),
                "conservative" if profile == "conservative" else "default",
            )
            # qq_types 里是路由协议类型的逐字副本, 结构一致, 运行时按鸭子类型调用
            return cast(MessagingProvider, qq)
        if instance.kind == "github":
            if self.github is None:
                self.github = GitHubAppProvider(
                    lambda instance_id: github_config(settings, instance_id)
                )
            return self.github
        if instance.kind == "qqbot":
            config = BotConfig(
                instance.config.get("app_id", ""),
                instance.config.get("app_secret", ""),
                instance.config.get("api_base", "") or API_BASE,
            )
            return cast(MessagingProvider, QQBotProvider(instance.id, config))
        raise SessionNotFoundError(f"platform {instance.kind} has no router provider yet")

    def qzone_for(self, settings: Settings, instance: InstanceRow) -> QzoneProvider:
        """同一实例上的空间通道; 复用聊天通道的 OneBot adapter 取 cookie."""
        with self.lock:
            cached: QzoneProvider | None = self.qzones.get(instance.id)
            if cached is not None:
                return cached
            record: MessagingInstance | None = get_instance_by_id(settings, instance.id)
            if record is None or instance.kind != "qq":
                raise SessionNotFoundError(f"instance {instance.id} has no QQ Zone")
            adapter: MessagingAdapter = get_adapter(settings, record)
            provider = QzoneProvider(
                instance.id,
                adapter,  # type: ignore[arg-type]  # OneBotAdapter implements call_action
                instance.config.get("rate_profile", "default"),
            )
            self.qzones[instance.id] = provider
            QZONE_SHAPER.configure(instance.id, profile_for(instance, "qzonepost"))
            return provider

    def for_session(
        self, settings: Settings, instance: InstanceRow, session_type: str
    ) -> MessagingProvider:
        if session_type in QZONE_TYPES:
            return cast(MessagingProvider, self.qzone_for(settings, instance))
        return self.provider_for(settings, instance)

    def forget(self, instance_id: int) -> None:
        with self.lock:
            self.providers.pop(instance_id, None)
            self.qzones.pop(instance_id, None)
            if self.github is not None:
                self.github.caches.pop(instance_id, None)

    def clear(self) -> None:
        with self.lock:
            self.providers.clear()
            self.qzones.clear()
            self.github = None


HUB: ProviderHub = ProviderHub()


def profile_for(instance: InstanceRow, session_type: str = "") -> RateProfile:
    if instance.kind == "github":
        return GITHUB_PROFILE
    if instance.kind == "qqbot":
        return QQBOT_PROFILE
    conservative: bool = instance.config.get("rate_profile") == "conservative"
    if session_type in QZONE_TYPES:
        return QZONE_CONSERVATIVE if conservative else QZONE_DEFAULT
    if conservative:
        return QQ_CONSERVATIVE
    return QQ_DEFAULT


def shaper_for(session_type: str) -> Shaper:
    """出站按会话类型选桶: 空间评论走空间档, 其余走账号的聊天档."""
    return QZONE_SHAPER if session_type in QZONE_TYPES else SHAPER


def github_config(settings: Settings, instance_id: int) -> GitHubAppConfig:
    """Decrypt one GitHub instance's App config; unreadable config sends nothing."""
    with connect(settings) as connection:
        row: sqlite3.Row | None = connection.execute(
            "SELECT config_encrypted FROM messaging_instances WHERE id = ? AND kind = 'github'",
            (instance_id,),
        ).fetchone()
    sealed: str = str(row["config_encrypted"] or "") if row is not None else ""
    if not sealed:
        return EMPTY_GITHUB
    try:
        return open_app_config(settings, sealed)
    except (ValueError, OSError) as error:
        LOGGER.warning("cannot open GitHub App config for instance %s: %s", instance_id, error)
        return EMPTY_GITHUB


def load_instance(settings: Settings, instance_id: int) -> InstanceRow | None:
    record: MessagingInstance | None = get_instance_by_id(settings, instance_id)
    if record is None:
        return None
    config: dict[str, str] = dict(record.config) if record.kind in ("qq", "qqbot") else {}
    if record.kind == "github":
        app: GitHubAppConfig = github_config(settings, instance_id)
        config = {
            "app_id": app.app_id,
            "app_slug": app.app_slug,
            DISABLED_ACTIONS_KEY: record.config.get(DISABLED_ACTIONS_KEY, ""),
        }
    return InstanceRow(record.id, record.user_id, record.kind, record.name, record.status, config)


def require_owned(settings: Settings, user_id: int, instance_id: int) -> InstanceRow:
    """An instance the caller owns, or ``session_not_found`` (never leak foreign ids)."""
    instance: InstanceRow | None = load_instance(settings, instance_id)
    if instance is None or instance.user_id != user_id:
        raise SessionNotFoundError(f"instance {instance_id} is not yours")
    if instance.kind not in SUPPORTED_KINDS:
        raise SessionNotFoundError(f"platform {instance.kind} has no router provider yet")
    return instance


def owned_instances(settings: Settings, user_id: int) -> list[InstanceRow]:
    with connect(settings) as connection:
        rows: list[sqlite3.Row] = connection.execute(
            "SELECT id FROM messaging_instances WHERE user_id = ? ORDER BY id", (user_id,)
        ).fetchall()
    out: list[InstanceRow] = []
    for row in rows:
        instance: InstanceRow | None = load_instance(settings, int(row["id"]))
        if instance is not None and instance.kind in SUPPORTED_KINDS:
            out.append(instance)
    return out
