"""Thin ``MessagingAdapter`` so the web console can open a GitHub App instance.

GitHub instances are created by the App manifest flow and never had an adapter, so
every ``/api/v1/messaging/instances/{id}/...`` call answered 400 "not available yet".
Conversations, messages and sending for every platform now go through the gateway;
this adapter only answers the instance-level questions (status, login, capabilities).
"""

from __future__ import annotations

from hx_email.config import Settings
from hx_email.server.gateway.providers import github_config
from hx_email.server.messaging.types import (
    AdapterStatus,
    LoginState,
    LoginTicket,
    MessageTarget,
    MessagingAdapter,
    MessagingConversation,
    MessagingError,
    MessagingInstance,
    MessagingMessage,
)
from hx_email.server.router.providers.github import GITHUB_CAPABILITIES
from hx_email.server.router.providers.impl.github.github_auth import GitHubAppConfig


class GitHubAppAdapter(MessagingAdapter):
    kind: str = "github"
    display_name: str = "GitHub"
    capabilities = GITHUB_CAPABILITIES

    def __init__(self, settings: Settings, instance: MessagingInstance) -> None:
        self.settings: Settings = settings
        self.instance: MessagingInstance = instance

    def config(self) -> GitHubAppConfig:
        return github_config(self.settings, self.instance.id)

    def start(self) -> None:
        if not self.config().app_id:
            raise MessagingError("GitHub App 尚未创建, 请先在设置页一键创建并安装")

    def stop(self) -> None:
        return None

    def status(self) -> AdapterStatus:
        config: GitHubAppConfig = self.config()
        if not config.app_id:
            return AdapterStatus(state="stopped", message="GitHub App 尚未创建")
        return AdapterStatus(
            state="online",
            account_id=config.app_id,
            account_name=config.bot_login,
            message="GitHub App 已配置, 事件经 webhook 推送",
        )

    def create_login(self) -> LoginTicket:
        return LoginTicket(
            mode="github_app",
            instructions="GitHub 使用 App 身份, 无需扫码; 在设置页一键创建 App 并安装到仓库即可",
        )

    def check_login(self) -> LoginState:
        current: AdapterStatus = self.status()
        return LoginState(
            logged_in=current.state == "online",
            account_id=current.account_id,
            account_name=current.account_name,
            message=current.message,
        )

    def send_message(self, target: MessageTarget, text: str) -> str:
        raise MessagingError("GitHub 发送走路由网关 /api/v1/router/messages")

    def list_conversations(self) -> list[MessagingConversation]:
        return []

    def list_messages(self, conversation_id: str, limit: int = 50) -> list[MessagingMessage]:
        return []
