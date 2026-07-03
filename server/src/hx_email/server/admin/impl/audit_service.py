"""Audit trail facade."""

from __future__ import annotations

from hx_email.config import Settings
from hx_email.server.admin.impl.audit_models import (
    AuditEvent,
    AuditQuery,
    AuditRequest,
    AuditResponse,
)
from hx_email.server.admin.impl.audit_policy import AuditClassifier
from hx_email.server.admin.impl.audit_store import AuditLogRepository
from hx_email.server.auth import authenticate_token


class AuditTrail:
    def __init__(
        self,
        settings: Settings,
        repository: AuditLogRepository | None = None,
        classifier: AuditClassifier | None = None,
    ) -> None:
        self.settings: Settings = settings
        self.repository: AuditLogRepository = repository or AuditLogRepository(settings)
        self.classifier: AuditClassifier = classifier or AuditClassifier()

    def capture(self, request: AuditRequest, response: AuditResponse) -> None:
        event: AuditEvent | None = self.classifier.classify(request, response)
        if event is not None:
            self.repository.insert(event)

    def identify_user(self, authorization: str | None) -> int | None:
        scheme: str
        token: str
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not token:
            return None
        user = authenticate_token(self.settings, token)
        return user.id if user is not None else None

    def query(self, query: AuditQuery) -> dict[str, object]:
        return self.repository.search(query)

    def record(self, event: AuditEvent) -> None:
        self.repository.insert(event)


def log_audit(
    settings: Settings,
    user_id: int | None,
    action: str,
    resource_type: str,
    resource_id: int | None = None,
    detail: str = "",
    ip_address: str = "",
) -> None:
    AuditTrail(settings).record(
        AuditEvent(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            detail=detail,
            ip_address=ip_address,
        )
    )


def get_audit_logs(
    settings: Settings,
    limit: int = 50,
    offset: int = 0,
    action: str | None = None,
    resource_type: str | None = None,
    user_id: int | None = None,
) -> dict[str, object]:
    return AuditTrail(settings).query(
        AuditQuery(
            limit=limit,
            offset=offset,
            action=action,
            resource_type=resource_type,
            user_id=user_id,
        )
    )
