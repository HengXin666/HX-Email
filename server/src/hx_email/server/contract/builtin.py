"""Built-in declarations for the platforms the router ships with, and the shared registry.

QQ (NapCat, OneBot 11) and GitHub (App) as implemented today. v1 mapping:
- ``qq:<iid>/private/<qq>``  is ``qq:<iid>:private:<qq>``
- ``qq:<iid>/group/<gid>``   is ``qq:<iid>:group:<gid>``
- ``qq:<iid>/temp/<gid>-<qq>`` is ``qq:<iid>:temp:<gid>-<qq>``
- ``github:<iid>/repo/<owner>/<name>`` is ``github:<iid>:repo:<owner>/<name>``
- ``github:<iid>/repo/<owner>/<name>/issue/<n>`` is ``github:<iid>:issue:<owner>/<name>#<n>``
  (issue and pull request share GitHub's number space, so one kind covers both threads)
"""

from __future__ import annotations

from typing import Final

from hx_email.server.contract.capabilities import (
    ActionSpec,
    AddressKind,
    CapabilityRegistry,
    KindRule,
    PlatformCapabilities,
)

DIGITS: Final[str] = r"[0-9]+"
REPO_NAME: Final[str] = r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"

QQ: Final[PlatformCapabilities] = PlatformCapabilities(
    platform="qq",
    title="QQ (NapCat / OneBot 11)",
    risk_level="third_party",
    delivery="push",
    kinds=(
        AddressKind(
            "private",
            id_pattern=DIGITS,
            legacy_type="private",
            legacy_peer="{private}",
            sendable=True,
            description="好友私聊, id 为对方 QQ 号",
        ),
        AddressKind(
            "group",
            id_pattern=DIGITS,
            legacy_type="group",
            legacy_peer="{group}",
            sendable=True,
            description="群聊, id 为群号",
        ),
        AddressKind(
            "temp",
            id_pattern=r"[0-9]+-[0-9]+",
            legacy_type="temp",
            legacy_peer="{temp}",
            sendable=True,
            description="群临时会话, id 为 <群号>-<QQ 号>, 只能回复不能首发",
        ),
    ),
    event_kinds=("message",),
    default_event_kind="message",
    signals=("from_self",),
    actions=(
        ActionSpec(
            "message_send",
            targets=("private", "group", "temp"),
            description="发文本, 可带 reply_to 引用一条平台消息",
        ),
    ),
)

GITHUB: Final[PlatformCapabilities] = PlatformCapabilities(
    platform="github",
    title="GitHub (App)",
    risk_level="official",
    delivery="push",
    kinds=(
        AddressKind(
            "repo",
            arity=2,
            id_pattern=REPO_NAME,
            legacy_type="repo",
            legacy_peer="{repo}",
            sendable=True,
            description="仓库, id 为 owner/name; 向仓库发送即新开 issue",
        ),
        AddressKind(
            "issue",
            parent="repo",
            id_pattern=DIGITS,
            legacy_type="issue",
            legacy_peer="{repo}#{issue}",
            sendable=True,
            description="issue 或 pull request 线程, id 为编号",
        ),
    ),
    event_kinds=("thread_opened", "comment", "review_comment"),
    default_event_kind="comment",
    signals=("from_self",),
    actions=(
        ActionSpec(
            "message_send",
            targets=("repo", "issue"),
            description="在线程下评论; 发到仓库时新开 issue",
            requires=("title when target is repo",),
        ),
    ),
    kind_rules=(
        KindRule("ic:", "comment"),
        KindRule("rc:", "review_comment"),
        KindRule("is:", "thread_opened"),
        KindRule("pr:", "thread_opened"),
    ),
)

REGISTRY: Final[CapabilityRegistry] = CapabilityRegistry((QQ, GITHUB))
