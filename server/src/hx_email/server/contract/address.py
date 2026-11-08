"""Address v2: hierarchical, platform-declared paths (docs/messaging-router.md 2.5).

Grammar::

    address  := platform ":" instance_id ( "/" kind [ "/" id ] )*
    id       := part ( "/" part ){arity - 1}

``qq:3/group/123`` and ``github:7/repo/hx/HX-Email/issue/42`` are full addresses. Any
shorter path is a selector: ``qq:3`` (one account), ``qq:3/group`` (every group),
``github:7/repo/hx/HX-Email`` (the repo and every thread under it). Prefix match is on
path steps, never on characters, so ``group/12`` does not cover ``group/123``.

Storage still keys rows by the v1 string. ``to_legacy`` and ``from_legacy`` convert one
address, and ``legacy_scope`` turns a selector into the exact value plus LIKE patterns
the reader uses, so v2 needs no data migration.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from hx_email.server.contract.builtin import REGISTRY
from hx_email.server.contract.capabilities import (
    PLACEHOLDER,
    AddressKind,
    PlatformCapabilities,
)

V2_HEAD: Final[re.Pattern[str]] = re.compile(r"^([a-z][a-z0-9_]*):([0-9]+)(/.*)?$")
LIKE_ESCAPE: Final[str] = "\\"


class AddressError(ValueError):
    """Not a valid v2 address or selector for any registered platform."""


@dataclass(frozen=True)
class Step:
    """One path level; ``ident`` is empty when a selector stops at the kind."""

    kind: str
    ident: str = ""


@dataclass(frozen=True)
class Address:
    platform: str
    instance_id: int
    steps: tuple[Step, ...] = ()

    @property
    def text(self) -> str:
        path: str = "".join(
            f"/{step.kind}/{step.ident}" if step.ident else f"/{step.kind}" for step in self.steps
        )
        return f"{self.platform}:{self.instance_id}{path}"

    @property
    def is_full(self) -> bool:
        return bool(self.steps) and all(step.ident for step in self.steps)

    @property
    def parent(self) -> Address:
        """The address one level up; an account root is its own parent."""
        return Address(self.platform, self.instance_id, self.steps[:-1]) if self.steps else self

    def ids(self) -> dict[str, str]:
        return {step.kind: step.ident for step in self.steps}


@dataclass(frozen=True)
class LegacyScope:
    """What a selector means against v1 ``chat_id`` values."""

    platform: str
    instance_id: int
    exact: str = ""
    patterns: tuple[str, ...] = ()


def is_v2(text: str) -> bool:
    """v2 has no colon after the instance id; v1 always does."""
    return V2_HEAD.match(text) is not None


def capabilities_of(platform: str) -> PlatformCapabilities:
    found: PlatformCapabilities | None = REGISTRY.get(platform)
    if found is None:
        raise AddressError(f"unknown platform: {platform!r}")
    return found


# 地址由平台声明的 kind 树解析, 存储仍是 v1; 新平台只加声明不改这里
# 决策记录: .agents/notes/implemented/feature/2026-11-08-router-contract-v2.md
def parse_address(text: str) -> Address:
    head: re.Match[str] | None = V2_HEAD.match(text)
    if head is None:
        raise AddressError(f"not a v2 address: {text!r}")
    platform, instance_text, path = head.group(1), head.group(2), head.group(3) or ""
    caps: PlatformCapabilities = capabilities_of(platform)
    if int(instance_text) <= 0:
        raise AddressError(f"instance id must be positive: {text!r}")
    parts: list[str] = path.split("/")[1:] if path else []
    steps: list[Step] = []
    parent: str = ""
    while parts:
        kind: AddressKind | None = caps.kind(parts.pop(0))
        if kind is None or kind.parent != parent:
            raise AddressError(f"unexpected kind in {text!r}")
        if not parts:
            steps.append(Step(kind.name))
            break
        if len(parts) < kind.arity:
            raise AddressError(f"{kind.name} id needs {kind.arity} parts in {text!r}")
        ident: str = "/".join(parts[: kind.arity])
        del parts[: kind.arity]
        if not kind.id_matches(ident):
            raise AddressError(f"invalid {kind.name} id {ident!r}")
        steps.append(Step(kind.name, ident))
        parent = kind.name
    return Address(platform, int(instance_text), tuple(steps))


def fill(template: str, ids: dict[str, str], escape: bool) -> str:
    """Fill ``{kind}`` slots; a missing id becomes ``%`` when building a LIKE pattern.

    ``PLACEHOLDER.split`` alternates literal text (even index) and kind names (odd index).
    """
    out: list[str] = []
    for index, piece in enumerate(PLACEHOLDER.split(template)):
        if index % 2 == 0:
            out.append(like_escape(piece) if escape else piece)
            continue
        value: str | None = ids.get(piece)
        if value is None:
            if not escape:
                raise AddressError(f"missing {piece} id for {template}")
            out.append("%")
        else:
            out.append(like_escape(value) if escape else value)
    return "".join(out)


def like_escape(value: str) -> str:
    return value.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2).replace("%", "\\%").replace("_", "\\_")


def to_legacy(address: Address) -> str:
    """v1 string of a full address whose last kind is stored as a session."""
    caps: PlatformCapabilities = capabilities_of(address.platform)
    kind: AddressKind | None = caps.kind(address.steps[-1].kind) if address.steps else None
    if not address.is_full or kind is None or not kind.legacy_type:
        raise AddressError(f"{address.text} is not a session address")
    peer: str = fill(kind.legacy_peer, address.ids(), escape=False)
    return f"{address.platform}:{address.instance_id}:{kind.legacy_type}:{peer}"


def from_legacy(text: str) -> Address:
    """v2 form of a v1 ``<platform>:<iid>:<type>:<peer>`` string."""
    parts: list[str] = text.split(":", 3)
    if len(parts) != 4 or not parts[1].isdigit():
        raise AddressError(f"not a v1 session address: {text!r}")
    caps: PlatformCapabilities = capabilities_of(parts[0])
    kind: AddressKind | None = caps.legacy_kind(parts[2])
    if kind is None:
        raise AddressError(f"unknown v1 session type: {parts[2]!r}")
    lineage: list[str] = caps.lineage(kind.name)
    regex: str = "".join(
        f"(?P<{piece}>.+?)" if index % 2 else re.escape(piece)
        for index, piece in enumerate(PLACEHOLDER.split(kind.legacy_peer))
    )
    found: re.Match[str] | None = re.fullmatch(regex, parts[3])
    if found is None:
        raise AddressError(f"peer does not fit {kind.legacy_peer}: {text!r}")
    steps: tuple[Step, ...] = tuple(Step(name, found.group(name)) for name in lineage)
    address: Address = Address(parts[0], int(parts[1]), steps)
    return parse_address(address.text)


def legacy_scope(address: Address) -> LegacyScope:
    """Exact v1 value (full session address) plus LIKE patterns for everything below it."""
    caps: PlatformCapabilities = capabilities_of(address.platform)
    head: str = f"{like_escape(address.platform)}:{address.instance_id}:"
    if not address.steps:
        return LegacyScope(address.platform, address.instance_id, patterns=(f"{head}%",))
    last: Step = address.steps[-1]
    ids: dict[str, str] = address.ids()
    if not last.ident:
        ids.pop(last.kind, None)
    exact: str = ""
    patterns: list[str] = []
    for kind in caps.subtree(last.kind):
        if not kind.legacy_type:
            continue
        if kind.name == last.kind and last.ident:
            exact = to_legacy(address)
            continue
        peer: str = fill(kind.legacy_peer, ids, escape=True)
        patterns.append(f"{head}{like_escape(kind.legacy_type)}:{peer}")
    return LegacyScope(address.platform, address.instance_id, exact, tuple(patterns))


def address_of_legacy(text: str) -> str:
    """Best-effort v2 text for output; an unmappable v1 value yields an empty string."""
    try:
        return from_legacy(text).text
    except AddressError:
        return ""
