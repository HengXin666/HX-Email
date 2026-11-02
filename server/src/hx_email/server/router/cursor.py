"""Cursor encoding and consistency boundary (docs/messaging-router.md section 7.1).

Format: ``c1.<instance_id>.<messaging_messages.id>``. ``c1.0.<id>`` is the global
position for prefixes that span instances. Callers treat the string as opaque.

Consistency boundary:
- ``messaging_messages.id`` is a SQLite AUTOINCREMENT key. It is monotonic only under the
  single-writer, single-process deployment of ADR 0002, and ids are never reused.
- Reads are ``WHERE id > position ORDER BY id ASC``; within one session order is by id.
  Across sessions every row is eventually readable, with no global causal order.
- Delivery is at least once; consumers dedupe on the envelope ``id``.
- A cursor older than retention-deleted rows resumes at the smallest live id with
  ``gap=true``. A cursor past the newest id ever issued is out of range.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from hx_email.server.router.errors import CursorInvalidError

CURSOR_VERSION: Final[str] = "c1"
GLOBAL_INSTANCE_ID: Final[int] = 0
MAX_POSITION: Final[int] = 2**63 - 1


@dataclass(frozen=True, order=True)
class Cursor:
    instance_id: int
    position: int

    def encode(self) -> str:
        return encode_cursor(self.instance_id, self.position)

    def advance(self, position: int) -> Cursor:
        """Move forward only; a smaller position keeps the current cursor."""
        return Cursor(self.instance_id, max(self.position, position))


def is_plain_number(text: str) -> bool:
    """ASCII digits only, no sign, no leading zeros except a lone ``0``."""
    return text.isascii() and text.isdigit() and (text == "0" or not text.startswith("0"))


def encode_cursor(instance_id: int, position: int) -> str:
    if instance_id < 0 or position < 0 or position > MAX_POSITION:
        raise CursorInvalidError(f"cursor parts out of range: {instance_id}, {position}")
    return f"{CURSOR_VERSION}.{instance_id}.{position}"


def decode_cursor(value: str) -> Cursor:
    parts: list[str] = value.split(".")
    if len(parts) != 3 or parts[0] != CURSOR_VERSION:
        raise CursorInvalidError(f"cannot parse cursor: {value!r}")
    instance_text, position_text = parts[1], parts[2]
    if not (is_plain_number(instance_text) and is_plain_number(position_text)):
        raise CursorInvalidError(f"cannot parse cursor: {value!r}")
    position: int = int(position_text)
    if position > MAX_POSITION:
        raise CursorInvalidError(f"cursor position out of range: {value!r}")
    return Cursor(int(instance_text), position)


def earliest_cursor(instance_id: int) -> Cursor:
    return Cursor(instance_id, 0)


def ensure_scope(cursor: Cursor, scope_instance_id: int) -> None:
    """A cursor is valid only for the scope that issued it (one instance or global)."""
    if cursor.instance_id != scope_instance_id:
        raise CursorInvalidError(
            f"cursor belongs to instance {cursor.instance_id}, scope is {scope_instance_id}"
        )


def ensure_not_ahead(cursor: Cursor, newest_issued: int) -> None:
    """Reject positions the server could never have issued."""
    if cursor.position > newest_issued:
        raise CursorInvalidError(f"cursor position {cursor.position} is beyond {newest_issued}")


def has_gap(cursor: Cursor, oldest_live_id: int | None) -> bool:
    """True when rows right after the cursor were deleted by retention."""
    return oldest_live_id is not None and cursor.position + 1 < oldest_live_id
