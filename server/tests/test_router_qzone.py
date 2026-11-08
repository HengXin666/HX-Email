"""QQ 空间通道: 签名与解析, 地址, 映射与触发信号, 评论发送, 轮询入库与退避, 风控档位."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest
import requests
from hx_email.config import Settings
from hx_email.database import migrate
from hx_email.server.contract.address import legacy_scope, parse_address
from hx_email.server.contract.builtin import REGISTRY
from hx_email.server.contract.event import event_view
from hx_email.server.gateway import providers as gateway_providers
from hx_email.server.gateway.impl import qzone_poll
from hx_email.server.gateway.impl.qzone_poll import QzonePoller, watch_list
from hx_email.server.gateway.providers import (
    QZONE_SHAPER,
    SHAPER,
    InstanceRow,
    profile_for,
    shaper_for,
)
from hx_email.server.messaging.store import create_instance, update_instance_status
from hx_email.server.router.envelope import parse_session, validate_inbound
from hx_email.server.router.impl.reader import read_messages
from hx_email.server.router.provider import OutboundPayload, SessionRef
from hx_email.server.router.providers.impl.qq_types import OneBotCallResult
from hx_email.server.router.providers.impl.qzone.qzone_contract import (
    QZONE_DEFAULT,
    classify,
    decode_body,
    g_tk,
    parse_cookies,
    uin_of,
)
from hx_email.server.router.providers.impl.qzone.qzone_events import feed_envelopes
from hx_email.server.router.providers.qzone import QzoneProvider

ME = "10001"
FRIEND = "20002"
TID = "a8b625d6ca6ded6650e70800"


class FakeCaller:
    def __init__(self, cookies: str = f"uin=o00{ME}; p_skey=abc; skey=x") -> None:
        self.cookies = cookies
        self.calls: list[str] = []

    def call_action(self, action: str, params: Mapping[str, object]) -> OneBotCallResult:
        self.calls.append(action)
        return OneBotCallResult("ok", data={"cookies": self.cookies})


class FakeResponse:
    def __init__(self, body: object, status_code: int = 200) -> None:
        self.status_code = status_code
        self.text = body if isinstance(body, str) else f"_Callback({json.dumps(body)});"


class FakeHttp:
    def __init__(self, *bodies: object) -> None:
        self.bodies: list[object] = list(bodies)
        self.sent: list[dict[str, object]] = []

    def respond(self, url: str, kwargs: dict[str, object]) -> FakeResponse:
        self.sent.append({"url": url} | kwargs)
        body: object = self.bodies.pop(0)
        if isinstance(body, Exception):
            raise body
        return FakeResponse(body)

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        return self.respond(url, kwargs)

    def post(self, url: str, **kwargs: object) -> FakeResponse:
        return self.respond(url, kwargs)


def post(owner: str = ME) -> dict[str, object]:
    return {
        "tid": TID,
        "uin": int(owner),
        "name": "me",
        "content": "今天天气不错",
        "created_time": 1793635200,
        "pic": [{"url1": "u"}],
        "commentlist": [
            {
                "tid": 1,
                "uin": int(FRIEND),
                "name": "friend",
                "content": "@{uin:10001,nick:me,who:1} 去哪玩",
                "create_time": 1793635260,
                "list_3": [
                    {"tid": 1, "uin": int(ME), "name": "me", "content": "公园", "create_time": 1},
                    {
                        "tid": 2,
                        "uin": int(FRIEND),
                        "name": "friend",
                        "content": "好",
                        "create_time": 2,
                    },
                ],
            }
        ],
    }


def test_signature_cookies_and_body() -> None:
    assert g_tk("abc") == 193485963
    jar = parse_cookies(f"uin=o00{ME}; p_skey=a=b; skey=x")
    assert jar["p_skey"] == "a=b" and uin_of(jar) == ME
    assert decode_body('_Callback({"code": 0, "msglist": []});') == {"code": 0, "msglist": []}
    with pytest.raises(ValueError):
        decode_body("<html>login</html>")
    assert classify({"code": 0}) is None
    throttled = classify({"code": -10000, "message": "操作过于频繁"})
    assert throttled is not None and throttled.status == "retry" and throttled.risk_signal
    logged_out = classify({"code": "-3000"})
    assert logged_out is not None and logged_out.error_code == "provider_auth"
    risky = classify({"code": -1, "message": "请输入验证码"})
    assert risky is not None and risky.risk_signal and risky.status == "failed"


def test_addresses_capabilities_and_profiles() -> None:
    session = parse_session(f"qq:3/qzone/{ME}/post/{TID}")
    assert session.address == f"qq:3:qzonepost:{ME}_{TID}"
    scope = legacy_scope(parse_address(f"qq:3/qzone/{ME}"))
    assert scope.exact == "" and scope.patterns == (f"qq:3:qzonepost:{ME}\\_%",)
    caps = REGISTRY.get("qq")
    assert caps is not None
    kinds = {item["name"]: item for item in caps.to_dict()["address_kinds"]}  # type: ignore[union-attr]
    assert kinds["post"]["risk_level"] == "unofficial_web"
    assert kinds["post"]["rate_profile"] == "qzone"
    assert kinds["group"]["risk_level"] == "third_party" and kinds["group"]["rate_profile"] == "qq"
    assert caps.event_kind("qzc:1:2:3") == "comment"
    instance = InstanceRow(1, 1, "qq", "qq", "online", {"rate_profile": "conservative"})
    assert profile_for(instance, "qzonepost").name == "qzone_conservative"
    assert profile_for(instance, "group").name != "qzone_conservative"
    assert shaper_for("qzonepost") is QZONE_SHAPER and shaper_for("group") is SHAPER
    assert QZONE_DEFAULT.daily_cap < profile_for(instance, "group").daily_cap


def test_feed_maps_posts_comments_and_triggers() -> None:
    envelopes = feed_envelopes(3, [post(), {"tid": "bad/tid", "uin": 1}], ME)
    assert [e["platform_message_id"] for e in envelopes] == [
        f"qzp:{TID}",
        f"qzc:{TID}:1:{FRIEND}",
        f"qzr:{TID}:1:1:{ME}",
        f"qzr:{TID}:1:2:{FRIEND}",
    ]
    for envelope in envelopes:
        validate_inbound(envelope, 3)
    own, comment, own_reply, friend_reply = envelopes
    assert own["kind"] == "post" and own["text"] == "今天天气不错\n[image x1]"
    assert own["flags"] == {"from_self": True, "mention_self": False, "reply_to_self": False}
    assert comment["text"] == "@me 去哪玩" and comment["reply_to"] == f"qzp:{TID}"
    assert comment["mentions"] == [{"id": ME, "name": "me", "is_self": True}]
    assert comment["flags"] == {"from_self": False, "mention_self": True, "reply_to_self": True}
    assert own_reply["flags"]["from_self"] is True  # type: ignore[index]
    assert friend_reply["flags"]["reply_to_self"] is False  # type: ignore[index]
    assert friend_reply["occurred_at"] == "1970-01-01T00:00:02Z"


def ref(peer: str = f"{FRIEND}_{TID}") -> SessionRef:
    return SessionRef(f"qq:3:qzonepost:{peer}", "qq", 3, "qzonepost", peer, "")


def test_send_comment_reply_and_failures() -> None:
    http = FakeHttp({"code": 0, "data": {"commentid": 7}}, {"code": 0}, {"code": -10000})
    provider = QzoneProvider(3, FakeCaller(), http=http)
    sent = provider.send(ref(), OutboundPayload("d_1", "赞", "", ""))
    assert (sent.status, sent.platform_message_id) == ("sent", f"qzc:{TID}:7:{ME}")
    form = http.sent[0]["data"]
    assert form["topicId"] == f"{FRIEND}_{TID}__1" and form["paramstr"] == 1  # type: ignore[index]
    assert http.sent[0]["params"] == {"g_tk": g_tk("abc")}
    reply = provider.send(ref(), OutboundPayload("d_2", "嗯", f"qzc:{TID}:1:{FRIEND}", ""))
    assert reply.status == "sent"
    form = http.sent[1]["data"]
    assert (form["paramstr"], form["commentId"], form["commentUin"]) == (2, "1", FRIEND)  # type: ignore[index]
    throttled = provider.send(ref(), OutboundPayload("d_3", "x", "", ""))
    assert throttled.status == "retry" and throttled.risk_signal
    bad = provider.send(ref("nope"), OutboundPayload("d_4", "x", "", ""))
    assert bad.error_code == "session_not_found"
    timeout = QzoneProvider(3, FakeCaller(), http=FakeHttp(requests.Timeout("slow")))
    unknown = timeout.send(ref(), OutboundPayload("d_5", "x", "", ""))
    assert (unknown.status, unknown.retryable) == ("unknown", False)
    logged_out = QzoneProvider(3, FakeCaller(cookies="uin=o010001"), http=FakeHttp())
    assert logged_out.send(ref(), OutboundPayload("d_6", "x", "", "")).error_code == "provider_auth"


def test_watch_list_rules() -> None:
    assert watch_list({"qzone_watch": "self, 2, 2, abc, 3, 4, 5, 6"}) == [
        "self",
        "2",
        "3",
        "4",
        "5",
    ]
    assert watch_list({}) == []


def test_poll_round_stores_and_backs_off(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    instance = create_instance(settings, 1, "qq", "qq", {"qzone_watch": "self"})
    update_instance_status(settings, instance.id, "online")
    http = FakeHttp({"code": 0, "msglist": [post()]}, {"code": -10000})
    provider = QzoneProvider(instance.id, FakeCaller(), http=http)
    monkeypatch.setattr(gateway_providers.HUB, "qzone_for", lambda _s, _i: provider)
    risks: list[int] = []
    monkeypatch.setattr(qzone_poll.BREAKER, "record_risk", risks.append)
    poller = QzonePoller()
    delay = poller.round(settings, 1000.0)
    assert http.sent[0]["params"]["uin"] == ME  # type: ignore[index]
    assert 30.0 <= delay <= 600.0
    page = read_messages(settings, 1, f"qq:{instance.id}/qzone/{ME}", "", limit=10)
    views = [event_view(item.to_dict()) for item in page.messages]
    assert [view["kind"] for view in views] == ["post", "comment", "comment", "comment"]
    assert views[1]["flags"]["reply_to_self"] is True  # type: ignore[index]
    assert views[1]["address"] == f"qq:{instance.id}/qzone/{ME}/post/{TID}"
    state = poller.states[instance.id]
    poller.round(settings, state.next_at + 1)
    assert poller.states[instance.id].backoff_minutes == 20 and risks == [instance.id]
    update_instance_status(settings, instance.id, "offline")
    poller.round(settings, state.next_at + 10_000)
    assert instance.id not in poller.states
