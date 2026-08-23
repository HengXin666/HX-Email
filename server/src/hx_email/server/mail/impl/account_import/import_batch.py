"""Bulk credential-import executor (one connection, chunked commits).

Replaces the old per-line ``find_account``/``add_email_account``/… calls that
opened 2 SQLite connections and committed twice per imported line. For a 5000
line import that was ~10000 connects + ~10000 fsync commits — minutes on slow
disks (docker volumes / VPS). This module executes a pre-planned op list in a
single connection with chunked commits and one Fernet instance.

Semantics mirror ``add_email_account`` / ``update_account_credentials`` exactly
(same SQL, same error messages), so duplicate handling, counting and error
shapes are unchanged.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from cryptography.fernet import Fernet

from hx_email.config import Settings
from hx_email.database import utc_now_iso
from hx_email.security import ENCRYPTED_PREFIX, load_secret_key
from hx_email.server.auth import require_inserted_id
from hx_email.server.mail.email_accounts import DuplicateUsableEmailError
from hx_email.server.mail.imap.impl.address_guard import validate_proxy_host

BATCH_COMMIT_EVERY: int = 300

ProgressCallback = Callable[[int, int, int], None]  # (processed_ops, imported, failed)


@dataclass(frozen=True)
class ImportOp:
    kind: str  # "add" | "update"
    provider: str
    address: str
    password: str
    imap_host: str
    imap_port: int | None
    client_id: str
    refresh_token: str


def existing_address_ids(connection: sqlite3.Connection, user_id: int) -> dict[str, int]:
    """Preload all primary addresses of the user (address -> account id)."""
    rows = connection.execute(
        "SELECT id, primary_address FROM email_accounts WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    return {str(row["primary_address"]): int(row["id"]) for row in rows}


def _encrypt(fernet: Fernet, value: str) -> str:
    if not value or value.startswith(ENCRYPTED_PREFIX):
        return value
    return f"{ENCRYPTED_PREFIX}{fernet.encrypt(value.encode()).decode()}"


def _add_account(
    connection: sqlite3.Connection,
    user_id: int,
    op: ImportOp,
    group_id: int | None,
    fernet: Fernet,
) -> int:
    """Insert account + primary usable email; returns the new account id.

    Mirrors ``email_accounts.add_email_account`` incl. IntegrityError ->
    DuplicateUsableEmailError with the same messages, and rolls back the
    account row when the usable_emails insert fails (same-transaction
    consistency the old per-line connections gave us).
    """
    created_at: str = utc_now_iso()
    try:
        cursor = connection.execute(
            """
            INSERT INTO email_accounts (
                user_id, provider, primary_address, display_name, imap_host,
                imap_port, username, imap_password, client_id, refresh_token,
                group_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                op.provider,
                op.address,
                op.address,
                op.imap_host,
                op.imap_port,
                op.address,
                op.password,
                op.client_id,
                _encrypt(fernet, op.refresh_token),
                group_id,
                created_at,
            ),
        )
    except sqlite3.IntegrityError:
        raise DuplicateUsableEmailError(
            "Email account primary address already exists for this user"
        ) from None
    account_id: int = require_inserted_id(cursor.lastrowid)
    try:
        connection.execute(
            """
            INSERT INTO usable_emails (
                user_id, email_account_id, address, label, kind, status, active,
                group_id, created_at
            )
            VALUES (?, ?, ?, ?, 'primary', 'active', 1, ?, ?)
            """,
            (user_id, account_id, op.address, op.address, group_id, created_at),
        )
    except sqlite3.IntegrityError:
        connection.execute("DELETE FROM email_accounts WHERE id = ?", (account_id,))
        raise DuplicateUsableEmailError(
            "Usable email address already exists for this user"
        ) from None
    return account_id


def _update_credentials(
    connection: sqlite3.Connection,
    user_id: int,
    account_id: int,
    op: ImportOp,
    fernet: Fernet,
) -> None:
    """Mirrors ``account_transfer.update_account_credentials``."""
    if op.imap_host.strip():
        validate_proxy_host(op.imap_host)
    connection.execute(
        """
        UPDATE email_accounts
        SET provider = ?, imap_host = ?, imap_port = ?, username = ?,
            imap_password = ?, client_id = ?, refresh_token = ?, status = 'active'
        WHERE id = ? AND user_id = ?
        """,
        (
            op.provider,
            op.imap_host,
            op.imap_port,
            op.address,
            op.password,
            op.client_id,
            _encrypt(fernet, op.refresh_token),
            account_id,
            user_id,
        ),
    )
    connection.execute(
        """
        UPDATE usable_emails
        SET status = 'active', active = 1
        WHERE user_id = ? AND email_account_id = ? AND kind = 'primary'
        """,
        (user_id, account_id),
    )


def execute_batch_ops(
    connection: sqlite3.Connection,
    settings: Settings,
    user_id: int,
    ops: list[ImportOp],
    *,
    existing: dict[str, int],
    group_id: int | None,
    errors: list[dict[str, object]],
    by_provider: dict[str, dict[str, int]] | None = None,
    on_progress: ProgressCallback | None = None,
) -> tuple[int, int]:
    """Execute planned ops; returns (imported, failed). Appends failures to errors."""
    if not ops:
        return 0, 0
    fernet: Fernet = Fernet(load_secret_key(settings))
    group_exists: bool = True
    allowed_provider: str = ""
    if group_id is not None:
        row = connection.execute(
            "SELECT allowed_provider FROM groups WHERE id = ? AND user_id = ?",
            (group_id, user_id),
        ).fetchone()
        group_exists = row is not None
        allowed_provider = "" if row is None else str(row["allowed_provider"] or "").strip().lower()

    processed: int = 0
    failed: int = 0
    imported: int = 0
    added_ids: dict[str, int] = {}
    for processed, op in enumerate(ops, 1):
        try:
            if op.kind == "update":
                account_id = added_ids.get(op.address) or existing.get(op.address)
                if account_id is None:
                    raise ValueError("account no longer exists")
                _update_credentials(connection, user_id, account_id, op, fernet)
            else:
                if group_id is not None and (
                    not group_exists or (allowed_provider and allowed_provider != op.provider)
                ):
                    raise ValueError(
                        f"Group does not allow provider '{op.provider}' (channel restricted)"
                    )
                if op.imap_host.strip():
                    validate_proxy_host(op.imap_host)
                account_id = _add_account(connection, user_id, op, group_id, fernet)
                added_ids[op.address] = account_id
            imported += 1
            if by_provider is not None:
                by_provider.setdefault(op.provider, {"imported": 0, "skipped": 0, "failed": 0})[
                    "imported"
                ] += 1
        except (DuplicateUsableEmailError, ValueError) as exc:
            failed += 1
            if by_provider is not None:
                by_provider.setdefault(op.provider, {"imported": 0, "skipped": 0, "failed": 0})[
                    "failed"
                ] += 1
            errors.append({"email": op.address, "error": str(exc)})
        if processed % BATCH_COMMIT_EVERY == 0:
            connection.commit()
            if on_progress is not None:
                on_progress(processed, imported, failed)
    connection.commit()
    if on_progress is not None:
        on_progress(len(ops), imported, failed)
    return imported, failed
