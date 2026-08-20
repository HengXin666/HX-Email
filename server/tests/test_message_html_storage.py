"""Tests: fetched messages persist HTML body + parsed sender email (HTML 渲染/别名识别基础)."""

from __future__ import annotations

from typing import Any

from hx_email.config import Settings
from hx_email.database import connect, migrate
from hx_email.server.mail import EmailAccountMailbox, MailboxMessage
from hx_email.server.mail.imap.impl.fetch_batch import message_from_raw
from hx_email.server.mail.imap.message_store import get_messages, save_messages

RAW_MULTIPART: bytes = (
    b"From: GitHub <noreply@github.com>\r\n"
    b"To: Me <me@example.com>\r\n"
    b"Subject: =?utf-8?B?W0dpdEh1Yl0g5qGM6Imy6K2w?=\r\n"
    b"MIME-Version: 1.0\r\n"
    b"Content-Type: multipart/alternative; boundary=b1\r\n"
    b"\r\n"
    b"--b1\r\n"
    b"Content-Type: text/plain; charset=utf-8\r\n"
    b"\r\n"
    b"Hello plain\r\n"
    b"--b1\r\n"
    b"Content-Type: text/html; charset=utf-8\r\n"
    b"\r\n"
    b"<html><body><b>Hello</b> <a href='https://github.com'>html</a></body></html>\r\n"
    b"--b1--\r\n"
)


def test_message_from_raw_keeps_html_and_parsed_sender(tmp_path: Any) -> None:
    parsed = message_from_raw(
        RAW_MULTIPART,
        (b"1 (UID 42 FLAGS (\\Seen))", b"ignored"),
        "42",
        EmailAccountMailbox(id=1, provider="qq", primary_address="me@example.com"),
    )

    assert parsed.body == "Hello plain"
    assert "Hello" in parsed.body_html and "html" in parsed.body_html
    assert parsed.from_email == "noreply@github.com"
    assert "GitHub" in parsed.from_address
    assert parsed.message_id == "42"
    assert parsed.is_read is True


def test_html_only_message_falls_back_to_stripped_text(tmp_path: Any) -> None:
    raw: bytes = (
        b"From: no-reply@google.com\r\n"
        b"Subject: code\r\n"
        b"MIME-Version: 1.0\r\n"
        b"Content-Type: text/html; charset=utf-8\r\n"
        b"\r\n"
        b"<html><body>Your code is <b>123456</b></body></html>\r\n"
    )
    parsed = message_from_raw(
        raw,
        (b"1 (UID 7)", b"ignored"),
        "7",
        EmailAccountMailbox(id=1, provider="gmail", primary_address="me@example.com"),
    )

    assert "123456" in parsed.body
    assert "<b>123456</b>" in parsed.body_html
    assert parsed.from_email == "no-reply@google.com"


def test_save_and_read_back_html_and_sender_columns(tmp_path: Any) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    with connect(settings) as conn:
        conn.execute(
            "INSERT INTO usable_emails (id, user_id, email_account_id, address, kind) "
            "VALUES (1, 1, 1, 'me@example.com', 'primary')"
        )

    messages = [
        MailboxMessage(
            recipient_address="me@example.com",
            subject="s",
            body="text",
            from_address="GitHub <noreply@github.com>",
            from_email="noreply@github.com",
            body_html="<b>html</b>",
            message_id="9",
        )
    ]
    inserted = save_messages(settings, 1, 1, 1, messages)
    assert inserted == 1

    stored = get_messages(settings, 1)
    assert len(stored) == 1
    assert stored[0]["from_email"] == "noreply@github.com"
    assert stored[0]["body_html"] == "<b>html</b>"
    assert stored[0]["body"] == "text"
