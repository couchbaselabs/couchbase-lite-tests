import json
import shutil
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import create_autospec, patch

import pytest
from cbltest.api import edgeserver, syncgateway
from cbltest.httpclient import AsyncHTTPClient


@contextmanager
def fake_sync_gateways(count: int) -> Iterator[list[syncgateway.SyncGateway]]:
    with (
        # Only Sync Gateway's own sessions, so a manager built on these nodes keeps real ones.
        patch(
            "cbltest.api.syncgateway.AsyncHTTPClient",
            side_effect=lambda *args, **kwargs: create_autospec(AsyncHTTPClient, instance=True),
        ),
        patch("cbltest.api.caddy.AsyncHTTPClient", autospec=True),
        # Every sidecar probe answers, so these nodes report both sidecars.
        patch("cbltest.api.syncgateway.is_sidecar_reachable", return_value=True),
        patch("cbltest.api.caddy.is_sidecar_reachable", return_value=True),
    ):
        # A bare host, as the config supplies: SyncGateway builds its own URLs from this,
        # and a scheme here produces nonsense like "http://https://example.com:20001".
        yield [
            syncgateway.SyncGateway(
                url="sgw.example.com",
                username="user",
                password="pass",
            )
            for _ in range(count)
        ]


def set_using_rosmar(sync_gateway: syncgateway.SyncGateway, value: bool) -> None:
    """Settle `sync_gateway.using_rosmar` as though it had already fetched /_config."""
    config = syncgateway.StartupConfigResponse.model_validate(
        {"bootstrap": {"server": "rosmar:/?mode=memory" if value else "couchbase://localhost"}}
    )

    class Settled:
        def __await__(self) -> Generator[None, None, syncgateway.StartupConfigResponse]:
            return config
            yield

    sync_gateway.__dict__["_startup_config"] = Settled()


@contextmanager
def fake_edge_server(tmp_path: Path) -> Iterator[edgeserver.EdgeServer]:
    """An Edge Server whose sessions never reach the network. Its config declares no users,
    so the client it builds sends no credentials."""
    config = tmp_path / "edge_server_config.json"
    config.write_text(json.dumps({"interface": "0.0.0.0:59840", "databases": {"db": {"path": "db.cblite2"}}}))
    with (
        patch("cbltest.httpclient.ClientSession", autospec=True),
    ):
        yield edgeserver.EdgeServer(url="es.example.com", config_file=str(config))


@dataclass(frozen=True)
class NestedPytest:
    pytester: pytest.Pytester
    args: tuple[str, ...]


@pytest.fixture
def nested_pytest(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> NestedPytest:
    """A pytester folder with its own config files, so the nested run never reads client/pyproject.toml."""
    # Plugins warn from pytest_configure, before -W applies, so only the interpreter's filter catches those.
    monkeypatch.setenv("PYTHONWARNINGS", "error")
    shutil.copy(Path(__file__).with_name("empty_config.json"), pytester.path)
    pytester.makepyprojecttoml("""
        [tool.pytest.ini_options]
        asyncio_default_fixture_loop_scope = "session"
    """)
    return NestedPytest(pytester, ("--config", "empty_config.json", "-p", "no:randomly", "-W", "error"))
