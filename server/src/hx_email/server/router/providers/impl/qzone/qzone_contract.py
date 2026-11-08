"""QQ 空间 (Qzone) 的风控档位, 轮询参数与结果分类.

QQ 空间没有 OneBot 接口, 读写都走空间网页 CGI: 用 NapCat ``get_cookies`` 取得登录 cookie,
由 ``p_skey`` 算 ``g_tk`` 签名 (docs/providers/qq-zone.md 2). 网页接口的风控与聊天消息
分开计数, 而且对程序化访问更敏感, 所以它有自己的档位, 比 QQ 聊天的 conservative 还严.
全部数值是本项目的保守取值, 不是腾讯公布的阈值, 只允许往更严的方向调.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Final

from hx_email.server.router.impl.shaper import RateProfile
from hx_email.server.router.provider import SendResult

QZONE_DEFAULT: Final[RateProfile] = RateProfile(
    name="qzone",
    per_session_interval_seconds=60.0,  # 同一条说说下两次评论至少隔 1 分钟
    per_session_per_minute=1,
    burst=1,
    refill_interval_seconds=60.0,  # 账号级每分钟补 1 个令牌
    per_account_per_minute=2,
    per_account_per_hour=10,
    daily_cap=30,  # 自然日 Asia/Shanghai
    jitter_min_seconds=3.0,  # 比聊天更长的抖动, 打散固定节奏
    jitter_max_seconds=8.0,
    max_text_length=500,  # 评论长度上限需复核 (qq-zone.md 7)
    fanout_interval_seconds=300.0,  # 同一段文字 5 分钟内不评到第二条说说
)

QZONE_CONSERVATIVE: Final[RateProfile] = RateProfile(
    name="qzone_conservative",
    per_session_interval_seconds=180.0,
    per_session_per_minute=1,
    burst=1,
    refill_interval_seconds=180.0,
    per_account_per_minute=1,
    per_account_per_hour=5,
    daily_cap=15,
    jitter_min_seconds=5.0,
    jitter_max_seconds=15.0,
    max_text_length=500,
    fanout_interval_seconds=900.0,
)

# 轮询: 读接口同样会触发风控, 间隔下限 5 分钟, 节流时翻倍退避到 1 小时
POLL_DEFAULT_MINUTES: Final[int] = 10
POLL_MIN_MINUTES: Final[int] = 5
POLL_MAX_BACKOFF_MINUTES: Final[int] = 60
POLL_JITTER_RATIO: Final[float] = 0.2
MAX_WATCHED_SPACES: Final[int] = 5  # 每个实例最多关注 5 个空间
POSTS_PER_POLL: Final[int] = 10  # 每次只看最新 10 条说说
COMMENTS_PER_POST: Final[int] = 20  # 每条说说带回最新 20 条评论

COOKIE_DOMAIN: Final[str] = "user.qzone.qq.com"
REQUEST_TIMEOUT_SECONDS: Final[float] = 10.0

# CGI 返回码: -10000 是节流, -3000 与 -4001 是登录态失效; 其它非零码的含义需复核
CODE_THROTTLED: Final[frozenset[int]] = frozenset({-10000})
CODE_LOGGED_OUT: Final[frozenset[int]] = frozenset({-3000, -4001})
RISK_KEYWORDS: Final[tuple[str, ...]] = ("频繁", "风控", "验证码", "安全验证", "异常", "限制")


class QzoneError(Exception):
    """A Qzone call failed; ``result`` says how the router should treat it."""

    def __init__(self, message: str, result: SendResult) -> None:
        super().__init__(message)
        self.result: SendResult = result


def int_of(value: object) -> int:
    """接口里的数字有时是字符串; 认不出的按 0."""
    text: str = str(value).strip() if isinstance(value, int | str) else ""
    return int(text) if text.lstrip("-").isdigit() else 0


def g_tk(p_skey: str) -> int:
    """空间网页接口的 CSRF 签名: 对 ``p_skey`` 做 DJB 风格哈希, 取低 31 位."""
    value: int = 5381
    for char in p_skey:
        value += (value << 5) + ord(char)
    return value & 0x7FFFFFFF


def parse_cookies(header: str) -> dict[str, str]:
    """``a=1; b=2`` 到字典; 值里的 ``=`` 保留."""
    jar: dict[str, str] = {}
    for part in header.split(";"):
        name, sep, value = part.strip().partition("=")
        if sep and name:
            jar[name] = value
    return jar


def uin_of(jar: Mapping[str, str]) -> str:
    """cookie 里的登录号: ``uin=o0012345`` 去掉 o 与前导 0."""
    raw: str = jar.get("p_uin") or jar.get("uin") or ""
    digits: str = raw.lstrip("o").lstrip("0")
    return digits if digits.isdigit() else ""


def decode_body(text: str) -> dict[str, object]:
    """JSON 或 JSONP (``_Callback({...});``) 到字典; 解析不了时抛 ValueError."""
    start: int = text.find("{")
    end: int = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("qzone response carries no JSON object")
    decoded: object = json.loads(text[start : end + 1])
    if not isinstance(decoded, dict):
        raise ValueError("qzone response is not an object")
    return {str(key): value for key, value in decoded.items()}


def classify(body: Mapping[str, object]) -> SendResult | None:
    """None 表示成功; 否则给出路由层该怎么处理 (节流与风控都会喂给熔断)."""
    code: int = int_of(body.get("code", body.get("ret", 0)))
    message: str = str(body.get("message") or body.get("msg") or "")
    if code == 0:
        return None
    if code in CODE_THROTTLED:
        return SendResult(
            "retry",
            retryable=True,
            risk_signal=True,
            error_code="rate_limited_by_platform",
            error_message=message or f"qzone code {code}",
            retry_after_seconds=POLL_MIN_MINUTES * 60,
        )
    if code in CODE_LOGGED_OUT:
        return SendResult("failed", error_code="provider_auth", error_message=f"qzone code {code}")
    if any(keyword in message for keyword in RISK_KEYWORDS):
        return SendResult(
            "failed", risk_signal=True, error_code="risk_control", error_message=message
        )
    return SendResult(
        "failed", error_code="provider_error", error_message=message or f"qzone code {code}"
    )
