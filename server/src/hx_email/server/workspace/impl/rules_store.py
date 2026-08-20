"""Platform recognition rules persistence (per-user CRUD + validation).

规则 = 用户自定义的「邮件 → 平台」映射: match_field(from/domain/subject/body)
x match_type(contains/exact/regex) x patterns(多域名/多关键词列表); 支持
JSON 导入/导出分享。
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from sqlite3 import Row
from typing import Any

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.workspace.impl.default_rules import DEFAULT_PLATFORM_RULES

MATCH_FIELDS: tuple[str, ...] = ("from", "domain", "subject", "body")
MATCH_TYPES: tuple[str, ...] = ("contains", "exact", "regex")


@dataclass(frozen=True)
class PlatformRule:
    id: int
    user_id: int
    name: str
    match_field: str
    match_type: str
    patterns: tuple[str, ...]
    platform_name: str
    enabled: bool


def rule_from_row(row: Row) -> PlatformRule:
    patterns: list[str] = []
    try:
        parsed: Any = json.loads(str(row["patterns"] or ""))
        patterns = [str(item) for item in parsed if str(item).strip()]
    except (ValueError, TypeError):
        patterns = []
    # 旧数据兼容: patterns 为空时回退到单值 pattern 列
    if not patterns and str(row["pattern"] or "").strip():
        patterns = [str(row["pattern"])]
    return PlatformRule(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        name=str(row["name"]),
        match_field=str(row["match_field"]),
        match_type=str(row["match_type"]),
        patterns=tuple(patterns),
        platform_name=str(row["platform_name"]),
        enabled=bool(row["enabled"]),
    )


def validate_rule(match_field: str, match_type: str, patterns: list[str]) -> None:
    if match_field not in MATCH_FIELDS:
        raise ValueError(f"不支持的匹配字段: {match_field}")
    if match_type not in MATCH_TYPES:
        raise ValueError(f"不支持的匹配方式: {match_type}")
    cleaned: list[str] = [p.strip() for p in patterns if p and p.strip()]
    if not cleaned:
        raise ValueError("匹配模式不能为空")
    if match_type == "regex":
        for pattern in cleaned:
            try:
                re.compile(pattern)
            except re.error as error:
                raise ValueError(f"正则无效: {error}") from error


def _rule_signature(
    match_field: str, match_type: str, patterns: list[str], platform_name: str
) -> tuple[object, ...]:
    return (match_field, match_type, tuple(patterns), platform_name.strip())


def _insert_rule(
    connection: sqlite3.Connection,
    user_id: int,
    name: str,
    match_field: str,
    match_type: str,
    patterns: list[str],
    platform_name: str,
    enabled: bool,
) -> int | None:
    cursor = connection.execute(
        """
        INSERT INTO platform_rules (
            user_id, name, match_field, match_type, pattern, patterns,
            platform_name, enabled
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            name,
            match_field,
            match_type,
            patterns[0],
            json.dumps(patterns, ensure_ascii=False),
            platform_name,
            1 if enabled else 0,
        ),
    )
    return cursor.lastrowid


def list_rules(settings: Settings, user_id: int) -> list[PlatformRule]:
    """规则列表; 按 id 倒序, 后添加的自定义规则优先于种入的默认规则。"""
    with connect(settings) as connection:
        rows = connection.execute(
            "SELECT * FROM platform_rules WHERE user_id = ? ORDER BY id DESC",
            (user_id,),
        ).fetchall()
    return [rule_from_row(row) for row in rows]


def create_rule(
    settings: Settings,
    user_id: int,
    *,
    name: str,
    match_field: str,
    match_type: str,
    patterns: list[str],
    platform_name: str,
    enabled: bool = True,
) -> PlatformRule:
    validate_rule(match_field, match_type, patterns)
    if not platform_name.strip():
        raise ValueError("目标平台名称不能为空")
    cleaned: list[str] = [p.strip() for p in patterns if p and p.strip()]
    with connect(settings) as connection:
        rule_id = _insert_rule(
            connection,
            user_id,
            name.strip(),
            match_field,
            match_type,
            cleaned,
            platform_name.strip(),
            enabled,
        )
        if rule_id is None:
            raise RuntimeError("Failed to create platform rule")
    return get_rule(settings, user_id, rule_id)  # type: ignore[return-value]


def get_rule(settings: Settings, user_id: int, rule_id: int) -> PlatformRule | None:
    with connect(settings) as connection:
        row = connection.execute(
            "SELECT * FROM platform_rules WHERE id = ? AND user_id = ?",
            (rule_id, user_id),
        ).fetchone()
    return rule_from_row(row) if row is not None else None


