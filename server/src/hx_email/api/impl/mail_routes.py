from fastapi import APIRouter

from hx_email.api.impl.mail import (
    register_account_transfer_routes,
    register_batch_routes,
    register_email_account_routes,
    register_email_routes,
    register_export_routes,
    register_mail_pool_routes,
    register_refresh_log_routes,
    register_refresh_routes,
    register_token_tool_routes,
    register_usable_email_routes,
)
from hx_email.config import Settings
from hx_email.server.mail.verification import MailboxProvider


def register_mail_routes(
    router: APIRouter,
    settings: Settings,
    mailbox_provider: MailboxProvider,
) -> None:
    # Static-path routes MUST register before parameterized {account_id} routes,
    # otherwise Starlette matches "refresh-logs" as an account_id → 422.
    register_usable_email_routes(router, settings, mailbox_provider)
    register_mail_pool_routes(router, settings)
    register_account_transfer_routes(router, settings)
    register_batch_routes(router, settings)
    register_export_routes(router, settings)
    register_email_routes(router, settings, mailbox_provider)
    register_token_tool_routes(router, settings)
    register_refresh_routes(router, settings, mailbox_provider)
    register_refresh_log_routes(router, settings)
    # Parameterized {account_id} routes — registered LAST
    register_email_account_routes(router, settings)
