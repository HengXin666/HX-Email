"""Unified messaging abstraction shared by all platform adapters.

QQ/WeChat/Telegram/Discord 适配器都实现 :class:`MessagingAdapter`,
业务层与 API 层只依赖本模块中的抽象类型。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal

ChatType = Literal["private", "group", "channel"]
AdapterState = Literal["stopped", "connecting", "online", "error"]
RiskLevel = Literal["official", "third_party"]


@dataclass(frozen=True)
class MessagingInstance:
    """A user-scoped connection to one messaging platform (e.g. one QQ account)."""

    id: int
    user_id: int
    kind: str
    name: str
    status: str
    config: dict[str, str]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class Capabilities:
    """能力位:声明平台适配器支持的操作范围。"""

    supports_qr_login: bool = False
    supports_groups: bool = False
    supports_history: bool = False
    risk_level: RiskLevel = "official"
    risk_notice: str = ""


@dataclass(frozen=True)
class MessageTarget:
    chat_id: str
    chat_type: ChatType = "private"


@dataclass(frozen=True)
class MessagingMessage:
    direction: str
    chat_id: str
    chat_type: ChatType
    sender_id: str = ""
    sender_name: str = ""
    text: str = ""
    message_id: str = ""
    raw: dict[str, object] = field(default_factory=dict)
    created_at: str = ""


@dataclass(frozen=True)
class MessagingConversation:
    chat_id: str
    chat_type: ChatType
    name: str = ""
    raw: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class MessagingGroup:
    group_id: str
    name: str = ""
    member_count: int = 0
    raw: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class AdapterStatus:
    state: AdapterState = "stopped"
    account_id: str = ""
    account_name: str = ""
    message: str = ""


@dataclass(frozen=True)
class LoginTicket:
    mode: str
    url: str = ""
    qr_image_url: str = ""
    instructions: str = ""
    expires_in: int = 0


@dataclass(frozen=True)
class LoginState:
    logged_in: bool
    account_id: str = ""
    account_name: str = ""
    message: str = ""


@dataclass(frozen=True)
class GroupAction:
    action: str
    member_id: str = ""
    duration_seconds: int = 0


class MessagingError(Exception):
    """Platform adapter failure (offline, permission, risk control)."""


class MessagingAdapter(ABC):
    """统一平台适配器接口。"""

    kind: str = "base"
    display_name: str = "Base"
    capabilities: Capabilities = Capabilities()

    @abstractmethod
    def start(self) -> None:
        """建立连接或完成连通性探测。"""

    @abstractmethod
    def stop(self) -> None:
        """停止连接/清理资源。"""

    @abstractmethod
    def status(self) -> AdapterStatus:
        """返回当前连接状态与登录账号信息。"""

    @abstractmethod
    def create_login(self) -> LoginTicket:
        """生成扫码/授权引导(QQ 为 NapCat WebUI,TG/Discord 为 token 输入)。"""

    @abstractmethod
    def check_login(self) -> LoginState:
        """查询登录态。"""

    @abstractmethod
    def send_message(self, target: MessageTarget, text: str) -> str:
        """发送文本消息,返回平台消息 ID。"""

    @abstractmethod
    def list_conversations(self) -> list[MessagingConversation]:
        """列出私聊/群聊会话。"""

    @abstractmethod
    def list_messages(self, conversation_id: str, limit: int = 50) -> list[MessagingMessage]:
        """拉取某个会话的历史消息(能力位 supports_history)。"""

    def list_groups(self) -> list[MessagingGroup]:
        raise MessagingError(f"{self.display_name} 不支持群组能力")

    def group_action(self, group_id: str, action: GroupAction) -> bool:
        raise MessagingError(f"{self.display_name} 不支持群组管理操作")
