"""Risk-control circuit breaker per instance (docs/messaging-router.md section 9.3).

Why it exists: QQ bans follow bursts of sends that keep going after the platform has
already started answering "频繁" or "风控". The shaper keeps the normal rate low; the
breaker is what stops the account from digging deeper once the platform pushes back.

- 3 risk-flagged failures within 5 minutes -> outbound ``held`` for 30 minutes.
- second trip on the same natural day -> 6 hours; third trip -> ``manual_hold``.
- ``manual_hold`` only clears through ``resume``; receiving never stops.

State is in memory on purpose: it costs a few floats per instance, and a restart that
forgets an automatic hold is still covered by the shaper's conservative windows. A
manual hold additionally parks queued rows as ``held`` in the outbox, which survives a
restart until the user resumes.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final

from hx_email.server.gateway.providers import SHAPER

RISK_WINDOW_SECONDS: Final[float] = 300.0
RISK_TRIP_COUNT: Final[int] = 3
FIRST_HOLD_SECONDS: Final[float] = 1800.0
SECOND_HOLD_SECONDS: Final[float] = 21600.0
MANUAL_AFTER_TRIPS: Final[int] = 3


@dataclass
class BreakerState:
    risks: deque[float] = field(default_factory=deque)
    held_until: float = 0.0
    trips_day: str = ""
    trips: int = 0
    manual: bool = False


class Breaker:
    def __init__(self) -> None:
        self.lock: threading.Lock = threading.Lock()
        self.states: dict[int, BreakerState] = {}

    def state(self, instance_id: int) -> BreakerState:
        current: BreakerState | None = self.states.get(instance_id)
        if current is None:
            current = BreakerState()
            self.states[instance_id] = current
        return current

    def record_risk(self, instance_id: int, *, frozen: bool = False) -> None:
        """Count one risk-flagged failure; a freeze notice trips immediately."""
        now: float = time.time()
        with self.lock:
            current: BreakerState = self.state(instance_id)
            current.risks.append(now)
            while current.risks and now - current.risks[0] > RISK_WINDOW_SECONDS:
                current.risks.popleft()
            if frozen or len(current.risks) >= RISK_TRIP_COUNT:
                self._trip(instance_id, current, now)

    def _trip(self, instance_id: int, current: BreakerState, now: float) -> None:
        day: str = time.strftime("%Y-%m-%d", time.localtime(now))
        if current.trips_day != day:
            current.trips_day, current.trips = day, 0
        current.trips += 1
        current.risks.clear()
        if current.trips >= MANUAL_AFTER_TRIPS:
            current.manual = True
            current.held_until = 0.0
            SHAPER.hold(instance_id, SECOND_HOLD_SECONDS)
            return
        seconds: float = FIRST_HOLD_SECONDS if current.trips == 1 else SECOND_HOLD_SECONDS
        current.held_until = now + seconds
        SHAPER.hold(instance_id, seconds)

    def manual_hold(self, instance_id: int) -> None:
        with self.lock:
            self.state(instance_id).manual = True

    def resume(self, instance_id: int) -> None:
        with self.lock:
            current: BreakerState = self.state(instance_id)
            current.manual = False
            current.held_until = 0.0
            current.risks.clear()
        SHAPER.release(instance_id)

    def is_manual(self, instance_id: int) -> bool:
        with self.lock:
            return self.state(instance_id).manual

    def outbound(self, instance_id: int) -> tuple[str, str]:
        """``(open|held|manual_hold, held_until ISO or "")`` for ``sources_list``."""
        with self.lock:
            current: BreakerState = self.state(instance_id)
            if current.manual:
                return "manual_hold", ""
            if current.held_until > time.time():
                until: str = datetime.fromtimestamp(current.held_until, UTC).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                )
                return "held", until
        return "open", ""

    def clear(self) -> None:
        with self.lock:
            self.states.clear()


BREAKER: Breaker = Breaker()
