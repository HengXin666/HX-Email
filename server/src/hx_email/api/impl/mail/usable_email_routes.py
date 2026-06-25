from typing import Annotated, cast

from fastapi import APIRouter, Header, HTTPException, status

from hx_email.api.dependencies import require_user
from hx_email.api.schemas import UsableEmailCreate
from hx_email.api.serializers import serialize_usable_email, serialize_verification_reading
from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.mail.imap.message_store import (
    get_message_count,
)
from hx_email.server.mail.imap.message_store import (
    get_messages as get_stored_messages,
)
from hx_email.server.mail.impl.email_fetch_service import (
    fetch_and_store_for_account,
)
from hx_email.server.mail.usable_emails import (
    add_usable_email,
    deactivate_usable_email,
    delete_usable_email,
    get_usable_email,
    list_usable_emails,
)
from hx_email.server.mail.verification import (
    MailboxProvider,
    get_verification_history,
    get_verification_state,
    read_verification,
)


def _lookup_account_refresh(
    settings: Settings,
    email_account_id: int | None,
) -> str | None:
    """Return last_refresh_at for an email account, or None."""
    if email_account_id is None:
        return None
    with connect(settings) as conn:
        row = conn.execute(
            "SELECT last_refresh_at FROM email_accounts WHERE id = ?",
            (email_account_id,),
        ).fetchone()
    return row["last_refresh_at"] if row else None


