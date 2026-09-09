"""Tests for the Caddy and Shell2Http sidecar clients, against fake sidecars on loopback."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from aiohttp import web
from cbltest.api.error import CblHttpError, CblTestError, CblTimeoutError
from cbltest.api.jsonserializable import JSONDictionary
from cbltest.api.sidecar import Caddy, Shell2Http

# A port nothing listens on, for the calls that must fail rather than reach a server.
_DEAD_PORT = 20002


class _FakeSidecar:
    """Records what arrives, and answers however the test asked it to."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.status = 200
        self.reply = "ok"
        self.hang = False
        # Released at teardown, so a hung handler does not hold the server open.
        self.released = asyncio.Event()

    async def handle(self, request: web.Request) -> web.Response:
        self.calls.append(
            {
                "method": request.method,
                "path": request.path_qs,
                "body": await request.text(),
                "content_type": request.headers.get("Content-Type"),
            }
        )
        if self.hang:
            # Answers only once the test is over, so the client is what gives up.
            await self.released.wait()
        return web.Response(status=self.status, text=self.reply)


@asynccontextmanager
async def _fake_sidecar() -> AsyncIterator[tuple[Shell2Http, _FakeSidecar]]:
    """A Shell2Http pointed at a fake shell2http, both torn down on the way out."""
    fake = _FakeSidecar()
    app = web.Application()
    app.router.add_route("*", "/{tail:.*}", fake.handle)
    runner = web.AppRunner(app)
    await runner.setup()
    try:
        await web.TCPSite(runner, "127.0.0.1", 0).start()
        port = next(iter(runner.addresses))[1]
        sidecar = Shell2Http("127.0.0.1", port)
        try:
            yield sidecar, fake
        finally:
            await sidecar.close()
    finally:
        fake.released.set()
        await runner.cleanup()


@pytest.fixture(autouse=True)
def _http_log_in_tmp_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """Every call writes to the HTTP log, which belongs in the test's own directory."""
    monkeypatch.chdir(tmp_path)


@pytest.mark.asyncio
async def test_get_sends_the_query_string_and_no_body() -> None:
    async with _fake_sidecar() as (sidecar, fake):
        assert await sidecar.get("/start-sgw?config=bootstrap") == "ok"

    assert fake.calls == [{"method": "GET", "path": "/start-sgw?config=bootstrap", "body": "", "content_type": None}]


@pytest.mark.asyncio
async def test_text_and_json_bodies_are_labelled_for_the_script_reading_them() -> None:
    async with _fake_sidecar() as (sidecar, fake):
        await sidecar.post("/upload-cert", "ca.pem\n-----BEGIN-----")
        await sidecar.post("/reset-db", JSONDictionary({"filename": "db.cblite2"}))
        await sidecar.post("/kill-edgeserver")

    assert [(call["content_type"], call["body"]) for call in fake.calls[:2]] == [
        ("text/plain", "ca.pem\n-----BEGIN-----"),
        ("application/json", '{\n  "filename": "db.cblite2"\n}'),
    ]
    assert fake.calls[2]["body"] == "", "an endpoint that takes no body is sent none"


@pytest.mark.asyncio
async def test_a_failing_script_says_which_call_failed_where() -> None:
    async with _fake_sidecar() as (sidecar, fake):
        fake.status = 500
        fake.reply = "start-sgw.sh: no such config"

        with pytest.raises(
            CblHttpError, match=r"POST /restart-sgw failed on 127.0.0.1: 500 - .*no such config"
        ) as raised:
            await sidecar.post("/restart-sgw", "bootstrap")

        assert (raised.value.code, raised.value.body) == (500, "start-sgw.sh: no such config")


@pytest.mark.asyncio
async def test_a_script_that_never_answers_times_out_with_its_budget() -> None:
    async with _fake_sidecar() as (sidecar, fake):
        fake.hang = True

        with pytest.raises(CblTimeoutError, match=r"GET /stop-sgw timed out on 127.0.0.1 after 0.1s"):
            await sidecar.get("/stop-sgw", timeout=0.1)


