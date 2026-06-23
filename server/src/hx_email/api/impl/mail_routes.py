from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, status

from hx_email.api.dependencies import require_user
from hx_email.api.schemas import AliasCreate, EmailAccountCreate, UsableEmailCreate
from hx_email.api.serializers import (
    serialize_email_account,
    serialize_usable_email,
    serialize_verification_reading,
)
from hx_email.config import Settings
from hx_email.server.mail.email_accounts import (
    DuplicateUsableEmailError,
    InvalidAliasAddressError,
    add_alias_to_email_account,
    add_email_account,
    deactivate_email_account,
    get_email_account,
)
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


def register_mail_routes(
    app: FastAPI,
    settings: Settings,
    mailbox_provider: MailboxProvider,
) -> None:
    register_usable_email_routes(app, settings, mailbox_provider)
    register_email_account_routes(app, settings)


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


def register_email_account_routes(app: FastAPI, settings: Settings) -> None:
    @app.post("/email-accounts", status_code=status.HTTP_201_CREATED)
    def create_email_account(
        payload: EmailAccountCreate,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        try:
            account = add_email_account(
                settings,
                user.id,
                payload.provider,
                payload.primary_address,
                payload.display_name,
                payload.imap_host,
                payload.imap_port,
                payload.username,
                payload.alias_addresses,
            )
        except InvalidAliasAddressError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except DuplicateUsableEmailError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
        return serialize_email_account(account)

    @app.get("/email-accounts/{account_id}")
    def get_account(
        account_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        account = get_email_account(settings, user.id, account_id)
        if account is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Email account not found"
            )
        return serialize_email_account(account)

    @app.post("/email-accounts/{account_id}/aliases", status_code=status.HTTP_201_CREATED)
    def create_account_alias(
        account_id: int,
        payload: AliasCreate,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        try:
            alias = add_alias_to_email_account(
                settings,
                user.id,
                account_id,
                payload.address,
                payload.label or payload.address,
            )
        except InvalidAliasAddressError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except DuplicateUsableEmailError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
        if alias is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Email account not found"
            )
        return serialize_usable_email(alias)

    @app.post("/email-accounts/{account_id}/deactivate")
    def deactivate_account(
        account_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        account = deactivate_email_account(settings, user.id, account_id)
        if account is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Email account not found"
            )
        return serialize_email_account(account)
