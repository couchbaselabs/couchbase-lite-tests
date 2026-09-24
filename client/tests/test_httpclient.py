import asyncio
import re
import socket
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from aiohttp import ClientTimeout, TCPConnector, web
from aiohttp.abc import AbstractResolver, ResolveResult
from cbltest.api.error import CblTimeoutError
from cbltest.httpclient import get_client_session


@pytest_asyncio.fixture(loop_scope="function")
async def slow_server() -> AsyncIterator[str]:
    release = asyncio.Event()

    async def slow(_: web.Request) -> web.Response:
        await release.wait()
        return web.Response()

    async def stalled(request: web.Request) -> web.StreamResponse:
        resp = web.StreamResponse()
        resp.content_length = 10
        await resp.prepare(request)
        await resp.write(b"abc")
        await release.wait()
        return resp

    app = web.Application()
    app.router.add_get("/slow", slow)
    app.router.add_get("/stalled", stalled)
    runner = web.AppRunner(app)
    await runner.setup()
    sock = socket.create_server(("localhost", 0))
    await web.SockSite(runner, sock).start()
    yield f"http://localhost:{sock.getsockname()[1]}"
    release.set()
    await runner.cleanup()


@pytest.mark.asyncio
async def test_timeout_names_the_request(slow_server: str) -> None:
    async with get_client_session(slow_server, timeout=ClientTimeout(total=0.2)) as session:
        with pytest.raises(
            CblTimeoutError,
            match=r"^GET http://localhost:\d+/slow\?x=1 timed out after \d+\.\ds waiting for the response$",
        ):
            await session.get("/slow", params={"x": "1"})


@pytest.mark.asyncio
async def test_timeout_is_still_a_timeout_error(slow_server: str) -> None:
    async with get_client_session(slow_server) as session:
        with pytest.raises(TimeoutError):
            await session.request("get", "/slow", timeout=ClientTimeout(total=0.2))


class _HangingResolver(AbstractResolver):
    """Never resolves, so a total timeout fires while connecting, outside the middleware."""

    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[ResolveResult]:
        await asyncio.sleep(5)
        return []

    async def close(self) -> None:
        pass


@pytest.mark.asyncio
async def test_timeout_while_connecting_notes_the_request() -> None:
    async with get_client_session(
        connector=TCPConnector(resolver=_HangingResolver()), timeout=ClientTimeout(total=0.2)
    ) as session:
        with pytest.raises(TimeoutError) as excinfo:
            await session.get("http://sgw.example.com:4985/_all_dbs")

    cause = excinfo.value.__cause__
    assert isinstance(cause, asyncio.CancelledError)
    notes = getattr(cause, "__notes__", [])
    assert len(notes) == 1
    assert re.fullmatch(r"GET http://sgw\.example\.com:4985/_all_dbs was cancelled after \d+\.\ds", notes[0])


@pytest.mark.asyncio
async def test_timeout_while_reading_the_body_names_the_request(slow_server: str) -> None:
    async with get_client_session(slow_server, timeout=ClientTimeout(total=0.2)) as session:
        resp = await session.get("/stalled")
        with pytest.raises(
            CblTimeoutError,
            match=r"^GET http://localhost:\d+/stalled timed out after \d+\.\ds reading the body, received 3 B of 10 B \(30%\)$",
        ):
            await resp.text()
