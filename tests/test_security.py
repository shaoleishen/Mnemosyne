"""Tests for local path boundary validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from knowcran.security import resolve_allowed_data_dir, resolve_allowed_path, resolve_allowed_vault_dir


def test_resolve_allowed_path_returns_env_root_when_request_is_none(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("KNOWCRAN_DATA_DIR", str(tmp_path))

    assert resolve_allowed_data_dir(None) == tmp_path.resolve()


def test_resolve_allowed_path_accepts_child_directory(tmp_path, monkeypatch) -> None:
    child = tmp_path / "child"
    child.mkdir()
    monkeypatch.setenv("KNOWCRAN_DATA_DIR", str(tmp_path))

    assert resolve_allowed_data_dir(str(child)) == child.resolve()


def test_resolve_allowed_path_rejects_parent_escape(tmp_path, monkeypatch) -> None:
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    monkeypatch.setenv("KNOWCRAN_DATA_DIR", str(allowed))

    with pytest.raises(ValueError, match="Security Error"):
        resolve_allowed_data_dir(str(outside))


def test_resolve_allowed_vault_dir_uses_vault_env_root(tmp_path, monkeypatch) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("KNOWCRAN_VAULT_DIR", str(vault))

    assert resolve_allowed_vault_dir(None) == vault.resolve()


def test_resolve_allowed_path_uses_default_name_when_env_absent(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("KNOWCRAN_DATA_DIR", raising=False)
    default_data = tmp_path / "data"

    assert resolve_allowed_path(None, "data", "KNOWCRAN_DATA_DIR") == default_data.resolve()
