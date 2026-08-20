"""Platform recognition rules persistence (per-user CRUD + validation).

规则是用户自定义的「邮件 → 平台」映射: match_field 指定匹配来源
(from/domain/subject/body), match_type 指定匹配方式 (contains/exact/regex)。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from sqlite3 import Row

from hx_email.config import Settings
from hx_email.database import connect

MATCH_FIELDS: tuple[str, ...] = ("from", "domain", "subject", "body")
MATCH_TYPES: tuple[str, ...] = ("contains", "exact", "regex")


@dataclass(frozen=True)
class PlatformRule:
    id: int
    user_id: int
    name: str
    match_field: str
    match_type: str
    pattern: str
    platform_name: str
    enabled: bool


def rule_from_row(row: Row) -> PlatformRule:
    return PlatformRule(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        name=str(row["name"]),
        match_field=str(row["match_field"]),
        match_type=str(row["match_type"]),
        pattern=str(row["pattern"]),
        platform_name=str(row["platform_name"]),
        enabled=bool(row["enabled"]),
    )


def validate_rule(match_field: str, match_type: str, pattern: str) -> None:
    if match_field not in MATCH_FIELDS:
        raise ValueError(f"不支持的匹配字段: {match_field}")
    if match_type not in MATCH_TYPES:
        raise ValueError(f"不支持的匹配方式: {match_type}")
    if not pattern.strip():
        raise ValueError("匹配模式不能为空")
    if match_type == "regex":
        try:
            re.compile(pattern)
        except re.error as error:
            raise ValueError(f"正则无效: {error}") from error


def list_rules(settings: Settings, user_id: int) -> list[PlatformRule]:
    with connect(settings) as connection:
        rows = connection.execute(
            "SELECT * FROM platform_rules WHERE user_id = ? ORDER BY id",
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
    pattern: str,
    platform_name: str,
    enabled: bool = True,
) -> PlatformRule:
    validate_rule(match_field, match_type, pattern)
    if not platform_name.strip():
        raise ValueError("目标平台名称不能为空")
    with connect(settings) as connection:
        cursor = connection.execute(
            """
            INSERT INTO platform_rules (
                user_id, name, match_field, match_type, pattern, platform_name, enabled
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                name.strip(),
                match_field,
                match_type,
                pattern.strip(),
                platform_name.strip(),
                1 if enabled else 0,
            ),
        )
        rule_id: int | None = cursor.lastrowid
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
    pattern: str,
    platform_name: str,
    enabled: bool,
) -> PlatformRule | None:
    validate_rule(match_field, match_type, pattern)
    if not platform_name.strip():
        raise ValueError("目标平台名称不能为空")
    with connect(settings) as connection:
        connection.execute(
            """
            UPDATE platform_rules
            SET name = ?, match_field = ?, match_type = ?, pattern = ?,
                platform_name = ?, enabled = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                name.strip(),
                match_field,
                match_type,
                pattern.strip(),
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
