"""In-process import job registry + background runner.

The credential-import endpoint used to block for the whole batch (a 5000 line
import took minutes with no feedback). Jobs let the frontend poll a progress
snapshot while the import runs in a daemon thread. Single-worker uvicorn (the
deployment's default) keeps this registry process-local, matching the existing
patrol/scheduler background-thread pattern. Jobs are pruned to the last few
per user; a server restart loses in-flight jobs (frontend surfaces that as an
error and asks to retry).
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import cast

from hx_email.config import Settings
from hx_email.server.mail.impl.accounts.import_service import (
    import_accounts_with_provider,
)

MAX_JOBS_PER_USER: int = 5

JobResult = dict[str, object]


@dataclass
class ImportJob:
    job_id: str
    user_id: int
    status: str = "running"  # running | done | error
    total: int = 0
    processed: int = 0
    imported: int = 0
    skipped: int = 0
    failed: int = 0
    error: str = ""
    result: JobResult | None = None
    created_at: float = field(default_factory=time.time)

    def snapshot(self) -> dict[str, object]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "total": self.total,
            "processed": self.processed,
            "imported": self.imported,
            "skipped": self.skipped,
            "failed": self.failed,
            "error": self.error,
            "result": self.result,
        }


_jobs: dict[int, dict[str, ImportJob]] = {}
_jobs_lock: threading.Lock = threading.Lock()


def get_import_job(user_id: int, job_id: str) -> ImportJob | None:
    with _jobs_lock:
        job = _jobs.get(user_id, {}).get(job_id)
    return job


def _prune(user_id: int) -> None:
    bucket: dict[str, ImportJob] = _jobs.setdefault(user_id, {})
    if len(bucket) <= MAX_JOBS_PER_USER:
        return
    for stale_id in sorted(bucket, key=lambda jid: bucket[jid].created_at)[
        : len(bucket) - MAX_JOBS_PER_USER
    ]:
        del bucket[stale_id]


def start_import_job(
    settings: Settings,
    user_id: int,
    text: str,
    *,
    provider: str,
    group_id: int | None,
    duplicate_strategy: str,
    custom_imap_host: str,
    custom_imap_port: int,
    total: int = 0,
) -> ImportJob:
    job = ImportJob(job_id=uuid.uuid4().hex, user_id=user_id, total=total)
    with _jobs_lock:
        _jobs.setdefault(user_id, {})[job.job_id] = job
        _prune(user_id)

    def run() -> None:
        try:
            result = import_accounts_with_provider(
                settings,
                user_id,
                text,
                provider=provider,
                group_id=group_id,
                duplicate_strategy=duplicate_strategy,
                custom_imap_host=custom_imap_host,
                custom_imap_port=custom_imap_port,
                on_progress=_apply_progress,
            )
            job.processed = job.total
            job.imported = cast(int, result["imported"])
            job.skipped = cast(int, result["skipped"])
            job.failed = cast(int, result["failed"])
            job.result = result
            job.status = "done"
        except Exception as exc:  # surface any failure to the user
            job.status = "error"
            job.error = str(exc)

    def _apply_progress(processed: int, imported: int, skipped: int, failed: int) -> None:
        job.processed = processed
        job.imported = imported
        job.skipped = skipped
        job.failed = failed

    threading.Thread(target=run, daemon=True, name=f"import-{user_id}").start()
    return job
