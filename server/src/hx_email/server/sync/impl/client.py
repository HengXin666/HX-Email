"""HTTP client that pulls and pushes instance snapshots to the master instance."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from hx_email.config import Settings

SNAPSHOT_PATH: str = "/api/v1/admin/sync/snapshot"
PUSH_PATH: str = "/api/v1/admin/sync/push"
REQUEST_TIMEOUT_SECONDS: int = 300


class SyncClientError(RuntimeError):
    """Raised when the master instance cannot be reached or rejects a sync request."""


def redact_sync_url(settings: Settings, message: str) -> str:
    """Mask the master instance URL inside an error message."""
    sync_url: str = settings.sync_url.strip().rstrip("/")
    if not sync_url:
        return message
    return message.replace(sync_url, "<master-url>")


def redact_report_error(settings: Settings, report: dict[str, object]) -> dict[str, object]:
    """Return a copy of a sync report dict with its error URL redacted."""
    redacted: dict[str, object] = dict(report)
    error: object = redacted.get("error")
    if isinstance(error, str):
        redacted["error"] = redact_sync_url(settings, error)
    push: object = redacted.get("push")
    if isinstance(push, dict):
        redacted["push"] = redact_report_error(settings, push)
    return redacted


def _master_base_url(settings: Settings) -> str:
    base_url: str = settings.sync_url.strip().rstrip("/")
    if not base_url or not settings.sync_token.strip():
        raise SyncClientError("Sync is not configured: set sync_url and sync_token in settings")
    return base_url


def _authorized_request(url: str, settings: Settings) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {settings.sync_token.strip()}"},
    )


def fetch_snapshot(settings: Settings) -> bytes:
    base_url: str = _master_base_url(settings)
    request: urllib.request.Request = _authorized_request(f"{base_url}{SNAPSHOT_PATH}", settings)
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload: bytes = response.read()
    except urllib.error.HTTPError as error:
        raise SyncClientError(f"Master rejected sync request: HTTP {error.code}") from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise SyncClientError(f"Could not reach master at {base_url}: {error}") from error
    if not payload:
        raise SyncClientError("Master returned an empty snapshot")
    return payload


def push_snapshot_to_master(settings: Settings, archive_bytes: bytes) -> dict[str, Any]:
    base_url: str = _master_base_url(settings)
    request: urllib.request.Request = urllib.request.Request(
        f"{base_url}{PUSH_PATH}",
        data=archive_bytes,
        headers={
            "Authorization": f"Bearer {settings.sync_token.strip()}",
            "Content-Type": "application/zip",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload: bytes = response.read()
    except urllib.error.HTTPError as error:
        raise SyncClientError(f"Master rejected sync push: HTTP {error.code}") from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise SyncClientError(f"Could not reach master at {base_url}: {error}") from error
    try:
        parsed: object = json.loads(payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as error:
        raise SyncClientError("Master returned an invalid push response") from error
    if not isinstance(parsed, dict):
        raise SyncClientError("Master returned an invalid push response")
    return parsed
