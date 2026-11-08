"""QQ 官方机器人 OpenAPI 的最小客户端: 换取 access_token, 往子频道发消息.

access_token 有效期 7200 秒, 到期前 60 秒内重取会拿到新值; 这里在剩余不足 120 秒时刷新.
统一请求地址 ``https://api.bot.qq.com``, 鉴权头 ``Authorization: QQBot <token>``.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, Protocol

import requests

from hx_email.server.router.provider import SendResult
from hx_email.server.router.providers.impl.qqbot.qqbot_contract import classify
from hx_email.server.router.providers.impl.qqbot.qqbot_events import as_dict

API_BASE: Final[str] = "https://api.bot.qq.com"
TOKEN_URL: Final[str] = "https://api.bot.qq.com/app/getAppAccessToken"
TIMEOUT_SECONDS: Final[float] = 10.0
REFRESH_MARGIN_SECONDS: Final[float] = 120.0


class JsonResponse(Protocol):
    status_code: int

    def json(self) -> object: ...


class HttpPoster(Protocol):
    def post(self, url: str, **kwargs: object) -> JsonResponse: ...


@dataclass(frozen=True)
class BotConfig:
    app_id: str
    app_secret: str
    api_base: str = API_BASE


@dataclass
class Token:
    value: str = ""
    expires_at: float = 0.0


class QQBotClient:
    def __init__(
        self,
        config: BotConfig,
        http: HttpPoster | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config: BotConfig = config
        self.http: HttpPoster = http or requests.Session()  # type: ignore[assignment]
        self.clock: Callable[[], float] = clock
        self.token: Token = Token()
        self.lock: threading.Lock = threading.Lock()

    def access_token(self) -> str:
        with self.lock:
            now: float = self.clock()
            if self.token.value and self.token.expires_at - now > REFRESH_MARGIN_SECONDS:
                return self.token.value
            response: JsonResponse = self.http.post(
                TOKEN_URL,
                json={"appId": self.config.app_id, "clientSecret": self.config.app_secret},
                timeout=TIMEOUT_SECONDS,
            )
            body: dict[str, object] = as_dict(response.json())
            value: str = str(body.get("access_token") or "")
            if not value:
                raise PermissionError(f"getAppAccessToken failed: {body.get('code')}")
            expires: str = str(body.get("expires_in") or "0")
            seconds: float = float(expires) if expires.isdigit() else 0.0
            self.token = Token(value, now + seconds)
            return value

    def forget_token(self) -> None:
        with self.lock:
            self.token = Token()

    def post_channel_message(self, channel_id: str, content: str, reply_to: str) -> SendResult:
        """带 ``reply_to`` 是被动回复 (5 分钟内有效), 不带是主动消息 (按天限量)."""
        try:
            token: str = self.access_token()
        except PermissionError as error:
            return SendResult("failed", error_code="provider_auth", error_message=str(error))
        except requests.RequestException as error:
            return SendResult(
                "retry", retryable=True, error_code="provider_unreachable", error_message=str(error)
            )
        body: dict[str, object] = {"content": content}
        if reply_to:
            body["msg_id"] = reply_to
        try:
            response: JsonResponse = self.http.post(
                f"{self.config.api_base}/channels/{channel_id}/messages",
                json=body,
                headers={"Authorization": f"QQBot {token}", "X-Union-Appid": self.config.app_id},
                timeout=TIMEOUT_SECONDS,
            )
        except requests.Timeout as error:
            return SendResult("unknown", error_code="delivery_unknown", error_message=str(error))
        except requests.RequestException as error:
            return SendResult(
                "retry", retryable=True, error_code="provider_unreachable", error_message=str(error)
            )
        try:
            data: dict[str, object] = as_dict(response.json())
        except ValueError:
            data = {}
        code_value: object = data.get("err_code", data.get("code", 0))
        code: int = int(str(code_value)) if str(code_value).lstrip("-").isdigit() else 0
        if response.status_code < 300 and code == 0 and data.get("id"):
            return SendResult("sent", str(data["id"]))
        audit: str = str(
            as_dict(as_dict(data.get("data")).get("message_audit")).get("audit_id") or ""
        )
        result: SendResult = classify(
            response.status_code, code, str(data.get("message") or ""), audit
        )
        if result.error_code == "provider_auth":
            self.forget_token()
        return result
