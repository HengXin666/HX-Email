from dataclasses import dataclass

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.auth import require_inserted_id


@dataclass(frozen=True)
class Group:
    id: int
    name: str
    color: str


@dataclass(frozen=True)
class Tag:
    id: int
    name: str
    color: str


@dataclass(frozen=True)
class WorkbenchEmail:
    id: int
    address: str
    label: str
    kind: str
    status: str
    group: Group | None
    tags: tuple[Tag, ...]
    platform_binding_count: int


@dataclass(frozen=True)
class WorkbenchPage:
    usable_emails: tuple[WorkbenchEmail, ...]
    total: int
    page: int
    page_size: int


def create_group(settings: Settings, user_id: int, name: str, color: str) -> Group:
    with connect(settings) as connection:
        cursor = connection.execute(
            "INSERT INTO groups (user_id, name, color) VALUES (?, ?, ?)",
            (user_id, name, color),
        )
    return Group(id=require_inserted_id(cursor.lastrowid), name=name, color=color)


def create_tag(settings: Settings, user_id: int, name: str, color: str) -> Tag:
    with connect(settings) as connection:
        cursor = connection.execute(
            "INSERT INTO tags (user_id, name, color) VALUES (?, ?, ?)",
            (user_id, name, color),
        )
    return Tag(id=require_inserted_id(cursor.lastrowid), name=name, color=color)


def organize_usable_email(
    settings: Settings,
    user_id: int,
    usable_email_id: int,
    label: str | None,
    group_id: int | None,
    tag_ids: list[int],
) -> WorkbenchEmail | None:
    with connect(settings) as connection:
        usable_email = connection.execute(
            "SELECT id FROM usable_emails WHERE id = ? AND user_id = ?",
            (usable_email_id, user_id),
        ).fetchone()
        if usable_email is None:
            return None

        if group_id is not None:
            group = connection.execute(
                "SELECT id FROM groups WHERE id = ? AND user_id = ?",
                (group_id, user_id),
            ).fetchone()
            if group is None:
                return None

        if tag_ids:
            placeholders = ",".join("?" for _ in tag_ids)
            count = connection.execute(
                f"SELECT COUNT(*) FROM tags WHERE user_id = ? AND id IN ({placeholders})",
                (user_id, *tag_ids),
            ).fetchone()[0]
            if count != len(set(tag_ids)):
                return None

        if label is not None:
            connection.execute(
                "UPDATE usable_emails SET label = ?, group_id = ? WHERE id = ? AND user_id = ?",
                (label, group_id, usable_email_id, user_id),
            )
        else:
            connection.execute(
                "UPDATE usable_emails SET group_id = ? WHERE id = ? AND user_id = ?",
                (group_id, usable_email_id, user_id),
            )
        connection.execute(
            "DELETE FROM usable_email_tags WHERE usable_email_id = ?", (usable_email_id,)
        )
        connection.executemany(
            "INSERT INTO usable_email_tags (usable_email_id, tag_id) VALUES (?, ?)",
            [(usable_email_id, tag_id) for tag_id in dict.fromkeys(tag_ids)],
        )

    return get_workbench_email(settings, user_id, usable_email_id)


def get_workbench_email(
    settings: Settings, user_id: int, usable_email_id: int
) -> WorkbenchEmail | None:
    page = list_workbench_emails(settings, user_id, usable_email_id=usable_email_id)
    if not page.usable_emails:
        return None
    return page.usable_emails[0]


