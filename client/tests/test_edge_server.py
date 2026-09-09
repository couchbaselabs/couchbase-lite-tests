"""Tests for the EdgeServer client and EdgeServerConfig, the config file it parses."""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from cbltest.api.edgeserver import EdgeServer, EdgeServerConfig
from cbltest.api.error import CblHttpError, CblTestError

HOSTNAME = "es.example.com"
AUDIT_LOG = "/home/ec2-user/audit/EdgeServerAuditLog.txt"


@contextmanager
def no_network() -> Iterator[None]:
    """Keep the sessions an Edge Server client opens off the network."""
    with (
        patch("cbltest.api.edgeserver.ClientSession", autospec=True),
        patch("cbltest.api.sidecar.ClientSession", autospec=True),
    ):
        yield


def write_config(directory: Path, name: str, config: dict[str, Any]) -> str:
    path = directory / name
    path.write_text(json.dumps(config))
    return str(path)


def test_reads_the_parts_the_framework_needs(tmp_path: Path) -> None:
    config = EdgeServerConfig.load(
        write_config(
            tmp_path,
            "mtls.json",
            {
                "interface": "0.0.0.0:60000",
                "users": "/home/ec2-user/user/users.json",
                "https": {
                    "tls_cert_path": "/cert.pem",
                    "tls_key_path": "/key.pem",
                    "client_cert_path": "/ca.pem",
                },
                "logging": {"audit": {"file": AUDIT_LOG, "enable": "*"}},
            },
        )
    )

    assert config.port == 60000
    assert config.is_tls
    assert config.is_mtls
    assert config.declares_users
    assert config.audit_log == AUDIT_LOG


def test_defaults_where_the_config_is_silent(tmp_path: Path) -> None:
    config = EdgeServerConfig.load(write_config(tmp_path, "bare.json", {}))

    assert config.port == 59840
    assert not config.is_tls
    assert not config.is_mtls
    assert not config.declares_users
    assert config.audit_log is None


def test_tls_without_a_client_certificate_is_not_mtls(tmp_path: Path) -> None:
    config = EdgeServerConfig.load(
        write_config(tmp_path, "tls.json", {"https": {"tls_cert_path": "/cert.pem", "tls_key_path": "/key.pem"}})
    )

    assert config.is_tls
    assert not config.is_mtls


@pytest.mark.parametrize(
    "logging_block",
    [{}, {"console": False}, {"audit": {"enable": "*"}}],
    ids=["no logging keys", "logging without audit", "audit without a file"],
)
def test_no_audit_log_reads_as_none(tmp_path: Path, logging_block: dict) -> None:
    config = EdgeServerConfig.load(write_config(tmp_path, "quiet.json", {"logging": logging_block}))

    assert config.audit_log is None


def test_keeps_the_keys_it_does_not_declare(tmp_path: Path) -> None:
    """Edge Server adds config keys between versions, so an unknown one must not be rejected."""
    config = EdgeServerConfig.load(
        write_config(
            tmp_path,
            "future.json",
            {"databases": {"db": {"path": "/db.cblite2"}}, "a_key_from_a_later_release": 7},
        )
    )

    assert config.model_extra == {
        "databases": {"db": {"path": "/db.cblite2"}},
        "a_key_from_a_later_release": 7,
    }


def test_reads_json5(tmp_path: Path) -> None:
    """Edge Server accepts JSON5, so a config may carry comments and trailing commas."""
    path = tmp_path / "json5.json"
    path.write_text('{\n  // the port a test picked\n  "interface": "0.0.0.0:60001",\n}\n')

    assert EdgeServerConfig.load(str(path)).port == 60001


def test_audit_log_path_comes_from_the_running_config(tmp_path: Path) -> None:
    config_file = write_config(tmp_path, "audit.json", {"logging": {"audit": {"file": AUDIT_LOG}}})
    with no_network():
        client = EdgeServer(HOSTNAME, config_file=config_file)

    assert client.audit_log_path == AUDIT_LOG


def test_audit_log_path_raises_without_an_audit_log(tmp_path: Path) -> None:
    config_file = write_config(tmp_path, "quiet.json", {"logging": {"console": False}})
    with no_network():
        client = EdgeServer(HOSTNAME, config_file=config_file)

    with pytest.raises(CblTestError, match="declares no audit log"):
        _ = client.audit_log_path


@pytest.mark.asyncio
async def test_a_log_the_host_never_wrote_reads_as_missing(tmp_path: Path) -> None:
    """check_audit_log treats a missing log as an empty one, so a 404 must arrive as such."""
    config_file = write_config(tmp_path, "audit.json", {"logging": {"audit": {"file": AUDIT_LOG}}})
    with no_network():
        client = EdgeServer(HOSTNAME, config_file=config_file)

        async def download(uri: str, local_path: str | Path) -> Path:
            raise CblHttpError(404, f"Download {uri} failed on {HOSTNAME}: 404 - not found", body="not found")

        with patch.object(client.caddy, "download", download):
            with pytest.raises(FileNotFoundError, match="does not exist on es.example.com"):
                await client.download_log_file(AUDIT_LOG, tmp_path / "audit.txt")

            assert await client.check_audit_log("anything") == []
