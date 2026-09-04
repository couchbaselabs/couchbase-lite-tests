"""Tests for the Shell2Http sidecar client, against a fake shell2http on loopback."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from aiohttp import web
from cbltest.api.error import CblTestError, CblTimeoutError
from cbltest.api.jsonserializable import JSONDictionary
from cbltest.api.shell2http import Shell2Http

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

        with pytest.raises(CblTestError, match=r"POST /restart-sgw failed on 127.0.0.1: 500 - .*no such config"):
            await sidecar.post("/restart-sgw", "bootstrap")


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