def list_workbench_emails(
    settings: Settings,
    user_id: int,
    *,
    usable_email_id: int | None = None,
    kind: str | None = None,
    status: str | None = None,
    group_id: int | None = None,
    tag_id: int | None = None,
    keyword: str | None = None,
    platform_binding: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> WorkbenchPage:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 200)
    where = ["usable_emails.user_id = ?"]
    params: list[object] = [user_id]
    joins = [
        """
        LEFT JOIN groups
            ON groups.id = usable_emails.group_id
            AND groups.user_id = usable_emails.user_id
        """
    ]

    if usable_email_id is not None:
        where.append("usable_emails.id = ?")
        params.append(usable_email_id)
    if kind:
        where.append("usable_emails.kind = ?")
        params.append(kind)
    if status:
        where.append("usable_emails.status = ?")
        params.append(status)
    if group_id is not None:
        where.append("usable_emails.group_id = ?")
        params.append(group_id)
    if tag_id is not None:
        joins.append(
            "JOIN usable_email_tags filter_tags ON filter_tags.usable_email_id = usable_emails.id"
        )
        where.append("filter_tags.tag_id = ?")
        params.append(tag_id)
    if keyword:
        where.append("(usable_emails.address LIKE ? OR usable_emails.label LIKE ?)")
        like = f"%{keyword}%"
        params.extend([like, like])
    if platform_binding == "bound":
        where.append(
            """
            EXISTS (
                SELECT 1
                FROM platform_bindings
                WHERE platform_bindings.user_id = usable_emails.user_id
                    AND platform_bindings.usable_email_id = usable_emails.id
            )
            """
        )
    elif platform_binding == "unbound":
        where.append(
            """
            NOT EXISTS (
                SELECT 1
                FROM platform_bindings
                WHERE platform_bindings.user_id = usable_emails.user_id
                    AND platform_bindings.usable_email_id = usable_emails.id
            )
            """
        )

    where_sql = " AND ".join(where)
    join_sql = " ".join(joins)
    offset = (page - 1) * page_size

    with connect(settings) as connection:
        total = connection.execute(
            f"""
            SELECT COUNT(DISTINCT usable_emails.id)
            FROM usable_emails
            {join_sql}
            WHERE {where_sql}
            """,
            params,
        ).fetchone()[0]
        rows = connection.execute(
            f"""
            SELECT usable_emails.id, usable_emails.address, usable_emails.label,
                   usable_emails.kind, usable_emails.status,
                   groups.id AS group_id, groups.name AS group_name, groups.color AS group_color,
                   COUNT(DISTINCT platform_bindings.id) AS platform_binding_count
            FROM usable_emails
            {join_sql}
            LEFT JOIN platform_bindings ON platform_bindings.user_id = usable_emails.user_id
                AND platform_bindings.usable_email_id = usable_emails.id
            WHERE {where_sql}
            GROUP BY usable_emails.id
            ORDER BY usable_emails.id
            LIMIT ? OFFSET ?
            """,
            (*params, page_size, offset),
        ).fetchall()
        email_ids = [row["id"] for row in rows]
        tags_by_email: dict[int, list[Tag]] = {email_id: [] for email_id in email_ids}
        if email_ids:
            placeholders = ",".join("?" for _ in email_ids)
            tag_rows = connection.execute(
                f"""
                SELECT usable_email_tags.usable_email_id, tags.id, tags.name, tags.color
                FROM usable_email_tags
                JOIN tags ON tags.id = usable_email_tags.tag_id AND tags.user_id = ?
                WHERE usable_email_tags.usable_email_id IN ({placeholders})
                ORDER BY tags.id
                """,
                (user_id, *email_ids),
            ).fetchall()
            for row in tag_rows:
                tags_by_email[row["usable_email_id"]].append(
                    Tag(id=row["id"], name=row["name"], color=row["color"])
                )

    emails = tuple(
        WorkbenchEmail(
            id=row["id"],
            address=row["address"],
            label=row["label"],
            kind=row["kind"],
            status=row["status"],
            group=Group(id=row["group_id"], name=row["group_name"], color=row["group_color"])
            if row["group_id"] is not None
            else None,
            tags=tuple(tags_by_email[row["id"]]),
            platform_binding_count=row["platform_binding_count"],
        )
        for row in rows
    )
    return WorkbenchPage(usable_emails=emails, total=total, page=page, page_size=page_size)
