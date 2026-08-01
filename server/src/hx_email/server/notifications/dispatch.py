"""Simple public interface for durable new-mail delivery."""

from __future__ import annotations

import threading
from collections.abc import Sequence

from hx_email.config import Settings
from hx_email.server.notifications.impl.channels import run_script_test, send_delivery
from hx_email.server.notifications.impl.jobs import (
    claim_delivery_jobs,
    delivery_status,
    enqueue_delivery_jobs,
    event_channels,
    load_delivery_config,
    load_message_event,
    mark_delivery_failed,
    mark_delivery_sent,
    mark_delivery_skipped,
)
from hx_email.server.notifications.models import DeliveryConfig, DispatchSummary, StoredMessageEvent

DELIVERY_LOCK: threading.Lock = threading.Lock()


def dispatch_new_messages(
    settings: Settings,
    message_ids: Sequence[int],
) -> DispatchSummary:
    """Enqueue and immediately attempt all configured channels for new messages."""
    queued: int = enqueue_delivery_jobs(settings, message_ids)
    processed: DispatchSummary = process_delivery_jobs(settings, message_ids)
    return DispatchSummary(
        queued=queued,
        sent=processed.sent,
        failed=processed.failed,
        skipped=processed.skipped,
    )


def retry_pending_deliveries(settings: Settings) -> DispatchSummary:
    """Retry failed or pending jobs up to the configured attempt cap."""
    return process_delivery_jobs(settings)


def process_delivery_jobs(
    settings: Settings,
    message_ids: Sequence[int] | None = None,
) -> DispatchSummary:
    if not DELIVERY_LOCK.acquire(blocking=False):
        return DispatchSummary()
    sent: int = 0
    failed: int = 0
    skipped: int = 0
    try:
        config: DeliveryConfig = load_delivery_config(settings)
        for job in claim_delivery_jobs(settings, message_ids):
            event: StoredMessageEvent | None = load_message_event(
                settings,
                job.fetched_message_id,
            )
            if event is None:
                mark_delivery_skipped(settings, job.id, "Fetched message no longer exists")
                skipped += 1
                continue
            if job.channel not in event_channels(event, config):
                mark_delivery_skipped(settings, job.id, "Delivery was disabled before processing")
                skipped += 1
                continue
            try:
                send_delivery(settings, event, job.channel)
            except Exception as error:
                mark_delivery_failed(settings, job.id, str(error) or type(error).__name__)
                failed += 1
            else:
                mark_delivery_sent(settings, job.id)
                sent += 1
    finally:
        DELIVERY_LOCK.release()
    return DispatchSummary(sent=sent, failed=failed, skipped=skipped)


def get_delivery_status(settings: Settings) -> dict[str, object]:
    return delivery_status(settings)


def test_script_pipeline(
    settings: Settings,
    path_value: str,
    timeout_seconds: int | None = None,
) -> dict[str, object]:
    try:
        output: str = run_script_test(settings, path_value, timeout_seconds)
    except Exception as error:
        return {"success": False, "message": str(error) or type(error).__name__}
    return {
        "success": True,
        "message": output or "Shell pipeline completed successfully",
    }
