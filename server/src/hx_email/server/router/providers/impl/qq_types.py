"""Provider contract types used by the QQ provider.

The router-level `MessagingProvider` protocol is defined by ADR 0005 section 4 and is
being written in `server/router/provider.py` by another task. Until it lands, this file
carries a local copy of that contract plus the QQ-only types from
`docs/providers/qq-napcat.md` section 7.1, so the QQ provider can be tested on its own.
Once `server/router/provider.py` exists, the shared names here are replaced by imports.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal, Protocol

DeliveryMode = Literal["push", "pull"]
SendStatus = Literal["sent", "unknown", "failed", "retry"]
QQSessionType = Literal["private", "group", "temp"]
LoginPhase = Literal["stopped", "starting", "awaiting_scan", "online", "offline", "frozen", "error"]
Transport = Literal["ok", "timeout", "connect_error", "http_error"]

QQ_SESSION_TYPES: tuple[QQSessionType, ...] = ("private", "group", "temp")


@dataclass(frozen=True)
class ProviderLimits:
    """ADR 0005 section 4."""

    per_session_interval_seconds: float
    per_session_per_minute: int
    per_account_per_minute: int
    per_account_per_hour: int
    burst: int
    daily_cap: int
    max_text_length: int


@dataclass(frozen=True)
class SessionRef:
    """ADR 0005 section 4."""

    address: str
    platform: str
    instance_id: int
    session_type: str
    session_id: str
    title: str


@dataclass(frozen=True)
class OutboundPayload:
    """ADR 0005 section 4."""

    delivery_id: str
    text: str
    reply_to: str
    title: str


@dataclass(frozen=True)
class SendResult:
    """ADR 0005 section 4, fields explained in messaging-router 9.5."""

    status: SendStatus
    platform_message_id: str
    retryable: bool
    risk_signal: bool
    error_code: str
    error_message: str
    retry_after_seconds: int


@dataclass(frozen=True)
class QQSession:
    """qq-napcat 7.1: parsed form of `qq:<instance_id>:<session_type>:<peer>`."""

    address: str
    instance_id: int
    session_type: QQSessionType
    peer_user_id: str = ""
    peer_group_id: str = ""


@dataclass(frozen=True)
class OneBotCallResult:
    """qq-napcat 7.1, returned by `OneBotAdapter.call_action`.

    `data` is typed `object` because OneBot list actions (get_friend_list,
    get_group_list) return an array in `data`, not a mapping.
    """

    transport: Transport
    http_status: int = 0
    retcode: int = 0
    wording: str = ""
    data: object = field(default_factory=dict)


class OneBotCaller(Protocol):
    """Structured OneBot action interface (messaging-router 9.5).

    `OneBotAdapter.call_action` is planned but not yet in `onebot.py`; any object with
    this method can back the provider, which keeps tests free of HTTP.
    """

    def call_action(self, action: str, params: Mapping[str, object]) -> OneBotCallResult: ...


class MessagingProvider(Protocol):
    """ADR 0005 section 4 provider protocol (local copy until provider.py lands)."""

    platform: str
    delivery_mode: DeliveryMode
    limits: ProviderLimits

    def list_sessions(self, instance_id: int) -> list[SessionRef]: ...

    def send(self, session: SessionRef, payload: OutboundPayload) -> SendResult: ...

    def parse_event(
        self, instance_id: int, headers: dict[str, str], body: bytes
    ) -> list[dict[str, object]]: ...

    def verify_event(self, instance_id: int, headers: dict[str, str], body: bytes) -> bool: ...


class QQProviderError(Exception):
    """Base error carrying a router error code from messaging-router 9.4."""

    error_code: str = "provider_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message: str = message


class InvalidSessionError(QQProviderError):
    """Address does not parse per messaging-router section 2."""

    error_code: str = "session_not_found"


class SessionMismatchError(QQProviderError):
    """Address belongs to another instance; no cross-account switching (sticky)."""

    error_code: str = "session_not_found"


class SessionNotSendableError(QQProviderError):
    """Target was never returned by list_sessions (cold-start protection)."""

    error_code: str = "session_not_sendable"


class RiskSignalError(QQProviderError):
    """OneBot reported a rate-limit or risk-control failure; router should trip breaker."""

    error_code: str = "risk_control"

    def __init__(self, message: str, result: SendResult) -> None:
        super().__init__(message)
        self.result: SendResult = result
