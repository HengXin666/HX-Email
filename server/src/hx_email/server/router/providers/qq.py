"""QQ provider for the messaging router, backed by NapCat over OneBot 11.

Spec: docs/providers/qq-napcat.md sections 4, 5 and 7, docs/messaging-router.md
sections 2, 3.3 and 9. The provider only parses, classifies and calls OneBot;
token bucket, idempotency, outbox and circuit breaker belong to the router (qq-napcat 7.2).
"""

from __future__ import annotations

import hmac
import json
from collections.abc import Mapping

from hx_email.server.router.providers.impl.qq_events import (
    as_mapping,
    parse_session_address,
    session_address,
    to_envelope,
)
from hx_email.server.router.providers.impl.qq_limits import (
    AUTH_HTTP_STATUSES,
    AUTH_RETCODES,
    HTTP_429_RETRY_AFTER_SECONDS,
    MUTED_KEYWORDS,
    RATE_LIMIT_HTTP_STATUS,
    RETCODE_BAD_REQUEST,
    RETCODE_NOT_FOUND,
    RETRYABLE_HTTP_STATUSES,
    RISK_KEYWORDS,
    TARGET_GONE_KEYWORDS,
    RateProfileName,
    provider_limits,
)
from hx_email.server.router.providers.impl.qq_types import (
    DeliveryMode,
    LoginPhase,
    OneBotCaller,
    OneBotCallResult,
    OutboundPayload,
    ProviderLimits,
    QQProviderError,
    QQSession,
    QQSessionType,
    RiskSignalError,
    SendResult,
    SendStatus,
    SessionMismatchError,
    SessionNotSendableError,
    SessionRef,
)

EVENT_TOKEN_HEADER: str = "x-messaging-token"


def has_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    """Case-insensitive substring match."""
    lowered: str = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def make_result(
    status: SendStatus,
    code: str = "",
    message: str = "",
    *,
    message_id: str = "",
    risk: bool = False,
    retry_after: int = 0,
) -> SendResult:
    """Build a SendResult; `retryable` is true exactly when status is "retry"."""
    return SendResult(status, message_id, status == "retry", risk, code, message, retry_after)


def classify_call_result(result: OneBotCallResult) -> SendResult:
    """Map an OneBot call outcome to SendResult per qq-napcat 5.5 and 7.2."""
    wording: str = result.wording
    if result.transport == "ok" and result.retcode == 0:
        message_id: str = str(as_mapping(result.data).get("message_id", ""))
        return make_result("sent", message_id=message_id)
    if has_keyword(wording, RISK_KEYWORDS):
        return make_result("failed", "risk_control", wording, risk=True)
    if result.transport == "timeout":
        return make_result("unknown", "delivery_unknown", "onebot request timed out")
    if result.transport == "connect_error":
        return make_result("retry", "provider_unreachable", "onebot connection refused")
    if result.transport == "http_error":
        status_code: int = result.http_status
        if status_code == RATE_LIMIT_HTTP_STATUS:
            return make_result(
                "retry",
                "rate_limited_by_platform",
                "onebot http 429",
                risk=True,
                retry_after=HTTP_429_RETRY_AFTER_SECONDS,
            )
        if status_code in RETRYABLE_HTTP_STATUSES:
            return make_result("retry", "provider_unavailable", f"onebot http {status_code}")
        if status_code in AUTH_HTTP_STATUSES:
            return make_result("failed", "provider_auth", f"onebot http {status_code}")
        return make_result("failed", "provider_error", f"onebot http {status_code}")
    if result.retcode in AUTH_RETCODES:
        return make_result("failed", "provider_auth", f"retcode {result.retcode}")
    if result.retcode == RETCODE_BAD_REQUEST:
        return make_result("failed", "bad_request", wording or "retcode 1400")
    if result.retcode == RETCODE_NOT_FOUND:
        return make_result("failed", "action_not_found", wording or "retcode 1404")
    if has_keyword(wording, MUTED_KEYWORDS):
        return make_result("failed", "muted", wording)
    if has_keyword(wording, TARGET_GONE_KEYWORDS):
        return make_result("failed", "target_unavailable", wording)
    return make_result("failed", "provider_error", wording or f"retcode {result.retcode}")


def build_send_params(session: QQSession, text: str, reply_to: str) -> dict[str, object]:
    """OneBot `send_msg` params with a segment array, never a raw CQ string (qq-napcat 5.3)."""
    segments: list[dict[str, object]] = []
    if reply_to:
        segments.append({"type": "reply", "data": {"id": reply_to}})
    segments.append({"type": "text", "data": {"text": text}})
    params: dict[str, object] = {"message": segments, "auto_escape": False}
    if session.session_type == "group":
        params["message_type"] = "group"
        params["group_id"] = int(session.peer_group_id)
        return params
    params["message_type"] = "private"
    params["user_id"] = int(session.peer_user_id)
    if session.session_type == "temp":
        params["group_id"] = int(session.peer_group_id)
    return params


def list_items(result: OneBotCallResult) -> list[Mapping[str, object]]:
    """Items of an OneBot list action; accepts `data` as a list or `{"data": [...]}`."""
    if result.transport != "ok" or result.retcode != 0:
        raise QQProviderError(f"onebot list failed: {result.transport} {result.retcode}")
    data: object = result.data
    if isinstance(data, Mapping):
        data = data.get("data", [])
    items: list[object] = list(data) if isinstance(data, list) else []
    return [as_mapping(item) for item in items]


