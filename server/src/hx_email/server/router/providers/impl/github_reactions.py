"""GitHub reactions as a router action (``reaction_add``).

A reaction is not a message: it has no body to carry a delivery marker, so it cannot be
reconciled the way comments are. It does not need to be: GitHub answers 201 for a new
reaction and 200 with the existing one when the same user already left that emoji, so a
repeated call is harmless. That is why the provider retries a timed-out reaction instead
of parking it as ``unknown``.

Targets, all inside one ``github:<iid>:issue:<owner>/<name>#<n>`` thread:
- no ``message_id``: the issue or pull request itself
- ``ic:<id>``: an issue comment (also a PR conversation comment)
- ``rc:<id>``: a pull request review comment
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from hx_email.server.router.providers.impl.github.github_http import GITHUB_API

REACTION_PREFIX: Final[str] = "re"
COMMENT_PATHS: Final[dict[str, str]] = {"ic": "issues/comments", "rc": "pulls/comments"}


@dataclass(frozen=True)
class ReactionRequest:
    repo_full_name: str
    url: str
    body: dict[str, object]


def issue_thread(address: str) -> tuple[str, int] | None:
    """``(owner/name, number)`` of a v1 issue address, or None for anything else."""
    parts: list[str] = address.split(":", 3)
    if len(parts) != 4 or parts[0] != "github" or parts[2] != "issue":
        return None
    repo, sep, number = parts[3].rpartition("#")
    if not sep or "/" not in repo or not number.isdigit():
        return None
    return repo, int(number)


# 表情没有正文可放隐藏标记, 但 GitHub 对同一用户同一表情返回已有那条 (200), 重复调用无害, 不需要对账
# 决策记录: .agents/notes/implemented/feature/2026-11-09-github-outbound-actions.md
def reaction_request(address: str, params: Mapping[str, str]) -> ReactionRequest | None:
    thread: tuple[str, int] | None = issue_thread(address)
    content: str = params.get("content", "")
    if thread is None or not content:
        return None
    repo, number = thread
    base: str = f"{GITHUB_API}/repos/{repo}"
    message_id: str = params.get("message_id", "")
    if not message_id:
        return ReactionRequest(repo, f"{base}/issues/{number}/reactions", {"content": content})
    prefix, _sep, raw_id = message_id.partition(":")
    path: str | None = COMMENT_PATHS.get(prefix)
    if path is None or not raw_id.isdigit():
        return None
    return ReactionRequest(repo, f"{base}/{path}/{raw_id}/reactions", {"content": content})