def update_rule(
    settings: Settings,
    user_id: int,
    rule_id: int,
    *,
    name: str,
    match_field: str,
    match_type: str,
    patterns: list[str],
    platform_name: str,
    enabled: bool,
) -> PlatformRule | None:
    validate_rule(match_field, match_type, patterns)
    if not platform_name.strip():
        raise ValueError("目标平台名称不能为空")
    cleaned: list[str] = [p.strip() for p in patterns if p and p.strip()]
    with connect(settings) as connection:
        connection.execute(
            """
            UPDATE platform_rules
            SET name = ?, match_field = ?, match_type = ?, pattern = ?,
                patterns = ?, platform_name = ?, enabled = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                name.strip(),
                match_field,
                match_type,
                cleaned[0],
                json.dumps(cleaned, ensure_ascii=False),
                platform_name.strip(),
                1 if enabled else 0,
                rule_id,
                user_id,
            ),
        )
    return get_rule(settings, user_id, rule_id)


def delete_rule(settings: Settings, user_id: int, rule_id: int) -> bool:
    with connect(settings) as connection:
        cursor = connection.execute(
            "DELETE FROM platform_rules WHERE id = ? AND user_id = ?",
            (rule_id, user_id),
        )
    return cursor.rowcount > 0


def insert_default_rules(connection: sqlite3.Connection, user_id: int) -> int:
    """按 (匹配签名) 去重插入默认规则, 返回新增条数 (幂等)。"""
    existing: set[tuple[object, ...]] = {
        _rule_signature(str(r[0]), str(r[1]), json.loads(str(r[2] or "[]")), str(r[3]))
        for r in connection.execute(
            "SELECT match_field, match_type, patterns, platform_name "
            "FROM platform_rules WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    }
    installed: int = 0
    for name, match_field, match_type, patterns, platform_name in DEFAULT_PLATFORM_RULES:
        if _rule_signature(match_field, match_type, list(patterns), platform_name) in existing:
            continue
        _insert_rule(
            connection, user_id, name, match_field, match_type, list(patterns), platform_name, True
        )
        installed += 1
    return installed


def export_rules(settings: Settings, user_id: int) -> list[dict[str, object]]:
    """导出规则为 JSON 数组 (不含 id/user_id, 便于分享)。"""
    return [
        {
            "name": rule.name,
            "match_field": rule.match_field,
            "match_type": rule.match_type,
            "patterns": list(rule.patterns),
            "platform_name": rule.platform_name,
            "enabled": rule.enabled,
        }
        for rule in list_rules(settings, user_id)
    ]


def import_rules(
    settings: Settings,
    user_id: int,
    rules: list[dict[str, object]],
    strategy: str = "skip",
) -> dict[str, int]:
    """导入规则; strategy=skip 跳过已存在, replace 先删同名再写入。返回计数。"""
    imported: int = 0
    skipped: int = 0
    with connect(settings) as connection:
        existing: set[tuple[object, ...]] = {
            _rule_signature(
                str(r["match_field"]),
                str(r["match_type"]),
                json.loads(str(r["patterns"] or "[]")),
                str(r["platform_name"]),
            )
            for r in connection.execute(
                "SELECT match_field, match_type, patterns, platform_name "
                "FROM platform_rules WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        }
        for item in rules:
            try:
                match_field = str(item.get("match_field") or "domain")
                match_type = str(item.get("match_type") or "contains")
                raw_patterns: Any = item.get("patterns") or [item.get("pattern")]
                patterns = [str(p) for p in raw_patterns if str(p).strip()]
                platform_name = str(item.get("platform_name") or "")
                validate_rule(match_field, match_type, patterns)
                if not platform_name.strip():
                    raise ValueError("平台名称不能为空")
                name = str(item.get("name") or platform_name)
                enabled = bool(item.get("enabled", True))
            except (ValueError, TypeError):
                skipped += 1
                continue
            signature = _rule_signature(match_field, match_type, patterns, platform_name)
            if strategy == "replace":
                connection.execute(
                    "DELETE FROM platform_rules WHERE user_id = ? AND platform_name = ?",
                    (user_id, platform_name),
                )
                existing = {sig for sig in existing if sig[3] != platform_name}
            elif signature in existing:
                skipped += 1
                continue
            _insert_rule(
                connection, user_id, name, match_field, match_type, patterns, platform_name, enabled
            )
            existing.add(signature)
            imported += 1
    return {"imported": imported, "skipped": skipped}
