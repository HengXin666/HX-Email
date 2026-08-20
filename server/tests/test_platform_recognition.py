"""Tests for platform recognition: rules CRUD, historical scan, accept."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import migrate

API = "/api/v1"


def login_admin(client: TestClient, settings: Settings) -> dict[str, str]:
    session = client.post(
        f"{API}/auth/login",
        json={"username": settings.admin_username, "password": settings.admin_password},
    ).json()
    return {"Authorization": f"Bearer {session['access_token']}"}


def make_app(tmp_path: Any) -> tuple[TestClient, dict[str, str], Settings]:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))
    return client, login_admin(client, settings), settings


def insert_fetched_message(
    settings: Settings,
    *,
    from_address: str,
    subject: str,
    body: str,
    usable_email_id: int,
) -> None:
    from hx_email.database import connect

    with connect(settings) as connection:
        connection.execute(
            """
            INSERT INTO fetched_messages (
                user_id, usable_email_id, from_address, recipient_address,
                subject, body, message_id, received_at
            ) VALUES (1, ?, ?, '', ?, ?, 'mid', datetime('now'))
            """,
            (usable_email_id, from_address, subject, body),
        )


def test_rules_crud_and_validation(tmp_path: Any) -> None:
    client, headers, _settings = make_app(tmp_path)

    created = client.post(
        f"{API}/platform-rules",
        json={
            "name": "GitHub 通知",
            "match_field": "domain",
            "match_type": "contains",
            "pattern": "github.com",
            "platform_name": "GitHub",
            "enabled": True,
        },
        headers=headers,
    )
    assert created.status_code == 201
    rule = created.json()
    assert rule["platform_name"] == "GitHub"

    listed = client.get(f"{API}/platform-rules", headers=headers).json()["rules"]
    assert len(listed) == 1

    updated = client.put(
        f"{API}/platform-rules/{rule['id']}",
        json={
            "name": "GitHub 通知",
            "match_field": "from",
            "match_type": "regex",
            "pattern": r"noreply@github\\.com$",
            "platform_name": "GitHub",
            "enabled": True,
        },
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["match_type"] == "regex"

    bad = client.post(
        f"{API}/platform-rules",
        json={
            "match_field": "domain",
            "match_type": "regex",
            "pattern": "([",
            "platform_name": "X",
        },
        headers=headers,
    )
    assert bad.status_code == 422

    deleted = client.delete(f"{API}/platform-rules/{rule['id']}", headers=headers)
    assert deleted.status_code == 204
    assert client.get(f"{API}/platform-rules", headers=headers).json()["rules"] == []


def test_scan_groups_by_rule_and_domain_fallback(tmp_path: Any) -> None:
    client, headers, _settings = make_app(tmp_path)
    email = client.post(
        f"{API}/usable-emails", json={"address": "me@example.com"}, headers=headers
    ).json()
    email_id: int = email["id"]

    insert_fetched_message(
        _settings,
        from_address="noreply@github.com",
        subject="[GitHub] PR",
        body="hi",
        usable_email_id=email_id,
    )
    insert_fetched_message(
        _settings,
        from_address="noreply@github.com",
        subject="[GitHub] issue",
        body="yo",
        usable_email_id=email_id,
    )
    insert_fetched_message(
        _settings,
        from_address="no-reply@google.com",
        subject="验证码",
        body="123456",
        usable_email_id=email_id,
    )

    # 未配置规则: 回退到域名启发式
    scan = client.post(f"{API}/platforms/scan", headers=headers).json()["items"]
    assert [item["platform"] for item in scan] == ["github.com", "google.com"]
    github = scan[0]
    assert github["message_count"] == 2
    assert github["sender_count"] == 1
    assert github["usable_email_ids"] == [email_id]
    assert github["source"] == "domain"

    # 配置规则后: 规则优先, 覆盖域名
    client.post(
        f"{API}/platform-rules",
        json={
            "name": "GitHub 规则",
            "match_field": "domain",
            "match_type": "contains",
            "pattern": "github",
            "platform_name": "GitHub",
            "enabled": True,
        },
        headers=headers,
    )
    scan = client.post(f"{API}/platforms/scan", headers=headers).json()["items"]
    by_name = {item["platform"]: item for item in scan}
    assert "GitHub" in by_name
    assert by_name["GitHub"]["message_count"] == 2
    assert by_name["GitHub"]["source"] == "GitHub 规则"


def test_accept_scan_item_creates_platform_and_bindings(tmp_path: Any) -> None:
    client, headers, _settings = make_app(tmp_path)
    email = client.post(
        f"{API}/usable-emails", json={"address": "me@example.com"}, headers=headers
    ).json()
    email_id: int = email["id"]
    insert_fetched_message(
        _settings,
        from_address="no-reply@amazon.com",
        subject="order",
        body="ok",
        usable_email_id=email_id,
    )

    accepted = client.post(
        f"{API}/platforms/scan/accept",
        json={"platform": "amazon.com", "usable_email_ids": [email_id]},
        headers=headers,
    )
    assert accepted.status_code == 200
    result = accepted.json()
    assert result["platform"] == "amazon.com"
    assert result["bindings_created"] == 1

    platforms = client.get(f"{API}/platforms", headers=headers).json()["platforms"]
    assert any(p["name"] == "amazon.com" for p in platforms)

    # 重复接受: 平台与绑定已存在, 自动跳过
    again = client.post(
        f"{API}/platforms/scan/accept",
        json={"platform": "amazon.com", "usable_email_ids": [email_id]},
        headers=headers,
    ).json()
    assert again["bindings_created"] == 0
    assert again["bindings_skipped"] == 1


def test_analyze_email_only_rules_and_auto_binds(tmp_path: Any) -> None:
    """邮箱分析: 仅按已配置规则识别(不做域名启发式), 并自动创建平台+绑定。"""
    client, headers, settings = make_app(tmp_path)
    email = client.post(
        f"{API}/usable-emails", json={"address": "me@example.com"}, headers=headers
    ).json()
    email_id: int = email["id"]
    insert_fetched_message(
        settings,
        from_address="noreply@github.com",
        subject="[GitHub] PR",
        body="hello",
        usable_email_id=email_id,
    )
    insert_fetched_message(
        settings,
        from_address="no-reply@random-unknown-site.com",
        subject="promo",
        body="hi",
        usable_email_id=email_id,
    )

    # 未配置规则: 不做域名启发式, 结果为空
    empty = client.post(f"{API}/usable-emails/{email_id}/platforms/analyze", headers=headers).json()
    assert empty["results"] == []

    # 配置规则后: 只识别规则命中的平台, 自动创建平台与绑定
    client.post(
        f"{API}/platform-rules",
        json={
            "name": "GitHub 规则",
            "match_field": "domain",
            "match_type": "contains",
            "pattern": "github.com",
            "platform_name": "GitHub",
            "enabled": True,
        },
        headers=headers,
    )
    analyzed = client.post(
        f"{API}/usable-emails/{email_id}/platforms/analyze", headers=headers
    ).json()["results"]
    assert len(analyzed) == 1
    github = analyzed[0]
    assert github["platform"] == "GitHub"
    assert github["message_count"] == 1
    assert github["bindings_created"] == 1
    assert "random-unknown-site.com" not in [item["platform"] for item in analyzed]

    bindings = client.get(
        f"{API}/usable-emails/{email_id}/platform-bindings", headers=headers
    ).json()["platform_bindings"]
    assert any(binding["platform"]["name"] == "GitHub" for binding in bindings)

    # 再次分析: 绑定已存在, 跳过
    again = client.post(
        f"{API}/usable-emails/{email_id}/platforms/analyze", headers=headers
    ).json()["results"]
    assert again[0]["bindings_created"] == 0
    assert again[0]["bindings_skipped"] == 1


def test_analyze_email_rejects_missing_email(tmp_path: Any) -> None:
    client, headers, _settings = make_app(tmp_path)
    response = client.post(f"{API}/usable-emails/99999/platforms/analyze", headers=headers)
    assert response.status_code == 422


def test_accept_scan_item_without_emails_creates_platform_only(tmp_path: Any) -> None:
    client, headers, _settings = make_app(tmp_path)
    accepted = client.post(
        f"{API}/platforms/scan/accept",
        json={"platform": "example.com", "usable_email_ids": []},
        headers=headers,
    )
    assert accepted.status_code == 200
    assert accepted.json()["bindings_created"] == 0

    empty = client.post(
        f"{API}/platforms/scan/accept",
        json={"platform": "   ", "usable_email_ids": []},
        headers=headers,
    )
    assert empty.status_code == 422
