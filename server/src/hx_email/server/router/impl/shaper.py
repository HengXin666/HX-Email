"""Per-instance outbound rate shaping (spec section 9.1).

One ``Shaper`` owns one profile per instance and answers a ``Decision`` instead of
sleeping, so the same object serves the API path and the outbox drain loop without
blocking a worker. ``acquire`` is a pure query: only an ``allowed`` decision is meant
to be followed by a send, and only then does the caller count the token.

Four independent reasons can refuse a send, and each one exists for a different
failure we are trying to avoid:

- ``daily_cap``: the absolute ceiling per natural day.
- ``account_minute`` / ``account_hour``: sustained rate for one logged-in account.
- ``session_interval``: the same conversation must not be hammered.
- ``fanout_interval``: the same text must not fan out to many sessions at once, which
  is the pattern QQ treats as spam even when every individual interval is respected.
"""

from __future__ import annotations

import dataclasses
import random
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final

from hx_email.server.router.provider import ProviderLimits

HOLD_DEFAULT_SECONDS: Final[float] = 60.0
MINUTE: Final[float] = 60.0
HOUR: Final[float] = 3600.0
FANOUT_WINDOW_SECONDS: Final[float] = 30.0


@dataclass(frozen=True)
class RateProfile:
    """One column of the rate table; field order matches the spec's column order."""

    name: str
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
    fanout_interval_seconds: float = FANOUT_WINDOW_SECONDS

    def to_limits(self) -> ProviderLimits:
        return ProviderLimits(
            per_session_interval_seconds=self.per_session_interval_seconds,
            per_session_per_minute=self.per_session_per_minute,
            per_account_per_minute=self.per_account_per_minute,
            per_account_per_hour=self.per_account_per_hour,
            burst=self.burst,
            daily_cap=self.daily_cap,
            max_text_length=self.max_text_length,
        )


@dataclass(frozen=True)
class Decision:
    """Whether a send may happen now, and if not, why and how long to wait."""

    allowed: bool
    wait_seconds: float = 0.0
    reason: str = ""
    jitter_seconds: float = 0.0


@dataclass
class _Bucket:
    """Mutable per-instance state; the dataclass only groups it for readability."""

    profile: RateProfile
    tokens: float = 0.0
    last_refill: float = 0.0
    last_send: float = 0.0
    minute: deque[float] = field(default_factory=deque)
    hour: deque[float] = field(default_factory=deque)
    day_key: str = ""
    day_count: int = 0
    last_text: str = ""
    last_text_at: float = 0.0


