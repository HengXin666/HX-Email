"""In-process event hub: wake only the waiters whose scope a stored message falls in.

The old gateway had one ``threading.Condition`` and a version counter, so every new
message woke every waiter of every user and each re-ran its SQL (a thundering herd).
Here each waiter registers a ``Matcher`` built from its ``Source`` and the instances
its user owns; ``publish`` tests each hit against the matchers and fires only those.

A waiter is either async (an ``asyncio.Event`` set through ``call_soon_threadsafe``,
so a long-poll or SSE stream holds no thread while it waits) or sync (a
``threading.Event``, for callers that still run in the thread pool). A matcher may
over-match but never under-match: a waiter that wakes and finds nothing re-reads by
cursor and waits again, so the database stays the source of truth.
"""

from __future__ import annotations

import asyncio
import re
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Final

from hx_email.server.router.impl.reader import Source, peer_of

LIKE_ESCAPE: Final[str] = "\\"


@dataclass(frozen=True)
class Hit:
    """One stored message as the hub sees it: which instance, which chat_id."""

    instance_id: int
    chat_id: str = ""
    direction: str = "inbound"


def like_to_regex(pattern: str) -> re.Pattern[str]:
    """SQL ``LIKE ... ESCAPE '\\'`` to an anchored regex, so hub and SQL agree."""
    out: list[str] = []
    escaped: bool = False
    for char in pattern:
        if escaped:
            out.append(re.escape(char))
            escaped = False
        elif char == LIKE_ESCAPE:
            escaped = True
        elif char == "%":
            out.append(".*")
        elif char == "_":
            out.append(".")
        else:
            out.append(re.escape(char))
    return re.compile("^" + "".join(out) + "$", re.DOTALL)


@dataclass(frozen=True)
class Matcher:
    """The part of a ``Source`` the hub can test without touching the database."""

    instances: frozenset[int]
    exact: frozenset[str] = frozenset()
    patterns: tuple[re.Pattern[str], ...] = ()
    session_type: str = ""
    direction: str = "both"

    def matches(self, hit: Hit) -> bool:
        if hit.instance_id not in self.instances:
            return False
        if self.direction != "both" and hit.direction != self.direction:
            return False
        if not hit.chat_id:
            return True
        if self.exact or self.patterns:
            if hit.chat_id in self.exact or peer_of(hit.chat_id) in self.exact:
                return True
            return any(pattern.match(hit.chat_id) for pattern in self.patterns)
        if self.session_type:
            return f":{self.session_type}:" in hit.chat_id
        return True


def matcher_for(scope: Source, owned: Iterable[int], direction: str = "both") -> Matcher:
    """Build the matcher for one read scope of one user."""
    instances: frozenset[int] = (
        frozenset({scope.instance_id}) if scope.instance_id is not None else frozenset(owned)
    )
    exact: set[str] = set()
    if scope.chat_id:
        exact.update({scope.chat_id, peer_of(scope.chat_id)})
    return Matcher(
        instances=instances,
        exact=frozenset(exact),
        patterns=tuple(like_to_regex(pattern) for pattern in scope.patterns),
        session_type=scope.session_type or "",
        direction=direction,
    )


@dataclass(eq=False)
class Waiter:
    """One registered wait; ``fire`` is safe to call from any thread, any number of times."""

    matcher: Matcher
    fire: Callable[[], None]
    fired: threading.Event = field(default_factory=threading.Event)

    def wake(self) -> None:
        self.fired.set()
        self.fire()


class EventBus:
    """Registry of live waiters; publish is O(waiters) and touches no database."""

    def __init__(self) -> None:
        self.lock: threading.Lock = threading.Lock()
        self.waiters: set[Waiter] = set()
        self.published: int = 0

    def register(self, waiter: Waiter) -> Waiter:
        with self.lock:
            self.waiters.add(waiter)
        return waiter

    def unregister(self, waiter: Waiter) -> None:
        with self.lock:
            self.waiters.discard(waiter)

    def waiting(self) -> int:
        with self.lock:
            return len(self.waiters)

    def publish(self, hits: Iterable[Hit]) -> int:
        """Wake every waiter one of ``hits`` falls in; returns how many woke."""
        batch: list[Hit] = list(hits)
        if not batch:
            return 0
        with self.lock:
            self.published += len(batch)
            targets: list[Waiter] = [
                waiter
                for waiter in self.waiters
                if any(waiter.matcher.matches(hit) for hit in batch)
            ]
        for waiter in targets:
            waiter.wake()
        return len(targets)


BUS: EventBus = EventBus()


def async_waiter(matcher: Matcher) -> tuple[Waiter, asyncio.Event]:
    """A waiter that sets an ``asyncio.Event`` on the caller's loop, from any thread."""
    loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
    event: asyncio.Event = asyncio.Event()

    def fire() -> None:
        try:
            loop.call_soon_threadsafe(event.set)
        except RuntimeError:
            # 事件循环已关闭 (客户端断开后的收尾), 没人等了, 丢掉这次唤醒
            return

    return Waiter(matcher, fire), event


def sync_waiter(matcher: Matcher) -> Waiter:
    """A waiter for thread-pool callers; block on ``waiter.fired``."""
    return Waiter(matcher, lambda: None)
