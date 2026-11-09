"""Session addresses: ``<platform>:<instance_id>:<session_type>:<peer>`` (spec section 2).

Split out of the former ``envelope.py`` module (stage 3) to keep every file under the
300 line ceiling; ``hx_email.server.router.envelope`` still re-exports every name.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, Literal

from hx_email.server.contract.address import AddressError, is_v2, parse_address, to_legacy
from hx_email.server.contract.builtin import REGISTRY
from hx_email.server.router.errors import SessionNotFoundError

SessionType = Literal[
    "private", "group", "temp", "repo", "issue", "discussion", "commit", "qzonepost", "channel"
]
Direction = Literal["inbound", "outbound"]

PLATFORMS: Final[frozenset[str]] = REGISTRY.platform_names()
SESSION_TYPES: Final[frozenset[str]] = REGISTRY.legacy_types()
DIRECTIONS: Final[frozenset[str]] = frozenset({"inbound", "outbound"})
# 平台名可含下划线 (github_user), 与能力声明的 NAME_PATTERN 一致
SEGMENT_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9_]+$")


@dataclass(frozen=True)
class SessionAddress:
    """Parsed ``<platform>:<instance_id>:<session_type>:<peer>``."""

    platform: str
    instance_id: int
    session_type: str
    peer: str

    @property
    def address(self) -> str:
        return f"{self.platform}:{self.instance_id}:{self.session_type}:{self.peer}"

    @property
    def legacy_chat_type(self) -> str:
        """Value for the old ``chat_type`` column: private and temp are private."""
        return "private" if self.session_type in ("private", "temp") else "group"


def type_belongs(platform: str, session_type: str) -> bool:
    """会话类型按平台声明: ``qq:3:channel:1`` 与 ``qqbot:3:group:1`` 都不是合法地址."""
    caps = REGISTRY.get(platform)
    return caps is not None and caps.legacy_kind(session_type) is not None


# v2 地址在这里折回 v1, 落库, 幂等, 出站都只认 v1
# 决策记录: .agents/notes/implemented/feature/2026-11-08-router-contract-v2.md
def parse_session(address: str) -> SessionAddress:
    """Split on the first three colons; a v2 address is converted to v1 first."""
    if is_v2(address):
        try:
            address = to_legacy(parse_address(address))
        except AddressError as error:
            raise SessionNotFoundError(str(error)) from error
    parts: list[str] = address.split(":", 3)
    if len(parts) != 4:
        raise SessionNotFoundError(f"invalid session address: {address!r}")
    platform, instance_text, session_type, peer = parts
    valid: bool = (
        all(SEGMENT_PATTERN.match(part) for part in (platform, instance_text, session_type))
        and platform in PLATFORMS
        and instance_text.isdigit()
        and int(instance_text) > 0
        and session_type in SESSION_TYPES
        and type_belongs(platform, session_type)
        and bool(peer)
    )
    if not valid:
        raise SessionNotFoundError(f"invalid session address: {address!r}")
    return SessionAddress(platform, int(instance_text), session_type, peer)


def format_session(platform: str, instance_id: int, session_type: str, peer: str) -> str:
    """Build and validate an address in one step."""
    return parse_session(f"{platform}:{instance_id}:{session_type}:{peer}").address
