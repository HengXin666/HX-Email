from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, FastAPI, Header, Query, Request, Response

from hx_email.api.dependencies import require_admin
from hx_email.config import Settings
from hx_email.server.admin import AuditRequest, AuditResponse, AuditTrail, get_audit_logs


def register_audit_middleware(app: FastAPI, settings: Settings) -> None:
    trail: AuditTrail = AuditTrail(settings)

    @app.middleware("http")
    async def audit_request(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        user_id: int | None = trail.identify_user(request.headers.get("authorization"))
        response: Response = await call_next(request)
        route: object | None = request.scope.get("route")
        route_path: str = str(getattr(route, "path", request.url.path))
        client_host: str = request.client.host if request.client is not None else ""
        source: str = "external" if request.url.path.startswith("/api/external/") else "internal"
        audit_request_data: AuditRequest = AuditRequest(
            method=request.method,
            path=request.url.path,
            route_path=route_path,
            path_params=dict(request.path_params),
            query_params=dict(request.query_params),
            user_id=user_id,
            ip_address=client_host,
            source=source,
        )
        try:
            trail.capture(audit_request_data, AuditResponse(status_code=response.status_code))
        except Exception as error:
            request.app.state.last_audit_error = str(error)
        return response


def register_audit_routes(router: APIRouter, settings: Settings) -> None:
    @router.get("/audit-logs")
    def list_audit_logs(
        authorization: Annotated[str | None, Header()] = None,
        limit: int = Query(50),
        offset: int = Query(0),
        action: str | None = Query(None),
        resource_type: str | None = Query(None),
        user_id: int | None = Query(None),
    ) -> dict[str, object]:
        require_admin(settings, authorization)
        return get_audit_logs(
            settings,
            limit=limit,
            offset=offset,
            action=action,
            resource_type=resource_type,
            user_id=user_id,
        )
