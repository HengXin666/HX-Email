"""Session addresses and the unified envelope (docs/messaging-router.md sections 2 and 3).

The package splits addresses (``session``), the envelope model and its validation
(``model``) and raw storage helpers (``raw``); every name stays importable from here.
"""

from hx_email.server.router.envelope.model import (
    ISO_UTC_PATTERN,
    MESSAGE_ID_PREFIX,
    Attachment,
    Envelope,
    EnvelopeError,
    InboundMessage,
    Sender,
    attachment_to_dict,
    parse_attachments,
    parse_sender,
    require_str,
    validate_inbound,
)
from hx_email.server.router.envelope.raw import (
    RAW_DIR_NAME,
    RAW_INLINE_LIMIT_BYTES,
    SQLITE_TIME_FORMAT,
    encode_raw,
    iso_utc_from_sqlite,
    iso_utc_from_unix,
    load_raw,
    needs_offload,
    raw_relative_path,
    write_raw_file,
)
from hx_email.server.router.envelope.session import (
    DIRECTIONS,
    PLATFORMS,
    SEGMENT_PATTERN,
    SESSION_TYPES,
    Direction,
    SessionAddress,
    SessionType,
    format_session,
    parse_session,
)

__all__ = [
    "DIRECTIONS",
    "ISO_UTC_PATTERN",
    "MESSAGE_ID_PREFIX",
    "PLATFORMS",
    "RAW_DIR_NAME",
    "RAW_INLINE_LIMIT_BYTES",
    "SEGMENT_PATTERN",
    "SESSION_TYPES",
    "SQLITE_TIME_FORMAT",
    "Attachment",
    "Direction",
    "Envelope",
    "EnvelopeError",
    "InboundMessage",
    "Sender",
    "SessionAddress",
    "SessionType",
    "attachment_to_dict",
    "encode_raw",
    "format_session",
    "iso_utc_from_sqlite",
    "iso_utc_from_unix",
    "load_raw",
    "needs_offload",
    "parse_attachments",
    "parse_sender",
    "parse_session",
    "raw_relative_path",
    "require_str",
    "validate_inbound",
    "write_raw_file",
]
