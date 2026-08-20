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
    assert any(r["id"] == rule["id"] for r in listed)

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
    rules_after = client.get(f"{API}/platform-rules", headers=headers).json()["rules"]
    assert all(r["id"] != rule["id"] for r in rules_after)


def test_default_rules_seeded_once_on_fresh_database(tmp_path: Any) -> None:
    """首次 migrate 自动种入默认规则, 二次 migrate 不重复。"""
    from hx_email.database import migrate
    from hx_email.server.workspace.impl.default_rules import DEFAULT_PLATFORM_RULES

    client, headers, settings = make_app(tmp_path)
    listed = client.get(f"{API}/platform-rules", headers=headers).json()["rules"]
    assert len(listed) == len(DEFAULT_PLATFORM_RULES)
    assert any(r["platform_name"] == "GitHub" for r in listed)

    # 再次 migrate: 不重复种入
    migrate(settings)
    listed2 = client.get(f"{API}/platform-rules", headers=headers).json()["rules"]
    assert len(listed2) == len(DEFAULT_PLATFORM_RULES)


def test_scan_uses_default_rules_and_domain_fallback(tmp_path: Any) -> None:
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
        from_address="no-reply@random-weird-site.com",
        subject="promo",
        body="hello",
        usable_email_id=email_id,
    )

    # 默认规则命中 GitHub; 未命中默认规则的域名回退到域名启发式
    scan = client.post(f"{API}/platforms/scan", headers=headers).json()["items"]
    by_name = {item["platform"]: item for item in scan}
    assert by_name["GitHub"]["message_count"] == 2
    assert by_name["GitHub"]["source"] == "GitHub"
    assert by_name["random-weird-site.com"]["source"] == "domain"
    assert by_name["random-weird-site.com"]["message_count"] == 1

    # 自定义规则(后添加)优先于默认规则
    client.post(
        f"{API}/platform-rules",
        json={
            "name": "GitHub 自定义",
            "match_field": "domain",
            "match_type": "contains",
            "pattern": "github.com",
            "platform_name": "GitHub 自定义",
            "enabled": True,
        },
        headers=headers,
    )
    scan = client.post(f"{API}/platforms/scan", headers=headers).json()["items"]
    by_name = {item["platform"]: item for item in scan}
    assert by_name["GitHub 自定义"]["message_count"] == 2
    assert by_name["GitHub 自定义"]["source"] == "GitHub 自定义"
    assert "GitHub" not in by_name


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

    # 默认规则命中 GitHub(自动创建平台+绑定); 未命中规则的域名不做启发式
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

    # 自定义规则(后添加)优先: 同一发件人被映射到新平台
    client.post(
        f"{API}/platform-rules",
        json={
            "name": "GitHub 自定义",
            "match_field": "domain",
            "match_type": "contains",
            "pattern": "github.com",
            "platform_name": "GitHub 自定义",
            "enabled": True,
        },
        headers=headers,
    )
    analyzed = client.post(
        f"{API}/usable-emails/{email_id}/platforms/analyze", headers=headers
    ).json()["results"]
    by_platform = {item["platform"]: item for item in analyzed}
    assert by_platform["GitHub 自定义"]["bindings_created"] == 1
    # 自定义规则完全接管该发件人, 默认 GitHub 规则不再命中
    assert "GitHub" not in by_platform


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


def test_rule_supports_multiple_patterns(tmp_path: Any) -> None:
    """一条规则可配多个域名/模式, 任一命中即识别到该平台。"""
    client, headers, settings = make_app(tmp_path)
    email = client.post(
        f"{API}/usable-emails", json={"address": "me@example.com"}, headers=headers
    ).json()
    email_id: int = email["id"]
    insert_fetched_message(
        settings,
        from_address="noreply@github.com",
        subject="PR",
        body="hi",
        usable_email_id=email_id,
    )
    insert_fetched_message(
        settings,
        from_address="bot@raw.githubusercontent.com",
        subject="asset",
        body="yo",
        usable_email_id=email_id,
    )

    created = client.post(
        f"{API}/platform-rules",
        json={
            "name": "GitHub 全家桶",
            "match_field": "domain",
            "match_type": "contains",
            "patterns": ["github.com", "githubusercontent.com"],
            "platform_name": "GitHub 全家桶",
            "enabled": True,
        },
        headers=headers,
    )
    assert created.status_code == 201
    rule = created.json()
    assert rule["patterns"] == ["github.com", "githubusercontent.com"]

    # 两条不同域名消息都命中同一规则
    analyzed = client.post(
        f"{API}/usable-emails/{email_id}/platforms/analyze", headers=headers
    ).json()["results"]
    assert analyzed[0]["platform"] == "GitHub 全家桶"
    assert analyzed[0]["message_count"] == 2

    # 编辑规则: 移除一个模式后只命中剩余模式
    updated = client.put(
        f"{API}/platform-rules/{rule['id']}",
        json={
            "name": "GitHub 全家桶",
            "match_field": "domain",
            "match_type": "contains",
            "patterns": ["githubusercontent.com"],
            "platform_name": "GitHub 全家桶",
            "enabled": True,
        },
        headers=headers,
    )
    assert updated.status_code == 200
    analyzed = client.post(
        f"{API}/usable-emails/{email_id}/platforms/analyze", headers=headers
    ).json()["results"]
    assert analyzed[0]["message_count"] == 1


def test_rules_export_and_import(tmp_path: Any) -> None:
    """规则可导出 JSON, 导入按策略去重/替换。"""
    client, headers, _settings = make_app(tmp_path)
    client.post(
        f"{API}/platform-rules",
        json={
            "name": "MySite",
            "match_field": "domain",
            "match_type": "contains",
            "patterns": ["mysite.com", "mysite.cn"],
            "platform_name": "MySite",
            "enabled": True,
        },
        headers=headers,
    )
    exported = client.get(f"{API}/platform-rules/export", headers=headers).json()["rules"]
    my_site = next(r for r in exported if r["platform_name"] == "MySite")
    assert my_site["patterns"] == ["mysite.com", "mysite.cn"]

    # 导入完全相同规则: skip 跳过
    result = client.post(
        f"{API}/platform-rules/import",
        json={"rules": [my_site], "strategy": "skip"},
        headers=headers,
    ).json()
    assert result["skipped"] == 1
    assert result["imported"] == 0

    # 导入新规则
    extra = {
        "name": "Another",
        "match_field": "subject",
        "match_type": "regex",
        "patterns": [r"verify[-\s]?code"],
        "platform_name": "Another",
        "enabled": True,
    }
    result = client.post(
        f"{API}/platform-rules/import",
        json={"rules": [extra], "strategy": "skip"},
        headers=headers,
    ).json()
    assert result["imported"] == 1
    listed = client.get(f"{API}/platform-rules", headers=headers).json()["rules"]
    assert any(r["platform_name"] == "Another" for r in listed)

    # replace 策略: 同名平台规则被替换为新模式
    replaced = client.post(
        f"{API}/platform-rules/import",
        json={
            "rules": [{"platform_name": "MySite", "patterns": ["newsite.com"]}],
            "strategy": "replace",
        },
        headers=headers,
    ).json()
    assert replaced["imported"] == 1
    listed = client.get(f"{API}/platform-rules", headers=headers).json()["rules"]
    my_site_now = next(r for r in listed if r["platform_name"] == "MySite")
    assert my_site_now["patterns"] == ["newsite.com"]
    assert sum(1 for r in listed if r["platform_name"] == "MySite") == 1
