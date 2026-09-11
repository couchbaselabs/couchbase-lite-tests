"""Tests for CouchbaseServer.collect_logs, the shell2http + Caddy path cbcollect uses."""

import json
from pathlib import Path

import aiohttp
import pytest
from cbltest.api.caddy import Caddy
from cbltest.api.couchbaseserver import _COLLECT_LOGS_TIMEOUT, CouchbaseServer

SidecarCall = tuple[str, str, str | None, aiohttp.ClientTimeout | None]


def make_server() -> CouchbaseServer:
    return CouchbaseServer(url="https://cbs.example.com", username="user", password="pass")


def stub_sidecar(monkeypatch: pytest.MonkeyPatch, server: CouchbaseServer, response: str = "{}") -> list[SidecarCall]:
    """Record what a server sends to its sidecar, so nothing reaches the network."""
    calls: list[SidecarCall] = []

    async def _call_sidecar(
        method: str, path: str, data: str | None = None, timeout: aiohttp.ClientTimeout | None = None
    ) -> str:
        calls.append((method, path, data, timeout))
        return response

    monkeypatch.setattr(server, "_call_sidecar", _call_sidecar)
    return calls


@pytest.mark.asyncio
async def test_collect_logs_downloads_the_archive_the_sidecar_made(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    downloads: list[tuple[str, Path]] = []

    async def fake_download(self: Caddy, filename: str, local_path: str | Path) -> Path:
        downloads.append((filename, Path(local_path)))
        return Path(local_path)

    monkeypatch.setattr(Caddy, "download", fake_download)

    server = make_server()
    calls = stub_sidecar(monkeypatch, server)

    archive = await server.collect_logs(tmp_path)

    assert [(method, path) for method, path, _, _ in calls] == [("post", "/collect-logs")]
    (_, _, body, timeout) = calls[0]
    assert body is not None
    filename = json.loads(body)["filename"]
    assert filename.startswith("cbcollect-cbs-example-com-"), filename
    assert filename.endswith(".zip"), filename
    assert timeout == _COLLECT_LOGS_TIMEOUT, (
        "must outlast the shell2http endpoint's own kill-after-bounded worst case, not race "
        "aiohttp's shorter 300s default against it"
    )
    assert downloads == [(filename, tmp_path / filename)], (
        "the archive is fetched by the plain filename cbcollect_info wrote, through this node's Caddy"
    )
    assert archive == tmp_path / filename


@pytest.mark.asyncio
async def test_collect_logs_surfaces_warnings_without_failing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_download(self: Caddy, filename: str, local_path: str | Path) -> Path:
        return Path(local_path)

    monkeypatch.setattr(Caddy, "download", fake_download)

    server = make_server()
    stub_sidecar(monkeypatch, server, response='{"warnings": "some component was unreachable"}')

    archive = await server.collect_logs(tmp_path)

    assert archive.suffix == ".zip"
