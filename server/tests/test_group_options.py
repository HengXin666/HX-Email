"""Group default-option settings and create/update option semantics."""

from pathlib import Path

from hx_email.config import Settings
from hx_email.database import migrate
from hx_email.server.settings_service import set_setting
from hx_email.server.workspace.groups import create_group, update_group


def _settings(tmp_path: Path) -> Settings:
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    return settings


def test_create_group_defaults_true_when_settings_unset(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    group = create_group(settings, 1, "默认", "#58a6ff")
    assert group.notify_enabled is True
    assert group.polling_enabled is True


def test_create_group_follows_system_default_settings(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    set_setting(settings, "group_default_notify_enabled", "false")
    set_setting(settings, "group_default_polling_enabled", "false")
    group = create_group(settings, 1, "工作", "#58a6ff")
    assert group.notify_enabled is False
    assert group.polling_enabled is False


def test_create_group_explicit_options_override_defaults(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    set_setting(settings, "group_default_notify_enabled", "false")
    set_setting(settings, "group_default_polling_enabled", "false")
    group = create_group(
        settings,
        1,
        "显式",
        "#58a6ff",
        notify_enabled=True,
        polling_enabled=True,
    )
    assert group.notify_enabled is True
    assert group.polling_enabled is True


def test_update_group_preserves_options_when_omitted(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    group = create_group(
        settings,
        1,
        "原",
        "#58a6ff",
        notify_enabled=False,
        polling_enabled=False,
    )
    updated = update_group(settings, 1, group.id, "新名", "#238636")
    assert updated is not None
    assert updated.name == "新名"
    assert updated.notify_enabled is False
    assert updated.polling_enabled is False


def test_update_group_applies_explicit_options(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    group = create_group(settings, 1, "原", "#58a6ff")
    updated = update_group(
        settings,
        1,
        group.id,
        "原",
        "#58a6ff",
        notify_enabled=False,
        polling_enabled=False,
    )
    assert updated is not None
    assert updated.notify_enabled is False
    assert updated.polling_enabled is False
