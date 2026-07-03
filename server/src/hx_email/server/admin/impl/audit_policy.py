"""Request-to-audit-event classification policy."""

from __future__ import annotations

import json
from collections.abc import Mapping

from hx_email.server.admin.impl.audit_models import AuditEvent, AuditRequest, AuditResponse

_MUTATION_METHODS: frozenset[str] = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_AUDITED_READS: frozenset[str] = frozenset({"/data/export", "/groups/{group_id}/export"})
_MAX_DETAIL_LENGTH: int = 1200
_MASKED_VALUE: str = "***"
_SENSITIVE_KEY_PARTS: tuple[str, ...] = (
    "authorization",
    "password",
    "token",
    "secret",
    "api_key",
    "refresh",
)
_ACTION_SEGMENTS: Mapping[str, str] = {
    "activate": "activate",
    "archive": "archive",
    "batch_delete": "batch_delete",
    "batch_notification_toggle": "batch_update",
    "batch_update_group": "batch_update",
    "batch_update_status": "batch_update",
    "claim": "claim",
    "claim_complete": "complete",
    "claim_random": "claim",
    "claim_release": "release",
    "clear": "clear",
    "complete": "complete",
    "cooldown": "cooldown",
    "deactivate": "deactivate",
    "delete": "delete",
    "exchange": "exchange",
    "export": "export",
    "export_selected": "export",
    "fetch_emails": "fetch",
    "finish": "finish",
    "import": "import",
    "install": "install",
    "login": "login",
    "logout": "logout",
    "prepare": "prepare",
    "prepare_from_config": "prepare",
    "read": "read",
    "refresh": "refresh",
    "refresh_failed": "refresh",
    "register": "register",
    "release": "release",
    "reload_plugins": "reload",
    "save": "save",
    "sync_domains": "sync",
    "tags": "tag",
    "telegram_toggle": "toggle",
    "trigger_update": "trigger",
    "uninstall": "uninstall",
    "validate_cron": "validate",
    "verify": "verify",
}
_RESOURCE_TYPES: Mapping[str, str] = {
    "admin": "setting",
    "auth": "user_session",
    "data": "data_transfer",
    "email-accounts": "email_account",
    "emails": "message",
    "external": "external_api",
    "groups": "group",
    "mail-pool": "pool_entry",
    "platform-bindings": "platform_binding",
    "platform-candidates": "platform_candidate",
    "platforms": "platform",
    "plugins": "plugin",
    "pool-admin": "pool_admin",
    "settings": "setting",
    "system": "system",
    "tags": "tag",
    "temp-mail": "temp_mail",
    "usable-emails": "usable_email",
}
_ID_PARAM_PRIORITY: tuple[str, ...] = (
    "account_id",
    "usable_email_id",
    "group_id",
    "tag_id",
    "platform_id",
    "binding_id",
    "message_id",
    "task_token",
)


class AuditClassifier:
    def classify(self, request: AuditRequest, response: AuditResponse) -> AuditEvent | None:
        normalized_path: str = self._normalize_path(request.route_path or request.path)
        if self._should_skip(request.method.upper(), normalized_path, response.status_code):
            return None

        action: str = self._resolve_action(request.method.upper(), normalized_path)
        resource_type: str = self._resolve_resource_type(normalized_path)
        detail: str = self._build_detail(request, response, normalized_path)
        return AuditEvent(
            user_id=request.user_id,
            action=action,
            resource_type=resource_type,
            resource_id=self._resolve_resource_id(request.path_params),
            detail=detail,
            ip_address=request.ip_address,
        )

    def _should_skip(self, method: str, normalized_path: str, status_code: int) -> bool:
        if normalized_path.startswith("/audit-logs"):
            return True
        if status_code < 200 or status_code >= 400:
            return True
        return method not in _MUTATION_METHODS and normalized_path not in _AUDITED_READS

    def _normalize_path(self, path: str) -> str:
        if path.startswith("/api/v1/"):
            return path.removeprefix("/api/v1")
        if path.startswith("/api/") and not path.startswith("/api/external/"):
            return path.removeprefix("/api")
        if path.startswith("/api/external/"):
            return path.removeprefix("/api")
        return path

    def _resolve_action(self, method: str, normalized_path: str) -> str:
        segments: list[str] = self._segments(normalized_path)
        for segment in reversed(segments):
            clean_segment: str = segment.strip("{}").replace("-", "_")
            if clean_segment in _ACTION_SEGMENTS:
                return _ACTION_SEGMENTS[clean_segment]
        if method == "POST":
            return "create"
        if method in {"PUT", "PATCH"}:
            return "update"
        if method == "DELETE":
            return "delete"
        return "read"

    def _resolve_resource_type(self, normalized_path: str) -> str:
        segments: list[str] = self._segments(normalized_path)
        first_segment: str = segments[0] if segments else "system"
        return _RESOURCE_TYPES.get(first_segment, first_segment.replace("-", "_"))

    def _resolve_resource_id(self, path_params: Mapping[str, object]) -> int | None:
        for key in _ID_PARAM_PRIORITY:
            if key in path_params:
                return self._coerce_int(path_params[key])
        return None

    def _coerce_int(self, value: object) -> int | None:
        try:
            return int(str(value))
        except ValueError:
            return None

    def _build_detail(
        self,
        request: AuditRequest,
        response: AuditResponse,
        normalized_path: str,
    ) -> str:
        detail: dict[str, object] = {
            "method": request.method.upper(),
            "path": request.path,
            "route": normalized_path,
            "source": request.source,
            "status_code": response.status_code,
        }
        if request.path_params:
            detail["params"] = self._sanitize_mapping(request.path_params)
        if request.query_params:
            detail["query"] = self._sanitize_mapping(request.query_params)
        raw: str = json.dumps(detail, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        if len(raw) <= _MAX_DETAIL_LENGTH:
            return raw
        return raw[: _MAX_DETAIL_LENGTH - 3] + "..."

    def _sanitize_mapping(self, values: Mapping[str, object]) -> dict[str, object]:
        return {key: self._sanitize_value(key, value) for key, value in values.items()}

    def _sanitize_value(self, key: str, value: object) -> object:
        lowered_key: str = key.lower()
        if any(part in lowered_key for part in _SENSITIVE_KEY_PARTS):
            return _MASKED_VALUE
        return value

    def _segments(self, normalized_path: str) -> list[str]:
        return [segment for segment in normalized_path.strip("/").split("/") if segment]
