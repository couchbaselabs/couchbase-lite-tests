import asyncio
import logging
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestServer
from cbltest.api.error import CblEdgeServerBadResponseError, CblRemoteBadResponseError, CblTimeoutError
from cbltest.httplog import _HttpLogWriter
from cbltest.shell2http import Shell2HttpClient, shell2http_timeout

HOST = "Test sidecar [127.0.0.1]"

# A client on the stand-in sidecar, the HTTP log directory it writes to, and the sidecar's port.
Sidecar = tuple[Shell2HttpClient, Path, int]


def script_response(exit_code: int, text: str, status: int = 200) -> web.Response:
    """A response as shell2http sends it, with the script's exit code in a header."""
    return web.Response(status=status, text=text, headers={"X-Shell2http-Exit-Code": str(exit_code)})


@pytest_asyncio.fixture(loop_scope="function")
async def sidecar(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AsyncIterator[Sidecar]:
    """
    A stand-in sidecar: /ok echoes the query string, /fail answers 500 as a timed-out script
    does, /killed answers 200 as a script a signal killed does, and /hang never answers.
    """
    monkeypatch.setattr(_HttpLogWriter, "_HttpLogWriter__record_path", tmp_path / "http_log")

    async def ok(request: web.Request) -> web.Response:
        return script_response(0, f"ran with [{request.query_string}]")

    async def fail(request: web.Request) -> web.Response:
        return script_response(124, "script output\nscript.sh timed out after 0.9s", status=500)

    async def killed(request: web.Request) -> web.Response:
        return script_response(-1, "script output\n\nexec error: signal: killed")

    async def hang(request: web.Request) -> web.Response:
        await asyncio.sleep(10)
        return script_response(0, "too late")

    app = web.Application()
    app.router.add_post("/ok", ok)
    app.router.add_get("/fail", fail)
    app.router.add_get("/killed", killed)
    app.router.add_get("/hang", hang)
    server = TestServer(app)
    await server.start_server()

    assert server.port is not None
    client = Shell2HttpClient("Test", server.host, server.port)
    yield client, tmp_path / "http_log", server.port

    await client.close()
    await server.close()


def logged(http_log: Path) -> dict[str, str]:
    """Every HTTP log file, keyed by its suffix: begin, end or error."""
    return {f.stem.rsplit("_", 1)[1]: f.read_text() for f in http_log.rglob("*.txt")}


@pytest.mark.parametrize(
    ("path", "timeout", "expected_path"),
    [
        ("/stop-sgw", 60, "/stop-sgw?timeout=57"),
        ("/start-sgw?config=bootstrap", 120, "/start-sgw?config=bootstrap&timeout=114"),
        ("/start-edgeserver", 0.6, "/start-edgeserver?timeout=0.57"),
    ],
)
def test_shell2http_timeout_gives_the_host_95_percent(path: str, timeout: float, expected_path: str) -> None:
    sent_path, budgets = shell2http_timeout(path, timeout)

    assert sent_path == expected_path
    assert budgets.total == timeout


@pytest.mark.asyncio
async def test_success_logs_the_request_and_the_host_timeout(sidecar: Sidecar) -> None:
    client, http_log, _ = sidecar

    body = await client.call("post", "/ok", data="payload", timeout=60)

    assert body == "ran with [timeout=57]"
    files = logged(http_log)
    assert files["begin"] == f"{HOST} -> POST /ok?timeout=57\n\npayload"
    assert files["end"] == f"{HOST} <- POST /ok?timeout=57 200 (exit code 0)\n\nran with [timeout=57]"


@pytest.mark.asyncio
async def test_no_timeout_sends_95_percent_of_the_default_to_the_host(sidecar: Sidecar) -> None:
    client, http_log, _ = sidecar

    assert await client.call("post", "/ok") == "ran with [timeout=285]"
    assert logged(http_log)["begin"] == f"{HOST} -> POST /ok?timeout=285\n\n"


@pytest.mark.asyncio
async def test_failure_logs_the_script_output_and_raises(sidecar: Sidecar, caplog: pytest.LogCaptureFixture) -> None:
    client, http_log, _ = sidecar

    with caplog.at_level(logging.WARNING, logger="CBL"), pytest.raises(CblRemoteBadResponseError) as e:
        await client.call("get", "/fail", timeout=10)

    assert e.value.code == 500
    assert str(e.value) == f"{HOST}: GET /fail?timeout=9.5 returned 500 (exit code 124)"
    assert "timed out after 0.9s" in e.value.body
    assert "timed out after 0.9s" in logged(http_log)["end"]
    assert [r.getMessage() for r in caplog.records] == [f"{e.value!s}:\n{e.value.body}"]


@pytest.mark.asyncio
async def test_signal_death_fails_despite_a_200(sidecar: Sidecar) -> None:
    client, _, _ = sidecar

    with pytest.raises(CblRemoteBadResponseError, match=r"returned 200 \(exit code -1\)$"):
        await client.call("get", "/killed")


@pytest.mark.asyncio
async def test_unknown_path_fails(sidecar: Sidecar) -> None:
    client, _, _ = sidecar

    with pytest.raises(CblRemoteBadResponseError, match=r"returned 404 \(exit code None\)$"):
        await client.call("get", "/missing")


@pytest.mark.asyncio
async def test_failure_raises_the_error_type_given(sidecar: Sidecar) -> None:
    _, _, port = sidecar
    client = Shell2HttpClient("Test", "127.0.0.1", port, error=CblEdgeServerBadResponseError)

    try:
        with pytest.raises(CblEdgeServerBadResponseError):
            await client.call("get", "/fail")
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_client_timeout_logs_an_error_and_raises(sidecar: Sidecar, caplog: pytest.LogCaptureFixture) -> None:
    client, http_log, _ = sidecar

    with caplog.at_level(logging.WARNING, logger="CBL"), pytest.raises(CblTimeoutError):
        await client.call("get", "/hang", timeout=0.2)

    files = logged(http_log)
    assert "end" not in files
    assert files["error"].startswith(f"{HOST} <- GET /hang?timeout=0.19 failed: ")
    assert caplog.records[0].getMessage() == files["error"]
    assert files["error"].endswith("(total 0.2s, sock_connect 30s)")
