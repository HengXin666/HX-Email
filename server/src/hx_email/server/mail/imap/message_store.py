"""Persisted messages: tokenize fetched mail and keep its IMAP UID."""

from hx_email.server.mail.imap.impl.store.persist import (
    legacy_body_hash,
    message_dedup_hash,
    save_messages,
)
from hx_email.server.mail.imap.impl.store.query import (
    delete_messages_for_email,
    get_latest_message_uid,
    get_message_count,
    get_messages,
)

__all__ = [
    "delete_messages_for_email",
    "get_latest_message_uid",
    "get_message_count",
    "get_messages",
    "legacy_body_hash",
    "message_dedup_hash",
    "save_messages",
]
