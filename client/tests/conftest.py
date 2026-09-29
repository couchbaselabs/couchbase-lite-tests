import json
from collections.abc import Generator, Iterator
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

    class Settled:
        def __await__(self) -> Generator[None, None, bool]:
            return value
            yield

    sync_gateway.__dict__["using_rosmar"] = Settled()


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
