"""github_user account checks shared by ``/router/github_user`` and ``PUT .../config``."""

from __future__ import annotations

from typing import Final

from hx_email.api.impl.messaging.serializers import instance_dict
from hx_email.config import Settings
from hx_email.server.contract.github_user.config import CLI_KEY, LOGIN_KEY, REPOSITORY_KEY
from hx_email.server.messaging.store import (
    get_instance,
    update_instance_config,
    update_instance_status,
)
from hx_email.server.messaging.types import MessagingInstance
from hx_email.server.router.providers.impl.github_user.gh_setup import SetupReport, check_setup

KIND: Final[str] = "github_user"
ACCOUNT_KEYS: Final[frozenset[str]] = frozenset({CLI_KEY, REPOSITORY_KEY})


async def run_check(
    settings: Settings, user_id: int, instance: MessagingInstance
) -> dict[str, object]:
    report: SetupReport = await check_setup(instance.config)
    config: dict[str, str] = {**instance.config, LOGIN_KEY: report.login if report.ok else ""}
    saved: MessagingInstance | None = update_instance_config(settings, user_id, instance.id, config)
    update_instance_status(settings, instance.id, "online" if report.ok else "error")
    fresh: MessagingInstance | None = get_instance(settings, user_id, instance.id) or saved
    return {"report": report.to_dict(), "instance": instance_dict(fresh) if fresh else {}}


def account_changed(current: dict[str, str], incoming: dict[str, str]) -> bool:
    """True when the update moves a github_user instance to another CLI or repository."""
    return any(
        key in incoming and incoming[key].strip() != current.get(key, "").strip()
        for key in ACCOUNT_KEYS
    )