class Shaper:
    """Token bucket plus sliding windows, one bucket per instance id."""

    def __init__(
        self,
        profile: RateProfile | None = None,
        *,
        clock: Callable[[], float] | None = None,
        rng: random.Random | None = None,
        day_of: Callable[[float], str] | None = None,
    ) -> None:
        self._default: RateProfile = profile or QQ_DEFAULT
        self._clock: Callable[[], float] = clock or time.monotonic
        self._rng: random.Random = rng or random.Random()
        self._day_of: Callable[[float], str] = day_of or _natural_day
        self._buckets: dict[int, _Bucket] = {}
        self._holds: dict[int, float] = {}

    def configure(self, instance_id: int, profile: RateProfile) -> None:
        """Replace the profile of one instance; counters are kept."""
        bucket: _Bucket = self._bucket(instance_id)
        bucket.profile = profile

    def hold(self, instance_id: int, seconds: float = HOLD_DEFAULT_SECONDS) -> None:
        """Refuse this instance until the breaker window passes."""
        self._holds[instance_id] = self._clock() + seconds

    def release(self, instance_id: int) -> None:
        self._holds.pop(instance_id, None)

    def acquire(self, instance_id: int, session: str, text: str = "") -> Decision:
        """Answer whether a send may happen now and, when it may, spend the slot.

        An allowed decision is the caller's authority to send, so the token and the
        window stamps are consumed right here. A refused decision spends nothing,
        which is what lets a caller poll without burning quota.
        """
        now: float = self._clock()
        bucket: _Bucket = self._bucket(instance_id)
        profile: RateProfile = bucket.profile
        self._refill(bucket, now)
        if self._holds.get(instance_id, 0.0) > now:
            return Decision(False, self._holds[instance_id] - now, "held", 0.0)
        self._rotate_day(bucket, now)
        if profile.daily_cap and bucket.day_count >= profile.daily_cap:
            return Decision(False, self._until_next_day(now), "daily_cap", 0.0)
        self._trim(bucket.minute, now, MINUTE)
        minute_cap: int = profile.per_account_per_minute
        if minute_cap and len(bucket.minute) >= minute_cap:
            return Decision(False, MINUTE - (now - bucket.minute[0]), "account_minute", 0.0)
        self._trim(bucket.hour, now, HOUR)
        hour_cap: int = profile.per_account_per_hour
        if hour_cap and len(bucket.hour) >= hour_cap:
            return Decision(False, HOUR - (now - bucket.hour[0]), "account_hour", 0.0)
        if (
            profile.per_session_interval_seconds > 0
            and bucket.last_send
            and now - bucket.last_send < profile.per_session_interval_seconds
        ):
            return Decision(
                False,
                profile.per_session_interval_seconds - (now - bucket.last_send),
                "session_interval",
                0.0,
            )
        if bucket.tokens < 1.0:
            return Decision(
                False, (1.0 - bucket.tokens) * profile.refill_interval_seconds, "burst", 0.0
            )
        if (
            text
            and bucket.last_text
            and _normalize(text) == bucket.last_text
            and now - bucket.last_text_at < profile.fanout_interval_seconds
        ):
            return Decision(
                False,
                profile.fanout_interval_seconds - (now - bucket.last_text_at),
                "fanout_interval",
                0.0,
            )
        jitter: float = self._rng.uniform(profile.jitter_min_seconds, profile.jitter_max_seconds)
        self.consume(instance_id, session, text)
        return Decision(True, 0.0, "", jitter)

    def consume(self, instance_id: int, session: str, text: str = "") -> None:
        """Record that the decision was acted on: one token and one stamp everywhere."""
        del session
        now: float = self._clock()
        bucket: _Bucket = self._bucket(instance_id)
        self._refill(bucket, now)
        bucket.tokens = max(0.0, bucket.tokens - 1.0)
        bucket.last_send = now
        bucket.minute.append(now)
        bucket.hour.append(now)
        self._rotate_day(bucket, now)
        bucket.day_count += 1
        if text:
            bucket.last_text = _normalize(text)
            bucket.last_text_at = now

    def profile_of(self, instance_id: int) -> RateProfile:
        return self._bucket(instance_id).profile

    def _bucket(self, instance_id: int) -> _Bucket:
        bucket: _Bucket | None = self._buckets.get(instance_id)
        if bucket is None:
            profile: RateProfile = self._default
            bucket = _Bucket(
                profile=profile,
                tokens=float(profile.burst),
                last_refill=self._clock(),
            )
            self._buckets[instance_id] = bucket
        return bucket

    def _refill(self, bucket: _Bucket, now: float) -> None:
        elapsed: float = now - bucket.last_refill
        if elapsed <= 0 or bucket.profile.refill_interval_seconds <= 0:
            bucket.last_refill = now
            return
        gained: float = elapsed / bucket.profile.refill_interval_seconds
        bucket.tokens = min(float(bucket.profile.burst), bucket.tokens + gained)
        bucket.last_refill = now

    def _rotate_day(self, bucket: _Bucket, now: float) -> None:
        key: str = self._day_of(now)
        if bucket.day_key != key:
            bucket.day_key = key
            bucket.day_count = 0

    def _until_next_day(self, now: float) -> float:
        current: str = self._day_of(now)
        probe: float = now
        waited: float = 0.0
        while self._day_of(probe) == current and waited < 86_400.0:
            probe += 60.0
            waited += 60.0
        return waited

    @staticmethod
    def _trim(window: deque[float], now: float, span: float) -> None:
        while window and now - window[0] >= span:
            window.popleft()


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _natural_day(moment: float) -> str:
    """Calendar day in local time; the daily cap resets at natural midnight."""
    return time.strftime("%Y-%m-%d", time.localtime(moment))


QQ_DEFAULT: Final[RateProfile] = RateProfile(
    "default",
    per_session_interval_seconds=3.0,
    per_session_per_minute=10,
    burst=3,
    refill_interval_seconds=1.0,
    per_account_per_minute=20,
    per_account_per_hour=300,
    daily_cap=1000,
    jitter_min_seconds=0.5,
    jitter_max_seconds=1.5,
    max_text_length=1500,
)

QQ_CONSERVATIVE: Final[RateProfile] = RateProfile(
    "conservative",
    per_session_interval_seconds=6.0,
    per_session_per_minute=5,
    burst=2,
    refill_interval_seconds=3.0,
    per_account_per_minute=8,
    per_account_per_hour=120,
    daily_cap=300,
    jitter_min_seconds=1.0,
    jitter_max_seconds=3.0,
    max_text_length=1500,
)


def from_provider_limits(name: str, limits: ProviderLimits) -> RateProfile:
    """Build a profile from the limits a provider advertises."""
    return dataclasses.replace(
        QQ_DEFAULT,
        name=name,
        per_session_interval_seconds=limits.per_session_interval_seconds,
        per_session_per_minute=limits.per_session_per_minute,
        burst=limits.burst,
        per_account_per_minute=limits.per_account_per_minute,
        per_account_per_hour=limits.per_account_per_hour,
        daily_cap=limits.daily_cap,
        max_text_length=limits.max_text_length,
    )
