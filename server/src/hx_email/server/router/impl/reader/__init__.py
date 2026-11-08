"""Cursor reads over ``messaging_messages``: scopes (``source``), rows, pages.

Split out of the former ``reader.py`` module (stage 3) to keep each file under the 300
line ceiling; every name callers used stays importable from this package.
"""

from hx_email.server.router.impl.reader.page import (
    BOUNDARY,
    DEFAULT_LIMIT,
    MAX_LIMIT,
    MAX_STORED_POSITION,
    ReadPage,
    latest_cursor,
    owned_instances,
    read_messages,
)
from hx_email.server.router.impl.reader.rows import (
    PLATFORM_OF_KIND,
    decode_attachments,
    row_to_envelope,
)
from hx_email.server.router.impl.reader.source import (
    COLUMNS,
    PLATFORMS,
    Source,
    build_query,
    parse_source,
    peer_of,
)

__all__ = [
    "BOUNDARY",
    "COLUMNS",
    "DEFAULT_LIMIT",
    "MAX_LIMIT",
    "MAX_STORED_POSITION",
    "PLATFORMS",
    "PLATFORM_OF_KIND",
    "ReadPage",
    "Source",
    "build_query",
    "decode_attachments",
    "latest_cursor",
    "owned_instances",
    "parse_source",
    "peer_of",
    "read_messages",
    "row_to_envelope",
]