@pytest.mark.asyncio
async def test_an_unreachable_host_fails_rather_than_hanging() -> None:
    sidecar = Shell2Http("127.0.0.1", _DEAD_PORT)
    async with sidecar:
        with pytest.raises(CblTestError, match="GET /stop-cbs failed to reach 127.0.0.1"):
            await sidecar.get("/stop-cbs")

    assert sidecar.closed, "leaving the block closes the session"
    await sidecar.close()


@pytest.mark.asyncio
async def test_a_host_with_no_sidecar_is_not_reachable() -> None:
    async with Shell2Http("127.0.0.1", _DEAD_PORT) as sidecar:
        assert not sidecar.is_reachable()


class _FakeFileServer:
    """Serves the files a test put in it, and a browse listing of them."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.browsable = True

    async def handle(self, request: web.Request) -> web.StreamResponse:
        if request.path == "/":
            if not self.browsable:
                return web.Response(status=404, text="not found")
            listing = [{"name": name, "is_dir": False} for name in self.files] + [{"name": "logs", "is_dir": True}]
            return web.json_response(listing)

        content = self.files.get(request.path.lstrip("/"))
        if content is None:
            return web.Response(status=404, text="not found")

        return web.Response(body=content)


@asynccontextmanager
async def _fake_file_server() -> AsyncIterator[tuple[Caddy, _FakeFileServer]]:
    """A Caddy pointed at a fake file server, both torn down on the way out."""
    fake = _FakeFileServer()
    app = web.Application()
    app.router.add_route("*", "/{tail:.*}", fake.handle)
    runner = web.AppRunner(app)
    await runner.setup()
    try:
        await web.TCPSite(runner, "127.0.0.1", 0).start()
        port = next(iter(runner.addresses))[1]
        caddy = Caddy("127.0.0.1", port)
        try:
            yield caddy, fake
        finally:
            await caddy.close()
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_download_writes_the_bytes_it_was_served(tmp_path: Path) -> None:
    async with _fake_file_server() as (caddy, fake):
        # Larger than one chunk, so the streaming path is what runs.
        fake.files["sgcollectinfo-abc.zip"] = bytes(range(256)) * 1024

        destination = await caddy.download("/sgcollectinfo-abc.zip", tmp_path / "logs" / "sgcollect.zip")

    assert destination.read_bytes() == fake.files["sgcollectinfo-abc.zip"]


@pytest.mark.asyncio
async def test_download_of_a_missing_file_leaves_nothing_behind(tmp_path: Path) -> None:
    destination = tmp_path / "sg_debug.log"
    async with _fake_file_server() as (caddy, _):
        with pytest.raises(CblHttpError, match="Download /sg_debug.log failed on 127.0.0.1: 404") as raised:
            await caddy.download("/sg_debug.log", destination)

    assert raised.value.code == 404, "a caller reads the code to tell a missing file from a failed call"
    assert not destination.exists(), "a failed download creates no file to mistake for a real one"


@pytest.mark.asyncio
async def test_list_returns_the_files_a_pattern_matches() -> None:
    async with _fake_file_server() as (caddy, fake):
        fake.files = {"sgcollectinfo-abc-redacted.zip": b"", "sgcollectinfo-abc.zip": b"", "sg_debug.log": b""}

        assert await caddy.list() == ["sgcollectinfo-abc-redacted.zip", "sgcollectinfo-abc.zip", "sg_debug.log"], (
            "a directory is not a file"
        )
        assert await caddy.list(pattern=r"sgcollect.*redacted\.zip") == ["sgcollectinfo-abc-redacted.zip"]


@pytest.mark.asyncio
async def test_list_without_browsing_enabled_says_so() -> None:
    async with _fake_file_server() as (caddy, fake):
        fake.browsable = False

        with pytest.raises(CblTestError, match="file_server browse"):
            await caddy.list()
