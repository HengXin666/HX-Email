from hx_email.cli import main


def test_migrate_command_uses_configured_data_dir(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("HX_EMAIL_DATA_DIR", str(tmp_path / "runtime-data"))

    exit_code = main(["migrate"])

    assert exit_code == 0
    assert (tmp_path / "runtime-data" / "hx_email.sqlite3").exists()
    assert "Migration complete" in capsys.readouterr().out
