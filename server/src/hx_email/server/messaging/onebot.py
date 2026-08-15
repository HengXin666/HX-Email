"""QQ adapter speaking the OneBot v11 HTTP API (NapCat / Lagrange)."""

from __future__ import annotations

from typing import Any

import requests
from hx_email.config import Settings
from hx_email.server.messaging.impl.config import config_float, config_str
from hx_email.server.messaging.impl.events import onebot_message_to_unified
from hx_email.server.messaging.store import update_instance_status
from hx_email.server.messaging.types import (
    AdapterState,
    AdapterStatus,
    Capabilities,
    GroupAction,
    LoginState,
    LoginTicket,
    MessageTarget,
    MessagingAdapter,
    MessagingConversation,
    MessagingError,
    MessagingGroup,
    MessagingInstance,
    MessagingMessage,
)

CAPABILITIES: Capabilities = Capabilities(
    supports_qr_login=True,
    supports_groups=True,
    supports_history=True,
    risk_level="third_party",
    risk_notice="QQ 个人号第三方协议存在封号/风控风险,请使用专用小号并控制频率。",
)

DEFAULT_TIMEOUT: float = 10.0
MAX_MESSAGE_LIMIT: int = 100


class OneBotAdapter(MessagingAdapter):
    kind: str = "qq"
    display_name: str = "QQ (OneBot 11)"
    capabilities: Capabilities = CAPABILITIES

    def __init__(self, settings: Settings, instance: MessagingInstance) -> None:
        self._settings: Settings = settings
        self._instance: MessagingInstance = instance
        self._config: dict[str, str] = instance.config
        self._session: requests.Session = requests.Session()
        base_url: str = config_str(self._config, "api_base_url").rstrip("/")
        self._base_url: str = base_url
        self._timeout: float = config_float(self._config, "timeout_seconds", DEFAULT_TIMEOUT)

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        token: str = config_str(self._config, "access_token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _call(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self._base_url:
            raise MessagingError("未配置 api_base_url (NapCat HTTP 地址)")
        try:
            response: requests.Response = self._session.post(
                f"{self._base_url}/{action}",
                json=params,
                headers=self._headers(),
                timeout=self._timeout,
            )
            response.raise_for_status()
        except requests.RequestException as error:
            raise MessagingError(f"OneBot 请求失败: {error}") from error
        payload: Any = response.json()
        if not isinstance(payload, dict):
            raise MessagingError("OneBot 响应格式无效")
        if (
            payload.get("status") not in {"ok", "async", None}
            or int(payload.get("retcode", 0)) != 0
        ):
            detail: str = str(payload.get("msg") or payload.get("wording") or "未知错误")
            raise MessagingError(f"OneBot 调用 {action} 失败: {detail}")
        data: Any = payload.get("data")
        return data if isinstance(data, dict) else {}

    def start(self) -> None:
        status: AdapterStatus = self.status()
        if status.state == "error":
            raise MessagingError(status.message)
        update_instance_status(self._settings, self._instance.id, "online")

    def stop(self) -> None:
        update_instance_status(self._settings, self._instance.id, "stopped")

    def status(self) -> AdapterStatus:
        try:
            info: dict[str, Any] = self._call("get_login_info", {})
        except MessagingError as error:
            update_instance_status(self._settings, self._instance.id, "error")
            return AdapterStatus(state="error", message=str(error))
        user_id: str = str(info.get("user_id", ""))
        nickname: str = str(info.get("nickname", ""))
        state: AdapterState = "online" if user_id else "stopped"
        if state == "online":
            update_instance_status(self._settings, self._instance.id, "online")
        return AdapterStatus(
            state=state,
            account_id=user_id,
            account_name=nickname,
            message="QQ 已登录" if user_id else "QQ 未登录",
        )

    def create_login(self) -> LoginTicket:
        webui_url: str = config_str(self._config, "webui_url")
        if webui_url:
            return LoginTicket(
                mode="redirect",
                url=webui_url,
                instructions=(
                    "在打开的 NapCat WebUI 中扫码登录;登录态由 NapCat 本地持久化,无需重复登录。"
                ),
            )
        return LoginTicket(
            mode="manual",
            instructions=(
                "未配置 NapCat WebUI 地址:请先在本机启动 NapCat "
                "并完成扫码登录,再填写 api_base_url。"
            ),
        )

    def check_login(self) -> LoginState:
        status: AdapterStatus = self.status()
        return LoginState(
            logged_in=status.state == "online",
            account_id=status.account_id,
            account_name=status.account_name,
            message=status.message,
        )

    def send_message(self, target: MessageTarget, text: str) -> str:
        if target.chat_type == "group":
            result: dict[str, Any] = self._call(
                "send_group_msg", {"group_id": int(target.chat_id), "message": text}
            )
        else:
            result = self._call(
                "send_private_msg", {"user_id": int(target.chat_id), "message": text}
            )
        return str(result.get("message_id", ""))

    def list_conversations(self) -> list[MessagingConversation]:
        conversations: list[MessagingConversation] = []
        friends: dict[str, Any] = self._call("get_friend_list", {})
        for item in friends.get("data", []):
            conversations.append(
                MessagingConversation(
                    chat_id=str(item.get("user_id", "")),
                    chat_type="private",
                    name=str(item.get("nickname", "")),
                    raw=item,
                )
            )
        groups: dict[str, Any] = self._call("get_group_list", {})
        for item in groups.get("data", []):
            conversations.append(
                MessagingConversation(
                    chat_id=str(item.get("group_id", "")),
                    chat_type="group",
                    name=str(item.get("group_name", "")),
                    raw=item,
                )
            )
        return conversations

    def list_messages(self, conversation_id: str, limit: int = 50) -> list[MessagingMessage]:
        safe_limit: int = max(1, min(limit, MAX_MESSAGE_LIMIT))
        messages: list[MessagingMessage] = []
        try:
            data: dict[str, Any] = self._call(
                "get_group_msg_history", {"group_id": int(conversation_id), "count": safe_limit}
            )
        except MessagingError:
            data = {}
        for item in data.get("data", []):
            messages.append(onebot_message_to_unified(item, direction="inbound"))
        if messages:
            return messages
        try:
            friend: dict[str, Any] = self._call(
                "get_friend_msg_history", {"user_id": int(conversation_id), "count": safe_limit}
            )
        except MessagingError:
            return []
        for item in friend.get("data", []):
            messages.append(onebot_message_to_unified(item, direction="inbound"))
        return messages

    def list_groups(self) -> list[MessagingGroup]:
        groups: dict[str, Any] = self._call("get_group_list", {})
        return [
            MessagingGroup(
                group_id=str(item.get("group_id", "")),
                name=str(item.get("group_name", "")),
                member_count=int(item.get("member_count", 0) or 0),
                raw=item,
            )
            for item in groups.get("data", [])
        ]

    def group_action(self, group_id: str, action: GroupAction) -> bool:
        group_int: int = int(group_id)
        if action.action == "kick":
            self._call(
                "set_group_kick",
                {
                    "group_id": group_int,
                    "user_id": int(action.member_id),
                    "reject_add_request": False,
                },
            )
        elif action.action == "ban":
            self._call(
                "set_group_ban",
                {
                    "group_id": group_int,
                    "user_id": int(action.member_id),
                    "duration": action.duration_seconds,
                },
            )
        elif action.action == "unban":
            self._call(
                "set_group_ban",
                {"group_id": group_int, "user_id": int(action.member_id), "duration": 0},
            )
        elif action.action == "mute_all":
            self._call("set_group_whole_ban", {"group_id": group_int, "enable": True})
        elif action.action == "unmute_all":
            self._call("set_group_whole_ban", {"group_id": group_int, "enable": False})
        elif action.action == "leave":
            self._call("set_group_leave", {"group_id": group_int})
        else:
            raise MessagingError(f"不支持的群操作: {action.action}")
        return True
