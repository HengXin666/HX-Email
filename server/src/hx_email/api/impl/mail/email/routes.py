"""Email operations routes: batch fetch, list, detail, extract, delete."""

from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query

from hx_email.api.dependencies import require_user
from hx_email.api.schemas import BatchEmailRequest, DeleteEmailRequest
from hx_email.config import Settings
from hx_email.server.mail.impl.email_service import (
    batch_fetch_emails,
    delete_emails,
    extract_verification_code,
    fetch_emails,
    get_email_detail,
)
from hx_email.server.mail.verification import MailboxProvider


def register_email_ops_routes(
    router: APIRouter,
    settings: Settings,
    mailbox_provider: MailboxProvider,
) -> None:
    """Register email operations endpoints."""

    @router.post("/emails/batch")
    def batch_fetch(
        payload: BatchEmailRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        return batch_fetch_emails(
            settings,
            mailbox_provider,
            payload.account_ids,
            folders=payload.folders,
            skip=payload.skip,
            top=payload.top,
        )

    @router.post("/emails/delete")
    def delete_emails_endpoint(
        payload: DeleteEmailRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        return delete_emails(
            settings,
            mailbox_provider,
            payload.email,
            payload.ids,
        )

    # Must be registered before catch-all /emails/{email_addr}
    @router.get("/emails/{email_addr}/extract-verification")
    def extract_verification(
        email_addr: str,
        code_length: Annotated[int | None, Query()] = None,
        code_regex: Annotated[str | None, Query()] = None,
        code_source: Annotated[str, Query()] = "all",
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        try:
            compiled = re.compile(code_regex) if code_regex else None
        except re.error as exc:
            raise HTTPException(status_code=400, detail=f"Invalid regex: {exc}") from exc
        _ = compiled
        return extract_verification_code(
            settings,
            mailbox_provider,
            email_addr,
            code_length=code_length,
            code_regex=code_regex,
            code_source=code_source,
        )

    @router.get("/email/{email_addr}/{message_id}")
    def email_detail(
        email_addr: str,
        message_id: str,
        folder: Annotated[str, Query()] = "inbox",
        method: Annotated[str | None, Query()] = None,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        try:
            return get_email_detail(
                settings,
                mailbox_provider,
                email_addr,
                message_id,
                folder=folder,
                method=method,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    # Catch-all list endpoint, registered last
    @router.get("/emails/{email_addr}")
    def email_list(
        email_addr: str,
        folder: Annotated[str, Query()] = "inbox",
        skip: Annotated[int, Query()] = 0,
        top: Annotated[int, Query()] = 20,
        method: Annotated[str | None, Query()] = None,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        return fetch_emails(
            settings,
            mailbox_provider,
            email_addr,
            folder=folder,
            skip=skip,
            top=top,
            method=method,
        )
