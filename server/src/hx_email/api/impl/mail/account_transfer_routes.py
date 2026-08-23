"""Account transfer routes — async import (job + progress), export, provider listing."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Response, status

from hx_email.api.dependencies import require_user
from hx_email.api.schemas import AccountTextImport
from hx_email.config import Settings
from hx_email.server.mail.impl.account_import.import_jobs import (
    get_import_job,
    start_import_job,
)
from hx_email.server.mail.impl.account_import.line_parse import get_provider_list
from hx_email.server.mail.impl.accounts.account_transfer import (
    export_account_text,
    normalize_lines,
)


def register_account_transfer_routes(router: APIRouter, settings: Settings) -> None:
    # ---- Import (async job so the UI can show real progress) ----

    @router.post("/email-accounts/import", status_code=status.HTTP_202_ACCEPTED)
    def import_accounts(
        payload: AccountTextImport,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        total: int = len(normalize_lines(payload.text))
        job = start_import_job(
            settings,
            user.id,
            payload.text,
            provider=payload.provider,
            group_id=payload.group_id,
            duplicate_strategy=payload.duplicate_strategy,
            custom_imap_host=payload.custom_imap_host,
            custom_imap_port=payload.custom_imap_port,
            total=total,
        )
        return job.snapshot()

    # ---- Import job status / result (polled by the frontend) ----

    @router.get("/email-accounts/import/{job_id}")
    def import_job_status(
        job_id: str,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        job = get_import_job(user.id, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Import job not found (server restarted?)")
        return job.snapshot()

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
