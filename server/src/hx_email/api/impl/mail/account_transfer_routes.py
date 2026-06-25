"""Account transfer routes — import, export, provider listing."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Response, status

from hx_email.api.dependencies import require_user
from hx_email.api.schemas import AccountTextImport
from hx_email.config import Settings
from hx_email.server.mail.impl.accounts.account_transfer import (
    export_account_text,
)
from hx_email.server.mail.impl.accounts.import_service import (
    get_provider_list,
    import_accounts_with_provider,
)


def register_account_transfer_routes(router: APIRouter, settings: Settings) -> None:
    # ---- Import (legacy + enhanced) ----

    @router.post("/email-accounts/import", status_code=status.HTTP_201_CREATED)
    def import_accounts(
        payload: AccountTextImport,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        return import_accounts_with_provider(
            settings,
            user.id,
            payload.text,
            provider=payload.provider,
            group_id=payload.group_id,
            add_to_pool=payload.add_to_pool,
            duplicate_strategy=payload.duplicate_strategy,
            custom_imap_host=payload.custom_imap_host,
            custom_imap_port=payload.custom_imap_port,
        )

    # ---- Export ----

    @router.get("/email-accounts/export-text")
    def export_accounts(
        authorization: Annotated[str | None, Header()] = None,
    ) -> Response:
        user = require_user(settings, authorization)
        text: str = export_account_text(settings, user.id)
        headers: dict[str, str] = {
            "Content-Disposition": 'attachment; filename="hx-email-accounts.txt"',
        }
        return Response(text, media_type="text/plain; charset=utf-8", headers=headers)

    # ---- Import preview ----

    @router.post("/email-accounts/import-preview")
    def preview_import_accounts(
        payload: AccountTextImport,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        if not payload.text.strip():
            raise HTTPException(status_code=422, detail="Import text is empty")
        return {"line_count": len(payload.text.splitlines())}

    # ---- Provider list ----

    @router.get("/email-accounts/providers")
    def list_providers(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        require_user(settings, authorization)
        return {"success": True, "providers": get_provider_list()}
