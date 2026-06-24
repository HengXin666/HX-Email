"""Temp mail service package.

Provides extended temp mail operations: options, message detail, delete, clear, refresh.
"""

from hx_email.server.mail.impl.temp_mail.temp_mail_options import get_temp_mail_options
from hx_email.server.mail.impl.temp_mail.temp_mail_service import (
    clear_temp_messages,
    delete_temp_mailbox,
    delete_temp_message,
    get_temp_message_detail,
    refresh_temp_mail,
)

__all__ = [
    "clear_temp_messages",
    "delete_temp_mailbox",
    "delete_temp_message",
    "get_temp_mail_options",
    "get_temp_message_detail",
    "refresh_temp_mail",
]
