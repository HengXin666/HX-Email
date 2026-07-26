"""CF Worker temp mail provider: create mailbox, list messages, error mapping."""

import json
from unittest.mock import patch

import pytest
from hx_email.config import Settings
from hx_email.database import migrate
from hx_email.server.mail.impl.temp_mail import CFWorkerTempMailProvider, get_temp_mail_options
from hx_email.server.mail.temp_mail import (
    MissingTempMailProviderError,
    TempMailProviderError,
)
from hx_email.server.settings_service import set_setting

MOCK_TARGET = "hx_email.server.mail.impl.temp_mail.cf_provider._http_request"

RAW_MIME = (
    "From: sender@example.com\r\n"
    "Subject: Your code\r\n"
    "Content-Type: text/plain; charset=utf-8\r\n"
    "\r\n"
    "Verification code: 123456\r\n"
)


def make_provider(tmp_path) -> tuple[CFWorkerTempMailProvider, Settings]:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    set_setting(settings, "cf_worker_base_url", "https://worker.example.dev")
    set_setting(settings, "cf_worker_admin_key", "admin-key")
    return CFWorkerTempMailProvider(settings), settings


def test_create_mailbox_calls_new_address_and_packs_jwt(tmp_path) -> None:
    provider, settings = make_provider(tmp_path)
    set_setting(settings, "cf_worker_default_domain", "mail.example.com")

    response = json.dumps({"address": "abc@mail.example.com", "jwt": "user-jwt", "id": 42})
    with patch(MOCK_TARGET, return_value=(200, response)) as http:
        mailbox = provider.create_mailbox(None)

    assert mailbox.address == "abc@mail.example.com"
    assert json.loads(mailbox.provider_mailbox_id) == {"id": "42", "jwt": "user-jwt"}
    method, url, headers = http.call_args[0][0], http.call_args[0][1], http.call_args[0][2]
    payload = http.call_args[0][3]
    assert method == "POST"
    assert url == "https://worker.example.dev/admin/new_address"
    assert headers["x-admin-auth"] == "admin-key"
    assert headers["User-Agent"].startswith("Mozilla/5.0")
    assert payload["domain"] == "mail.example.com"
    assert payload["enablePrefix"] is False
    assert payload["name"]


def test_create_mailbox_uses_requested_address(tmp_path) -> None:
    provider, _settings = make_provider(tmp_path)

    response = json.dumps({"address": "hello@d.com", "jwt": "j", "id": 1})
    with patch(MOCK_TARGET, return_value=(200, response)) as http:
        provider.create_mailbox("hello@d.com")

    payload = http.call_args[0][3]
    assert payload["name"] == "hello"
    assert payload["domain"] == "d.com"


def test_create_mailbox_raises_on_http_error(tmp_path) -> None:
    provider, _settings = make_provider(tmp_path)

    with (
        patch(MOCK_TARGET, return_value=(401, '{"error": "unauthorized"}')),
        pytest.raises(TempMailProviderError, match="HTTP 401"),
    ):
        provider.create_mailbox(None)


def test_create_mailbox_requires_config(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    provider = CFWorkerTempMailProvider(settings)

    with pytest.raises(MissingTempMailProviderError):
        provider.create_mailbox(None)


def test_list_messages_parses_raw_mime(tmp_path) -> None:
    provider, _settings = make_provider(tmp_path)

    response = json.dumps(
        {"results": [{"id": 7, "raw": RAW_MIME, "source": "fallback@example.com"}]}
    )
    mailbox_id = json.dumps({"id": "42", "jwt": "user-jwt"})
    with patch(MOCK_TARGET, return_value=(200, response)) as http:
        messages = provider.list_messages(mailbox_id)

    assert len(messages) == 1
    message = messages[0]
    assert message.id == "cf_7"
    assert message.from_address == "sender@example.com"
    assert message.subject == "Your code"
    assert "123456" in message.text
    method, url, headers = http.call_args[0][0], http.call_args[0][1], http.call_args[0][2]
    assert method == "GET"
    assert url.startswith("https://worker.example.dev/api/mails")
    assert headers["Authorization"] == "Bearer user-jwt"


def test_list_messages_requires_jwt(tmp_path) -> None:
    provider, _settings = make_provider(tmp_path)

    with pytest.raises(TempMailProviderError, match="访问凭证"):
        provider.list_messages(json.dumps({"id": "42", "jwt": ""}))


def test_options_read_synced_domains(tmp_path) -> None:
    _provider, settings = make_provider(tmp_path)
    set_setting(settings, "cf_worker_domains", '["a.com", "b.com"]')
    set_setting(settings, "cf_worker_default_domain", "b.com")

    options = get_temp_mail_options(settings, "cf")

    assert options["domains"] == ["a.com", "b.com"]
    assert options["default_domain"] == "b.com"
