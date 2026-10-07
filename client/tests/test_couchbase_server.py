"""Tests for CouchbaseServer.collect_logs, the shell2http + Caddy path cbcollect uses."""

import json
import logging
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

import pytest
from cbltest.api.caddy import Caddy
from cbltest.api.couchbaseserver import _COLLECT_LOGS_TIMEOUT, CouchbaseServer

SidecarCall = tuple[str, str, str | None, float | None]


def make_server() -> CouchbaseServer:
    with (
        patch("cbltest.api.couchbaseserver.Cluster", autospec=True),
        patch("cbltest.api.couchbaseserver.AsyncHTTPClient", autospec=True),
        patch("cbltest.api.caddy.AsyncHTTPClient", autospec=True),
    ):
        return CouchbaseServer(url="https://cbs.example.com", username="user", password="pass")


def _redacted_echo(data: str | None) -> str:
    """Default sidecar response: reports back the redacted archive collect-logs.sh would
    actually produce for the requested filename (see collect-logs.sh), not that name itself."""
    assert data is not None
    requested = json.loads(data)["filename"]
    return json.dumps({"file": f"{requested.removesuffix('.zip')}-redacted.zip"})


def stub_sidecar(
    monkeypatch: pytest.MonkeyPatch,
    server: CouchbaseServer,
    response: str | Callable[[str | None], str] = _redacted_echo,
) -> list[SidecarCall]:
    """Record what a server sends to its sidecar, so nothing reaches the network."""
    calls: list[SidecarCall] = []

    async def _call_sidecar(method: str, path: str, data: str | None = None, timeout: float | None = None) -> str:
        calls.append((method, path, data, timeout))
        return response if isinstance(response, str) else response(data)

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

    try:
        archive = await server.collect_logs(tmp_path)
    finally:
        await server.close()

    assert [(method, path) for method, path, _, _ in calls] == [("post", "/collect-logs")]
    (_, _, body, timeout) = calls[0]
    assert body is not None
    requested_filename = json.loads(body)["filename"]
    assert requested_filename.startswith("cbcollect-cbs-example-com-"), requested_filename
    assert requested_filename.endswith(".zip"), requested_filename
    assert timeout == _COLLECT_LOGS_TIMEOUT, (
        "must outlast the shell2http endpoint's own kill-after-bounded worst case, not race "
        "aiohttp's shorter 300s default against it"
    )
    downloaded_filename = f"{requested_filename.removesuffix('.zip')}-redacted.zip"
    assert downloads == [(downloaded_filename, tmp_path / downloaded_filename)], (
        "the archive fetched is the one the sidecar reports back in its response -- the "
        "redacted copy --, not necessarily the plain name originally requested"
    )
    assert archive == tmp_path / downloaded_filename


@pytest.mark.asyncio
async def test_collect_logs_surfaces_warnings_without_failing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def fake_download(self: Caddy, filename: str, local_path: str | Path) -> Path:
        return Path(local_path)

    monkeypatch.setattr(Caddy, "download", fake_download)

    server = make_server()
    stub_sidecar(
        monkeypatch,
        server,
        response='{"file": "cbcollect-cbs-example-com-x-redacted.zip", "warnings": "some component was unreachable"}',
    )

    with caplog.at_level(logging.WARNING, logger="CBL"):
        try:
            archive = await server.collect_logs(tmp_path)
        finally:
            await server.close()

    assert archive.suffix == ".zip"
    assert any("some component was unreachable" in record.message for record in caplog.records), (
        "collect_logs must surface the sidecar's reported warnings, not just succeed silently"
    )
