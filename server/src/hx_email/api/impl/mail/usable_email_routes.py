from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, status

from hx_email.api.dependencies import require_user
from hx_email.api.schemas import UsableEmailCreate
from hx_email.api.serializers import serialize_usable_email, serialize_verification_reading
from hx_email.config import Settings
from hx_email.server.mail.usable_emails import (
    add_usable_email,
    deactivate_usable_email,
    get_usable_email,
    list_usable_emails,
)
from hx_email.server.mail.verification import (
    MailboxProvider,
    get_verification_history,
    read_verification,
)


def register_usable_email_routes(
    app: FastAPI,
    settings: Settings,
    mailbox_provider: MailboxProvider,
) -> None:
    @app.post("/usable-emails", status_code=status.HTTP_201_CREATED)
    def create_usable_email(
        payload: UsableEmailCreate,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        usable_email = add_usable_email(settings, user.id, payload.address, payload.label)
        return serialize_usable_email(usable_email)

    @app.get("/usable-emails")
    def get_usable_emails(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, list[dict[str, object]]]:
        user = require_user(settings, authorization)
        return {
            "usable_emails": [
                serialize_usable_email(email) for email in list_usable_emails(settings, user.id)
            ]
        }

    @app.get("/usable-emails/{usable_email_id}")
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
        return serialize_usable_email(usable_email)

    @app.post("/usable-emails/{usable_email_id}/deactivate")
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
        return serialize_usable_email(usable_email)

    @app.post("/usable-emails/{usable_email_id}/verification/read")
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

    @app.get("/usable-emails/{usable_email_id}/verification/history")
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
