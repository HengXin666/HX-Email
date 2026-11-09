"""GitHub 用户账号 (gh CLI) 的出站动作: 与 App 同一套动作与参数, 权限写成 OAuth scope.

动作名, 目标种类与参数直接取自 ``contract/github_actions.py``, 只换 ``requires``: App 声明的是
App 权限 (``issues:write``), 用户账号的凭据是 ``gh auth login`` 拿到的 OAuth token, 权限按 scope 计.
两边的动作集因此不会漂移: App 加一个动作, 这里在 ``SCOPES`` 补一行 scope 才会对外声明.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Final

from hx_email.server.contract.capabilities import ActionSpec
from hx_email.server.contract.github_actions import GITHUB_ACTIONS

REPO_SCOPE: Final[tuple[str, ...]] = ("repo",)
# 仓库 discussion 的 GraphQL 读写只要 repo (公开仓库 public_repo); write:discussion 管的是团队
# discussion, 与仓库无关. 已用只有 repo 的经典 token 实测 createDiscussion / addDiscussionComment
# 决策记录: .agents/notes/implemented/feature/2026-11-09-github-user-live-fixes.md
DISCUSSION_SCOPES: Final[tuple[str, ...]] = REPO_SCOPE
SCOPES: Final[dict[str, tuple[str, ...]]] = {
    "message_send": (*REPO_SCOPE, "title when target is repo"),
    "comment_create": REPO_SCOPE,
    "reaction_add": REPO_SCOPE,
    "review_submit": REPO_SCOPE,
    "discussion_create": DISCUSSION_SCOPES,
    "discussion_comment_create": DISCUSSION_SCOPES,
}
NOTIFICATION_SCOPES: Final[tuple[str, ...]] = ("notifications", "repo")


# 动作集取自 App 声明只换权限写法, 两条线的动作与参数校验是同一份
def user_actions(app_actions: tuple[ActionSpec, ...]) -> tuple[ActionSpec, ...]:
    """App 的动作里有 scope 映射的那些, 换成 OAuth scope 后原样声明."""
    return tuple(
        replace(spec, requires=SCOPES[spec.name]) for spec in app_actions if spec.name in SCOPES
    )


GITHUB_USER_ACTIONS: Final[tuple[ActionSpec, ...]] = user_actions(GITHUB_ACTIONS)
