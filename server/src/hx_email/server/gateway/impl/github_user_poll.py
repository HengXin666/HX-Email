"""GitHub 用户账号的轮询循环: notifications 每分钟一次 (遵守 X-Poll-Interval), observe 开关按需拉.

一个守护线程跑一个 asyncio 事件循环, 子进程全部在这个循环里启动, 不占 web 服务的事件循环.
没有在线的 ``github_user`` 实例时每 2 分钟醒一次看配置, 不启动任何子进程. 每个实例的状态只有
三个小字段 (下次到期时间, ``Last-Modified``, observe 游标), 不缓存任何响应.

失败时间隔翻倍, 最多 15 分钟; 成功一次恢复. 进程重启后 notifications 不丢 (未读的仍是未读),
observe 游标从重启时刻重新开始 (不回补停机期间的动态, 见 docs/providers/github-user.md).
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.contract.github_user.config import GhUserConfig, parse_config
from hx_email.server.gateway.listen import store_envelopes
from hx_email.server.gateway.providers import InstanceRow, load_instance
from hx_email.server.router.providers.impl.github.github_http import (
    TransportConnectError,
    TransportTimeoutError,
)
from hx_email.server.router.providers.impl.github_user.gh_cli import GhCli
from hx_email.server.router.providers.impl.github_user.gh_inbox import (
    InboxRound,
    PollError,
    poll_inbox,
)
from hx_email.server.router.providers.impl.github_user.gh_observe import observe_round

LOGGER: logging.Logger = logging.getLogger("hx_email.gateway.github_user_poll")
IDLE_SECONDS: Final[float] = 120.0
MIN_SLEEP_SECONDS: Final[float] = 5.0
MAX_BACKOFF_SECONDS: Final[int] = 900


@dataclass
class AccountState:
    next_at: float = 0.0
    last_modified: str = ""
    since: str = ""
    backoff: int = 0


def utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def polling_instances(settings: Settings) -> list[InstanceRow]:
    """在线 (检查通过) 的 GitHub 用户账号实例."""
    with connect(settings) as connection:
        rows: list[sqlite3.Row] = connection.execute(
            "SELECT id FROM messaging_instances WHERE kind = 'github_user' ORDER BY id"
        ).fetchall()
    found: list[InstanceRow] = []
    for row in rows:
        instance: InstanceRow | None = load_instance(settings, int(row["id"]))
        if instance is not None and parse_config(instance.config, instance.status).ready:
            found.append(instance)
    return found


# 一个实例一轮: 先 notifications 再 observe; 间隔取配置与 X-Poll-Interval 的较大者, 出错翻倍退避
# 决策记录: .agents/notes/implemented/feature/2026-11-09-github-cli-account.md
async def poll_account(
    settings: Settings, instance: InstanceRow, state: AccountState, cli: GhCli | None = None
) -> int:
    """Poll one account once; returns seconds until it is due again."""
    config: GhUserConfig = parse_config(instance.config, instance.status)
    gh: GhCli = cli or GhCli(config.cli)

    def sink(envelopes: list[dict[str, object]]) -> int:
        return store_envelopes(settings, instance.id, envelopes)

    try:
        inbox: InboxRound = await poll_inbox(gh, config, instance.id, state.last_modified, sink)
        state.last_modified = inbox.last_modified
        if config.observing:
            state.since = state.since or utc_stamp()
            _stored, state.since = await observe_round(gh, config, instance.id, state.since, sink)
        else:
            state.since = ""
    except (PollError, TransportTimeoutError, TransportConnectError) as error:
        state.backoff = min(max(state.backoff, config.poll_seconds) * 2, MAX_BACKOFF_SECONDS)
        LOGGER.warning("github_user poll instance=%s failed: %s", instance.id, error)
        return state.backoff
    state.backoff = 0
    LOGGER.info(
        "github_user poll instance=%s stored=%s marked=%s", instance.id, inbox.stored, inbox.marked
    )
    return max(config.poll_seconds, inbox.poll_interval)


class GitHubUserPoller:
    def __init__(self) -> None:
        self.states: dict[int, AccountState] = {}
        self.lock: threading.Lock = threading.Lock()
        self.thread: threading.Thread | None = None
        self.settings: Settings | None = None

    def start(self, settings: Settings) -> None:
        self.settings = settings
        with self.lock:
            if self.thread is None or not self.thread.is_alive():
                self.thread = threading.Thread(
                    target=lambda: asyncio.run(self.main()), name="github-user-poll", daemon=True
                )
                self.thread.start()

    async def main(self) -> None:
        while True:
            delay: float = IDLE_SECONDS
            if self.settings is not None:
                try:
                    delay = await self.round(self.settings, time.monotonic())
                except Exception:  # pragma: no cover - keep the loop alive
                    LOGGER.exception("github_user poll round failed")
            await asyncio.sleep(delay)

    async def round(self, settings: Settings, now: float) -> float:
        """Poll every due account; returns seconds until the next one is due."""
        instances: list[InstanceRow] = polling_instances(settings)
        live: set[int] = {instance.id for instance in instances}
        for stale in set(self.states) - live:
            self.states.pop(stale)
        next_due: float = now + IDLE_SECONDS
        for instance in instances:
            state: AccountState = self.states.setdefault(instance.id, AccountState())
            if state.next_at <= now:
                state.next_at = now + await poll_account(settings, instance, state)
            next_due = min(next_due, state.next_at)
        return max(MIN_SLEEP_SECONDS, next_due - now)


GITHUB_USER_POLLER: GitHubUserPoller = GitHubUserPoller()
