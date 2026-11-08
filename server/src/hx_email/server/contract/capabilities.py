"""Platform capability declarations of the router contract v2 (docs/messaging-router.md 2.5).

A platform describes itself here as data: the tree of address kinds it exposes, how each
kind maps to the v1 ``<platform>:<iid>:<type>:<peer>`` form still used in storage, which
event kinds it emits, which signals (flags) it fills, and which actions it accepts. The
address parser, the MCP schema enums and ``capabilities_list`` all read this registry, so
a new platform is one declaration plus a provider, never an edit to a core enum.

Only what is implemented is declared; a kind joins the declaration in the stage that
implements it. Risk is declared per platform and may be overridden per kind, together
with the name of the rate profile its sends are shaped by: QQ chat and QQ Zone share an
account but not a risk tier (docs/providers/qq-zone.md 4).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Final, Literal

RiskLevel = Literal["official", "third_party", "unofficial_web"]
DeliveryMode = Literal["push", "pull"]
NAME_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*$")
PLACEHOLDER: Final[re.Pattern[str]] = re.compile(r"\{([a-z][a-z0-9_]*)\}")


class CapabilityError(ValueError):
    """A declaration is inconsistent (unknown parent, duplicate kind, bad template)."""


@dataclass(frozen=True)
class AddressKind:
    """One level of a platform's address tree.

    ``arity`` is how many ``/``-separated parts the id spans (a GitHub repo is
    ``owner/name``, so 2). ``legacy_type`` and ``legacy_peer`` map a full address that
    ends on this kind to the v1 string; ``legacy_peer`` names ids by kind, as in
    ``{repo}#{issue}``. A kind without ``legacy_type`` is a pure grouping level.
    """

    name: str
    parent: str = ""
    arity: int = 1
    id_pattern: str = r"[^/]+"
    legacy_type: str = ""
    legacy_peer: str = ""
    sendable: bool = False
    description: str = ""
    risk_level: str = ""
    rate_profile: str = ""

    def id_matches(self, ident: str) -> bool:
        parts: list[str] = ident.split("/")
        return len(parts) == self.arity and re.fullmatch(self.id_pattern, ident) is not None


@dataclass(frozen=True)
class ParamSpec:
    """One string parameter of an action; ``choices`` and ``pattern`` are checked as given."""

    name: str
    description: str
    required: bool = False
    choices: tuple[str, ...] = ()
    pattern: str = ""
    max_length: int = 0

    def problem(self, value: str) -> str:
        """Why ``value`` is not accepted, or ``""`` when it is."""
        if self.choices and value not in self.choices:
            return f"{self.name} must be one of {', '.join(self.choices)}"
        if self.pattern and value and re.fullmatch(self.pattern, value) is None:
            return f"{self.name} does not match {self.pattern}"
        if self.max_length and len(value) > self.max_length:
            return f"{self.name} is longer than {self.max_length} characters"
        return ""

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "required": self.required,
            "choices": list(self.choices),
            "pattern": self.pattern,
            "max_length": self.max_length,
        }


@dataclass(frozen=True)
class ActionSpec:
    """An outbound operation a platform accepts on some address kinds.

    ``params`` is the whole accepted parameter set: an action invoked with a key not
    listed here is refused, so the declaration is also the validation.
    """

    name: str
    targets: tuple[str, ...]
    description: str
    requires: tuple[str, ...] = ()
    params: tuple[ParamSpec, ...] = ()


@dataclass(frozen=True)
class KindRule:
    """``platform_message_id`` prefix to event kind, first match wins."""

    prefix: str
    kind: str


@dataclass(frozen=True)
class PlatformCapabilities:
    platform: str
    title: str
    risk_level: RiskLevel
    delivery: DeliveryMode
    kinds: tuple[AddressKind, ...]
    event_kinds: tuple[str, ...]
    default_event_kind: str
    signals: tuple[str, ...]
    actions: tuple[ActionSpec, ...]
    kind_rules: tuple[KindRule, ...] = ()
    rate_profile: str = ""
    index: dict[str, AddressKind] = field(default_factory=dict, compare=False, repr=False)

    def __post_init__(self) -> None:
        if not NAME_PATTERN.match(self.platform):
            raise CapabilityError(f"invalid platform name: {self.platform!r}")
        for kind in self.kinds:
            if not NAME_PATTERN.match(kind.name) or kind.name in self.index:
                raise CapabilityError(f"invalid or duplicate kind: {kind.name!r}")
            if kind.parent and kind.parent not in self.index:
                raise CapabilityError(f"kind {kind.name} declared before parent {kind.parent}")
            self.index[kind.name] = kind
        for kind in self.kinds:
            if kind.legacy_type and set(PLACEHOLDER.findall(kind.legacy_peer)) != set(
                self.lineage(kind.name)
            ):
                raise CapabilityError(f"legacy_peer of {kind.name} must name its whole lineage")

    def kind(self, name: str) -> AddressKind | None:
        return self.index.get(name)

    def children(self, name: str) -> list[AddressKind]:
        return [kind for kind in self.kinds if kind.parent == name]

    def lineage(self, name: str) -> list[str]:
        """Kind names from the root down to ``name``."""
        chain: list[str] = []
        current: AddressKind | None = self.index.get(name)
        while current is not None:
            chain.insert(0, current.name)
            current = self.index.get(current.parent) if current.parent else None
        return chain

    def subtree(self, name: str) -> list[AddressKind]:
        """``name`` and every kind below it, parents first."""
        own: AddressKind | None = self.index.get(name)
        found: list[AddressKind] = [own] if own is not None else []
        for child in self.children(name):
            found.extend(self.subtree(child.name))
        return found

    def action(self, name: str) -> ActionSpec | None:
        return next((item for item in self.actions if item.name == name), None)

    def legacy_kind(self, legacy_type: str) -> AddressKind | None:
        return next((kind for kind in self.kinds if kind.legacy_type == legacy_type), None)

    def event_kind(self, platform_message_id: str) -> str:
        for rule in self.kind_rules:
            if platform_message_id.startswith(rule.prefix):
                return rule.kind
        return self.default_event_kind

    def to_dict(self) -> dict[str, object]:
        return {
            "platform": self.platform,
            "title": self.title,
            "risk_level": self.risk_level,
            "delivery": self.delivery,
            "rate_profile": self.rate_profile,
            "address_kinds": [
                {
                    "name": kind.name,
                    "parent": kind.parent,
                    "id_parts": kind.arity,
                    "sendable": kind.sendable,
                    "description": kind.description,
                    "risk_level": kind.risk_level or self.risk_level,
                    "rate_profile": kind.rate_profile or self.rate_profile,
                }
                for kind in self.kinds
            ],
            "event_kinds": list(self.event_kinds),
            "signals": list(self.signals),
            "actions": [
                {
                    "name": action.name,
                    "targets": list(action.targets),
                    "requires": list(action.requires),
                    "description": action.description,
                    "params": [param.to_dict() for param in action.params],
                }
                for action in self.actions
            ],
        }


class CapabilityRegistry:
    """Process-wide table of platform declarations; registration order is listing order."""

    def __init__(self, declarations: tuple[PlatformCapabilities, ...] = ()) -> None:
        self.table: dict[str, PlatformCapabilities] = {}
        for item in declarations:
            self.register(item)

    def register(self, capabilities: PlatformCapabilities) -> None:
        if capabilities.platform in self.table:
            raise CapabilityError(f"platform already registered: {capabilities.platform}")
        self.table[capabilities.platform] = capabilities

    def get(self, platform: str) -> PlatformCapabilities | None:
        return self.table.get(platform)

    def platform_names(self) -> frozenset[str]:
        return frozenset(self.table)

    def legacy_types(self) -> frozenset[str]:
        return frozenset(
            kind.legacy_type
            for item in self.table.values()
            for kind in item.kinds
            if kind.legacy_type
        )

    def listing(self, platform: str = "") -> list[dict[str, object]]:
        return [
            item.to_dict()
            for item in self.table.values()
            if not platform or item.platform == platform
        ]
