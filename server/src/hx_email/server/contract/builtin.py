"""Built-in declarations for the platforms the router ships with, and the shared registry.

QQ (NapCat, OneBot 11) and GitHub (App) as implemented today. v1 mapping:
- ``qq:<iid>/private/<qq>``  is ``qq:<iid>:private:<qq>``
- ``qq:<iid>/group/<gid>``   is ``qq:<iid>:group:<gid>``
- ``qq:<iid>/temp/<gid>-<qq>`` is ``qq:<iid>:temp:<gid>-<qq>``
- ``qq:<iid>/qzone/<qq>/post/<tid>`` is ``qq:<iid>:qzonepost:<qq>_<tid>`` (QQ 空间说说;
  ``qzone`` alone is a grouping level for "every post in this space")
- ``qqbot:<iid>/guild/<guild>/channel/<channel>`` is ``qqbot:<iid>:channel:<guild>/<channel>``
  (QQ 频道走官方机器人 API, 是独立平台, 见 ADR 0009)
- ``github_user:<iid>/...`` 与 ``github`` 同一棵地址树, 存储键只换平台前缀
  (GitHub 用户账号经 gh CLI 接入, 是独立平台, 见 ADR 0010)
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
from hx_email.server.contract.github_actions import GITHUB_ACTIONS
from hx_email.server.contract.github_user.actions import GITHUB_USER_ACTIONS

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
            description=(
                "discussion 线程, id 为编号; message_send 不可发, 评论走 discussion_comment_create"
            ),
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
    actions=GITHUB_ACTIONS,
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

QQBOT: Final[PlatformCapabilities] = PlatformCapabilities(
    platform="qqbot",
    title="QQ 频道 (官方机器人)",
    risk_level="official",
    delivery="push",
    rate_profile="qqbot",
    kinds=(
        AddressKind(
            "guild",
            id_pattern=DIGITS,
            description="频道, id 为 guild_id; 只作分组, 订阅它即订阅其下全部子频道",
        ),
        AddressKind(
            "channel",
            parent="guild",
            id_pattern=DIGITS,
            legacy_type="channel",
            legacy_peer="{guild}/{channel}",
            sendable=True,
            description="文字子频道, id 为 channel_id; 公域机器人只收到 @ 它或回复它的消息",
        ),
    ),
    event_kinds=("message",),
    default_event_kind="message",
    signals=("from_self", "mention_self", "reply_to_self"),
    actions=(
        ActionSpec(
            "message_send",
            targets=("channel",),
            description=(
                "发到子频道; reply_to 为 5 分钟内的消息 id 时是被动回复, 不带是主动消息, "
                "默认每个子频道每天 20 条, 每个频道每天最多 2 个子频道"
            ),
        ),
    ),
)

# 用户账号与 App 共用地址树, 事件种类与动作参数; 只换平台名, 投递方式 (轮询) 与权限写法
GITHUB_USER: Final[PlatformCapabilities] = PlatformCapabilities(
    platform="github_user",
    title="GitHub 账号 (gh CLI)",
    risk_level="official",
    delivery="pull",
    rate_profile="github_user",
    kinds=GITHUB.kinds,
    event_kinds=(*GITHUB.event_kinds, "ci"),
    default_event_kind=GITHUB.default_event_kind,
    signals=GITHUB.signals,
    actions=GITHUB_USER_ACTIONS,
    kind_rules=(*GITHUB.kind_rules, KindRule("ci:", "ci")),
)

REGISTRY: Final[CapabilityRegistry] = CapabilityRegistry((QQ, GITHUB, QQBOT, GITHUB_USER))
