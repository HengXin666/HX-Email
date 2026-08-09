"""HTTP client that pulls an instance snapshot from the master instance."""

from __future__ import annotations

import urllib.error
import urllib.request

from hx_email.config import Settings

SNAPSHOT_PATH: str = "/api/v1/admin/sync/snapshot"
REQUEST_TIMEOUT_SECONDS: int = 300


class SyncClientError(RuntimeError):
    """Raised when the master snapshot cannot be fetched."""


def fetch_snapshot(settings: Settings) -> bytes:
    base_url: str = settings.sync_url.strip().rstrip("/")
    if not base_url or not settings.sync_token.strip():
        raise SyncClientError("HX_EMAIL_SYNC_URL and HX_EMAIL_SYNC_TOKEN are required")
    request = urllib.request.Request(
        f"{base_url}{SNAPSHOT_PATH}",
        headers={"Authorization": f"Bearer {settings.sync_token.strip()}"},
    )
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
