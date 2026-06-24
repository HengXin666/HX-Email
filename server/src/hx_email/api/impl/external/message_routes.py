"""External API message routes: messages, verification, wait, probe."""

from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, Query, status

from hx_email.config import Settings
from hx_email.server.external_api import (
    extract_verification_code,
    extract_verification_link,
    get_latest_message,
    get_message_detail,
    get_message_raw,
    get_messages,
    get_probe_status,
    require_api_key,
    wait_for_message,
)
from hx_email.server.mail.verification import MailboxProvider
from hx_email.server.settings_service import get_setting


def external_response(
    success: bool,
    data: object = None,
    code: str = "OK",
    message: str = "success",
    error_code: str | None = None,
) -> dict[str, object]:
    """Build consistent external API response wrapper."""
    if success:
        return {"success": True, "code": code, "message": message, "data": data}
    return {"success": False, "code": error_code or "ERROR", "message": message, "data": None}


def register_external_message_routes(
    app: FastAPI,
    settings: Settings,
    mailbox_provider: MailboxProvider,
) -> None:
    @app.get("/api/external/messages")
    def ext_messages(
        email: str = Query(...),
        folder: str = Query("inbox"),
        skip: int = Query(0),
        top: int = Query(20),
        from_contains: str | None = Query(None),
        subject_contains: str | None = Query(None),
        since_minutes: int | None = Query(None),
        claim_token: str | None = Query(None),
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_api_key(settings, authorization)
        result = get_messages(
            settings,
            mailbox_provider,
            email,
            folder=folder,
            skip=skip,
            top=top,
            from_contains=from_contains,
            subject_contains=subject_contains,
            since_minutes=since_minutes,
            claim_token=claim_token,
        )
        return external_response(True, data=result)

    @app.get("/api/external/messages/latest")
    def ext_latest_message(
        email: str = Query(...),
        folder: str = Query("inbox"),
        from_contains: str | None = Query(None),
        subject_contains: str | None = Query(None),
        since_minutes: int | None = Query(None),
        claim_token: str | None = Query(None),
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_api_key(settings, authorization)
        result = get_latest_message(
            settings,
            mailbox_provider,
            email,
            folder=folder,
            from_contains=from_contains,
            subject_contains=subject_contains,
            since_minutes=since_minutes,
            claim_token=claim_token,
        )
        return external_response(True, data=result)

    @app.get("/api/external/messages/{message_id}")
    def ext_message_detail(
        message_id: str,
        email: str = Query(...),
        folder: str = Query("inbox"),
        claim_token: str | None = Query(None),
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_api_key(settings, authorization)
        result = get_message_detail(
            settings,
            mailbox_provider,
            email,
            message_id,
            folder=folder,
            claim_token=claim_token,
        )
        return external_response(True, data=result)

    @app.get("/api/external/messages/{message_id}/raw")
    def ext_message_raw(
        message_id: str,
        email: str = Query(...),
        folder: str = Query("inbox"),
        claim_token: str | None = Query(None),
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_api_key(settings, authorization)
        disable_raw: str = get_setting(settings, "external_api_disable_raw_content", "false")
        if disable_raw == "true":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Raw content access is disabled",
            )
        result = get_message_raw(
            settings,
            mailbox_provider,
            email,
            message_id,
            folder=folder,
            claim_token=claim_token,
        )
        return external_response(True, data=result)

    @app.get("/api/external/verification-code")
    def ext_verification_code(
        email: str = Query(...),
        folder: str = Query("inbox"),
        from_contains: str | None = Query(None),
        subject_contains: str | None = Query(None),
        since_minutes: int | None = Query(None),
        code_length: int | None = Query(None),
        code_regex: str | None = Query(None),
        code_source: str = Query("all"),
        claim_token: str | None = Query(None),
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_api_key(settings, authorization)
        result = extract_verification_code(
            settings,
            mailbox_provider,
            email,
            folder=folder,
            from_contains=from_contains,
            subject_contains=subject_contains,
            since_minutes=since_minutes,
            code_length=code_length,
            code_regex=code_regex,
            code_source=code_source,
            claim_token=claim_token,
        )
        return external_response(True, data=result)

    @app.get("/api/external/verification-link")
    def ext_verification_link(
        email: str = Query(...),
        folder: str = Query("inbox"),
        from_contains: str | None = Query(None),
        subject_contains: str | None = Query(None),
        since_minutes: int | None = Query(None),
        claim_token: str | None = Query(None),
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_api_key(settings, authorization)
        result = extract_verification_link(
            settings,
            mailbox_provider,
            email,
            folder=folder,
            from_contains=from_contains,
            subject_contains=subject_contains,
            since_minutes=since_minutes,
            claim_token=claim_token,
        )
        return external_response(True, data=result)

    @app.get("/api/external/wait-message")
    def ext_wait_message(
        email: str = Query(...),
        folder: str = Query("inbox"),
        from_contains: str | None = Query(None),
        subject_contains: str | None = Query(None),
        since_minutes: int | None = Query(None),
        timeout_seconds: int = Query(30),
        poll_interval: int = Query(5),
        mode: str = Query("sync"),
        claim_token: str | None = Query(None),
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_api_key(settings, authorization)
        disable_wait: str = get_setting(settings, "external_api_disable_wait_message", "false")
        if disable_wait == "true":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Wait-message is disabled",
            )
        result = wait_for_message(
            settings,
            mailbox_provider,
            email,
            folder=folder,
            from_contains=from_contains,
            subject_contains=subject_contains,
            since_minutes=since_minutes,
            timeout_seconds=timeout_seconds,
            poll_interval=poll_interval,
            mode=mode,
            claim_token=claim_token,
        )
        return external_response(True, data=result)

    @app.get("/api/external/probe/{probe_id}")
    def ext_probe_status(
        probe_id: str,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_api_key(settings, authorization)
        result = get_probe_status(probe_id)
        return external_response(True, data=result)