class QQNapCatProvider:
    """MessagingProvider for one QQ instance (one NapCat container, one QQ account)."""

    platform: str = "qq"
    delivery_mode: DeliveryMode = "push"

    def __init__(
        self,
        instance_id: int,
        caller: OneBotCaller,
        event_token: str,
        rate_profile: RateProfileName = "default",
    ) -> None:
        self.instance_id: int = instance_id
        self.caller: OneBotCaller = caller
        self.event_token: str = event_token
        self.limits: ProviderLimits = provider_limits(rate_profile)
        self.phase: LoginPhase = "stopped"
        self.known_sessions: set[str] = set()

    def session_address(self, session_type: QQSessionType, peer: str) -> str:
        """Address of a session on this instance."""
        return session_address(self.instance_id, session_type, peer)

    def resolve_session(self, address: str) -> QQSession:
        """Parse and enforce session stickiness: the address must name this instance."""
        session: QQSession = parse_session_address(address)
        if session.instance_id != self.instance_id:
            raise SessionMismatchError(
                f"session {address} belongs to instance {session.instance_id}, "
                f"not {self.instance_id}"
            )
        return session

    def require_instance(self, instance_id: int) -> None:
        """Reject calls targeting another instance."""
        if instance_id != self.instance_id:
            raise SessionMismatchError(f"provider serves instance {self.instance_id} only")

    # 账号到实例一对一, session 地址里带 instance_id, 不做跨号切换发送
    # 决策记录: .agents/notes/implemented/feature/2026-11-02-messaging-router-gateway.md
    def list_sessions(self, instance_id: int) -> list[SessionRef]:
        """Friends and groups from OneBot; also refreshes the cold-start allow list."""
        self.require_instance(instance_id)
        sessions: list[SessionRef] = []
        for friend in list_items(self.caller.call_action("get_friend_list", {})):
            peer: str = str(friend.get("user_id", ""))
            title: str = str(friend.get("remark") or friend.get("nickname") or peer)
            sessions.append(self.session_ref("private", peer, title))
        for group in list_items(self.caller.call_action("get_group_list", {})):
            gid: str = str(group.get("group_id", ""))
            sessions.append(self.session_ref("group", gid, str(group.get("group_name") or gid)))
        temp_sessions: set[str] = {a for a in self.known_sessions if ":temp:" in a}
        self.known_sessions = {ref.address for ref in sessions} | temp_sessions
        return sessions

    def session_ref(self, session_type: QQSessionType, peer: str, title: str) -> SessionRef:
        """SessionRef for one friend, group or temp peer."""
        address: str = self.session_address(session_type, peer)
        return SessionRef(address, self.platform, self.instance_id, session_type, peer, title)

    def check_sendable(self, session: QQSession) -> None:
        """Cold-start protection: only targets already seen via list_sessions or inbound temp."""
        if session.address not in self.known_sessions:
            raise SessionNotSendableError(
                f"{session.address} is not a known friend, group or temp session"
            )

    def send_message(self, address: str, text: str, reply_to: str = "") -> SendResult:
        """Send text via OneBot `send_msg`.

        Raises SessionMismatchError, SessionNotSendableError, or RiskSignalError when
        OneBot reports a frequency or risk-control failure (router trips the breaker).
        """
        session: QQSession = self.resolve_session(address)
        self.check_sendable(session)
        if len(text) > self.limits.max_text_length:
            return make_result("failed", "text_too_long", f"limit {self.limits.max_text_length}")
        params: dict[str, object] = build_send_params(session, text, reply_to)
        result: SendResult = classify_call_result(self.caller.call_action("send_msg", params))
        if result.error_code == "provider_auth":
            self.phase = "error"
        if result.risk_signal:
            raise RiskSignalError(result.error_message, result)
        return result

    def send(self, session: SessionRef, payload: OutboundPayload) -> SendResult:
        """ADR 0005 protocol entry: never raises, risk shows as `risk_signal=True`."""
        try:
            return self.send_message(session.address, payload.text, payload.reply_to)
        except RiskSignalError as error:
            return error.result
        except QQProviderError as error:
            return make_result("failed", error.error_code, error.message)

    def to_envelope(self, event: Mapping[str, object]) -> dict[str, object] | None:
        """One OneBot event to an envelope; inbound temp sessions become replyable."""
        envelope: dict[str, object] | None = to_envelope(self.instance_id, event)
        if envelope is not None and envelope["session_type"] == "temp":
            self.known_sessions.add(str(envelope["session"]))
        return envelope

    def parse_event(
        self, instance_id: int, headers: dict[str, str], body: bytes
    ) -> list[dict[str, object]]:
        """ADR 0005 protocol entry: raw callback body to zero or one envelope."""
        self.require_instance(instance_id)
        try:
            decoded: object = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return []
        envelope: dict[str, object] | None = self.to_envelope(as_mapping(decoded))
        return [envelope] if envelope is not None else []

    def verify_event(self, instance_id: int, headers: dict[str, str], body: bytes) -> bool:
        """Constant-time token check on `X-Messaging-Token` or `Authorization: Bearer`.

        Which header NapCat really sends 需复核 (qq-napcat 1.2); both are accepted.
        """
        if instance_id != self.instance_id or not self.event_token:
            return False
        lowered: dict[str, str] = {key.lower(): value for key, value in headers.items()}
        candidates: list[str] = [lowered.get(EVENT_TOKEN_HEADER, "")]
        authorization: str = lowered.get("authorization", "")
        if authorization.lower().startswith("bearer "):
            candidates.append(authorization[7:].strip())
        expected: bytes = self.event_token.encode("utf-8")
        return any(
            hmac.compare_digest(candidate.encode("utf-8"), expected)
            for candidate in candidates
            if candidate
        )
