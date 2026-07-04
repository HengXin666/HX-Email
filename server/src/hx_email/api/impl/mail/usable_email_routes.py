from typing import Annotated

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
from hx_email.server.mail.impl.fetch.targets import (
    enrich_fetch_account_info,
    resolve_fetch_account_info,
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
        return {"usable_emails": enrich_fetch_account_info(settings, user.id, items)}

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
        account_info = resolve_fetch_account_info(settings, user.id, usable_email_id)
        result = serialize_usable_email(usable_email)
        result["email_account_id"] = account_info.email_account_id
        result["last_refresh_at"] = account_info.last_refresh_at
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
        account_info = resolve_fetch_account_info(settings, user.id, usable_email_id)
        result = serialize_usable_email(usable_email)
        result["email_account_id"] = account_info.email_account_id
        result["last_refresh_at"] = account_info.last_refresh_at
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
        account_info = resolve_fetch_account_info(settings, user.id, usable_email_id)
        return {
            "usable_email": {
                "id": row["id"],
                "address": row["address"],
                "label": row["label"],
                "kind": row["kind"],
                "status": row["status"],
                "email_account_id": account_info.email_account_id,
                "last_refresh_at": account_info.last_refresh_at,
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
        total = get_message_count(settings, usable_email_id)
        return {"messages": messages, "total": total}

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
        account_info = resolve_fetch_account_info(settings, user.id, usable_email_id)
        if account_info.email_account_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This email is not linked to an IMAP account",
            )
        result = fetch_and_store_for_account(
            settings, user.id, account_info.email_account_id, mailbox_provider
        )
        return result
