from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from hx_email.api.routes import register_routes
from hx_email.config import Settings
from hx_email.database import migrate
from hx_email.server.mail.graph.fallback_provider import FallbackMailProvider
from hx_email.server.mail.impl.email_fetch_service import start_background_fetch
from hx_email.server.mail.temp_mail import TempMailProvider
from hx_email.server.mail.verification import MailboxProvider

API_DESCRIPTION: str = (
    "多邮箱聚合与验证码读取服务。\n\n"
    "- 业务 API (`/api/v1/*`): `Authorization: Bearer <token>`, 通过 "
    "`POST /api/v1/auth/login` 获取 token。\n"
    "- 外部 API (`/api/external/*`): `X-API-Key: <key>`, 在系统设置中生成。\n\n"
    '错误响应统一为 `{"detail": "..."}` (FastAPI 约定), 校验错误返回 422。'
)

# Endpoints callable without credentials (login, health probes, OAuth callbacks)
PUBLIC_PATHS: frozenset[str] = frozenset(
    {
        "/health",
        "/healthz",
        "/img/{filename}",
        "/api/v1/auth/login",
        "/api/v1/auth/register",
        "/api/v1/csrf-token",
        "/api/v1/google-oauth/callback",
        "/api/v1/token-tool/callback",
    }
)

HTTP_METHODS: frozenset[str] = frozenset({"get", "post", "put", "patch", "delete"})

AUTH_HEADER_PARAMS: frozenset[str] = frozenset({"authorization", "x-api-key"})


def install_openapi_schema(app: FastAPI) -> None:
    """Attach security schemes and strip raw auth-header params from the spec.

    Auth is read via plain Header() params, which OpenAPI would otherwise list
    as ordinary per-operation parameters. Replacing them with standard
    securitySchemes gives Swagger UI a working Authorize button and lets
    generated clients (openapi-generator etc.) wire auth automatically.
    """

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        security_schemes = schema.setdefault("components", {}).setdefault("securitySchemes", {})
        security_schemes["BearerAuth"] = {
            "type": "http",
            "scheme": "bearer",
            "description": "POST /api/v1/auth/login 返回的 access_token",
        }
        security_schemes["ApiKeyAuth"] = {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": "系统设置中生成的外部 API Key",
        }
        for path, operations in schema.get("paths", {}).items():
            for method, operation in operations.items():
                if method not in HTTP_METHODS:
                    continue
                parameters = [
                    parameter
                    for parameter in operation.get("parameters", [])
                    if str(parameter.get("name", "")).lower() not in AUTH_HEADER_PARAMS
                ]
                if parameters:
                    operation["parameters"] = parameters
                else:
                    operation.pop("parameters", None)
                if path in PUBLIC_PATHS:
                    continue
                if path.startswith("/api/external/"):
                    operation["security"] = [{"ApiKeyAuth": []}]
                elif path.startswith("/api/v1/"):
                    operation["security"] = [{"BearerAuth": []}]
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]


def create_app(
    settings: Settings | None = None,
    mailbox_provider: MailboxProvider | None = None,
    temp_mail_providers: dict[str, TempMailProvider] | None = None,
) -> FastAPI:
    resolved_settings: Settings = settings or Settings()
    resolved_mailbox_provider: MailboxProvider = mailbox_provider or FallbackMailProvider(
        resolved_settings
    )
    app = FastAPI(title="HX Email", version="1.0.0", description=API_DESCRIPTION)
    register_routes(
        app,
        resolved_settings,
        resolved_mailbox_provider,
        temp_mail_providers or {},
    )
    install_openapi_schema(app)

    # Start background email fetcher (runs every 120 seconds)
    @app.on_event("startup")
    def _start_bg_fetch() -> None:
        migrate(resolved_settings)
        start_background_fetch(resolved_settings, interval=120)

    @app.on_event("shutdown")
    def _stop_bg_fetch() -> None:
        from hx_email.server.mail.impl.email_fetch_service import stop_background_fetch

        stop_background_fetch()

    return app


app: FastAPI = create_app()
