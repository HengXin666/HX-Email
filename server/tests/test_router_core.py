"""Router core: cursor, incremental reads, outbox, shaper, envelope, migration."""

from __future__ import annotations

import itertools
import random
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from hx_email.api.impl.router.errors import http_status_for, router_error_response
from hx_email.config import Settings
from hx_email.database import connect, migrate
from hx_email.models.messaging import migrate_messaging_schema
from hx_email.server.router.cursor import Cursor, decode_cursor, encode_cursor
from hx_email.server.router.envelope import (
    EnvelopeError,
    format_session,
    parse_session,
    validate_inbound,
)
from hx_email.server.router.errors import (
    CursorInvalidError,
    RouterError,
    SessionNotFoundError,
    error_from_code,
)
from hx_email.server.router.impl import outbox, outbox_admin
from hx_email.server.router.impl.reader import (
    build_query,
    latest_cursor,
    parse_source,
    read_messages,
)
from hx_email.server.router.impl.shaper import QQ_CONSERVATIVE, QQ_DEFAULT, RateProfile, Shaper
from hx_email.server.router.impl.store import store_inbound
from hx_email.server.router.provider import SendResult

T0 = datetime(2026, 11, 2, 12, 0, 0, tzinfo=UTC)


def make_settings(tmp_path: Path) -> Settings:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    return settings


def add_instance(settings: Settings, kind: str = "qq", user_id: int = 1) -> int:
    with connect(settings) as connection:
        cursor = connection.execute(
            "INSERT INTO messaging_instances (user_id, kind, name) VALUES (?, ?, ?)",
            (user_id, kind, kind),
        )
        assert cursor.lastrowid is not None
        return int(cursor.lastrowid)


def inbound(
    session: str, n: int, text: str = "", raw: dict[str, Any] | None = None, **extra: Any
) -> dict[str, object]:
    data: dict[str, object] = {
        "session": session,
        "direction": "inbound",
        "sender": {"id": "10001", "name": "alice", "is_self": False},
        "text": text or f"hello {n}",
        "platform_message_id": str(1000 + n),
        "occurred_at": "2026-11-02T15:20:05Z",
        "dedup_key": f"qq:{1000 + n}:{1793632805 + n}",
        "raw": raw,
    }
    data.update(extra)
    return data


def put(settings: Settings, iid: int, session: str, n: int, **extra: Any) -> int:
    result = store_inbound(settings, validate_inbound(inbound(session, n, **extra), iid))
    return result.message_id


# cursor


def test_cursor_roundtrip() -> None:
    for iid, pos in [(0, 0), (3, 10452), (7, 2**63 - 1)]:
        assert decode_cursor(encode_cursor(iid, pos)) == Cursor(iid, pos)
    assert Cursor(3, 5).advance(2) == Cursor(3, 5)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "c1",
        "c1.3",
        "c2.3.1",
        "c1.-1.5",
        "c1.3.-5",
        "c1.3.x",
        "c1.03.1",
        "c1.3.1.1",
        "c1.3.\uff19",
        f"c1.3.{2**63}",
        "c1. 3.1",
    ],
)
def test_cursor_rejects_bad_input(value: str) -> None:
    with pytest.raises(CursorInvalidError):
        decode_cursor(value)


def test_cursor_encode_out_of_range() -> None:
    with pytest.raises(CursorInvalidError):
        encode_cursor(-1, 0)
    with pytest.raises(CursorInvalidError):
        encode_cursor(1, 2**63)


# incremental reads


