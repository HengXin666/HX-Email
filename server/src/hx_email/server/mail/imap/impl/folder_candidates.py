"""IMAP folder name candidates per provider.

Maps logical folder names (inbox, sent, drafts, deleted, junk, archive)
to provider-specific IMAP folder paths.
"""

from __future__ import annotations

_FOLDER_CANDIDATES: dict[str, dict[str, list[str]]] = {
    "_default": {
        "inbox": ["INBOX"],
        "sent": ["Sent", "Sent Items", "Sent Messages", "INBOX.Sent"],
        "drafts": ["Drafts", "Draft"],
        "deleted": ["Trash", "Deleted Items", "Deleted Messages", "INBOX.Trash"],
        "junk": ["Junk", "Junk Email", "Spam", "Bulk Mail", "INBOX.Junk"],
        "archive": ["Archive", "Archived"],
    },
    "outlook": {
        "inbox": ["INBOX"],
        "sent": ["Sent", "Sent Items"],
        "drafts": ["Drafts"],
        "deleted": ["Deleted Items", "Deleted"],
        "junk": ["Junk Email", "Junk"],
        "archive": ["Archive"],
    },
    "gmail": {
        "inbox": ["INBOX"],
        "sent": ["[Gmail]/Sent Mail", "[Gmail]/Sent"],
        "drafts": ["[Gmail]/Drafts"],
        "deleted": ["[Gmail]/Trash", "[Gmail]/Bin"],
        "junk": ["[Gmail]/Spam"],
        "archive": ["[Gmail]/All Mail"],
    },
    "qq": {
        "inbox": ["INBOX"],
        "sent": ["Sent Messages", "Sent", "&XfJT0ZAB-"],
        "drafts": ["Drafts", "&g0l6P3ux-"],
        "deleted": ["Deleted Messages", "Trash", "&XfJSIJZk-"],
        "junk": ["Junk", "Junk Email", "&V4NXPpCuTvY-"],
    },
    "163": {
        "inbox": ["INBOX"],
        "sent": ["&XfJT0ZAB-", "Sent", "Sent Messages"],
        "drafts": ["&g0l6P3ux-", "Drafts"],
        "deleted": ["&XfJSIJZk-", "Deleted Messages", "Trash"],
        "junk": ["&V4NXPpCuTvY-", "Junk", "Junk Email"],
    },
    "126": {
        "inbox": ["INBOX"],
        "sent": ["&XfJT0ZAB-", "Sent", "Sent Messages"],
        "drafts": ["&g0l6P3ux-", "Drafts"],
        "deleted": ["&XfJSIJZk-", "Deleted Messages", "Trash"],
        "junk": ["&V4NXPpCuTvY-", "Junk", "Junk Email"],
    },
    "yahoo": {
        "inbox": ["INBOX"],
        "sent": ["Sent", "Bulk Mail"],
        "drafts": ["Draft", "Drafts"],
        "deleted": ["Trash", "Deleted Items"],
        "junk": ["Bulk Mail", "Spam"],
        "archive": ["Archive"],
    },
    "icloud": {
        "inbox": ["INBOX"],
        "sent": ["Sent Messages", "Sent"],
        "drafts": ["Drafts"],
        "deleted": ["Deleted Messages", "Trash"],
        "junk": ["Junk", "Bulk Mail"],
        "archive": ["Archive"],
    },
}


def get_imap_folder_candidates(provider: str, folder: str) -> list[str]:
    """Return candidate IMAP folder names for the given provider and logical folder."""
    provider_key: str = (provider or "_default").strip().lower()
    folder_key: str = normalize_folder_key(folder)
    provider_map: dict[str, list[str]] | None = _FOLDER_CANDIDATES.get(provider_key)
    if provider_map is None:
        provider_map = _FOLDER_CANDIDATES.get("_default", {})
    candidates: list[str] = list(provider_map.get(folder_key, ["INBOX"]))
    # Always include the raw folder name as last resort
    raw_name: str = folder.strip()
    if raw_name and raw_name not in candidates:
        candidates.append(raw_name)
    return candidates


def normalize_folder_key(folder: str) -> str:
    value = (folder or "inbox").strip().lower()
    aliases: dict[str, str] = {
        "junkemail": "junk",
        "junk email": "junk",
        "spam": "junk",
        "deleteditems": "deleted",
        "deleted items": "deleted",
        "trash": "deleted",
        "sentitems": "sent",
        "sent items": "sent",
    }
    return aliases.get(value, value)
