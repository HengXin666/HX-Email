"""Shared helper for the async credential-import API.

POST /email-accounts/import now starts a background job (202 + job_id);
GET /email-accounts/import/{job_id} returns progress and the final result.
``run_import`` POSTs then polls until done/error and returns the final
snapshot with the result fields merged to the top level (so callers keep
reading ``["imported"]`` / ``["skipped"]`` as before).
"""

from __future__ import annotations

import time
from typing import Any

API = "/api/v1"


def run_import(
    client: Any,
    headers: dict[str, str],
    payload: dict[str, object],
    timeout: float = 30.0,
) -> dict[str, object]:
    created = client.post(f"{API}/email-accounts/import", json=payload, headers=headers)
    assert created.status_code == 202, created.text
    job_id: str = created.json()["job_id"]
    deadline: float = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snap = client.get(f"{API}/email-accounts/import/{job_id}", headers=headers)
        assert snap.status_code == 200, snap.text
        data: dict[str, object] = snap.json()
        if data["status"] == "error":
            return data
        if data["status"] == "done":
            result: dict[str, object] | None = data.get("result")
            if isinstance(result, dict):
                return {**data, **result}
            return data
        time.sleep(0.01)
    raise AssertionError(f"import job {job_id} did not finish within {timeout}s")
