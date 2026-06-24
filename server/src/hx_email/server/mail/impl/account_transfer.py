import re
from dataclasses import dataclass
from sqlite3 import Connection, Row

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.mail.email_accounts import (
    DuplicateUsableEmailError,
    add_email_account,
)
from hx_email.server.mail.impl.providers import infer_provider, provider_defaults


@dataclass(frozen=True)
class ParsedAccountLine:
    address: str
    password: str
    provider: str
    imap_host: str
    imap_port: int | None
    client_id: str
    refresh_token: str


EMAIL_PATTERN: re.Pattern[str] = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def import_account_text(
    settings: Settings,
    user_id: int,
    text: str,
    duplicate_strategy: str,
) -> dict[str, object]:
    strategy: str = duplicate_strategy if duplicate_strategy in {"skip", "overwrite"} else "skip"
    imported: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[dict[str, object]] = []

    for line_number, line in enumerate(normalize_lines(text), 1):
        try:
            parsed = parse_account_line(line)
        except ValueError as error:
            failed += 1
            errors.append({"line": line_number, "error": str(error)})
            continue

        existing = find_account(settings, user_id, parsed.address)
        if existing is not None and strategy == "skip":
            skipped += 1
            continue
        if existing is not None:
            update_account_credentials(settings, user_id, int(existing["id"]), parsed)
            imported += 1
            continue

        try:
            add_email_account(
                settings,
                user_id,
                parsed.provider,
                parsed.address,
                parsed.address,
                parsed.imap_host,
                parsed.imap_port,
                parsed.address,
                parsed.password,
                parsed.client_id,
                parsed.refresh_token,
                [],
            )
            imported += 1
        except DuplicateUsableEmailError as error:
            failed += 1
            errors.append({"line": line_number, "email": parsed.address, "error": str(error)})

    return {
        "imported": imported,
        "skipped": skipped,
        "failed": failed,
        "errors": errors[:50],
        "errors_total": len(errors),
        "duplicate_strategy": strategy,
    }


def export_account_text(settings: Settings, user_id: int) -> str:
    with connect(settings) as connection:
        rows = connection.execute(
            """
            SELECT primary_address, provider, imap_host, imap_port, imap_password,
                   client_id, refresh_token
            FROM email_accounts
            WHERE user_id = ? AND status = 'active'
            ORDER BY id
            """,
            (user_id,),
        ).fetchall()
    return "\n".join(format_account_line(row) for row in rows)


def save_oauth_credentials(
    settings: Settings,
    user_id: int,
    account_id: int,
    client_id: str,
    refresh_token: str,
) -> bool:
    with connect(settings) as connection:
        cursor = connection.execute(
            """
            UPDATE email_accounts
            SET provider = 'outlook', client_id = ?, refresh_token = ?
            WHERE id = ? AND user_id = ?
            """,
            (client_id, refresh_token, account_id, user_id),
        )
    return cursor.rowcount > 0


def create_oauth_account(
    settings: Settings,
    user_id: int,
    address: str,
    client_id: str,
    refresh_token: str,
) -> int:
    account = add_email_account(
        settings,
        user_id,
        "outlook",
        address,
        address,
        "",
        None,
        address,
        "",
        client_id,
        refresh_token,
        [],
    )
    return account.id


def normalize_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        line: str = raw.strip()
        if not line or line.startswith("#"):
            continue
        if lines and "----" not in line:
            lines[-1] += line
        else:
            lines.append(line)
    return lines


def parse_account_line(line: str) -> ParsedAccountLine:
    parts: list[str] = [part.strip() for part in line.split("----")]
    if len(parts) not in {2, 3, 4, 5}:
        raise ValueError("Account line must have 2, 3, 4, or 5 segments")
    address: str = parts[0]
    if not EMAIL_PATTERN.match(address):
        raise ValueError("Invalid email address")

    if len(parts) == 4:
        return ParsedAccountLine(address, parts[1], "outlook", "", None, parts[2], parts[3])

    provider: str = infer_provider(address) if len(parts) == 2 else parts[2].lower()
    if provider == "outlook":
        raise ValueError(
            "Outlook accounts must use email----password----client_id----refresh_token"
        )
    defaults = provider_defaults(provider)
    host: str = defaults.imap_host
    port: int | None = defaults.imap_port
    if len(parts) == 5:
        host = parts[3]
        port = parse_port(parts[4])
    if not host:
        raise ValueError("Custom IMAP import requires host and port")
    return ParsedAccountLine(address, parts[1], provider, host, port, "", "")


def parse_port(value: str) -> int:
    try:
        port: int = int(value)
    except ValueError as error:
        raise ValueError("Invalid IMAP port") from error
    if port < 1 or port > 65535:
        raise ValueError("Invalid IMAP port")
    return port


def find_account(settings: Settings, user_id: int, address: str) -> Row | None:
    with connect(settings) as connection:
        row: Row | None = connection.execute(
            """
            SELECT id
            FROM email_accounts
            WHERE user_id = ? AND primary_address = ?
            """,
            (user_id, address),
        ).fetchone()
    return row


def update_account_credentials(
    settings: Settings,
    user_id: int,
    account_id: int,
    parsed: ParsedAccountLine,
) -> None:
    with connect(settings) as connection:
        connection.execute(
            """
            UPDATE email_accounts
            SET provider = ?, imap_host = ?, imap_port = ?, username = ?,
                imap_password = ?, client_id = ?, refresh_token = ?, status = 'active'
            WHERE id = ? AND user_id = ?
            """,
            (
                parsed.provider,
                parsed.imap_host,
                parsed.imap_port,
                parsed.address,
                parsed.password,
                parsed.client_id,
                parsed.refresh_token,
                account_id,
                user_id,
            ),
        )
        reactivate_account_emails(connection, user_id, account_id)


def reactivate_account_emails(connection: Connection, user_id: int, account_id: int) -> None:
    connection.execute(
        """
        UPDATE usable_emails
        SET status = 'active', active = 1
        WHERE user_id = ? AND email_account_id = ? AND kind = 'primary'
        """,
        (user_id, account_id),
    )


def format_account_line(row: Row) -> str:
    provider: str = str(row["provider"] or "")
    address: str = str(row["primary_address"] or "")
    password: str = str(row["imap_password"] or "")
    client_id: str = str(row["client_id"] or "")
    refresh_token: str = str(row["refresh_token"] or "")
    if provider == "outlook" or refresh_token:
        return f"{address}----{password}----{client_id}----{refresh_token}"
    if provider == "custom":
        host: str = str(row["imap_host"] or "")
        port: object = row["imap_port"] or 993
        return f"{address}----{password}----custom----{host}----{port}"
    return f"{address}----{password}----{provider}"
