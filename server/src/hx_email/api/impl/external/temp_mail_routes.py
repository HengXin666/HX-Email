"""External API temp mail routes: apply and finish temp email tasks."""

from typing import Annotated

from fastapi import FastAPI, Header

from hx_email.api.schemas import ExternalTempMailApply, ExternalTempMailFinish
from hx_email.config import Settings
from hx_email.server.external_api import (
    apply_temp_email,
    finish_temp_email,
    require_api_key,
)
from hx_email.server.mail.temp_mail import TempMailProvider


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


def register_external_temp_mail_routes(
    app: FastAPI,
    settings: Settings,
    temp_mail_providers: dict[str, TempMailProvider],
) -> None:
    @app.post("/api/external/temp-emails/apply")
    def ext_temp_email_apply(
        payload: ExternalTempMailApply,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_api_key(settings, authorization)
        result = apply_temp_email(
            settings,
            temp_mail_providers,
            caller_id=payload.caller_id,
            task_id=payload.task_id,
            prefix=payload.prefix,
            domain=payload.domain,
        )
        if not result.get("success"):
            return external_response(False, data=result, error_code="APPLY_FAILED")
        return external_response(True, data=result)

    @app.post("/api/external/temp-emails/{task_token}/finish")
    def ext_temp_email_finish(
        task_token: str,
        payload: ExternalTempMailFinish,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_api_key(settings, authorization)
        result = finish_temp_email(
            settings,
            task_token,
            result=payload.result,
            detail=payload.detail,
        )
        if not result.get("success"):
            return external_response(False, data=result, error_code="FINISH_FAILED")
        return external_response(True, data=result)
