"""Platform recognition: scan historical mail and accept candidates.

规则引擎: 用户自定义规则(见 rules_store)优先命中, 未命中时回退到发件人
域名启发式。扫描聚合用户全部 fetched_messages, 按识别出的平台归并;
「纳入平台」为已识别平台创建平台记录并为相关可用邮箱创建绑定
(用户显式确认, 不自动创建)。
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import asdict, dataclass
from email.utils import parseaddr
from sqlite3 import Row
from typing import TypedDict

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.workspace.impl.rules_store import (
    PlatformRule,
    create_rule,
    delete_rule,
    list_rules,
    update_rule,
)
from hx_email.server.workspace.platforms import (
    DuplicatePlatformBindingError,
    DuplicatePlatformNameError,
    create_platform,
    create_platform_binding,
)

DEFAULT_SOURCE: str = "domain"


class _GroupEntry(TypedDict):
    source: str
    senders: set[str]
    message_count: int
    usable_email_ids: set[int]
    first_seen: str
    last_seen: str


__all__ = [
    "PlatformRule",
    "ScanItem",
    "accept_scan_item",
    "create_rule",
    "delete_rule",
    "list_rules",
    "platform_for_message",
    "scan_historical_messages",
    "update_rule",
]


@dataclass(frozen=True)
class ScanItem:
    platform: str
    source: str
    senders: tuple[str, ...]
    sender_count: int
    message_count: int
    usable_email_ids: tuple[int, ...]
    first_seen: str
    last_seen: str


def scan_item_dict(item: ScanItem) -> dict[str, object]:
    data: dict[str, object] = asdict(item)
    data["senders"] = list(item.senders)
    data["usable_email_ids"] = list(item.usable_email_ids)
    return data


def _sender_email(from_address: str) -> str:
    _, address = parseaddr(from_address or "")
    return address.strip().lower()


def _sender_domain(from_address: str) -> str:
    address = _sender_email(from_address)
    if "@" not in address:
        return ""
    domain: str = address.rsplit("@", 1)[1]
    return domain if "." in domain else ""


def _rule_matches(
    rule: PlatformRule,
    from_address: str,
    subject: str,
    body: str,
) -> bool:
    if rule.match_field == "from":
        haystack = _sender_email(from_address)
    elif rule.match_field == "domain":
        haystack = _sender_domain(from_address)
    elif rule.match_field == "subject":
        haystack = subject or ""
    else:
        haystack = body or ""
    if not haystack:
        return False
    # 一个规则可含多个模式(多域名/多关键词), 任一命中即匹配
    for pattern in rule.patterns:
        if not pattern:
            continue
        if rule.match_type == "contains":
            if pattern.lower() in haystack.lower():
                return True
        elif rule.match_type == "exact":
            if haystack.lower() == pattern.lower():
                return True
        elif re.search(pattern, haystack) is not None:
            return True
    return False


def platform_for_message(
    from_address: str,
    subject: str,
    body: str,
    rules: list[PlatformRule],
    *,
    fallback: bool = True,
) -> tuple[str, str]:
    """返回 (平台名, 来源); 来源为规则名或 'domain' 启发式 (fallback=False 仅走规则)。"""
    for rule in rules:
        if rule.enabled and _rule_matches(rule, from_address, subject, body):
            return rule.platform_name, rule.name or rule.platform_name
    if not fallback:
        return "", ""
    domain: str = _sender_domain(from_address)
    return (domain, DEFAULT_SOURCE) if domain else ("", "")


def analyze_email_platforms(
    settings: Settings,
    user_id: int,
    usable_email_id: int,
) -> list[dict[str, object]]:
    """分析单个邮箱的历史邮件(仅按已配置规则), 自动创建平台并绑定。

    返回 [{platform, platform_id, message_count, bindings_created,
    bindings_skipped}]。只识别规则命中的平台, 不做域名启发式。
    """
    from hx_email.server.mail.usable_emails import get_usable_email

    if get_usable_email(settings, user_id, usable_email_id) is None:
        raise ValueError("邮箱不存在")
    rules: list[PlatformRule] = list_rules(settings, user_id)
    matched: dict[str, int] = {}
    with connect(settings) as connection:
        rows = connection.execute(
            """
            SELECT from_address, subject, body
            FROM fetched_messages
            WHERE user_id = ? AND usable_email_id = ?
            """,
            (user_id, usable_email_id),
        ).fetchall()
    for row in rows:
        platform, _source = platform_for_message(
            str(row["from_address"] or ""),
            str(row["subject"] or ""),
            str(row["body"] or ""),
            rules,
            fallback=False,
        )
        if platform:
            matched[platform] = matched.get(platform, 0) + 1
    results: list[dict[str, object]] = []
    for platform, message_count in matched.items():
        accepted = accept_scan_item(settings, user_id, platform, [usable_email_id])
        results.append({**accepted, "message_count": message_count})
    return results


def scan_historical_messages(settings: Settings, user_id: int) -> list[ScanItem]:
    """聚合全部历史邮件, 按识别平台归并, 按邮件数降序返回。"""
    rules: list[PlatformRule] = list_rules(settings, user_id)
    with connect(settings) as connection:
        rows = connection.execute(
            """
            SELECT from_address, subject, body, usable_email_id, received_at
            FROM fetched_messages
            WHERE user_id = ?
            ORDER BY received_at DESC, id DESC
            """,
            (user_id,),
        ).fetchall()

    groups: dict[str, _GroupEntry] = {}
    for row in rows:
        platform, source = platform_for_message(
            str(row["from_address"] or ""),
            str(row["subject"] or ""),
            str(row["body"] or ""),
            rules,
        )
        if not platform:
            continue
        entry: _GroupEntry = groups.setdefault(
            platform,
            {
                "source": source,
                "senders": set(),
                "message_count": 0,
                "usable_email_ids": set(),
                "first_seen": "",
                "last_seen": "",
            },
        )
        sender: str = _sender_email(str(row["from_address"] or ""))
        if sender:
            entry["senders"].add(sender)
        entry["message_count"] += 1
        entry["usable_email_ids"].add(int(row["usable_email_id"]))
        received: str = str(row["received_at"] or "")
        if not entry["first_seen"]:
            entry["first_seen"] = received
        if received and not entry["last_seen"]:
            entry["last_seen"] = received

    items: list[ScanItem] = []
    for platform, entry in groups.items():
        senders: list[str] = sorted(entry["senders"])
        items.append(
            ScanItem(
                platform=platform,
                source=entry["source"],
                senders=tuple(senders),
                sender_count=len(senders),
                message_count=entry["message_count"],
                usable_email_ids=tuple(sorted(entry["usable_email_ids"])),
                first_seen=entry["first_seen"],
                last_seen=entry["last_seen"],
            )
        )
    items.sort(key=lambda item: item.message_count, reverse=True)
    return items


def accept_scan_item(
    settings: Settings,
    user_id: int,
    platform_name: str,
    usable_email_ids: list[int],
) -> dict[str, object]:
    """把识别出的平台纳入平台目录并创建绑定; 已存在的平台/绑定自动跳过。"""
    name: str = platform_name.strip()
    if not name:
        raise ValueError("平台名称不能为空")
    try:
        platform_id: int = create_platform(settings, user_id, name).id
    except DuplicatePlatformNameError:
        platform_id = _find_platform_id(settings, user_id, name)

    created: int = 0
    skipped: int = 0
    for usable_email_id in usable_email_ids:
        try:
            create_platform_binding(settings, user_id, usable_email_id, platform_id, "active", "")
            created += 1
        except (DuplicatePlatformBindingError, sqlite3.IntegrityError):
            skipped += 1
    return {
        "platform": name,
        "platform_id": platform_id,
        "bindings_created": created,
        "bindings_skipped": skipped,
    }


def _find_platform_id(settings: Settings, user_id: int, name: str) -> int:
    with connect(settings) as connection:
        row: Row | None = connection.execute(
            "SELECT id FROM platforms WHERE user_id = ? AND name = ?",
            (user_id, name),
        ).fetchone()
    if row is None:
        raise RuntimeError(f"平台 {name} 不存在")
    return int(row["id"])
