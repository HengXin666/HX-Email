from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, Response, status

from hx_email.api.dependencies import require_user
from hx_email.api.schemas import AccountTextImport
from hx_email.config import Settings
from hx_email.server.mail.impl.account_transfer import (
    export_account_text,
    import_account_text,
)


def register_account_transfer_routes(app: FastAPI, settings: Settings) -> None:
    @app.post("/email-accounts/import", status_code=status.HTTP_201_CREATED)
    def import_accounts(
        payload: AccountTextImport,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        return import_account_text(
            settings,
            user.id,
            payload.text,
            payload.duplicate_strategy,
        )

    @app.get("/email-accounts/export-text")
    def export_accounts(
        authorization: Annotated[str | None, Header()] = None,
    ) -> Response:
        user = require_user(settings, authorization)
        text = export_account_text(settings, user.id)
        headers = {
            "Content-Disposition": 'attachment; filename="hx-email-accounts.txt"',
        }
        return Response(text, media_type="text/plain; charset=utf-8", headers=headers)

    @app.post("/email-accounts/import-preview")
    def preview_import_accounts(
        payload: AccountTextImport,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        if not payload.text.strip():
            raise HTTPException(status_code=422, detail="Import text is empty")
        return {"line_count": len(payload.text.splitlines())}
