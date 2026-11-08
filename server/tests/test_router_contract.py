"""Contract v2: address grammar, v1 mapping, selector scopes, capabilities, event view."""

from __future__ import annotations

import pytest
from hx_email.server.contract.address import (
    AddressError,
    address_of_legacy,
    from_legacy,
    is_v2,
    legacy_scope,
    parse_address,
    to_legacy,
)
from hx_email.server.contract.builtin import REGISTRY
from hx_email.server.contract.capabilities import (
    AddressKind,
    CapabilityError,
    CapabilityRegistry,
    PlatformCapabilities,
)
from hx_email.server.contract.event import event_view
from hx_email.server.router.envelope import parse_session
from hx_email.server.router.errors import SessionNotFoundError
from hx_email.server.router.impl.reader import parse_source


@pytest.mark.parametrize(
    ("v2", "v1"),
    [
        ("qq:3/private/10001", "qq:3:private:10001"),
        ("qq:3/group/555", "qq:3:group:555"),
        ("qq:3/temp/555-10001", "qq:3:temp:555-10001"),
        ("github:7/repo/hx/HX-Email", "github:7:repo:hx/HX-Email"),
        ("github:7/repo/hx/HX-Email/issue/42", "github:7:issue:hx/HX-Email#42"),
    ],
)
def test_v1_and_v2_round_trip(v2: str, v1: str) -> None:
    assert is_v2(v2) and not is_v2(v1)
    assert to_legacy(parse_address(v2)) == v1
    assert from_legacy(v1).text == v2
    assert parse_session(v2).address == v1


@pytest.mark.parametrize(
    "bad",
    [
        "qq:0/group/1",
        "qq:3/group/abc",
        "qq:3/issue/1",
        "github:7/issue/1",
        "github:7/repo/only",
        "nope:1/group/1",
        "qq:3/group/1/extra",
    ],
)
def test_invalid_v2_addresses_are_rejected(bad: str) -> None:
    with pytest.raises(AddressError):
        parse_address(bad)


def test_session_parser_maps_v2_errors_to_not_found() -> None:
    with pytest.raises(SessionNotFoundError):
        parse_session("qq:3/group")
    with pytest.raises(SessionNotFoundError):
        parse_session("qq:3/group/x")


def test_selectors_become_exact_value_and_like_patterns() -> None:
    repo = legacy_scope(parse_address("github:7/repo/hx/HX_Email"))
    assert repo.exact == "github:7:repo:hx/HX_Email"
    assert repo.patterns == (
        "github:7:issue:hx/HX\\_Email#%",
        "github:7:discussion:hx/HX\\_Email#%",
        "github:7:commit:hx/HX\\_Email@%",
    )
    every_repo = legacy_scope(parse_address("github:7/repo"))
    assert every_repo.exact == "" and every_repo.patterns == (
        "github:7:repo:%",
        "github:7:issue:%#%",
        "github:7:discussion:%#%",
        "github:7:commit:%@%",
    )
    groups = legacy_scope(parse_address("qq:3/group"))
    assert groups.patterns == ("qq:3:group:%",)
    account = legacy_scope(parse_address("qq:3"))
    assert account.patterns == ("qq:3:%",)
    one = legacy_scope(parse_address("qq:3/group/555"))
    assert one.exact == "qq:3:group:555" and one.patterns == ()


def test_reader_accepts_v2_sources() -> None:
    scope = parse_source("github:7/repo/hx/HX-Email")
    assert scope.instance_id == 7 and scope.chat_id == "github:7:repo:hx/HX-Email"
    assert scope.patterns == (
        "github:7:issue:hx/HX-Email#%",
        "github:7:discussion:hx/HX-Email#%",
        "github:7:commit:hx/HX-Email@%",
    )
    assert parse_source("qq:3/group/555").chat_id == "qq:3:group:555"
    with pytest.raises(SessionNotFoundError):
        parse_source("qq:3/channel")


def test_registry_drives_platforms_and_listing() -> None:
    assert REGISTRY.platform_names() == frozenset({"qq", "github"})
    assert REGISTRY.legacy_types() == frozenset(
        {"private", "group", "temp", "qzonepost", "repo", "issue", "discussion", "commit"}
    )
    listing = REGISTRY.listing("github")
    assert [item["platform"] for item in listing] == ["github"]
    kinds = listing[0]["address_kinds"]
    assert isinstance(kinds, list) and kinds[1]["parent"] == "repo"


def test_declarations_are_validated() -> None:
    def build(*kinds: AddressKind) -> PlatformCapabilities:
        return PlatformCapabilities("x", "X", "official", "push", kinds, ("m",), "m", (), ())

    with pytest.raises(CapabilityError):
        build(AddressKind("child", parent="missing"))
    with pytest.raises(CapabilityError):
        build(AddressKind("a"), AddressKind("a"))
    with pytest.raises(CapabilityError):
        build(AddressKind("a", legacy_type="a", legacy_peer="{b}"))
    registry = CapabilityRegistry((build(AddressKind("a")),))
    with pytest.raises(CapabilityError):
        registry.register(build(AddressKind("a")))


def test_event_view_adds_v2_fields_without_dropping_v1() -> None:
    envelope: dict[str, object] = {
        "platform": "github",
        "session": "github:7:issue:hx/HX-Email#42",
        "sender": {"id": "1", "name": "bot", "is_self": True},
        "text": "hi",
        "reply_to": "rc:9",
        "platform_message_id": "rc:10",
        "attachments": [],
    }
    view = event_view(envelope)
    assert view["session"] == envelope["session"]
    assert view["address"] == "github:7/repo/hx/HX-Email/issue/42"
    assert view["parent"] == "github:7/repo/hx/HX-Email"
    assert view["kind"] == "review_comment"
    assert view["flags"] == {"from_self": True, "mention_self": None, "reply_to_self": None}
    assert view["segments"] == [{"type": "reply", "id": "rc:9"}, {"type": "text", "text": "hi"}]
    qq = event_view({"platform": "qq", "session": "qq:3:group:555", "platform_message_id": "1"})
    assert qq["kind"] == "message" and qq["parent"] == "qq:3"
    given = event_view({**envelope, "flags": {"mention_self": True}, "mentions": [{"id": "1"}]})
    assert given["flags"] == {"from_self": True, "mention_self": True, "reply_to_self": None}
    assert given["mentions"] == [{"id": "1"}]
    assert address_of_legacy("qq:3:weird:1") == ""
