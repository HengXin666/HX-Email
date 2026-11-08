"""Built-in declarations for the platforms the router ships with, and the shared registry.

QQ (NapCat, OneBot 11) and GitHub (App) as implemented today. v1 mapping:
- ``qq:<iid>/private/<qq>``  is ``qq:<iid>:private:<qq>``
- ``qq:<iid>/group/<gid>``   is ``qq:<iid>:group:<gid>``
- ``qq:<iid>/temp/<gid>-<qq>`` is ``qq:<iid>:temp:<gid>-<qq>``
- ``qq:<iid>/qzone/<qq>/post/<tid>`` is ``qq:<iid>:qzonepost:<qq>_<tid>`` (QQ 空间说说;
  ``qzone`` alone is a grouping level for "every post in this space")
- ``github:<iid>/repo/<owner>/<name>`` is ``github:<iid>:repo:<owner>/<name>``
- ``github:<iid>/repo/<owner>/<name>/issue/<n>`` is ``github:<iid>:issue:<owner>/<name>#<n>``
  (issue and pull request share GitHub's number space, so one kind covers both threads)
- ``github:<iid>/repo/<owner>/<name>/discussion/<n>`` is
  ``github:<iid>:discussion:<owner>/<name>#<n>``
- ``github:<iid>/repo/<owner>/<name>/commit/<sha>`` is ``github:<iid>:commit:<owner>/<name>@<sha>``
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
COMMIT_SHA: Final[str] = r"[0-9a-f]{7,40}"
QZONE_TID: Final[str] = r"[0-9A-Za-z]+"

QQ: Final[PlatformCapabilities] = PlatformCapabilities(
    platform="qq",
    title="QQ (NapCat / OneBot 11)",
    risk_level="third_party",
    delivery="push",
    rate_profile="qq",
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
        AddressKind(
            "qzone",
            id_pattern=DIGITS,
            description="QQ 空间, id 为空间主人的 QQ 号; 只作分组, 订阅它即订阅其下全部说说",
            risk_level="unofficial_web",
            rate_profile="qzone",
        ),
        AddressKind(
            "post",
            parent="qzone",
            id_pattern=QZONE_TID,
            legacy_type="qzonepost",
            legacy_peer="{qzone}_{post}",
            sendable=True,
            description="一条说说, id 为 tid; 说说, 评论与二级回复都是这里的消息, 靠轮询拉取",
            risk_level="unofficial_web",
            rate_profile="qzone",
        ),
    ),
    event_kinds=("message", "post", "comment"),
    default_event_kind="message",
    signals=("from_self", "mention_self", "reply_to_self"),
    actions=(
        ActionSpec(
            "message_send",
            targets=("private", "group", "temp", "post"),
            description=(
                "发文本, 可带 reply_to 引用一条平台消息; 发到说说即评论, "
                "reply_to 为该说说下的评论 id 时回复那条评论"
            ),
        ),
    ),
    kind_rules=(
        KindRule("qzp:", "post"),
        KindRule("qzc:", "comment"),
        KindRule("qzr:", "comment"),
    ),
)

GITHUB: Final[PlatformCapabilities] = PlatformCapabilities(
    platform="github",
    title="GitHub (App)",
    risk_level="official",
    delivery="push",
    rate_profile="github",
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
        AddressKind(
            "discussion",
            parent="repo",
            id_pattern=DIGITS,
            legacy_type="discussion",
            legacy_peer="{repo}#{discussion}",
            description="discussion 线程, id 为编号; 只收不发",
        ),
        AddressKind(
            "commit",
            parent="repo",
            id_pattern=COMMIT_SHA,
            legacy_type="commit",
            legacy_peer="{repo}@{commit}",
            description="提交, id 为 sha; 推送的提交与提交评论落在这里, 只收不发",
        ),
    ),
    event_kinds=(
        "thread_opened",
        "thread_state",
        "comment",
        "review_comment",
        "review",
        "commit",
    ),
    default_event_kind="comment",
    signals=("from_self", "mention_self", "reply_to_self"),
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
        KindRule("dc:", "comment"),
        KindRule("cc:", "comment"),
        KindRule("rv:", "review"),
        KindRule("cm:", "commit"),
        KindRule("is:", "thread_opened"),
        KindRule("pr:", "thread_opened"),
        KindRule("dn:", "thread_opened"),
    ),
)

REGISTRY: Final[CapabilityRegistry] = CapabilityRegistry((QQ, GITHUB))
