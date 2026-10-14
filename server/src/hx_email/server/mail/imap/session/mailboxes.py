"""Resolving a logical folder to the mailbox name the server itself uses.

A server names its mailboxes in its own language and, for Gmail, in modified UTF-7:
on a Chinese account ``[Gmail]/&V4NXPpCuTvY-`` is Spam and ``[Gmail]/&YkBnCZCuTvY-``
is All Mail. The English names in ``impl/folder_candidates.py`` therefore never match
such an account, while LIST's RFC 6154 special-use attributes name the mailbox no
matter the language. The reader asks for those instead of assuming a name.

See .agents/notes/implemented/architecture/2026-10-14-imap-folders-by-special-use.md
"""

from __future__ import annotations

import imaplib

# Logical folder -> the LIST attributes (RFC 6154) that name it.
SPECIAL_USE_ATTRIBUTES: dict[str, tuple[str, ...]] = {
    "sent": ("\\SENT",),
    "drafts": ("\\DRAFTS",),
    "deleted": ("\\TRASH",),
    "junk": ("\\JUNK", "\\SPAM"),
    "archive": ("\\ALL", "\\ARCHIVE"),
}


def resolve_special_use_name(connection: imaplib.IMAP4, folder: str) -> str:
    """Return the server's own mailbox name for a logical folder, or "" if unknown."""
    wanted: tuple[str, ...] | None = SPECIAL_USE_ATTRIBUTES.get(folder)
    if wanted is None:
        return ""
    for line in list_mailboxes(connection):
        attributes: set[str] = list_attributes(line)
        if any(name in attributes for name in wanted):
            return mailbox_name(line)
    return ""


def list_mailboxes(connection: imaplib.IMAP4) -> list[str]:
    """Return LIST response lines (an empty list when the server refuses LIST)."""
    try:
        status, data = connection.list()
    except Exception:
        return []
    if not status_ok(status) or not data:
        return []
    return [flatten(item) for item in data if item is not None]


def flatten(item: object) -> str:
    """One LIST line as text; a literal response arrives as its separate parts."""
    if isinstance(item, tuple):
        return "".join(text(part) for part in item)
    return text(item)


def list_attributes(line: str) -> set[str]:
    """Upper-cased attributes from the parenthesised list heading a LIST line."""
    start: int = line.find("(")
    end: int = line.find(")", start + 1)
    if start < 0 or end < 0:
        return set()
    return {attribute.upper() for attribute in line[start + 1 : end].split()}


def mailbox_name(line: str) -> str:
    """The mailbox name at the end of a LIST line, unquoted."""
    rest: str = line.split(")", 1)[-1].strip()
    if rest.startswith('"'):
        closing: int = rest.find('"', 1)
        rest = rest[closing + 1 :].strip() if closing > 0 else ""
    else:
        rest = rest.partition(" ")[2].strip()
    if len(rest) > 1 and rest.startswith('"') and rest.endswith('"'):
        return rest[1:-1]
    return rest


def status_ok(status: object) -> bool:
    return text(status).upper() == "OK"


def text(value: object) -> str:
    if isinstance(value, bytes | bytearray):
        return bytes(value).decode("utf-8", errors="replace")
    return str(value)
