"""MCP sessions of the Streamable HTTP transport (``Mcp-Session-Id``), in memory.

``initialize`` mints a session bound to the credential that sent it (a SHA-256 of the
bearer token); every later POST, GET and DELETE must carry the id. A session holds:

- the notification ring: the last ``RING_SIZE`` SSE frames, numbered per session, so a
  GET stream that reconnects with ``Last-Event-ID`` gets what it missed;
- at most one attached GET stream (a newer GET replaces the older one);
- the resource watches (hub waiters) registered by ``resources/subscribe``.

Bounds: ``MAX_SESSIONS`` in total, ``MAX_PER_PRINCIPAL`` per credential (the oldest of
that credential is evicted), ``IDLE_SECONDS`` idle expiry. Nothing is buffered before
the first GET stream opens; afterwards notifications coalesce per resource, so the
ring cannot fill with repeats while the client is away.
"""

from __future__ import annotations

import asyncio
import json
import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Final

from hx_email.server.hub.bus import BUS, Waiter

MAX_SESSIONS: Final[int] = 256
MAX_PER_PRINCIPAL: Final[int] = 8
IDLE_SECONDS: Final[float] = 1800.0
RING_SIZE: Final[int] = 64
SWEEP_INTERVAL_SECONDS: Final[float] = 60.0
JsonDict = dict[str, object]


class SessionLimitError(Exception):
    """The process already holds ``MAX_SESSIONS`` live sessions."""


@dataclass(eq=False)
class StreamSlot:
    """One attached GET stream: the loop it runs on and the event that wakes it."""

    loop: asyncio.AbstractEventLoop
    wake: asyncio.Event
    closed: bool = False

    def poke(self) -> None:
        try:
            self.loop.call_soon_threadsafe(self.wake.set)
        except RuntimeError:
            # 流所在的事件循环已关闭, 收尾时 detach 会清掉这个槽
            return


def sse_frame(seq: int, message: JsonDict) -> str:
    return f"id: {seq}\nevent: message\ndata: {json.dumps(message, ensure_ascii=False)}\n\n"


@dataclass(eq=False)
class McpSession:
    session_id: str
    principal: str
    user_id: int
    protocol: str
    last_seen: float = field(default_factory=time.monotonic)
    seq: int = 0
    ring: deque[tuple[int, str]] = field(default_factory=lambda: deque(maxlen=RING_SIZE))
    stream: StreamSlot | None = None
    stream_seen: bool = False
    pending: set[str] = field(default_factory=set)
    watches: dict[str, Waiter] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)
    ended: bool = False

    def touch(self) -> None:
        self.last_seen = time.monotonic()

    def emit(self, message: JsonDict, coalesce: str = "") -> bool:
        """Queue one server message for the GET stream; safe from any thread."""
        with self.lock:
            if self.ended or not self.stream_seen:
                return False
            if coalesce and coalesce in self.pending:
                return False
            if coalesce:
                self.pending.add(coalesce)
            self.seq += 1
            self.ring.append((self.seq, sse_frame(self.seq, message)))
            slot: StreamSlot | None = self.stream
        if slot is not None:
            slot.poke()
        return True

    def attach(self, slot: StreamSlot, resume: int | None) -> int:
        """Make ``slot`` the session's stream; returns the seq it starts after."""
        with self.lock:
            previous: StreamSlot | None = self.stream
            self.stream = slot
            self.stream_seen = True
            start: int = self.seq if resume is None else min(max(resume, 0), self.seq)
        if previous is not None:
            previous.closed = True
            previous.poke()
        self.touch()
        return start

    def detach(self, slot: StreamSlot) -> None:
        with self.lock:
            if self.stream is slot:
                self.stream = None
        self.touch()

    def take_after(self, seq: int) -> list[tuple[int, str]]:
        """Frames newer than ``seq``; delivered resources may notify again."""
        with self.lock:
            frames: list[tuple[int, str]] = [item for item in self.ring if item[0] > seq]
            self.pending.clear()
        self.touch()
        return frames

    def end(self) -> None:
        """Drop the stream and every hub waiter; idempotent."""
        with self.lock:
            self.ended = True
            slot: StreamSlot | None = self.stream
            self.stream = None
            waiters: list[Waiter] = list(self.watches.values())
            self.watches.clear()
        for waiter in waiters:
            BUS.unregister(waiter)
        if slot is not None:
            slot.closed = True
            slot.poke()


class SessionTable:
    """Process-wide registry; every operation is O(sessions) at worst and bounded."""

    def __init__(self) -> None:
        self.lock: threading.Lock = threading.Lock()
        self.sessions: dict[str, McpSession] = {}
        self.last_sweep: float = 0.0

    def expired(self, session: McpSession, now: float) -> bool:
        return session.stream is None and now - session.last_seen > IDLE_SECONDS

    def sweep(self, force: bool = False) -> int:
        now: float = time.monotonic()
        if not force and now - self.last_sweep < SWEEP_INTERVAL_SECONDS:
            return 0
        with self.lock:
            self.last_sweep = now
            dead: list[McpSession] = [s for s in self.sessions.values() if self.expired(s, now)]
            for session in dead:
                self.sessions.pop(session.session_id, None)
        for session in dead:
            session.end()
        return len(dead)

    # 会话只放内存并设上限: 单进程部署 (ADR 0002), 重启后客户端按规范收到 404 再 initialize
    # 决策记录: .agents/notes/implemented/feature/2026-11-09-mcp-completion.md
    def create(self, principal: str, user_id: int, protocol: str) -> McpSession:
        self.sweep(force=True)
        session = McpSession(secrets.token_urlsafe(24), principal, user_id, protocol)
        evicted: McpSession | None = None
        with self.lock:
            own: list[McpSession] = [s for s in self.sessions.values() if s.principal == principal]
            if len(own) >= MAX_PER_PRINCIPAL:
                evicted = min(own, key=lambda s: s.last_seen)
                self.sessions.pop(evicted.session_id, None)
            if len(self.sessions) >= MAX_SESSIONS:
                raise SessionLimitError(f"at most {MAX_SESSIONS} MCP sessions")
            self.sessions[session.session_id] = session
        if evicted is not None:
            evicted.end()
        return session

    def get(self, session_id: str, principal: str) -> McpSession | None:
        """Live session of this credential; unknown, expired or foreign is None."""
        self.sweep()
        with self.lock:
            session: McpSession | None = self.sessions.get(session_id)
        if session is None or session.principal != principal:
            return None
        if self.expired(session, time.monotonic()):
            self.close(session_id, principal)
            return None
        session.touch()
        return session

    def close(self, session_id: str, principal: str) -> bool:
        with self.lock:
            session: McpSession | None = self.sessions.get(session_id)
            if session is None or session.principal != principal:
                return False
            self.sessions.pop(session_id, None)
        session.end()
        return True

    def of_user(self, user_id: int) -> list[McpSession]:
        with self.lock:
            return [s for s in self.sessions.values() if s.user_id == user_id]

    def count(self) -> int:
        with self.lock:
            return len(self.sessions)

    def clear(self) -> None:
        with self.lock:
            sessions: list[McpSession] = list(self.sessions.values())
            self.sessions.clear()
        for session in sessions:
            session.end()


TABLE: SessionTable = SessionTable()
