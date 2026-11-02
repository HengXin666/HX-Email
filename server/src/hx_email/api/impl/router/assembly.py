"""装配 GitHub 入站端点: 把 provider, 去重账本, 消费线程接到 app 上.

没有这个装配之前, `ingress_github.py` 里的端点是死代码: 它定义了 POST
`/api/v1/router/ingress/github/{instance_id}`, 但没有任何地方 include 它, 公网回调
进来只会 404. 这里把它连上, 并让 sink 把 envelope 落到 `messaging_messages`.

sink 走 `store_inbound`, 与 QQ 入站共用同一张表与同一套 `(instance_id, dedup_key)`
唯一索引, 所以两个平台的重投去重是同一份保证, 不是两套.

一个 GitHub 实例的配置在 `messaging_instances.config_encrypted` 里, 由
`open_app_config` 解密. loader 每次读库而不是缓存, 这样用户在设置页改完 App 配置
立刻生效, 不需要重启.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable

from fastapi import APIRouter

from hx_email.api.impl.router.ingress_github import build_github_ingress_router
from hx_email.api.impl.router.ingress_queue import (
    DeliveryLedger,
    IngressWorker,
    MemoryDeliveryLedger,
)
from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.router.envelope import validate_inbound
from hx_email.server.router.impl.store import store_inbound
from hx_email.server.router.providers.github import GitHubAppProvider
from hx_email.server.router.providers.impl.github.github_auth import (
    GitHubAppConfig,
    open_app_config,
)

LOGGER: logging.Logger = logging.getLogger("hx_email.router.assembly")
GITHUB_KIND: str = "github"


def _instance_exists(settings: Settings, instance_id: int) -> bool:
    with connect(settings) as connection:
        row: sqlite3.Row | None = connection.execute(
            "SELECT 1 AS found FROM messaging_instances WHERE id = ? AND kind = ?",
            (instance_id, GITHUB_KIND),
        ).fetchone()
    return row is not None


def _load_config(settings: Settings, instance_id: int) -> GitHubAppConfig:
    """Decrypt one instance's App config; an unconfigured instance verifies nothing."""
    with connect(settings) as connection:
        row: sqlite3.Row | None = connection.execute(
            "SELECT config_encrypted FROM messaging_instances WHERE id = ? AND kind = ?",
            (instance_id, GITHUB_KIND),
        ).fetchone()
    sealed: str = str(row["config_encrypted"] or "") if row is not None else ""
    if not sealed:
        return GitHubAppConfig("", "", "", "", "")
    try:
        return open_app_config(settings, sealed)
    except (ValueError, OSError) as error:
        LOGGER.warning("cannot open GitHub App config for instance %s: %s", instance_id, error)
        return GitHubAppConfig("", "", "", "", "")


def _sink(settings: Settings) -> Callable[[int, list[dict[str, object]]], None]:
    """Store parsed envelopes; a bad envelope is logged rather than killing the worker."""

    def store(instance_id: int, envelopes: list[dict[str, object]]) -> None:
        for envelope in envelopes:
            try:
                store_inbound(settings, validate_inbound(envelope, instance_id))
            except (ValueError, OSError) as error:
                LOGGER.warning(
                    "dropped invalid inbound envelope for instance %s: %s", instance_id, error
                )

    return store


def _parser(
    provider: GitHubAppProvider,
) -> Callable[[int, dict[str, str], bytes], list[dict[str, object]]]:
    def parse(instance_id: int, headers: dict[str, str], body: bytes) -> list[dict[str, object]]:
        return provider.parse_event(instance_id, headers, body)

    return parse


def build_github_ingress(
    settings: Settings,
    ledger: DeliveryLedger | None = None,
) -> tuple[APIRouter, IngressWorker]:
    """Build the GitHub ingress router plus the worker that drains its queue."""
    provider = GitHubAppProvider(lambda instance_id: _load_config(settings, instance_id))
    resolved_ledger: DeliveryLedger = ledger or MemoryDeliveryLedger()
    worker = IngressWorker(_parser(provider), _sink(settings), resolved_ledger)
    router = build_github_ingress_router(
        provider,
        resolved_ledger,
        worker,
        lambda instance_id: _instance_exists(settings, instance_id),
    )
    return router, worker


def register_router_ingress(app: object, settings: Settings) -> IngressWorker:
    """Attach the router ingress router to ``app``; returns the worker for shutdown."""
    from fastapi import FastAPI

    if not isinstance(app, FastAPI):  # pragma: no cover - defensive
        raise TypeError("register_router_ingress expects a FastAPI app")
    router, worker = build_github_ingress(settings)
    app.include_router(router)
    return worker
