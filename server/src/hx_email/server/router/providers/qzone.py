"""QQ 空间 provider: 同一个 NapCat 实例上的第二条通道, 拉取说说与评论, 发评论.

QQ 空间是 QQ 平台下的 ``qzone`` / ``post`` 两级地址 (contract/builtin.py), 和聊天共用实例与
账号, 但风控档位独立: 出站走自己的整形桶 (``QZONE_DEFAULT``), 入站靠轮询而不是推送.
规格: docs/providers/qq-zone.md.
"""

from __future__ import annotations

from typing import Final

from hx_email.server.router.provider import (
    DeliveryMode,
    OutboundPayload,
    ProviderLimits,
    SendResult,
    SessionRef,
)
from hx_email.server.router.providers.impl.qq_types import OneBotCaller
from hx_email.server.router.providers.impl.qzone.qzone_client import HttpClient, QzoneClient
from hx_email.server.router.providers.impl.qzone.qzone_contract import (
    QZONE_CONSERVATIVE,
    QZONE_DEFAULT,
    QzoneError,
)
from hx_email.server.router.providers.impl.qzone.qzone_events import (
    POST_TYPE,
    TID_PATTERN,
    JsonDict,
    Target,
    feed_envelopes,
    reply_target,
)

SELF_ALIAS: Final[str] = "self"


def split_post_peer(peer: str) -> tuple[str, str]:
    """``<主人>_<tid>`` 到 (主人, tid); 形状不对返回空串."""
    owner, sep, tid = peer.partition("_")
    if not sep or not owner.isdigit() or not TID_PATTERN.match(tid):
        return "", ""
    return owner, tid


class QzoneProvider:
    """一个 QQ 实例的空间通道; 实例与账号一对一, 不跨号."""

    platform: str = "qq"
    delivery_mode: DeliveryMode = "pull"

    def __init__(
        self,
        instance_id: int,
        caller: OneBotCaller,
        rate_profile: str = "default",
        http: HttpClient | None = None,
    ) -> None:
        self.instance_id: int = instance_id
        self.client: QzoneClient = QzoneClient(caller, http)
        profile = QZONE_CONSERVATIVE if rate_profile == "conservative" else QZONE_DEFAULT
        self.limits: ProviderLimits = profile.to_limits()

    def list_sessions(self, instance_id: int) -> list[SessionRef]:
        """说说会话由轮询入库后从消息表列出, 这里不另外枚举."""
        return []

    def parse_event(
        self, instance_id: int, headers: dict[str, str], body: bytes
    ) -> list[dict[str, object]]:
        return []

    def verify_event(self, instance_id: int, headers: dict[str, str], body: bytes) -> bool:
        return False

    # 只评论已入库的说说: 地址里带主人与 tid, reply_to 是评论 id 时回复该评论
    # 决策记录: .agents/notes/implemented/feature/2026-11-09-qzone-provider.md
    def send(self, session: SessionRef, payload: OutboundPayload) -> SendResult:
        if session.instance_id != self.instance_id or session.session_type != POST_TYPE:
            return SendResult(
                "failed", error_code="session_not_sendable", error_message=session.address
            )
        owner, tid = split_post_peer(session.session_id)
        if not owner:
            return SendResult(
                "failed", error_code="session_not_found", error_message=session.address
            )
        target: Target = reply_target(owner, tid, payload.reply_to)
        try:
            return SendResult("sent", self.client.comment(target, payload.text))
        except QzoneError as error:
            return error.result

    def resolve_owner(self, owner: str) -> str:
        return self.client.credentials().uin if owner == SELF_ALIAS else owner

    def poll(self, owner: str) -> list[JsonDict]:
        """``owner`` (QQ 号或 ``self``) 空间最新说说与评论的 envelope; 失败抛 QzoneError."""
        resolved: str = self.resolve_owner(owner)
        posts: list[JsonDict] = self.client.list_posts(resolved)
        return feed_envelopes(self.instance_id, posts, self.client.credentials().uin)
