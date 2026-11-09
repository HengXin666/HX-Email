"""GitHub 用户账号实例的配置键与解析: 只有 CLI 路径, 仓库与开关, 没有任何凭据.

实例配置是明文键值 (``messaging_instances``), 其中:

- ``cli``: gh 包装脚本的绝对路径, 例如 ``/home/me/.local/bin/gh-agent``
- ``repository``: ``owner/name``, 一个实例只服务一个仓库, 入站与出站都限定在它上面
- ``observe_issues`` / ``observe_pulls`` / ``observe_comments`` / ``observe_ci``: ``1`` 开 ``0`` 关,
  默认全关; 全关时只收 notifications 里涉及本账号的内容 (mention, review_requested, assign ...)
- ``poll_seconds``: 轮询间隔, 默认 60, 不低于 60; GitHub 的 ``X-Poll-Interval`` 更长时以它为准
- ``login``: 检查通过后由服务端写入的登录名, 用于判断 from_self 与 @ 本账号
- ``disabled_actions``: 与 App 相同的出站动作开关
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

CLI_KEY: Final[str] = "cli"
REPOSITORY_KEY: Final[str] = "repository"
LOGIN_KEY: Final[str] = "login"
POLL_KEY: Final[str] = "poll_seconds"
OBSERVE_KEYS: Final[tuple[str, ...]] = (
    "observe_issues",
    "observe_pulls",
    "observe_comments",
    "observe_ci",
)
DEFAULT_POLL_SECONDS: Final[int] = 60
MAX_POLL_SECONDS: Final[int] = 3600
REPOSITORY_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
TRUE_VALUES: Final[frozenset[str]] = frozenset({"1", "true", "on", "yes"})


def flag(raw: Mapping[str, str], key: str) -> bool:
    return str(raw.get(key, "")).strip().lower() in TRUE_VALUES


def poll_seconds(raw: Mapping[str, str]) -> int:
    text: str = str(raw.get(POLL_KEY, "")).strip()
    value: int = int(text) if text.isdigit() else DEFAULT_POLL_SECONDS
    return min(max(value, DEFAULT_POLL_SECONDS), MAX_POLL_SECONDS)


@dataclass(frozen=True)
class GhUserConfig:
    """一个用户账号实例的有效配置; ``ready`` 表示检查通过 (在线且已读到登录名)."""

    cli: str
    repository: str
    login: str = ""
    observe_issues: bool = False
    observe_pulls: bool = False
    observe_comments: bool = False
    observe_ci: bool = False
    poll_seconds: int = DEFAULT_POLL_SECONDS
    ready: bool = False

    @property
    def observing(self) -> bool:
        return self.observe_issues or self.observe_pulls or self.observe_comments or self.observe_ci


# 配置里只有 CLI 路径与开关, token 只在包装脚本自己的 GH_CONFIG_DIR 里, 从不进本服务
# 决策记录: .agents/notes/implemented/feature/2026-11-09-github-cli-account.md
def parse_config(raw: Mapping[str, str], status: str = "") -> GhUserConfig:
    login: str = str(raw.get(LOGIN_KEY, "")).strip()
    cli: str = str(raw.get(CLI_KEY, "")).strip()
    repository: str = str(raw.get(REPOSITORY_KEY, "")).strip()
    return GhUserConfig(
        cli=cli,
        repository=repository,
        login=login,
        observe_issues=flag(raw, "observe_issues"),
        observe_pulls=flag(raw, "observe_pulls"),
        observe_comments=flag(raw, "observe_comments"),
        observe_ci=flag(raw, "observe_ci"),
        poll_seconds=poll_seconds(raw),
        ready=status == "online" and bool(login and cli and repository),
    )


def config_problem(raw: Mapping[str, str]) -> str | None:
    """保存前的格式检查; ``None`` 表示格式没问题 (能否用要靠 setup 检查)."""
    cli: str = str(raw.get(CLI_KEY, "")).strip()
    if not cli.startswith("/"):
        return "cli must be an absolute path to the gh wrapper script"
    if REPOSITORY_PATTERN.match(str(raw.get(REPOSITORY_KEY, "")).strip()) is None:
        return "repository must be owner/name"
    return None
