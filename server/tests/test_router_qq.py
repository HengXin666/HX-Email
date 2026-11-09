"""Tests for the QQ (NapCat / OneBot 11) router provider."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from pathlib import Path

import pytest
from hx_email.config import Settings
from hx_email.database import migrate
from hx_email.server.contract.builtin import REGISTRY
from hx_email.server.contract.event import event_view
from hx_email.server.hub.route_model import filter_from
from hx_email.server.messaging.store import create_instance
from hx_email.server.router.envelope import validate_inbound
from hx_email.server.router.impl.reader import read_messages
from hx_email.server.router.impl.store import store_inbound
from hx_email.server.router.providers.impl import qq_events as ev
from hx_email.server.router.providers.impl import qq_limits
from hx_email.server.router.providers.impl import qq_types as qt
from hx_email.server.router.providers.qq import QQNapCatProvider, classify_call_result

OneBotCallResult = qt.OneBotCallResult
SessionRef = qt.SessionRef
OutboundPayload = qt.OutboundPayload

IID = 3
GROUP = "qq:3:group:123456789"
FRIENDS = [{"user_id": 10001, "nickname": "alice"}]
GROUPS = [{"group_id": 123456789, "group_name": "dev"}]


class FakeCaller:
    def __init__(self, send_result: OneBotCallResult | None = None) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.send_result = send_result or OneBotCallResult("ok", data={"message_id": 777})

    def call_action(self, action: str, params: Mapping[str, object]) -> OneBotCallResult:
        self.calls.append((action, dict(params)))
        lists = {"get_friend_list": FRIENDS, "get_group_list": GROUPS}
        return OneBotCallResult("ok", data=lists[action]) if action in lists else self.send_result


def ready(result: OneBotCallResult | None = None) -> tuple[QQNapCatProvider, FakeCaller]:
    caller = FakeCaller(result)
    provider = QQNapCatProvider(IID, caller, event_token="tok")
    provider.list_sessions(IID)
    return provider, caller


def text(value: str) -> dict[str, object]:
    return {"type": "text", "data": {"text": value}}


BASE_EVENT = json.loads(
    '{"post_type": "message", "message_type": "group", "sub_type": "normal", "self_id": 20002,'
    ' "user_id": 10001, "group_id": 123456789, "message_id": 1873992211, "time": 1793632805,'
    ' "sender": {"nickname": "alice", "card": "A"}}'
)


def event(segments: list[dict[str, object]], **overrides: object) -> dict[str, object]:
    return {**BASE_EVENT, "message": segments, **overrides}


def envelope(segments: list[dict[str, object]], **overrides: object) -> dict[str, object]:
    result = ev.to_envelope(IID, event(segments, **overrides))
    assert result is not None
    return result


def test_group_message_envelope():
    env = envelope([text("今晚的发布推迟到 9 点")])
    assert (env["session"], env["session_type"], env["platform"]) == (GROUP, "group", "qq")
    assert (env["instance_id"], env["direction"]) == (3, "inbound")
    assert env["sender"] == {"id": "10001", "name": "alice", "is_self": False}
    assert env["text"] == "今晚的发布推迟到 9 点"
    assert env["platform_message_id"] == "1873992211"
    assert env["occurred_at"] == "2026-11-02T15:20:05Z"
    assert env["dedup_key"] == "qq:1873992211:1793632805"
    assert (env["reply_to"], env["attachments"]) == ("", [])


def test_private_message_envelope_and_is_self():
    friend = {"message_type": "private", "sub_type": "friend", "sender": {"nickname": "me"}}
    env = envelope([text("hi"), text(" there")], user_id=20002, **friend)
    assert (env["session"], env["session_type"]) == ("qq:3:private:20002", "private")
    assert env["text"] == "hi there"
    assert env["sender"] == {"id": "20002", "name": "me", "is_self": True}


def test_temp_message_envelope():
    env = envelope([text("x")], message_type="private", sub_type="group", group_id=600001)
    assert (env["session"], env["session_type"]) == ("qq:3:temp:600001-10001", "temp")


def test_image_envelope():
    image = {"type": "image", "data": {"file": "a.jpg", "url": "u://a", "file_size": "2048"}}
    env = envelope([text("看图"), image])
    assert env["text"] == "看图[image]"
    assert env["attachments"] == [{"kind": "image", "url": "u://a", "name": "a.jpg", "size": 2048}]


def test_reply_envelope():
    env = envelope([{"type": "reply", "data": {"id": "1838273"}}, text("收到")])
    assert (env["reply_to"], env["text"]) == ("1838273", "收到")


def test_at_envelope():
    at_one = {"type": "at", "data": {"qq": "10002"}}
    at_all = {"type": "at", "data": {"qq": "all"}}
    assert envelope([at_one, text(" 看一下"), at_all])["text"] == "@10002 看一下@all"


def test_at_self_sets_mention_flags():
    at_self = {"type": "at", "data": {"qq": "20002", "name": "bot"}}
    env = envelope([at_self, text(" 帮忙"), {"type": "at", "data": {"qq": "all"}}])
    assert env["kind"] == "message"
    assert env["mentions"] == [{"id": "20002", "name": "bot", "is_self": True}]
    assert env["flags"] == {"from_self": False, "mention_self": True, "reply_to_self": False}


def test_at_other_is_not_mention_self():
    env = envelope([{"type": "at", "data": {"qq": "10002"}}, text(" 看一下")])
    assert env["mentions"] == [{"id": "10002", "name": "", "is_self": False}]
    assert env["flags"]["mention_self"] is False


def test_own_message_never_mentions_self():
    env = envelope([{"type": "at", "data": {"qq": "20002"}}], user_id=20002)
    assert env["flags"] == {"from_self": True, "mention_self": False, "reply_to_self": False}


def test_missing_self_id_leaves_flags_unknown():
    env = envelope([{"type": "at", "data": {"qq": "20002"}}], self_id=None)
    assert env["flags"] == {}


def test_stored_reply_and_mention_reach_view_and_filter(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    iid = create_instance(settings, 1, "qq", "qq", {}).id
    own = event([text("发布推迟")], user_id=20002, message_id=777)
    at_self = {"type": "at", "data": {"qq": "20002"}}
    reply = event([{"type": "reply", "data": {"id": "777"}}, at_self, text(" 收到")])
    for item in (own, reply | {"message_id": 778}):
        mapped = ev.to_envelope(iid, item)
        assert mapped is not None
        store_inbound(settings, validate_inbound(mapped, iid))
    page = read_messages(settings, 1, f"qq:{iid}/group/123456789", "", limit=10)
    views = [event_view(item.to_dict()) for item in page.messages]
    assert views[0]["flags"] == {"from_self": True, "mention_self": False, "reply_to_self": False}
    assert views[1]["flags"] == {"from_self": False, "mention_self": True, "reply_to_self": True}
    wanted = filter_from({"mention_self": True})
    assert [wanted.accepts(view) for view in views] == [False, True]
    caps = REGISTRY.get("qq")
    flags = views[1]["flags"]
    assert caps is not None and isinstance(flags, dict)
    assert set(caps.signals) == set(flags)


def test_non_message_events_dropped_with_debug(caplog):
    caplog.set_level(logging.DEBUG)
    assert ev.to_envelope(IID, {"post_type": "meta_event", "meta_event_type": "heartbeat"}) is None
    assert ev.to_envelope(IID, {"post_type": "notice", "notice_type": "group_recall"}) is None
    assert "post_type=meta_event" in caplog.text
    assert "post_type=notice" in caplog.text


def test_parse_event_body_and_registers_temp():
    provider = QQNapCatProvider(IID, FakeCaller(), event_token="tok")
    raw = event([], message_type="private", sub_type="group", user_id=10009, group_id=600001)
    envelopes = provider.parse_event(IID, {}, json.dumps(raw).encode())
    assert [e["session"] for e in envelopes] == ["qq:3:temp:600001-10009"]
    assert "qq:3:temp:600001-10009" in provider.known_sessions
    assert provider.parse_event(IID, {}, b"not json") == []


def test_verify_event_tokens():
    provider = QQNapCatProvider(IID, FakeCaller(), event_token="tok")
    assert provider.verify_event(IID, {"X-Messaging-Token": "tok"}, b"") is True
    assert provider.verify_event(IID, {"Authorization": "Bearer tok"}, b"") is True
    assert provider.verify_event(IID, {"X-Messaging-Token": "bad"}, b"") is False
    assert provider.verify_event(4, {"X-Messaging-Token": "tok"}, b"") is False


def test_dedup_key_and_session_address_build_and_parse():
    assert ev.dedup_key(1873992211, 1793632805) == "qq:1873992211:1793632805"
    assert ev.dedup_key("5", "1700000000") == "qq:5:1700000000"
    assert ev.dedup_key(5, 1) != ev.dedup_key(5, 2)
    assert ev.session_address(3, "group", "123456789") == GROUP
    assert ev.session_address(3, "private", "10001") == "qq:3:private:10001"
    assert ev.session_address(3, "temp", "123456789-10001") == "qq:3:temp:123456789-10001"
    temp = ev.parse_session_address("qq:3:temp:123456789-10001")
    assert (temp.instance_id, temp.session_type) == (3, "temp")
    assert (temp.peer_group_id, temp.peer_user_id) == ("123456789", "10001")
    group = ev.parse_session_address("qq:3:group:600001")
    assert (group.peer_group_id, group.peer_user_id) == ("600001", "")


BAD_ADDRESSES = "qq:20002:p:10001 qq:3:g:1 github:3:group:1 qq:x:group:1 qq:3:group: qq:3:temp:1"


@pytest.mark.parametrize("address", BAD_ADDRESSES.split())
def test_session_address_invalid(address):
    with pytest.raises(qt.InvalidSessionError):
        ev.parse_session_address(address)
    with pytest.raises(qt.InvalidSessionError):
        ev.session_address(3, "group", "abc")


def test_instance_mismatch_rejected():
    provider, caller = ready()
    with pytest.raises(qt.SessionMismatchError):
        provider.resolve_session("qq:4:group:123456789")
    with pytest.raises(qt.SessionMismatchError):
        provider.send_message("qq:4:group:123456789", "hi")
    with pytest.raises(qt.SessionMismatchError):
        provider.list_sessions(4)
    assert all(action != "send_msg" for action, _ in caller.calls)


def test_list_sessions_maps_friends_and_groups():
    refs = QQNapCatProvider(IID, FakeCaller(), event_token="tok").list_sessions(IID)
    assert refs == [
        SessionRef("qq:3:private:10001", "qq", 3, "private", "10001", "alice"),
        SessionRef(GROUP, "qq", 3, "group", "123456789", "dev"),
    ]


def test_cold_start_blocks_unknown_targets():
    provider = QQNapCatProvider(IID, FakeCaller(), event_token="tok")
    with pytest.raises(qt.SessionNotSendableError):
        provider.send_message(GROUP, "hi")
    provider.list_sessions(IID)
    with pytest.raises(qt.SessionNotSendableError):
        provider.send_message("qq:3:private:99999", "hi")
    ref = SessionRef("qq:3:private:99999", "qq", 3, "private", "99999", "")
    result = provider.send(ref, OutboundPayload("d1", "hi", "", ""))
    assert (result.status, result.error_code) == ("failed", "session_not_sendable")


def test_send_group_success_params():
    provider, caller = ready()
    result = provider.send_message(GROUP, "[CQ:face,id=1]", reply_to="42")
    assert (result.status, result.platform_message_id, result.retryable) == ("sent", "777", False)
    action, params = caller.calls[-1]
    assert (action, params["message_type"], params["group_id"]) == ("send_msg", "group", 123456789)
    assert params["message"] == [{"type": "reply", "data": {"id": "42"}}, text("[CQ:face,id=1]")]


def test_send_temp_carries_group_and_user():
    provider, caller = ready()
    provider.known_sessions.add("qq:3:temp:600001-10001")
    provider.send_message("qq:3:temp:600001-10001", "hi")
    params = caller.calls[-1][1]
    assert params["message_type"] == "private"
    assert (params["user_id"], params["group_id"]) == (10001, 600001)


def test_send_text_too_long():
    provider, caller = ready()
    result = provider.send_message(GROUP, "a" * 1501)
    assert (result.status, result.error_code) == ("failed", "text_too_long")
    assert caller.calls[-1][0] == "get_group_list"


def http(status: int) -> OneBotCallResult:
    return OneBotCallResult("http_error", http_status=status)


def retcode(code: int, wording: str = "") -> OneBotCallResult:
    return OneBotCallResult("ok", retcode=code, wording=wording)


@pytest.mark.parametrize(
    ("call", "status", "retryable", "code"),
    [
        (OneBotCallResult("timeout"), "unknown", False, "delivery_unknown"),
        (OneBotCallResult("connect_error"), "retry", True, "provider_unreachable"),
        (http(502), "retry", True, "provider_unavailable"),
        (http(503), "retry", True, "provider_unavailable"),
        (http(504), "retry", True, "provider_unavailable"),
        (http(500), "failed", False, "provider_error"),
        (http(401), "failed", False, "provider_auth"),
        (http(403), "failed", False, "provider_auth"),
        (retcode(1401), "failed", False, "provider_auth"),
        (retcode(1403), "failed", False, "provider_auth"),
        (retcode(1400, "bad"), "failed", False, "bad_request"),
        (retcode(1404), "failed", False, "action_not_found"),
        (retcode(100, "对方不是好友"), "failed", False, "target_unavailable"),
        (retcode(100, "你已被禁言"), "failed", False, "muted"),
        (retcode(100, "oops"), "failed", False, "provider_error"),
    ],
)
def test_send_error_classification(call, status, retryable, code):
    provider, _ = ready(call)
    result = provider.send_message(GROUP, "hi")
    assert (result.status, result.retryable, result.error_code) == (status, retryable, code)
    assert (result.risk_signal, result.platform_message_id) == (False, "")
    assert provider.phase == ("error" if code == "provider_auth" else "stopped")


RISK_WORDINGS = ["发送消息过于频繁", "账号异常, 已触发风控", "账号已冻结"]


@pytest.mark.parametrize("call", [*(retcode(100, w) for w in RISK_WORDINGS), http(429)])
def test_risk_signal_raises_and_send_flags(call):
    provider, _ = ready(call)
    with pytest.raises(qt.RiskSignalError) as info:
        provider.send_message(GROUP, "hi")
    assert (info.value.result.risk_signal, info.value.error_code) == (True, "risk_control")
    ref = SessionRef(GROUP, "qq", 3, "group", "123456789", "dev")
    result = provider.send(ref, OutboundPayload("d1", "hi", "", ""))
    assert result.risk_signal is True
    assert result.status == ("retry" if call.http_status == 429 else "failed")
    if call.http_status == 429:
        assert (result.retryable, classify_call_result(call).retry_after_seconds) == (True, 60)


SPEC_PROFILES = {
    "per_session_interval_seconds": (3.0, 6.0),
    "per_session_per_minute": (10, 5),
    "burst": (3, 2),
    "refill_interval_seconds": (1.0, 3.0),
    "per_account_per_minute": (20, 8),
    "per_account_per_hour": (300, 120),
    "daily_cap": (1000, 300),
    "jitter_min_seconds": (0.5, 1.0),
    "jitter_max_seconds": (1.5, 3.0),
    "max_text_length": (1500, 1500),
}


@pytest.mark.parametrize("field", sorted(SPEC_PROFILES))
def test_profiles_match_spec(field):
    expected_default, expected_conservative = SPEC_PROFILES[field]
    assert getattr(qq_limits.DEFAULT_PROFILE, field) == expected_default
    assert getattr(qq_limits.CONSERVATIVE_PROFILE, field) == expected_conservative


def test_other_limits_match_spec():
    limits = qq_limits
    assert limits.DAILY_CAP_TIMEZONE == "Asia/Shanghai"
    assert (limits.BROADCAST_MIN_GAP_SECONDS, limits.BROADCAST_JITTER_MAX_SECONDS) == (8.0, 4.0)
    assert limits.BROADCAST_DAILY_SESSION_CAP == 20
    assert (limits.REQUEST_TIMEOUT_SECONDS, limits.RETRY_MAX_ATTEMPTS) == (10.0, 3)
    assert limits.RETRY_JITTER_RATIO == 0.2
    assert [limits.retry_delay_seconds(n) for n in (1, 2, 3, 10)] == [2.0, 4.0, 8.0, 60.0]
    assert limits.BACKFILL_LIMIT == 20
    assert frozenset({502, 503, 504}) == limits.RETRYABLE_HTTP_STATUSES
    conservative = QQNapCatProvider(IID, FakeCaller(), "tok", rate_profile="conservative").limits
    assert (conservative.per_account_per_minute, conservative.burst) == (8, 2)
    default = QQNapCatProvider(IID, FakeCaller(), "tok").limits
    assert (default.per_session_interval_seconds, default.daily_cap) == (3.0, 1000)
