"""QQ 官方机器人 (频道) 的风控档位, 回调签名与错误码分类.

依据 QQ 机器人官方文档 (bot.q.qq.com/wiki/develop/api-v2): 回调用 Ed25519 签名, 种子是
Bot Secret 重复拼接到 32 字节; 子频道每秒最多 5 条, 主动消息默认每个子频道每天 20 条, 每个频道
每天只能往 2 个子频道推主动消息, 被动回复 5 分钟内有效 (docs/providers/qq-bot.md 4).
"""

from __future__ import annotations

from typing import Final

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hx_email.server.router.impl.shaper import RateProfile
from hx_email.server.router.provider import SendResult

SEED_SIZE: Final[int] = 32

# 官方渠道没有封号风险, 档位只为不撞平台限频: 子频道 5 条每秒, 本项目取 1 秒 1 条
QQBOT_PROFILE: Final[RateProfile] = RateProfile(
    name="qqbot",
    per_session_interval_seconds=1.0,
    per_session_per_minute=30,
    burst=5,
    refill_interval_seconds=1.0,
    per_account_per_minute=120,
    per_account_per_hour=3000,
    daily_cap=0,  # 主动消息的每日上限按子频道计, 由平台返回 304045 时按限频处理
    jitter_min_seconds=0.0,
    jitter_max_seconds=0.0,
    max_text_length=2000,  # 单条长度上限需复核 (qq-bot.md 8)
    fanout_interval_seconds=0.0,
)

# 平台限频: 重试并喂给熔断; 主动消息配额用完也在这里, 第二天才恢复
RATE_LIMIT_CODES: Final[frozenset[int]] = frozenset(
    {20028, 304035, 304045, 304047, 304049, 304050, 1100100, 1100308}
)
# 安全打击与封禁: 不重试, 计为风控
RISK_CODES: Final[frozenset[int]] = frozenset({11254, 11265, 304025, 1100101, 1100103, 3300006})
AUTH_CODES: Final[frozenset[int]] = frozenset({11241, 11242, 11243, 11251, 11261, 11275})
AUDIT_CODES: Final[frozenset[int]] = frozenset({304023, 304024})
EXPIRED_REPLY_CODES: Final[frozenset[int]] = frozenset({304026, 304027, 304028, 40034005})
OFFLINE_CODES: Final[frozenset[int]] = frozenset({304018})
RATE_LIMIT_RETRY_SECONDS: Final[int] = 60


def private_key(secret: str) -> Ed25519PrivateKey:
    """Bot Secret 重复拼接到至少 32 字节再截取, 作为 Ed25519 种子."""
    if not secret:
        raise ValueError("bot secret is empty")
    seed: str = secret
    while len(seed) < SEED_SIZE:
        seed = seed * 2
    return Ed25519PrivateKey.from_private_bytes(seed[:SEED_SIZE].encode("utf-8"))


def sign_hex(secret: str, message: bytes) -> str:
    return private_key(secret).sign(message).hex()


def verify_signature(secret: str, timestamp: str, body: bytes, signature_hex: str) -> bool:
    """校验 ``X-Signature-Ed25519`` (十六进制) 覆盖 ``timestamp + body``."""
    try:
        signature: bytes = bytes.fromhex(signature_hex)
        key = private_key(secret).public_key()
    except ValueError:
        return False
    if len(signature) != 64 or not timestamp:
        return False
    try:
        key.verify(signature, timestamp.encode("utf-8") + body)
    except InvalidSignature:
        return False
    return True


def classify(http_status: int, code: int, message: str, audit_id: str = "") -> SendResult:
    """非成功响应到 SendResult; 先看业务码, 再看 HTTP 状态."""
    text: str = message or f"qqbot http {http_status} code {code}"
    if code in AUDIT_CODES:
        # 消息已受理, 等人工审核; 没有消息 id, 用审核单号占位
        return SendResult("sent", f"audit:{audit_id or code}")
    if code in RATE_LIMIT_CODES or http_status == 429:
        return SendResult(
            "retry",
            retryable=True,
            risk_signal=True,
            error_code="rate_limited_by_platform",
            error_message=text,
            retry_after_seconds=RATE_LIMIT_RETRY_SECONDS,
        )
    if code in RISK_CODES:
        return SendResult("failed", risk_signal=True, error_code="risk_control", error_message=text)
    if code in AUTH_CODES or http_status == 401:
        return SendResult("failed", error_code="provider_auth", error_message=text)
    if code in EXPIRED_REPLY_CODES:
        return SendResult("failed", error_code="reply_window_expired", error_message=text)
    if code in OFFLINE_CODES or http_status >= 500:
        return SendResult(
            "retry", retryable=True, error_code="provider_unavailable", error_message=text
        )
    return SendResult("failed", error_code="provider_error", error_message=text)
