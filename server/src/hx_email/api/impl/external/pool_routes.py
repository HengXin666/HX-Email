"""External API pool routes: claim, release, complete, stats."""

from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, status

from hx_email.api.schemas import (
    ExternalPoolClaim,
    ExternalPoolComplete,
    ExternalPoolRelease,
)
from hx_email.config import Settings
from hx_email.server.external_api import (
    claim_complete,
    claim_random,
    claim_release,
    get_pool_stats,
    require_api_key,
)
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


def _check_pool_enabled(settings: Settings) -> None:
    """Raise 403 if pool external is disabled."""
    pool_enabled: str = get_setting(settings, "pool_external_enabled", "false")
    if pool_enabled != "true":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Pool external API is disabled",
        )


def register_external_pool_routes(app: FastAPI, settings: Settings) -> None:
    @app.post("/api/external/pool/claim-random")
    def ext_pool_claim_random(
        payload: ExternalPoolClaim,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_api_key(settings, authorization)
        _check_pool_enabled(settings)
        result = claim_random(
            settings,
            caller_id=payload.caller_id,
            task_id=payload.task_id,
            provider=payload.provider,
            project_key=payload.project_key,
            email_domain=payload.email_domain,
        )
        if result is None:
            return external_response(
                False,
                code="NO_ACCOUNT",
                message="No available email in pool",
                error_code="NO_ACCOUNT",
            )
        return external_response(True, data=result)

    @app.post("/api/external/pool/claim-release")
    def ext_pool_claim_release(
        payload: ExternalPoolRelease,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_api_key(settings, authorization)
        _check_pool_enabled(settings)
        result = claim_release(
            settings,
            account_id=payload.account_id,
            claim_token=payload.claim_token,
            caller_id=payload.caller_id,
            task_id=payload.task_id,
            reason=payload.reason,
        )
        return external_response(bool(result["success"]), data=result)

    @app.post("/api/external/pool/claim-complete")
    def ext_pool_claim_complete(
        payload: ExternalPoolComplete,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_api_key(settings, authorization)
        _check_pool_enabled(settings)
        result = claim_complete(
            settings,
            account_id=payload.account_id,
            claim_token=payload.claim_token,
            caller_id=payload.caller_id,
            task_id=payload.task_id,
            result=payload.result,
            detail=payload.detail,
        )
        return external_response(bool(result["success"]), data=result)

    @app.get("/api/external/pool/stats")
    def ext_pool_stats(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_api_key(settings, authorization)
        _check_pool_enabled(settings)
        result = get_pool_stats(settings)
        return external_response(True, data=result)
