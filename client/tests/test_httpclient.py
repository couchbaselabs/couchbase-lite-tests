import asyncio
import gzip
import os
import socket
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from aiohttp import ClientTimeout, TCPConnector, web
from aiohttp.abc import AbstractResolver, ResolveResult
from cbltest.api.error import CblTestError, CblTimeoutError
from cbltest.httpclient import AsyncHTTPClient


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

    async def stalled_gzip(request: web.Request) -> web.StreamResponse:
        # Hex text compresses about 2:1, so the decompressed count runs well ahead of the raw one.
        compressed = gzip.compress(os.urandom(32 * 1024).hex().encode())
        resp = web.StreamResponse(headers={"Content-Encoding": "gzip"})
        resp.content_length = len(compressed)
        await resp.prepare(request)
        await resp.write(compressed[: 16 * 1024])
        await release.wait()
        return resp

    async def file(_: web.Request) -> web.Response:
        return web.Response(body=b"hello")

    async def missing(_: web.Request) -> web.Response:
        return web.Response(status=404)

    async def broken(_: web.Request) -> web.Response:
        return web.Response(status=500, text="boom")

    async def stalled_error(request: web.Request) -> web.StreamResponse:
        resp = web.StreamResponse(status=500)
        resp.content_length = 10
        await resp.prepare(request)
        await release.wait()
        return resp

    app = web.Application()
    app.router.add_get("/slow", slow)
    app.router.add_get("/stalled", stalled)
    app.router.add_get("/stalled-gzip", stalled_gzip)
    app.router.add_get("/file", file)
    app.router.add_get("/missing", missing)
    app.router.add_get("/broken", broken)
    app.router.add_get("/stalled-error", stalled_error)
    runner = web.AppRunner(app)
    await runner.setup()
    sock = socket.create_server(("localhost", 0))
    await web.SockSite(runner, sock).start()
    yield f"http://localhost:{sock.getsockname()[1]}"
    release.set()
    await runner.cleanup()


@pytest.mark.asyncio
async def test_timeout_names_the_request(slow_server: str) -> None:
    async with AsyncHTTPClient(slow_server, timeout=ClientTimeout(total=0.2)) as session:
        with pytest.raises(
            CblTimeoutError,
            match=r"^GET http://localhost:\d+/slow\?x=1 timed out after \d+\.\ds waiting for the response \(total 0\.2s\)$",
        ):
            await session.get("/slow", params={"x": "1"})


@pytest.mark.asyncio
async def test_timeout_names_the_per_request_budget(slow_server: str) -> None:
    async with AsyncHTTPClient(slow_server) as session:
        with pytest.raises(TimeoutError, match=r"\(total 0\.2s\)$"):
            await session.get("/slow", timeout=ClientTimeout(total=0.2))


@pytest.mark.asyncio
async def test_timeout_names_a_numeric_per_request_budget(slow_server: str) -> None:
    async with AsyncHTTPClient(slow_server) as session:
        with pytest.raises(TimeoutError, match=r"\(total 0\.2s\)$"):
            await session.get("/slow", timeout=0.2)  # ty: ignore[invalid-argument-type]


class _HangingResolver(AbstractResolver):
    """Never resolves, so a total timeout fires while connecting."""

    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[ResolveResult]:
        await asyncio.sleep(5)
        return []

    async def close(self) -> None:
        pass


@pytest.mark.asyncio
async def test_timeout_while_connecting_names_the_request() -> None:
    async with AsyncHTTPClient(
        connector=TCPConnector(resolver=_HangingResolver()), timeout=ClientTimeout(total=0.2)
    ) as session:
        with pytest.raises(
            CblTimeoutError,
            match=r"^GET http://sgw\.example\.com:4985/_all_dbs timed out after \d+\.\ds waiting for the response",
        ):
            await session.get("http://sgw.example.com:4985/_all_dbs")


@pytest.mark.asyncio
async def test_timeout_while_reading_the_body_names_the_request(slow_server: str) -> None:
    async with AsyncHTTPClient(slow_server, timeout=ClientTimeout(total=0.2)) as session:
        resp = await session.get("/stalled")
        with pytest.raises(
            CblTimeoutError,
            match=r"^GET http://localhost:\d+/stalled timed out after \d+\.\ds reading the body, "
            r"received 3 B of 10 B \(30%\) \(total 0\.2s\)$",
        ):
            await resp.text()


@pytest.mark.asyncio
async def test_body_progress_counts_compressed_bytes(slow_server: str) -> None:
    async with AsyncHTTPClient(slow_server, timeout=ClientTimeout(total=0.2)) as session:
        resp = await session.get("/stalled-gzip")
        with pytest.raises(CblTimeoutError, match=r"received 16\.0 KiB of \d+\.\d KiB \(\d{2}%\)"):
            await resp.read()


@pytest.mark.asyncio
async def test_stream_download_writes_the_body(slow_server: str, tmp_path: Path) -> None:
    destination = tmp_path / "nested" / "file.txt"
    async with AsyncHTTPClient(slow_server) as session:
        written = await session.stream_download("get", "/file", destination)

    assert written == 5
    assert destination.read_bytes() == b"hello"


@pytest.mark.asyncio
async def test_stream_download_raises_for_a_missing_file(slow_server: str, tmp_path: Path) -> None:
    destination = tmp_path / "file.txt"
    async with AsyncHTTPClient(slow_server) as session:
        with pytest.raises(FileNotFoundError, match=r"^GET http://localhost:\d+/missing returned 404$"):
            await session.stream_download("get", "/missing", destination)

    assert not destination.exists()


@pytest.mark.asyncio
async def test_stream_download_raises_for_an_error_status(slow_server: str, tmp_path: Path) -> None:
    async with AsyncHTTPClient(slow_server) as session:
        with pytest.raises(CblTestError, match=r"returned HTTP 500 - boom$"):
            await session.stream_download("get", "/broken", tmp_path / "file.txt")


@pytest.mark.asyncio
async def test_stream_download_timeout_reports_progress_and_removes_the_file(slow_server: str, tmp_path: Path) -> None:
    destination = tmp_path / "file.txt"
    async with AsyncHTTPClient(slow_server, timeout=ClientTimeout(total=0.2)) as session:
        with pytest.raises(
            CblTimeoutError,
            match=r"^GET http://localhost:\d+/stalled timed out after \d+\.\ds reading the body, "
            r"received 3 B of 10 B \(30%\) \(total 0\.2s\)$",
        ):
            await session.stream_download("get", "/stalled", destination)

    assert not destination.exists()


@pytest.mark.asyncio
async def test_stream_download_timeout_on_an_error_page(slow_server: str, tmp_path: Path) -> None:
    async with AsyncHTTPClient(slow_server, timeout=ClientTimeout(total=0.2)) as session:
        with pytest.raises(
            CblTimeoutError,
            match=r"^GET http://localhost:\d+/stalled-error timed out after \d+\.\ds reading the body",
        ):
            await session.stream_download("get", "/stalled-error", tmp_path / "file.txt")


@pytest.mark.asyncio
async def test_body_timeout_counts_from_the_request(slow_server: str) -> None:
    async with AsyncHTTPClient(slow_server, timeout=ClientTimeout(total=0.5)) as session:
        resp = await session.get("/stalled")
        await asyncio.sleep(0.3)
        with pytest.raises(CblTimeoutError, match=r"timed out after 0\.[5-9]s"):
            await resp.read()
