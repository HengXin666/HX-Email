"""Shared audit data contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class AuditRequest:
    method: str
    path: str
    route_path: str
    path_params: Mapping[str, object]
    query_params: Mapping[str, object]
    user_id: int | None
    ip_address: str
    source: str


@dataclass(frozen=True)
class AuditResponse:
    status_code: int


@dataclass(frozen=True)
class AuditEvent:
    user_id: int | None
    action: str
    resource_type: str
    resource_id: int | None
    detail: str
    ip_address: str


@dataclass(frozen=True)
class AuditQuery:
    limit: int = 50
    offset: int = 0
    action: str | None = None
    resource_type: str | None = None
    user_id: int | None = None
