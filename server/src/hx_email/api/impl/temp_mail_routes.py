from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, status

from hx_email.api.dependencies import require_user
from hx_email.api.schemas import TempMailboxCreate
from hx_email.api.serializers import serialize_temp_mailbox
from hx_email.config import Settings
from hx_email.server.mail.email_accounts import DuplicateUsableEmailError
from hx_email.server.mail.temp_mail import (
    MissingTempMailProviderError,
    TempMailboxNotFoundError,
    TempMailMessage,
    TempMailProvider,
    archive_temp_mailbox,
    create_cf_temp_mailbox,
    extract_codes,
    extract_links,
    list_temp_messages,
)


def register_temp_mail_routes(
    app: FastAPI,
    settings: Settings,
    temp_mail_providers: dict[str, TempMailProvider],
) -> None:
    @app.post("/temp-mail/cf/mailboxes", status_code=status.HTTP_201_CREATED)
    def create_temp_mailbox(
        payload: TempMailboxCreate,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        provider = temp_mail_providers.get("cf")
        if provider is None:
            detail = "CF temp mail provider not configured"
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)
        try:
            mailbox = create_cf_temp_mailbox(
                settings,
                user.id,
                provider,
                address=payload.address,
                label=payload.label,
            )
        except DuplicateUsableEmailError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
        return serialize_temp_mailbox(mailbox)

    @app.post("/temp-mail/{usable_email_id}/archive")
    def archive_temp_mail(
        usable_email_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        mailbox = archive_temp_mailbox(settings, user.id, usable_email_id)
        if mailbox is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Temp mailbox not found"
            )
        return serialize_temp_mailbox(mailbox)

    register_temp_mail_read_routes(app, settings, temp_mail_providers)


def register_temp_mail_read_routes(
    app: FastAPI,
    settings: Settings,
    temp_mail_providers: dict[str, TempMailProvider],
) -> None:
    @app.get("/temp-mail/{usable_email_id}/messages")
    def get_temp_mail_messages(
        usable_email_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, list[dict[str, object]]]:
        user = require_user(settings, authorization)
        messages = load_temp_messages(settings, user.id, usable_email_id, temp_mail_providers)
        return {
            "messages": [
                {
                    "id": message.id,
                    "from_address": message.from_address,
                    "subject": message.subject,
                    "text": message.text,
                    "html": message.html,
                }
                for message in messages
            ]
        }

    @app.get("/temp-mail/{usable_email_id}/codes")
    def get_temp_mail_codes(
        usable_email_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, list[dict[str, str]]]:
        user = require_user(settings, authorization)
        messages = load_temp_messages(settings, user.id, usable_email_id, temp_mail_providers)
        return {
            "codes": [
                {"message_id": code.message_id, "code": code.code}
                for code in extract_codes(messages)
            ]
        }

    @app.get("/temp-mail/{usable_email_id}/verification-links")
    def get_temp_mail_verification_links(
        usable_email_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, list[dict[str, str]]]:
        user = require_user(settings, authorization)
        messages = load_temp_messages(settings, user.id, usable_email_id, temp_mail_providers)
        return {
            "links": [
                {"message_id": link.message_id, "url": link.url} for link in extract_links(messages)
            ]
        }


def load_temp_messages(
    settings: Settings,
    user_id: int,
    usable_email_id: int,
    temp_mail_providers: dict[str, TempMailProvider],
) -> tuple[TempMailMessage, ...]:
    try:
        return list_temp_messages(settings, user_id, usable_email_id, temp_mail_providers)
    except TempMailboxNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except MissingTempMailProviderError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
        ) from error
