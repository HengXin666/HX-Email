"""GitHub 入站的投递层去重与异步处理队列.

去重键为 (instance_id, X-GitHub-Delivery). 规格把它落在 router_ingress_deliveries 表 (R1 的 models),
该表落盘前这里用进程内实现, 接口按表的语义设计 (claim 即 INSERT ... ON CONFLICT DO NOTHING),
落盘后换成表实现即可, 路由与测试不变.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

DEDUP_RETENTION_SECONDS: float = 7 * 24 * 3600
LOGGER: logging.Logger = logging.getLogger("hx_email.router.ingress.github")

EnvelopeSink = Callable[[int, list[dict[str, object]]], None]
EventParser = Callable[[int, dict[str, str], bytes], list[dict[str, object]]]


class DeliveryLedger(Protocol):
    def claim(self, instance_id: int, delivery_id: str, event: str) -> bool: ...

    def mark(self, instance_id: int, delivery_id: str, status: str) -> None: ...


class MemoryDeliveryLedger:
    """线程安全的进程内去重表, 保留 7 天, 过期行在 claim 时顺带清理."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock: Callable[[], float] = clock
        self.rows: dict[tuple[int, str], tuple[float, str, str]] = {}
        self.lock: threading.Lock = threading.Lock()

    def claim(self, instance_id: int, delivery_id: str, event: str) -> bool:
        now: float = self.clock()
        key: tuple[int, str] = (instance_id, delivery_id)
        with self.lock:
            expired: list[tuple[int, str]] = [
                k for k, row in self.rows.items() if now - row[0] > DEDUP_RETENTION_SECONDS
            ]
            for stale in expired:
                self.rows.pop(stale, None)
            if key in self.rows:
                return False
            self.rows[key] = (now, event, "pending")
            return True

    def mark(self, instance_id: int, delivery_id: str, status: str) -> None:
        key: tuple[int, str] = (instance_id, delivery_id)
        with self.lock:
            row: tuple[float, str, str] | None = self.rows.get(key)
            if row is not None:
                self.rows[key] = (row[0], row[1], status)

    def status(self, instance_id: int, delivery_id: str) -> str:
        row: tuple[float, str, str] | None = self.rows.get((instance_id, delivery_id))
        return row[2] if row is not None else ""


@dataclass(frozen=True)
class IngressJob:
    instance_id: int
    delivery_id: str
    headers: dict[str, str]
    body: bytes


class IngressWorker:
    """单个后台线程消费入站任务; 第一次提交时才启动, 空闲时不占 CPU."""

    def __init__(self, parser: EventParser, sink: EnvelopeSink, ledger: DeliveryLedger) -> None:
        self.parser: EventParser = parser
        self.sink: EnvelopeSink = sink
        self.ledger: DeliveryLedger = ledger
        self.jobs: queue.Queue[IngressJob] = queue.Queue()
        self.thread: threading.Thread | None = None
        self.start_lock: threading.Lock = threading.Lock()

    def submit(self, job: IngressJob) -> None:
        self.ensure_started()
        self.jobs.put(job)

    def ensure_started(self) -> None:
        with self.start_lock:
            if self.thread is None or not self.thread.is_alive():
                self.thread = threading.Thread(target=self.run, name="github-ingress", daemon=True)
                self.thread.start()

    def run(self) -> None:
        while True:
            job: IngressJob = self.jobs.get()
            try:
                self.process(job)
            finally:
                self.jobs.task_done()

    def process(self, job: IngressJob) -> None:
        try:
            envelopes: list[dict[str, object]] = self.parser(job.instance_id, job.headers, job.body)
            if envelopes:
                self.sink(job.instance_id, envelopes)
            self.ledger.mark(job.instance_id, job.delivery_id, "done")
        except Exception:
            LOGGER.exception("github ingress failed: delivery=%s", job.delivery_id)
            self.ledger.mark(job.instance_id, job.delivery_id, "failed")

    def drain(self) -> None:
        """等待队列清空, 测试与优雅停机用."""
        self.jobs.join()