def _batch_enrich_refresh(
    settings: Settings,
    items: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Add last_refresh_at to a list of serialized usable-email dicts via a
    single batch query against email_accounts."""
    account_ids: list[int] = [
        cast(int, i["email_account_id"])
        for i in items
        if isinstance(i.get("email_account_id"), int)
    ]
    if not account_ids:
        for item in items:
            item["last_refresh_at"] = None
        return items
    with connect(settings) as conn:
        placeholders = ",".join("?" for _ in account_ids)
        rows = conn.execute(
            f"SELECT id, last_refresh_at FROM email_accounts WHERE id IN ({placeholders})",
            account_ids,
        ).fetchall()
    refresh_map: dict[int, str | None] = {r["id"]: r["last_refresh_at"] for r in rows}
    for item in items:
        aid = item.get("email_account_id")
        item["last_refresh_at"] = refresh_map.get(aid) if isinstance(aid, int) else None
    return items


def _resolve_account_info(
    settings: Settings,
    user_id: int,
    usable_email_id: int,
) -> tuple[int | None, str | None]:
    """Return (email_account_id, last_refresh_at) by joining usable_emails
    with email_accounts.
    get_usable_email() omits email_account_id from its SELECT, so callers
    that need it should use this helper instead of relying on the
    UsableEmail object.
    """
    with connect(settings) as conn:
        row = conn.execute(
            """
            SELECT ue.email_account_id, ea.last_refresh_at
            FROM usable_emails ue
            LEFT JOIN email_accounts ea ON ea.id = ue.email_account_id
            WHERE ue.id = ? AND ue.user_id = ?
            """,
            (usable_email_id, user_id),
        ).fetchone()
    if row is None:
        return None, None
    return row["email_account_id"], row["last_refresh_at"]


def register_usable_email_routes(
    router: APIRouter,
    settings: Settings,
    mailbox_provider: MailboxProvider,
) -> None:
    @router.post("/usable-emails", status_code=status.HTTP_201_CREATED)
    def create_usable_email(
        payload: UsableEmailCreate,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        usable_email = add_usable_email(settings, user.id, payload.address, payload.label)
        result = serialize_usable_email(usable_email)
        result["last_refresh_at"] = None
        return result

    @router.get("/usable-emails")
    def get_usable_emails(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, list[dict[str, object]]]:
        user = require_user(settings, authorization)
        items = [serialize_usable_email(email) for email in list_usable_emails(settings, user.id)]
        return {"usable_emails": _batch_enrich_refresh(settings, items)}

    @router.get("/usable-emails/{usable_email_id}")
    def get_usable_email_detail(
        usable_email_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        usable_email = get_usable_email(settings, user.id, usable_email_id)
        if usable_email is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Usable email not found"
            )
        email_account_id, last_refresh_at = _resolve_account_info(
            settings,
            user.id,
            usable_email_id,
        )
        result = serialize_usable_email(usable_email)
        result["email_account_id"] = email_account_id
        result["last_refresh_at"] = last_refresh_at
        return result

    @router.post("/usable-emails/{usable_email_id}/deactivate")
    def deactivate_email(
        usable_email_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        usable_email = deactivate_usable_email(settings, user.id, usable_email_id)
        if usable_email is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Usable email not found"
            )
        email_account_id, last_refresh_at = _resolve_account_info(
            settings,
            user.id,
            usable_email_id,
        )
        result = serialize_usable_email(usable_email)
        result["email_account_id"] = email_account_id
        result["last_refresh_at"] = last_refresh_at
        return result

    @router.delete("/usable-emails/{usable_email_id}")
    def delete_email(
        usable_email_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        ok = delete_usable_email(settings, user.id, usable_email_id)
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    "Usable email not found or linked to an account (use delete account instead)"
                ),
            )
        return {"success": True, "message": "Email permanently deleted"}

    @router.post("/usable-emails/{usable_email_id}/activate")
    def activate_email(
        usable_email_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        with connect(settings) as connection:
            row = connection.execute(
                "UPDATE usable_emails SET status = 'active', active = 1 "
                "WHERE id = ? AND user_id = ? "
                "RETURNING id, address, label, kind, status, email_account_id",
                (usable_email_id, user.id),
            ).fetchone()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Usable email not found"
            )
        email_account_id: int | None = row["email_account_id"]
        return {
            "usable_email": {
                "id": row["id"],
                "address": row["address"],
                "label": row["label"],
                "kind": row["kind"],
                "status": row["status"],
                "email_account_id": email_account_id,
                "last_refresh_at": _lookup_account_refresh(settings, email_account_id),
            }
        }

    @router.post("/usable-emails/{usable_email_id}/verification/read")
    def read_email_verification(
        usable_email_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        reading = read_verification(settings, user.id, usable_email_id, mailbox_provider)
        if reading is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Usable email not found"
            )
        return serialize_verification_reading(reading)

    @router.get("/usable-emails/{usable_email_id}/verification/history")
    def get_email_verification_history(
        usable_email_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        reading = get_verification_history(settings, user.id, usable_email_id)
        if reading is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Usable email not found"
            )
        return serialize_verification_reading(reading)

    @router.get("/usable-emails/{usable_email_id}/verification/state")
    def get_email_verification_state(
        usable_email_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        state = get_verification_state(settings, user.id, usable_email_id)
        msg_count = get_message_count(settings, usable_email_id)
        return {
            "last_extracted_at": state.last_extracted_at,
            "seen_codes": list(state.seen_codes),
            "message_count": msg_count,
        }

    @router.get("/usable-emails/{usable_email_id}/messages")
    def list_email_messages(
        usable_email_id: int,
        authorization: Annotated[str | None, Header()] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, object]:
        """List persisted email messages for a usable_email, newest first."""
        user = require_user(settings, authorization)
        email = get_usable_email(settings, user.id, usable_email_id)
        if email is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Usable email not found"
            )
        messages = get_stored_messages(settings, usable_email_id, limit=limit, offset=offset)
        return {"messages": messages, "total": len(messages)}

    @router.post("/usable-emails/{usable_email_id}/fetch-emails")
    def trigger_email_fetch(
        usable_email_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        """Trigger IMAP fetch for this email's account, storing messages and extracting codes."""
        user = require_user(settings, authorization)
        email = get_usable_email(settings, user.id, usable_email_id)
        if email is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Usable email not found"
            )
        with connect(settings) as conn:
            row = conn.execute(
                "SELECT email_account_id FROM usable_emails WHERE id = ? AND user_id = ?",
                (usable_email_id, user.id),
            ).fetchone()
        if row is None or not row["email_account_id"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This email is not linked to an IMAP account",
            )
        result = fetch_and_store_for_account(settings, user.id, row["email_account_id"])
        return result
