"""QQ 频道 provider, 走 QQ 官方机器人 API (ADR 0009), 与 NapCat 个人号通道完全分开.

一个实例对应一个机器人应用 (AppID + AppSecret). 入站靠开放平台的 webhook 回调 (Ed25519 签名),
出站调 OpenAPI 往子频道发消息. 规格: docs/providers/qq-bot.md.
"""

from __future__ import annotations

import json

from hx_email.server.router.provider import (
    DeliveryMode,
    OutboundPayload,
    ProviderLimits,
    SendResult,
    SessionRef,
)
from hx_email.server.router.providers.impl.qqbot.qqbot_contract import (
    QQBOT_PROFILE,
    sign_hex,
    verify_signature,
)
from hx_email.server.router.providers.impl.qqbot.qqbot_events import (
    ID_PATTERN,
    JsonDict,
    as_dict,
    payload_envelopes,
)
from hx_email.server.router.providers.impl.qqbot.qqbot_http import (
    BotConfig,
    HttpPoster,
    QQBotClient,
)

SIGNATURE_HEADER: str = "x-signature-ed25519"
TIMESTAMP_HEADER: str = "x-signature-timestamp"


class QQBotProvider:
    platform: str = "qqbot"
    delivery_mode: DeliveryMode = "push"

    def __init__(self, instance_id: int, config: BotConfig, http: HttpPoster | None = None) -> None:
        self.instance_id: int = instance_id
        self.config: BotConfig = config
        self.client: QQBotClient = QQBotClient(config, http)
        self.limits: ProviderLimits = QQBOT_PROFILE.to_limits()

    def list_sessions(self, instance_id: int) -> list[SessionRef]:
        """子频道由收到的消息入库后列出; 不为列表多调一次频道接口."""
        return []

    # 被动回复与主动消息同一个出口: reply_to 有值即带 msg_id, 主动配额由平台按子频道计
    # 决策记录: .agents/notes/implemented/feature/2026-11-09-qqbot-guild.md
    def send(self, session: SessionRef, payload: OutboundPayload) -> SendResult:
        guild_id, _, channel_id = session.session_id.partition("/")
        valid: bool = bool(ID_PATTERN.match(guild_id) and ID_PATTERN.match(channel_id))
        if (
            session.instance_id != self.instance_id
            or session.session_type != "channel"
            or not valid
        ):
            return SendResult(
                "failed", error_code="session_not_sendable", error_message=session.address
            )
        return self.client.post_channel_message(channel_id, payload.text, payload.reply_to)

    def verify_event(self, instance_id: int, headers: dict[str, str], body: bytes) -> bool:
        lowered: dict[str, str] = {key.lower(): value for key, value in headers.items()}
        if instance_id != self.instance_id or not self.config.app_secret:
            return False
        return verify_signature(
            self.config.app_secret,
            lowered.get(TIMESTAMP_HEADER, ""),
            body,
            lowered.get(SIGNATURE_HEADER, ""),
        )

    def parse_event(
        self, instance_id: int, headers: dict[str, str], body: bytes
    ) -> list[dict[str, object]]:
        try:
            decoded: object = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            return []
        return payload_envelopes(instance_id, as_dict(decoded))

    def validation_reply(self, data: JsonDict) -> dict[str, str]:
        """op 13 回调地址验证: 用 Bot Secret 派生的私钥签 ``event_ts + plain_token``."""
        plain_token: str = str(data.get("plain_token") or "")
        event_ts: str = str(data.get("event_ts") or "")
        message: bytes = (event_ts + plain_token).encode("utf-8")
        return {"plain_token": plain_token, "signature": sign_hex(self.config.app_secret, message)}
