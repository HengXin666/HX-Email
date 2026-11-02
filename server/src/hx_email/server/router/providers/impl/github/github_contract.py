"""GitHub-specific additions to the shared router contract.

Only the two names that are genuinely GitHub-only live here: the write action that
maps a session address plus payload onto one REST call, and the advertised limits.
Everything else (``SendResult``, ``SessionRef``, ``OutboundPayload``, ``ProviderLimits``)
comes from :mod:`hx_email.server.router.provider`, so the provider implements exactly
the protocol the router routes against.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from hx_email.server.router.provider import ProviderLimits

GitHubWriteKind = Literal["comment", "open_issue", "reply_review_comment"]
WRITE_KINDS: Final[frozenset[str]] = frozenset({"comment", "open_issue", "reply_review_comment"})


@dataclass(frozen=True)
class GitHubWriteAction:
    """One REST write: which endpoint, which body, and the marker that makes it findable.

    ``reply_to_comment_id`` is only set for ``reply_review_comment``, where GitHub needs
    the parent comment id in the path rather than in the body.
    """

    kind: GitHubWriteKind
    repo_full_name: str
    delivery_id: str
    number: int = 0
    body: str = ""
    title: str = ""
    reply_to_comment_id: int = 0

    def __post_init__(self) -> None:
        if self.kind not in WRITE_KINDS:
            raise ValueError(f"unknown GitHub write kind: {self.kind}")
        if "/" not in self.repo_full_name:
            raise ValueError(f"repo must be owner/name, got {self.repo_full_name!r}")


# GitHub is generous next to QQ: the installation token is per-app, rate limits are
# counted per installation, and secondary limits are the real constraint. The numbers
# below are deliberately below the documented primary limits so a burst never trips a
# secondary limit; docs/providers/github-app.md 6.3 marks them 需复核 against a live app.
GITHUB_LIMITS: Final[ProviderLimits] = ProviderLimits(
    per_session_interval_seconds=1.0,
    per_session_per_minute=30,
    per_account_per_minute=60,
    per_account_per_hour=1000,
    burst=5,
    daily_cap=5000,
    max_text_length=65000,
)
