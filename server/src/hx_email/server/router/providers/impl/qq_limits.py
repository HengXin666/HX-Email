"""QQ (NapCat / OneBot 11) rate, retry and classification constants.

Every number cites its source. "qq-napcat" is docs/providers/qq-napcat.md, "router" is
docs/messaging-router.md. All rate numbers are this project's conservative values,
not limits published by Tencent (qq-napcat 5 preamble, router 9.1); they may only be
tightened unless a 14-day test-account record supports loosening them.
The router's token bucket enforces these (qq-napcat 5.2); the provider only declares them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from hx_email.server.router.providers.impl.qq_types import ProviderLimits

RateProfileName = Literal["default", "conservative"]


@dataclass(frozen=True)
class QQRateProfile:
    """One column of router 9.1."""

    per_session_interval_seconds: float
    per_session_per_minute: int
    burst: int
    refill_interval_seconds: float
    per_account_per_minute: int
    per_account_per_hour: int
    daily_cap: int
    jitter_min_seconds: float
    jitter_max_seconds: float
    max_text_length: int


DEFAULT_PROFILE: QQRateProfile = QQRateProfile(
    per_session_interval_seconds=3.0,  # qq-napcat 5.2, router 9.1: same session min gap 3 s
    per_session_per_minute=10,  # qq-napcat 5.2, router 9.1: same session 10 per minute
    burst=3,  # qq-napcat 5.2, router 9.1: account burst 3
    refill_interval_seconds=1.0,  # qq-napcat 5.2, router 9.1: then 1 token per second
    per_account_per_minute=20,  # qq-napcat 5.2, router 9.1: sliding window
    per_account_per_hour=300,  # qq-napcat 5.2, router 9.1: sliding window
    daily_cap=1000,  # qq-napcat 5.2, router 9.1: natural day in Asia/Shanghai
    jitter_min_seconds=0.5,  # qq-napcat 5.2, router 9.1: jitter 0.5 to 1.5 s
    jitter_max_seconds=1.5,  # qq-napcat 5.2, router 9.1
    max_text_length=1500,  # qq-napcat 5.2, router 9.1; real QQ client cap 需复核
)

CONSERVATIVE_PROFILE: QQRateProfile = QQRateProfile(
    per_session_interval_seconds=6.0,  # router 9.1 conservative column
    per_session_per_minute=5,  # router 9.1 conservative column
    burst=2,  # router 9.1 conservative column
    refill_interval_seconds=3.0,  # router 9.1: 1 token every 3 s
    per_account_per_minute=8,  # router 9.1 conservative column
    per_account_per_hour=120,  # router 9.1 conservative column
    daily_cap=300,  # router 9.1 conservative column
    jitter_min_seconds=1.0,  # router 9.1: jitter 1 to 3 s
    jitter_max_seconds=3.0,  # router 9.1
    max_text_length=1500,  # router 9.1; real QQ client cap 需复核
)

RATE_PROFILES: dict[RateProfileName, QQRateProfile] = {
    "default": DEFAULT_PROFILE,
    "conservative": CONSERVATIVE_PROFILE,
}

DAILY_CAP_TIMEZONE: str = "Asia/Shanghai"  # qq-napcat 5.2, router 9.1

# Same content to many sessions, qq-napcat 5.2 and router 9.1.
BROADCAST_MIN_GAP_SECONDS: float = 8.0  # gap between two sessions for identical content
BROADCAST_JITTER_MAX_SECONDS: float = 4.0  # plus 0 to 4 s jitter
BROADCAST_DAILY_SESSION_CAP: int = 20  # identical content to at most 20 sessions per day

# Backoff for retryable send failures, qq-napcat 5.5 and router 7.4.
RETRY_BASE_SECONDS: float = 2.0  # 2, 4, 8 s
RETRY_MAX_SINGLE_SECONDS: float = 60.0  # single wait cap 60 s
RETRY_JITTER_RATIO: float = 0.2  # plus 20% jitter
RETRY_MAX_ATTEMPTS: int = 3  # at most 3 retries (4 attempts total)
REQUEST_TIMEOUT_SECONDS: float = 10.0  # qq-napcat 5.5 default timeout, onebot.py DEFAULT_TIMEOUT

# Retry-After hint for HTTP 429. Not in qq-napcat 5.5; 60 s equals the per-minute window
# of qq-napcat 5.2 so the router waits at least one window. 需复核.
HTTP_429_RETRY_AFTER_SECONDS: int = 60

# Inbound backfill on reconnect, qq-napcat 3.2 and router 7.4: last 20 per session.
BACKFILL_LIMIT: int = 20

# HTTP status classes, qq-napcat 5.5.
RETRYABLE_HTTP_STATUSES: frozenset[int] = frozenset({502, 503, 504})
AUTH_HTTP_STATUSES: frozenset[int] = frozenset({401, 403})
# 429 is not listed in qq-napcat 5.5; treated as a frequency-limit risk signal. 需复核.
RATE_LIMIT_HTTP_STATUS: int = 429

# OneBot 11 standard retcodes, qq-napcat 5.5. NapCat custom codes 需复核 (qq-napcat 9).
RETCODE_BAD_REQUEST: int = 1400
RETCODE_UNAUTHORIZED: int = 1401
RETCODE_FORBIDDEN: int = 1403
RETCODE_NOT_FOUND: int = 1404
AUTH_RETCODES: frozenset[int] = frozenset({RETCODE_UNAUTHORIZED, RETCODE_FORBIDDEN})

# Risk wording keywords, qq-napcat 5.5 "风控, 频繁, 账号异常, 冻结". NapCat's real
# `wording` texts 需复核 by collecting non-zero retcodes from test-period logs.
RISK_KEYWORDS: tuple[str, ...] = ("风控", "频繁", "账号异常", "冻结", "rate limit", "too many")
# Give-up wording, qq-napcat 5.5: target not a friend, not in group, muted. 需复核.
TARGET_GONE_KEYWORDS: tuple[str, ...] = ("不是好友", "不在群", "不存在", "not friend", "not found")
MUTED_KEYWORDS: tuple[str, ...] = ("禁言", "muted")


def provider_limits(profile_name: RateProfileName = "default") -> ProviderLimits:
    """Project a rate profile onto ADR 0005 `ProviderLimits`."""
    profile: QQRateProfile = RATE_PROFILES[profile_name]
    return ProviderLimits(
        per_session_interval_seconds=profile.per_session_interval_seconds,
        per_session_per_minute=profile.per_session_per_minute,
        per_account_per_minute=profile.per_account_per_minute,
        per_account_per_hour=profile.per_account_per_hour,
        burst=profile.burst,
        daily_cap=profile.daily_cap,
        max_text_length=profile.max_text_length,
    )


def retry_delay_seconds(attempt: int) -> float:
    """Backoff before retry number `attempt` (1-based), without jitter."""
    exponent: int = max(attempt, 1) - 1
    delay: float = RETRY_BASE_SECONDS * (2**exponent)
    return min(delay, RETRY_MAX_SINGLE_SECONDS)
