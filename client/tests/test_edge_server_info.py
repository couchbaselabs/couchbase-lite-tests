"""Tests for EdgeServerInfo's default config path."""

from pathlib import Path

import pytest
from cbltest import configparser
from cbltest.configparser import EdgeServerInfo

DEFAULT_CONFIG = Path("environment/aws/es_setup/config/config.json")


def _checkout(root: Path, *, with_config: bool) -> Path:
    """A fake checkout under ``root`` holding configparser.py, and the default Edge Server config if asked."""
    module = root / "client" / "src" / "cbltest" / "configparser.py"
    module.parent.mkdir(parents=True)
    module.touch()
    if with_config:
        (root / DEFAULT_CONFIG).parent.mkdir(parents=True)
        (root / DEFAULT_CONFIG).write_text("{}")
    return module


def test_default_config_found_whatever_the_checkout_is_named(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Jenkins names the workspace after the job, so the folder name says nothing about the repository.
    root = tmp_path / "e2e-functional-dotnet"
    monkeypatch.setattr(configparser, "__file__", str(_checkout(root, with_config=True)))

    info = EdgeServerInfo({"hostname": "es.example.com"})

    assert Path(info.config_path) == (root / DEFAULT_CONFIG).resolve()


def test_missing_default_config_is_a_clear_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(configparser, "__file__", str(_checkout(tmp_path / "ws", with_config=False)))

    with pytest.raises(ValueError, match="no environment.aws.es_setup.config.config.json was found"):
        EdgeServerInfo({"hostname": "es.example.com"})


def test_given_config_path_is_used_without_searching(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(configparser, "__file__", str(_checkout(tmp_path / "ws", with_config=False)))

    info = EdgeServerInfo({"hostname": "es.example.com", "config_path": "/etc/es/config.json"})

    assert info.config_path == "/etc/es/config.json"
