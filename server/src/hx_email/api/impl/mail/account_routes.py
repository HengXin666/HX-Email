from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, status

from hx_email.api.dependencies import require_user
from hx_email.api.schemas import (
    AccountUpdate,
    AliasCreate,
    EmailAccountCreate,
    RemarkUpdate,
)
from hx_email.api.serializers import serialize_email_account, serialize_usable_email
from hx_email.config import Settings
from hx_email.server.mail.email_accounts import (
    DuplicateUsableEmailError,
    InvalidAliasAddressError,
    add_alias_to_email_account,
    add_email_account,
    deactivate_email_account,
    get_email_account,
)
from hx_email.server.mail.impl.accounts import (
    delete_email_account,
    delete_email_account_by_email,
    list_email_accounts_enhanced,
    search_email_accounts,
    update_account_remark,
    update_email_account,
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

    @app.put("/email-accounts/{account_id}")
    def update_account(
        account_id: int,
        payload: AccountUpdate,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        account = update_email_account(
            settings,
            user.id,
            account_id,
            email=payload.email,
            password=payload.password,
            client_id=payload.client_id,
            refresh_token=payload.refresh_token,
            group_id=payload.group_id,
            remark=payload.remark,
            status=payload.status,
            provider=payload.provider,
            imap_host=payload.imap_host,
            imap_port=payload.imap_port,
        )
        if account is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Email account not found"
            )
        return serialize_email_account(account)

    @app.delete("/email-accounts/{account_id}")
    def delete_account(
        account_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        if not delete_email_account(settings, user.id, account_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Email account not found"
            )
        return {"success": True}

    @app.patch("/email-accounts/{account_id}/remark")
    def update_account_remark_handler(
        account_id: int,
        payload: RemarkUpdate,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        account = update_account_remark(settings, user.id, account_id, payload.remark)
        if account is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Email account not found"
            )
        return serialize_email_account(account)

    @app.delete("/email-accounts/email/{email_addr:path}")
    def delete_account_by_email(
        email_addr: str,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        if not delete_email_account_by_email(settings, user.id, email_addr):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Email account not found"
            )
        return {"success": True}

    @app.get("/email-accounts/search")
    def search_accounts(
        q: str,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        accounts = search_email_accounts(settings, user.id, q)
        return {
            "accounts": [serialize_email_account(a) for a in accounts],
            "total": len(accounts),
        }

    @app.get("/email-accounts")
    def get_accounts_enhanced(
        authorization: Annotated[str | None, Header()] = None,
        group_id: int | None = None,
        page: int = 1,
        page_size: int = 50,
        search: str | None = None,
        sort_by: str | None = None,
        sort_order: str | None = None,
        tag_id: int | None = None,
        tag_ids: str | None = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        parsed_tag_ids: list[int] | None = None
        if tag_ids:
            try:
                parsed_tag_ids = [int(t.strip()) for t in tag_ids.split(",") if t.strip()]
            except ValueError:
                parsed_tag_ids = []
        result = list_email_accounts_enhanced(
            settings,
            user.id,
            group_id=group_id,
            page=page,
            page_size=page_size,
            search=search,
            sort_by=sort_by,
            sort_order=sort_order,
            tag_id=tag_id,
            tag_ids=parsed_tag_ids,
        )
        total_pages = max(1, (result.total_count + result.page_size - 1) // result.page_size)
        return {
            "accounts": [serialize_email_account(a) for a in result.accounts],
            "pagination": {
                "page": result.page,
                "page_size": result.page_size,
                "total_count": result.total_count,
                "total_pages": total_pages,
            },
        }
