from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, status

from hx_email.api.dependencies import require_user
from hx_email.api.schemas import AliasCreate, EmailAccountCreate
from hx_email.api.serializers import serialize_email_account, serialize_usable_email
from hx_email.config import Settings
from hx_email.server.mail.email_accounts import (
    DuplicateUsableEmailError,
    InvalidAliasAddressError,
    add_alias_to_email_account,
    add_email_account,
    deactivate_email_account,
    get_email_account,
    list_email_accounts,
)


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
                payload.imap_password,
                payload.client_id,
                payload.refresh_token,
                payload.alias_addresses,
            )
        except InvalidAliasAddressError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except DuplicateUsableEmailError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
        return serialize_email_account(account)

    @app.get("/email-accounts")
    def get_accounts(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, list[dict[str, object]]]:
        user = require_user(settings, authorization)
        return {
            "email_accounts": [
                serialize_email_account(account)
                for account in list_email_accounts(settings, user.id)
            ]
        }

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
