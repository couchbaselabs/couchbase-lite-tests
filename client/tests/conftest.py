import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import create_autospec, patch

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
        patch("cbltest.api.syncgateway.requests.get", autospec=True),
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
