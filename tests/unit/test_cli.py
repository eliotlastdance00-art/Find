from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import Mock

import pytest

from dfd import cli
from dfd.config import Settings
from dfd.infrastructure.db.repositories import SqlUserRepository
from dfd.infrastructure.db.session import create_session_factory
from dfd.infrastructure.ml import download


def test_models_command_lists_installed_models(
    weights_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DFD_WEIGHTS_DIR", str(weights_dir))
    cli.main(["models"])
    report = json.loads(capsys.readouterr().out)
    assert report["visual"]["available"] is True
    assert report["audio"]["arch"] == "AASIST"


def test_create_user_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DFD_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DFD_WEIGHTS_DIR", str(tmp_path / "none"))
    cli.main(["create-user", "operator", "--password", "a-long-password", "--admin"])
    assert "created admin 'operator'" in capsys.readouterr().out

    engine, sessions = create_session_factory(Settings().resolved_database_url())
    user = SqlUserRepository(sessions).get_by_username("operator")
    engine.dispose()
    assert user is not None and user.role.value == "admin"
    assert user.password_hash.startswith("$argon2id$")

    with pytest.raises(SystemExit) as failure:
        cli.main(["create-user", "operator", "--password", "a-long-password"])
    assert failure.value.code == 1
    assert "username_taken" in capsys.readouterr().err


def test_secret_key_is_generated_once_and_kept_private(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path)  # type: ignore[call-arg]
    key = settings.resolved_secret_key()
    assert len(key) >= 48
    assert settings.resolved_secret_key() == key
    if os.name == "posix":  # Windows has no permission bits; the file inherits the folder's ACL
        assert (tmp_path / "secret.key").stat().st_mode & 0o777 == 0o600
    assert Settings(_env_file=None, secret_key="explicit").resolved_secret_key() == "explicit"  # type: ignore[call-arg]


def test_models_download_command_is_explicit_and_reports_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DFD_WEIGHTS_DIR", str(tmp_path))
    fetch = Mock()
    monkeypatch.setattr(download, "download_smaug", fetch)
    cli.main(["models"])
    fetch.assert_not_called()
    cli.main(["models", "--download"])
    assert fetch.call_count == 1 and fetch.call_args.args[0] == tmp_path
    fetch.call_args.args[1]("fetching")
    assert "fetching" in capsys.readouterr().err
    fetch.side_effect = download.ModelDownloadError("offline; retry the command")
    with pytest.raises(SystemExit, match="retry the command"):
        cli.main(["models", "--download"])
