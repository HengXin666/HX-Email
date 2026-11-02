"""Minimal provider contract of the router layer (ADR 0005 section 4, spec 9.5).

A platform joins the router by implementing :class:`MessagingProvider` and registering it.
Rate shaping, idempotency, retries, subscriptions and cursors belong to the router, never
to a provider.

How the existing adapter fits in:
- The QQ provider is a thin wrapper around the existing ``OneBotAdapter`` instance. It
  reuses ``list_conversations`` for ``list_sessions`` and the existing segment flattening
  for ``parse_event``, but rebuilds session addresses with spec section 2.
- ``MessagingAdapter`` keeps every signature unchanged. ``send`` does not wrap
  ``send_message`` (it returns a bare id and loses retcode and timeout detail); per spec
  9.5 it calls the adapter's structured ``call_action`` and maps the result to
  :class:`SendResult`.
- The GitHub provider is new code and returns :class:`SendResult` directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal, Protocol

DeliveryMode = Literal["push", "pull"]
SendStatus = Literal["sent", "unknown", "failed", "retry"]

SEND_STATUSES: Final[frozenset[str]] = frozenset({"sent", "unknown", "failed", "retry"})


@dataclass(frozen=True)
class ProviderLimits:
    """Limits a provider advertises; values for QQ live in the shaper profiles."""

    per_session_interval_seconds: float
    per_session_per_minute: int
    per_account_per_minute: int
    per_account_per_hour: int
    burst: int
    daily_cap: int
    max_text_length: int


@dataclass(frozen=True)
class SessionRef:
    """One listenable or sendable session; ``address`` is the spec section 2 string."""

    address: str
    platform: str
    instance_id: int
    session_type: str
    session_id: str
    title: str


@dataclass(frozen=True)
class OutboundPayload:
    """What the outbox hands a provider; ``delivery_id`` is ``d_<router_outbox.id>``."""

    delivery_id: str
    text: str
    reply_to: str
    title: str


@dataclass(frozen=True)
class SendResult:
    """Structured send outcome that drives outbox state.

    ``sent`` succeeded, ``unknown`` means the platform may have received it (timeout),
    ``failed`` is terminal, ``retry`` is retryable. ``risk_signal`` feeds the breaker.
    """

    status: SendStatus
    platform_message_id: str = ""
    retryable: bool = False
    risk_signal: bool = False
    error_code: str = ""
    error_message: str = ""
    retry_after_seconds: int = 0

    def __post_init__(self) -> None:
        if self.status not in SEND_STATUSES:
            raise ValueError(f"unknown send status: {self.status}")
        if self.status == "sent" and not self.platform_message_id:
            raise ValueError("a sent result needs platform_message_id")
        if self.retry_after_seconds < 0:
            raise ValueError("retry_after_seconds must be >= 0")


class MessagingProvider(Protocol):
    """Contract every platform provider implements."""

    platform: str
    delivery_mode: DeliveryMode
    limits: ProviderLimits

    # 路由层拥有订阅, cursor, 整形与幂等, provider 只做平台连接
    # 决策记录: .agents/notes/implemented/feature/2026-11-02-messaging-router-gateway.md
    def list_sessions(self, instance_id: int) -> list[SessionRef]: ...

    def send(self, session: SessionRef, payload: OutboundPayload) -> SendResult: ...

    def parse_event(
        self, instance_id: int, headers: dict[str, str], body: bytes
    ) -> list[dict[str, object]]:
        """Return envelope dicts for ``envelope.validate_inbound``; ``[]`` for non-messages."""
        ...

    def verify_event(self, instance_id: int, headers: dict[str, str], body: bytes) -> bool: ...
