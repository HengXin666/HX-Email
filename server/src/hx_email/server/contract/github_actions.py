"""GitHub's declared actions: what ``action_invoke`` accepts on a GitHub instance.

Kept apart from ``builtin.py`` because the GitHub list carries full parameter
declarations. The declaration is also the validation: the gateway refuses any action,
target kind or parameter not written here, before anything is queued.
"""

from __future__ import annotations

from typing import Final

from hx_email.server.contract.capabilities import ActionSpec, ParamSpec

MAX_BODY: Final[int] = 65000
GITHUB_REACTIONS: Final[tuple[str, ...]] = (
    "+1",
    "-1",
    "laugh",
    "confused",
    "heart",
    "hooray",
    "rocket",
    "eyes",
)
GITHUB_REVIEW_EVENTS: Final[tuple[str, ...]] = ("APPROVE", "REQUEST_CHANGES", "COMMENT")
GITHUB_WRITE: Final[tuple[str, ...]] = ("issues:write", "pull_requests:write")
GITHUB_DISCUSSIONS: Final[tuple[str, ...]] = ("discussions:write",)
COMMENT_REF: Final[str] = r"(ic|rc):[0-9]+"
DISCUSSION_PARENT: Final[str] = r"dc:[0-9]+|[A-Za-z0-9_-]{4,100}"

# 声明即校验: 动作名, 目标种类与参数都按这里拒绝; 前端按实例开关的动作列表也取自这里
# 决策记录: .agents/notes/implemented/feature/2026-11-09-github-outbound-actions.md
GITHUB_ACTIONS: Final[tuple[ActionSpec, ...]] = (
    ActionSpec(
        "message_send",
        targets=("repo", "issue"),
        description="在线程下评论; 发到仓库时新开 issue",
        requires=("title when target is repo",),
    ),
    ActionSpec(
        "comment_create",
        targets=("issue",),
        description="在 issue 或 PR 线程下评论; reply_to 为 rc:<id> 时回复那条 review 评论",
        requires=GITHUB_WRITE,
        params=(
            ParamSpec("text", "评论正文, Markdown", required=True, max_length=MAX_BODY),
            ParamSpec("reply_to", "可选, ic:<id> 或 rc:<id>", pattern=COMMENT_REF),
        ),
    ),
    ActionSpec(
        "reaction_add",
        targets=("issue",),
        description="给线程本身或其中一条评论加表情; 同一表情重复添加不会重复, 天然幂等",
        requires=GITHUB_WRITE,
        params=(
            ParamSpec("content", "表情", required=True, choices=GITHUB_REACTIONS),
            ParamSpec(
                "message_id", "可选, ic:<id> 或 rc:<id>; 不带则加在线程本身", pattern=COMMENT_REF
            ),
        ),
    ),
    ActionSpec(
        "review_submit",
        targets=("issue",),
        description=(
            "对 pull request 提交 review; 目标是普通 issue 时失败; "
            "不可幂等, 超时进 unknown, 不自动重发"
        ),
        requires=("pull_requests:write",),
        params=(
            ParamSpec("event", "review 结论", required=True, choices=GITHUB_REVIEW_EVENTS),
            ParamSpec(
                "body",
                "review 正文, Markdown; event 为 REQUEST_CHANGES 或 COMMENT 时必填",
                max_length=MAX_BODY,
                required_if_param="event",
                required_if_values=("REQUEST_CHANGES", "COMMENT"),
            ),
        ),
    ),
    ActionSpec(
        "discussion_create",
        targets=("repo",),
        description="在仓库新建 discussion; category 按名称或 slug 匹配, 每次调用现查, 不缓存",
        requires=GITHUB_DISCUSSIONS,
        params=(
            ParamSpec("title", "标题", required=True, max_length=256),
            ParamSpec("body", "正文, Markdown", required=True, max_length=MAX_BODY),
            ParamSpec("category", "分类名称或 slug", required=True, max_length=100),
        ),
    ),
    ActionSpec(
        "discussion_comment_create",
        targets=("discussion",),
        description="在 discussion 下评论; reply_to 可选, 为父评论的 node id 或 dc:<id>",
        requires=GITHUB_DISCUSSIONS,
        params=(
            ParamSpec("body", "评论正文, Markdown", required=True, max_length=MAX_BODY),
            ParamSpec("reply_to", "可选, 父评论 node id 或 dc:<id>", pattern=DISCUSSION_PARENT),
        ),
    ),
)