def test_paging_has_no_gaps_or_repeats(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    iid = add_instance(settings)
    group = f"qq:{iid}:group:123456789"
    other = f"qq:{iid}:private:10001"
    ids = [put(settings, iid, group if n % 3 else other, n) for n in range(1, 26)]
    expected = [i for n, i in zip(range(1, 26), ids, strict=True) if n % 3]
    seen: list[int] = []
    cursor = f"c1.{iid}.0"
    pages = 0
    while True:
        page = read_messages(settings, 1, group, cursor, limit=4)
        pages += 1
        seen += [int(m.id[2:]) for m in page.messages]
        assert all(m.session == group for m in page.messages)
        cursor = page.next_cursor
        if not page.has_more:
            break
    assert seen == expected
    assert pages == 5
    tail = read_messages(settings, 1, group, cursor)
    assert tail.messages == [] and tail.next_cursor == cursor and not tail.has_more
    new_id = put(settings, iid, group, 99)
    assert [m.id for m in read_messages(settings, 1, group, cursor).messages] == [f"m_{new_id}"]


def test_prefix_and_global_reads(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    a, b = add_instance(settings), add_instance(settings)
    put(settings, a, f"qq:{a}:group:1", 1)
    put(settings, a, f"qq:{a}:private:2", 2)
    put(settings, b, f"qq:{b}:group:1", 3)
    groups = read_messages(settings, 1, f"qq:{a}:group:", f"c1.{a}.0")
    assert [m.session for m in groups.messages] == [f"qq:{a}:group:1"]
    everything = read_messages(settings, 1, "qq:", "c1.0.0")
    assert len(everything.messages) == 3
    assert everything.next_cursor.startswith("c1.0.")


def test_read_rejects_foreign_and_out_of_range(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    iid = add_instance(settings)
    foreign = add_instance(settings, user_id=2)
    session = f"qq:{iid}:group:1"
    put(settings, iid, session, 1)
    with pytest.raises(CursorInvalidError):
        read_messages(settings, 1, session, "c1.0.0")
    with pytest.raises(CursorInvalidError):
        read_messages(settings, 1, session, f"c1.{iid}.999")
    with pytest.raises(SessionNotFoundError):
        read_messages(settings, 1, f"qq:{foreign}:group:1", f"c1.{foreign}.0")
    with pytest.raises(SessionNotFoundError):
        parse_source("telegram:1:")
    assert latest_cursor(settings, iid) == f"c1.{iid}.1"


def test_gap_after_retention_delete(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    iid = add_instance(settings)
    session = f"qq:{iid}:group:1"
    for n in range(1, 6):
        put(settings, iid, session, n)
    with connect(settings) as connection:
        connection.execute("DELETE FROM messaging_messages WHERE id <= 3")
    page = read_messages(settings, 1, session, f"c1.{iid}.0")
    assert page.gap and [m.id for m in page.messages] == ["m_4", "m_5"]


def test_single_session_read_uses_index(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    scope = parse_source("qq:3:group:1")
    sql, params = build_query(scope, [3], 0, "inbound", 50)
    with connect(settings) as connection:
        plan = " ".join(str(r[3]) for r in connection.execute(f"EXPLAIN QUERY PLAN {sql}", params))
    assert "idx_messaging_messages_instance_chat" in plan
    assert "SCAN messaging_messages" not in plan


# store and envelope


def test_inbound_dedup_and_edit(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    iid = add_instance(settings)
    session = f"qq:{iid}:group:1"
    first = store_inbound(settings, validate_inbound(inbound(session, 1), iid))
    again = store_inbound(settings, validate_inbound(inbound(session, 1), iid))
    assert first.stored and not again.stored and again.message_id == first.message_id
    other_time = inbound(session, 1, dedup_key="qq:1001:1")
    assert store_inbound(settings, validate_inbound(other_time, iid)).stored
    edited = store_inbound(
        settings, validate_inbound(inbound(session, 1, text="v2", edit=True), iid)
    )
    assert edited.updated
    page = read_messages(settings, 1, session, f"c1.{iid}.0")
    assert page.messages[0].text == "v2" and len(page.messages) == 2


@pytest.mark.parametrize(
    "drop", ["session", "sender", "platform_message_id", "occurred_at", "dedup_key", "text"]
)
def test_envelope_missing_field(drop: str) -> None:
    data = inbound("qq:3:group:1", 1)
    del data[drop]
    with pytest.raises(EnvelopeError):
        validate_inbound(data, 3)


def test_envelope_invalid_values() -> None:
    with pytest.raises(EnvelopeError):
        validate_inbound(inbound("qq:3:group:1", 1), 4)
    with pytest.raises(EnvelopeError):
        validate_inbound(inbound("qq:3:group:1", 1, occurred_at="2026-11-02 15:20:05"), 3)
    with pytest.raises(EnvelopeError):
        validate_inbound(inbound("qq:3:channel:1", 1), 3)
    with pytest.raises(EnvelopeError):
        validate_inbound(inbound("qq:3:group:1", 1, sender={"name": "x"}), 3)


def test_session_address_parse() -> None:
    issue = parse_session("github:7:issue:hx/HX-Email#42")
    assert issue.peer == "hx/HX-Email#42" and issue.legacy_chat_type == "group"
    assert parse_session("qq:3:temp:1-2").legacy_chat_type == "private"
    assert format_session("qq", 3, "private", "10001") == "qq:3:private:10001"
    for bad in ["qq:3:group:", "QQ:3:group:1", "qq:0:group:1", "qq:x:group:1", "qq:3"]:
        with pytest.raises(SessionNotFoundError):
            parse_session(bad)


def test_large_raw_goes_to_file(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    iid = add_instance(settings)
    session = f"qq:{iid}:group:1"
    big = {"blob": "x" * (17 * 1024)}
    small = {"post_type": "message"}
    big_id = put(settings, iid, session, 1, raw=big)
    put(settings, iid, session, 2, raw=small)
    page = read_messages(settings, 1, session, f"c1.{iid}.0", include_raw=True)
    first, second = page.messages
    assert first.raw_ref.startswith("router_raw/") and first.raw_ref.endswith(f"/{big_id}.json")
    assert (tmp_path / first.raw_ref).is_file() and first.raw == big
    assert second.raw_ref == "" and second.raw == small
    assert first.to_dict()["raw"] is None and first.received_at.endswith("Z")


# outbox


def test_outbox_idempotent_send(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    iid = add_instance(settings)
    one = outbox.enqueue_send(settings, 1, iid, f"qq:{iid}:group:1", {"text": "a"}, "key-0001")
    two = outbox.enqueue_send(settings, 1, iid, f"qq:{iid}:group:1", {"text": "b"}, "key-0001")
    assert not one.deduplicated and two.deduplicated and two.entry.id == one.entry.id
    other = add_instance(settings)
    three = outbox.enqueue_send(settings, 1, other, f"qq:{other}:group:1", {}, "key-0001")
    assert not three.deduplicated
    with pytest.raises(ValueError):
        outbox.enqueue_send(settings, 1, iid, f"qq:{iid}:group:1", {}, "short")
    hook = outbox.enqueue_webhook(settings, 1, 5, {"messages": []}, 10452, 10460)
    hook2 = outbox.enqueue_webhook(settings, 1, 5, {"messages": []}, 10452, 10460)
    assert hook.entry.idempotency_key == "m_10452-m_10460" and hook2.deduplicated


def test_outbox_check_constraint(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    with connect(settings) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO router_outbox (user_id, kind, payload_json, idempotency_key, give_up_at)"
            " VALUES (1, 'send', '{}', 'k-000001', '2099-01-01 00:00:00')"
        )


def test_outbox_state_flow_and_retry(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    iid = add_instance(settings)
    rng = random.Random(1)
    entry = outbox.enqueue_send(settings, 1, iid, f"qq:{iid}:group:1", {}, "key-0002", now=T0).entry
    assert outbox.claim_due(settings, now=T0 - timedelta(seconds=1)) == []
    claimed = outbox.claim_due(settings, now=T0)
    assert [c.id for c in claimed] == [entry.id] and claimed[0].status == "sending"
    assert outbox.claim_due(settings, now=T0) == []
    retry = SendResult(status="retry", retryable=True, error_code="http_503")
    moment = T0
    for attempt in range(1, 4):
        row = outbox_admin.record_result(settings, entry.id, retry, now=moment, rng=rng)
        assert row.status == "queued" and row.attempts == attempt
        moment = datetime.strptime(row.next_attempt_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        assert outbox.claim_due(settings, now=moment - timedelta(seconds=1)) == []
        assert outbox.claim_due(settings, now=moment)[0].attempts == attempt + 1
    final = outbox_admin.record_result(settings, entry.id, retry, now=moment, rng=rng)
    assert final.status == "failed" and final.attempts == 4
    with pytest.raises(ValueError):
        outbox_admin.record_result(settings, entry.id, retry, now=moment)


def test_outbox_sent_unknown_and_restart(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    iid = add_instance(settings)
    session = f"qq:{iid}:group:1"
    a = outbox.enqueue_send(settings, 1, iid, session, {}, "key-000a", now=T0).entry
    b = outbox.enqueue_send(settings, 1, iid, session, {}, "key-000b", now=T0).entry
    c = outbox.enqueue_send(settings, 1, iid, session, {}, "key-000c", now=T0).entry
    hook = outbox.enqueue_webhook(settings, 1, 9, {}, 1, 2, now=T0).entry
    outbox.claim_due(settings, now=T0)
    sent = outbox_admin.record_result(settings, a.id, SendResult("sent", "1873992260"), now=T0)
    assert sent.status == "sent" and sent.platform_message_id == "1873992260"
    unknown = outbox_admin.record_result(settings, b.id, SendResult("unknown"), now=T0)
    assert unknown.status == "unknown"
    assert outbox_admin.recover_after_restart(settings, now=T0) == (1, 1)
    assert outbox_admin.get_entry(settings, c.id).status == "unknown"  # type: ignore[union-attr]
    assert outbox_admin.get_entry(settings, hook.id).status == "queued"  # type: ignore[union-attr]
    found = outbox_admin.find_send(settings, iid, "key-000a")
    assert found is not None and found.delivery_id == f"d_{a.id}"


def test_outbox_rate_wait_not_counted_and_give_up(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    iid = add_instance(settings)
    entry = outbox.enqueue_send(settings, 1, iid, f"qq:{iid}:group:1", {}, "key-000d", now=T0).entry
    outbox.claim_due(settings, now=T0)
    waited = outbox_admin.record_result(
        settings, entry.id, SendResult("retry", retry_after_seconds=30), now=T0
    )
    assert waited.attempts == 0 and waited.next_attempt_at == "2026-11-02 12:00:30"
    late = T0 + timedelta(hours=25)
    assert outbox.claim_due(settings, now=late) == []
    assert outbox_admin.get_entry(settings, entry.id).status == "failed"  # type: ignore[union-attr]
    assert outbox_admin.purge_terminal(settings, now=late + timedelta(days=8)) == 1


def test_outbox_hold_and_webhook_serial(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    iid = add_instance(settings)
    session = f"qq:{iid}:group:1"
    outbox.enqueue_send(settings, 1, iid, session, {}, "key-000e", now=T0)
    assert outbox_admin.set_instance_held(settings, iid, True) == 1
    held = outbox.enqueue_send(settings, 1, iid, session, {}, "key-000f", held=True, now=T0)
    assert held.entry.status == "held"
    assert outbox.claim_due(settings, now=T0) == []
    assert outbox_admin.set_instance_held(settings, iid, False) == 2
    first = outbox.enqueue_webhook(settings, 1, 4, {}, 1, 2, now=T0).entry
    second = outbox.enqueue_webhook(settings, 1, 4, {}, 3, 4, now=T0).entry
    claimed = [c.id for c in outbox.claim_due(settings, now=T0)]
    assert first.id in claimed and second.id not in claimed
    failed_hook = outbox_admin.record_result(settings, first.id, SendResult("failed"), now=T0)
    assert failed_hook.status == "queued"


# shaper


class FakeClock:
    def __init__(self, start: float = 1_793_620_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


def drain(shaper: Shaper, clock: FakeClock, iid: int, session: str, count: int) -> list[float]:
    times: list[float] = []
    while len(times) < count:
        decision = shaper.acquire(iid, session)
        if decision.allowed:
            times.append(clock.now)
            assert QQ_DEFAULT.jitter_min_seconds <= decision.jitter_seconds
        else:
            clock.now += decision.wait_seconds
    return times


def test_shaper_spreads_bursts_and_isolates_instances() -> None:
    clock = FakeClock()
    shaper = Shaper(clock=clock, rng=random.Random(0))
    times = drain(shaper, clock, 1, "qq:1:group:1", 5)
    assert all(b - a >= 3.0 for a, b in itertools.pairwise(times))
    assert shaper.acquire(2, "qq:2:group:1").allowed


def test_shaper_account_minute_and_daily_cap() -> None:
    clock = FakeClock()
    shaper = Shaper(clock=clock, rng=random.Random(0))
    times = [t for n in range(25) for t in drain(shaper, clock, 1, f"qq:1:group:{n}", 1)]
    in_first_minute = [t for t in times if t < times[0] + 60]
    assert len(in_first_minute) <= QQ_DEFAULT.per_account_per_minute
    tight = RateProfile("t", 0.0, 0, 5, 0.0, 0, 0, 2, 0.0, 0.0, 100)
    shaper.configure(9, tight)
    assert shaper.acquire(9, "a").allowed and shaper.acquire(9, "b").allowed
    blocked = shaper.acquire(9, "c")
    assert not blocked.allowed and blocked.reason == "daily_cap" and blocked.wait_seconds > 0


def test_shaper_profiles_configurable() -> None:
    clock = FakeClock()
    shaper = Shaper(clock=clock, rng=random.Random(0))
    shaper.configure(1, QQ_CONSERVATIVE)
    times = drain(shaper, clock, 1, "qq:1:group:1", 3)
    assert all(b - a >= 6.0 for a, b in itertools.pairwise(times))
    assert QQ_CONSERVATIVE.to_limits().per_account_per_minute == 8


def test_shaper_same_content_fanout() -> None:
    clock = FakeClock()
    shaper = Shaper(clock=clock, rng=random.Random(0))
    assert shaper.acquire(1, "qq:1:group:1", "same text").allowed
    clock.now += 4
    second = shaper.acquire(1, "qq:1:group:2", "same  text")
    assert not second.allowed and second.reason == "fanout_interval"


# errors


def test_error_mapping_is_4xx() -> None:
    assert http_status_for(CursorInvalidError("x")) == 400
    assert http_status_for(SessionNotFoundError()) == 404
    assert http_status_for(error_from_code("rate_limited")) == 429
    assert http_status_for(error_from_code("text_too_long")) == 422
    assert http_status_for(error_from_code("no_such_code")) == 502
    response = router_error_response(error_from_code("provider_offline"))
    assert response.status_code == 503 and b'"retryable":true' in response.body
    assert isinstance(error_from_code("session_not_found"), RouterError)


# migration


OLD_MESSAGES_SQL = """
CREATE TABLE messaging_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT, instance_id INTEGER NOT NULL,
    direction TEXT NOT NULL, chat_id TEXT NOT NULL, chat_type TEXT NOT NULL,
    sender_id TEXT NOT NULL DEFAULT '', sender_name TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL DEFAULT '', message_id TEXT NOT NULL DEFAULT '',
    raw_json TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now')))
"""


def test_migration_idempotent_on_old_database(tmp_path: Path) -> None:
    path = tmp_path / "old.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(OLD_MESSAGES_SQL)
        for _ in range(2):
            connection.execute(
                "INSERT INTO messaging_messages (instance_id, direction, chat_id, chat_type, text)"
                " VALUES (1, 'inbound', '123', 'group', 'dup')"
            )
    for _ in range(2):
        with sqlite3.connect(path) as connection:
            migrate_messaging_schema(connection)
    with sqlite3.connect(path) as connection:
        columns = {r[1] for r in connection.execute("PRAGMA table_info(messaging_messages)")}
        tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master")}
        rows = connection.execute("SELECT dedup_key, is_self FROM messaging_messages").fetchall()
    assert {
        "is_self",
        "reply_to",
        "attachments_json",
        "occurred_at",
        "raw_ref",
        "dedup_key",
    } <= columns
    assert {
        "router_routes",
        "router_outbox",
        "router_ingress_deliveries",
        "router_api_keys",
    } <= tables
    assert {"uq_messaging_messages_dedup", "uq_router_outbox_send"} <= tables
    assert rows == [("", 0), ("", 0)]


def test_full_migrate_twice(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    migrate(settings)
    migrate(settings)
