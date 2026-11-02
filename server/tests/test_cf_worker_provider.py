"""CF Worker temp mail provider: create mailbox, list messages, error mapping."""

import importlib
import json
from unittest.mock import patch

import pytest
from hx_email.config import Settings
from hx_email.database import migrate
from hx_email.server.mail.impl.temp_mail import CFWorkerTempMailProvider, get_temp_mail_options
from hx_email.server.mail.temp_mail import (
    MissingTempMailProviderError,
    TempMailMessage,
    TempMailProviderError,
    extract_codes,
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

ESCAPED_UNICODE_MIME = (
    "From: account-security-noreply@accountprotection.microsoft.com\r\n"
    "Subject: Microsoft account security code\r\n"
    "Content-Type: text/html; charset=utf-8\r\n"
    "\r\n"
    "<html><body>\\u5b89\\u5168\\u4ee3\\u7801: 432939</body></html>\r\n"
)


def raw_code_message(code: str) -> str:
    return (
        "From: sender@example.com\r\n"
        "Subject: Verification code\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        f"Verification code: {code}\r\n"
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


def test_list_messages_sorts_by_created_at_newest_first(tmp_path) -> None:
    provider, _settings = make_provider(tmp_path)
    response = json.dumps(
        {
            "results": [
                {
                    "id": 4515,
                    "created_at": "2026-08-01 16:56:23",
                    "raw": raw_code_message("899261"),
                },
                {
                    "id": 4566,
                    "created_at": "2026-08-01 19:42:37",
                    "raw": raw_code_message("068320"),
                },
            ]
        }
    )
    mailbox_id = json.dumps({"id": "3769", "jwt": "user-jwt"})

    with patch(MOCK_TARGET, return_value=(200, response)):
        messages = provider.list_messages(mailbox_id)

    assert [message.id for message in messages] == ["cf_4566", "cf_4515"]
    assert [message.received_at for message in messages] == [
        "2026-08-01 19:42:37",
        "2026-08-01 16:56:23",
    ]
    assert [code.code for code in extract_codes(tuple(messages))] == ["068320", "899261"]
    assert [code.received_at for code in extract_codes(tuple(messages))] == [
        "2026-08-01 19:42:37",
        "2026-08-01 16:56:23",
    ]


def test_list_messages_bypasses_cached_mail_list_responses(tmp_path) -> None:
    provider, _settings = make_provider(tmp_path)
    response = json.dumps({"results": []})
    mailbox_id = json.dumps({"id": "42", "jwt": "user-jwt"})

    with patch(MOCK_TARGET, return_value=(200, response)) as http:
        provider.list_messages(mailbox_id)
        provider.list_messages(mailbox_id)

    first_call = http.call_args_list[0]
    second_call = http.call_args_list[1]
    assert first_call.args[1] != second_call.args[1]
    for call in http.call_args_list:
        assert call.args[2]["Cache-Control"] == "no-cache, no-store, max-age=0"
        assert call.args[2]["Pragma"] == "no-cache"


def test_list_messages_decodes_escaped_unicode_before_code_extraction(tmp_path) -> None:
    provider, _settings = make_provider(tmp_path)
    response = json.dumps({"results": [{"id": 8, "raw": ESCAPED_UNICODE_MIME}]})
    mailbox_id = json.dumps({"id": "42", "jwt": "user-jwt"})

    with patch(MOCK_TARGET, return_value=(200, response)):
        messages = provider.list_messages(mailbox_id)

    assert len(messages) == 1
    message = messages[0]
    assert isinstance(message, TempMailMessage)
    assert "安全代码: 432939" in message.html
    assert extract_codes((message,))[0].code == "432939"


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


def test_options_filter_excluded_domains_and_fall_back_default(tmp_path) -> None:
    _provider, settings = make_provider(tmp_path)
    set_setting(settings, "cf_worker_domains", '["@a.com", "@b.com", "@c.com"]')
    set_setting(settings, "cf_worker_excluded_domains", '["a.com", "@b.com"]')
    set_setting(settings, "cf_worker_default_domain", "@a.com")

    options = get_temp_mail_options(settings, "cf")

    assert options["domains"] == ["@c.com"]
    assert options["default_domain"] == "@c.com"


def test_options_all_domains_excluded_gives_empty_default(tmp_path) -> None:
    _provider, settings = make_provider(tmp_path)
    set_setting(settings, "cf_worker_domains", '["a.com", "b.com"]')
    set_setting(settings, "cf_worker_excluded_domains", '["@a.com", "@b.com"]')
    set_setting(settings, "cf_worker_default_domain", "a.com")

    options = get_temp_mail_options(settings, "cf")

    assert options["domains"] == []
    assert options["default_domain"] == ""


def test_create_mailbox_skips_excluded_default_domain(tmp_path) -> None:
    provider, settings = make_provider(tmp_path)
    set_setting(settings, "cf_worker_domains", '["@a.com", "@b.com"]')
    set_setting(settings, "cf_worker_excluded_domains", '["a.com"]')
    set_setting(settings, "cf_worker_default_domain", "@a.com")

    response = json.dumps({"address": "x@b.com", "jwt": "j", "id": 1})
    with patch(MOCK_TARGET, return_value=(200, response)) as http:
        provider.create_mailbox(None)

    assert http.call_args[0][3]["domain"] == "b.com"


def test_create_mailbox_raises_when_all_synced_domains_excluded(tmp_path) -> None:
    provider, settings = make_provider(tmp_path)
    set_setting(settings, "cf_worker_domains", '["@a.com", "@b.com"]')
    set_setting(settings, "cf_worker_excluded_domains", '["@a.com", "b.com"]')

    with (
        patch(MOCK_TARGET) as http,
        pytest.raises(Exception, match="已被删除") as excinfo,
    ):
        provider.create_mailbox(None)

    assert excinfo.type.__name__ == "NoUsableTempMailDomainError"
    assert excinfo.value.status_code == 409
    http.assert_not_called()


def test_create_mailbox_without_synced_domains_lets_worker_choose(tmp_path) -> None:
    provider, settings = make_provider(tmp_path)
    set_setting(settings, "cf_worker_excluded_domains", '["@a.com"]')

    response = json.dumps({"address": "x@w.com", "jwt": "j", "id": 1})
    with patch(MOCK_TARGET, return_value=(200, response)) as http:
        provider.create_mailbox(None)

    assert "domain" not in http.call_args[0][3]


OPTIONS_MODULE = "hx_email.server.mail.impl.temp_mail.temp_mail_options"
CREATED = json.dumps({"address": "x@b.com", "jwt": "j", "id": 1})


def test_normalize_domains_trims_lowercases_filters_and_dedupes() -> None:
    normalize_domains = importlib.import_module(OPTIONS_MODULE).normalize_domains

    values = [" @@A.com ", "a.com", "", "   ", "@", "@@", "B.com", "@b.COM", "c.com"]

    assert normalize_domains(values) == ["a.com", "b.com", "c.com"]


def test_create_mailbox_rejects_explicit_address_on_excluded_domain(tmp_path) -> None:
    provider, settings = make_provider(tmp_path)
    set_setting(settings, "cf_worker_domains", '["@a.com", "@b.com"]')
    set_setting(settings, "cf_worker_excluded_domains", '["a.com"]')

    with (
        patch(MOCK_TARGET, return_value=(200, CREATED)) as http,
        pytest.raises(Exception, match=r"a\.com") as excinfo,
    ):
        provider.create_mailbox("me@A.com")

    assert excinfo.type.__name__ == "NoUsableTempMailDomainError"
    assert excinfo.value.status_code == 409
    http.assert_not_called()


def test_create_mailbox_sends_normalized_explicit_domain(tmp_path) -> None:
    provider, settings = make_provider(tmp_path)
    set_setting(settings, "cf_worker_domains", '["@a.com", "@b.com"]')
    set_setting(settings, "cf_worker_excluded_domains", '["a.com"]')

    with patch(MOCK_TARGET, return_value=(200, CREATED)) as http:
        provider.create_mailbox("me@ @B.com")

    assert http.call_args[0][3] == {"name": "me", "enablePrefix": False, "domain": "b.com"}


def test_options_exclusion_ignores_case(tmp_path) -> None:
    _provider, settings = make_provider(tmp_path)
    set_setting(settings, "cf_worker_domains", '["@A.com", "@b.com"]')
    set_setting(settings, "cf_worker_excluded_domains", '["a.COM"]')
    set_setting(settings, "cf_worker_default_domain", "@A.com")

    options = get_temp_mail_options(settings, "cf")

    assert options["domains"] == ["@b.com"]
    assert options["default_domain"] == "@b.com"


def test_create_mailbox_excluded_default_ignores_case(tmp_path) -> None:
    provider, settings = make_provider(tmp_path)
    set_setting(settings, "cf_worker_domains", '["a.com", "b.com"]')
    set_setting(settings, "cf_worker_excluded_domains", '["A.COM"]')
    set_setting(settings, "cf_worker_default_domain", "A.com")

    with patch(MOCK_TARGET, return_value=(200, CREATED)) as http:
        provider.create_mailbox(None)

    assert http.call_args[0][3]["domain"] == "b.com"


def test_default_domain_outside_synced_list_falls_back_to_first_usable(tmp_path) -> None:
    provider, settings = make_provider(tmp_path)
    set_setting(settings, "cf_worker_domains", '["@a.com", "@b.com"]')
    set_setting(settings, "cf_worker_excluded_domains", '["a.com"]')
    set_setting(settings, "cf_worker_default_domain", "stale.com")

    options = get_temp_mail_options(settings, "cf")
    with patch(MOCK_TARGET, return_value=(200, CREATED)) as http:
        provider.create_mailbox(None)

    assert options["domains"] == ["@b.com"]
    assert options["default_domain"] == "@b.com"
    assert http.call_args[0][3]["domain"] == "b.com"


def test_options_dirty_and_duplicate_synced_values_are_cleaned(tmp_path) -> None:
    _provider, settings = make_provider(tmp_path)
    set_setting(settings, "cf_worker_domains", '["@a.com", "A.com", "@", " ", "@b.com", "b.com"]')
    set_setting(settings, "cf_worker_excluded_domains", '["", "@", "@b.com", "B.com"]')

    options = get_temp_mail_options(settings, "cf")

    assert options["domains"] == ["@a.com"]
    assert options["default_domain"] == "@a.com"


def test_create_mailbox_all_excluded_raises_no_usable_domain_error(tmp_path) -> None:
    provider, settings = make_provider(tmp_path)
    set_setting(settings, "cf_worker_domains", '["@a.com", "@B.com"]')
    set_setting(settings, "cf_worker_excluded_domains", '["A.com", "b.com"]')
    set_setting(settings, "cf_worker_default_domain", "stale.com")

    with (
        patch(MOCK_TARGET, return_value=(200, CREATED)) as http,
        pytest.raises(Exception, match="已被删除") as excinfo,
    ):
        provider.create_mailbox(None)

    assert excinfo.type.__name__ == "NoUsableTempMailDomainError"
    assert excinfo.value.status_code == 409
    http.assert_not_called()
