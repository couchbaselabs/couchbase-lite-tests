"""
The HTTP sidecars that every AWS-provisioned host runs alongside the service it holds.

Couchbase Server, Sync Gateway and Edge Server hosts each run two of them, which is how the
framework does what the service's own REST API does not cover, without needing SSH:

* :class:`Caddy`, a file server on :data:`CADDY_PORT`, retrieves whole files from the host --
  ``sg_debug.log``, an sgcollect archive, an Edge Server audit log.
* :class:`Shell2Http`, a shell runner on :data:`SHELL2HTTP_PORT`, changes the host -- stopping
  a service, restarting it on another config, writing a certificate, adding a firewall rule.
"""

import re
from collections.abc import AsyncGenerator
from contextlib import AbstractContextManager, aclosing
from json import loads
from pathlib import Path
from types import TracebackType
from typing import ClassVar, Self

import aiofiles
import requests
from aiohttp import ClientError, ClientSession, ClientTimeout
from opentelemetry.trace import Span, get_tracer

from cbltest.api.error import CblHttpError, CblTestError, CblTimeoutError
from cbltest.api.jsonserializable import JSONSerializable
from cbltest.httplog import get_next_writer
from cbltest.logging import cbl_info
from cbltest.version import VERSION

_tracer = get_tracer(__name__, VERSION)

CADDY_PORT: int = 20000
"""The port the Caddy file server listens on."""

SHELL2HTTP_PORT: int = 20001
"""The port the shell2http runner listens on."""

# Caddy serves whole files, whose size grows with the length of the run, so no total duration
# is both generous enough for a big one and tight enough to catch a wedged server.  The tight
# budget is sock_read, on the gap between chunks; the total is only a backstop against a server
# dribbling just fast enough to keep resetting it.
_CADDY_TIMEOUT = ClientTimeout(total=10 * 60, connect=30, sock_read=60)

# Every shell2http endpoint runs a script that starts or stops a service and answers with a
# line or two, so the budget is on the whole call rather than on the body arriving.
_SHELL2HTTP_TIMEOUT = ClientTimeout(total=5 * 60, connect=30)

_CHUNK_SIZE = 64 * 1024


def _describe_transfer(received: int, expected: int | None) -> str:
    """
    Describes how much of a response body arrived, for error messages on a transfer that
    did not finish.

    :param received: Bytes actually read so far
    :param expected: Bytes the response promised via Content-Length, or None if it did not say
    :return: Something like "12.3 MiB of 40.0 MiB (31%)", or "12.3 MiB of unknown total"
    """

    def size(n: int) -> str:
        value = float(n)
        for unit in ("B", "KiB", "MiB", "GiB"):
            if value < 1024 or unit == "GiB":
                return f"{value:.1f} {unit}" if unit != "B" else f"{n} B"
            value /= 1024
        raise AssertionError("unreachable")

    if expected is None:
        return f"{size(received)} of unknown total"
    if expected == 0:
        return f"{size(received)} of 0 B"
    return f"{size(received)} of {size(expected)} ({received * 100 // expected}%)"


class _Sidecar:
    """
    One sidecar on one host, and the request plumbing every sidecar shares.

    Owns an aiohttp session, so close it or use it as an async context manager.
    """

    _NAME: ClassVar[str]
    """What this sidecar calls itself in the HTTP log and in spans."""

    _ERROR_BODY_LIMIT: ClassVar[int] = 4 * 1024
    """How much of a failed response goes in the error, for a body that is worth reading."""

    def __init__(self, hostname: str, port: int, timeout: ClientTimeout) -> None:
        self._hostname = hostname
        self._port = port
        # One session for every request, so connections are reused and the budgets above
        # apply in one place.
        self._session = ClientSession(f"http://{hostname}:{port}", timeout=timeout)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        """Closes the aiohttp session this sidecar requests on.  Safe to call more than once."""
        if not self._session.closed:
            await self._session.close()

    @property
    def closed(self) -> bool:
        """Whether this sidecar's session has been closed"""
        return self._session.closed

    def is_reachable(self, timeout: float = 1.0) -> bool:
        """
        Whether this host's sidecar is answering at all, on any status.  Synchronous, so a
        constructor can call it.

        :param timeout: Seconds to wait before deciding nothing is listening
        :return: True if the sidecar answered
        """
        try:
            requests.get(self._url("/"), timeout=timeout)
            return True
        except requests.RequestException:
            return False

    async def download(self, uri: str, local_path: str | Path) -> Path:
        """
        Downloads what a path serves to local disk, creating the parent directory if needed.
        Writes each chunk as it arrives, so a file larger than memory still transfers, and
        keeps the bytes as they are, so it suits archives as well as text.

        :param uri: Path on this sidecar, from its root (e.g. '/sgcollectinfo-xxx-redacted.zip')
        :param local_path: Local path to write the file to
        :return: The local path the file was written to
        :raises CblTimeoutError: If the transfer stops making progress
        :raises CblHttpError: If the sidecar answers with a status this call cannot use,
            404 among them, which a caller reads as a missing file where that is what it means
        :raises CblTestError: If the host cannot be reached
        """
        destination = Path(local_path)
        written = 0
        operation = f"Download {uri}"
        with self._span(uri, operation):
            async with aclosing(self._stream("get", uri, operation)) as stream:
                # The first chunk comes before the file is opened, so a request that fails
                # outright never creates the file at all.
                first = await anext(stream, b"")
                destination.parent.mkdir(parents=True, exist_ok=True)
                try:
                    async with aiofiles.open(destination, "wb") as f:
                        await f.write(first)
                        written += len(first)
                        async for chunk in stream:
                            await f.write(chunk)
                            written += len(chunk)
                except BaseException:
                    # A file left half written is worse than none, since a caller cannot tell
                    # that it is incomplete.
                    destination.unlink(missing_ok=True)
                    raise

        cbl_info(f"Successfully downloaded {uri} to {destination} ({written} bytes)")
        return destination

    def _url(self, path: str) -> str:
        """The full URL a path names on this sidecar, for messages and spans."""
        return f"http://{self._hostname}:{self._port}{path}"

    def _span(self, path: str, operation: str) -> AbstractContextManager[Span]:
        """The span one call runs in, for a caller to hold open across it."""
        return _tracer.start_as_current_span(
            f"{self._NAME}_request",
            attributes={f"cbl.{self._NAME}.url": self._url(path), f"cbl.{self._NAME}.operation": operation},
        )

    async def _send_request(
        self,
        method: str,
        path: str,
        operation: str,
        data: str | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> str:
        """
        Calls one endpoint, reads the whole response into memory, and records the exchange in
        the HTTP log.  Only for a body known to be small, such as a line of script output or a
        directory listing; anything file-sized belongs in :meth:`_stream`.

        :param method: HTTP method the endpoint answers on
        :param path: Path to request, including any query string
        :param operation: What the call is doing, used in the log and in error messages
        :param data: Request body, for the endpoints that take one
        :param headers: Request headers, if the endpoint needs any
        :param timeout: Total timeout in seconds, if the session default is too generous
        :return: The response body, decoded as UTF-8
        :raises CblTimeoutError: If the sidecar does not answer in time
        :raises CblHttpError: If the sidecar answers with a status this call cannot use
        :raises CblTestError: If the host cannot be reached
        """
        writer = get_next_writer()
        writer.write_begin(f"{self._NAME} [{self._hostname}] -> {operation}", data or "")
        with self._span(path, operation):
            try:
                chunks = [chunk async for chunk in self._stream(method, path, operation, data, headers, timeout)]
            except (CblTestError, CblTimeoutError) as e:
                writer.write_error(str(e))
                raise

        text = b"".join(chunks).decode("utf-8", errors="replace")
        writer.write_end(f"{self._NAME} [{self._hostname}] <- {operation}", text)
        return text

    async def _stream(
        self,
        method: str,
        path: str,
        operation: str,
        data: str | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> AsyncGenerator[bytes]:
        """
        Yields the response body in chunks, so a caller never needs the whole of it at once.
        Yields nothing but the body of a response this sidecar can use, since any other status
        raises.  The caller owns the span, since a generator suspends between chunks.  Takes
        what :meth:`_send_request` takes.

        :return: The response body, chunk by chunk
        :raises CblTimeoutError: If the transfer stalls, or exceeds the total budget
        :raises CblHttpError: If the sidecar answers with a status this call cannot use
        :raises CblTestError: If the host cannot be reached
        """
        # aiohttp falls back to the session default only when the argument is absent, so an
        # override restates the other budgets rather than dropping them.
        session_budget = self._session.timeout
        budget = (
            session_budget
            if timeout is None
            else ClientTimeout(total=timeout, connect=session_budget.connect, sock_read=session_budget.sock_read)
        )
        # Tracked across the whole transfer so a failure can report how far it got.
        received = 0
        expected: int | None = None
        try:
            async with self._session.request(method, path, data=data, headers=headers, timeout=budget) as response:
                if not response.ok:
                    # A body can be arbitrarily large, and it goes in the message, so keep
                    # only as much as this sidecar's failures are worth, as bytes if it is
                    # not text.
                    body = await response.content.read(self._ERROR_BODY_LIMIT)
                    received += len(body)
                    try:
                        detail = body.decode("utf-8")
                    except UnicodeDecodeError:
                        detail = f"binary body of {len(body)} bytes, starting {body[:200]!r}"

                    raise CblHttpError(
                        response.status,
                        f"{operation} failed on {self._hostname}: {response.status} - {detail}",
                        body=detail,
                    )

                expected = response.content_length
                async for chunk in response.content.iter_chunked(_CHUNK_SIZE):
                    received += len(chunk)
                    yield chunk

        # One clause for both, since aiohttp's timeouts subclass ClientError, and either way
        # the message says how far the transfer got.  Nothing to say of a call that read no bytes.
        except (TimeoutError, ClientError) as e:
            progress = f", having received {_describe_transfer(received, expected)}" if received or expected else ""
            if isinstance(e, TimeoutError):
                # The budgets besides the total that could have expired, where this session sets them.
                named = (("connect", budget.connect), ("read-chunk", budget.sock_read))
                budgets = ", ".join(f"{name} {seconds}s" for name, seconds in named if seconds)
                # A total timeout stringifies to "", so its own text is appended only if it has any.
                detail = f": {e}" if str(e) else ""
                raise CblTimeoutError(
                    f"{operation} timed out on {self._hostname} after {budget.total}s{progress}"
                    f"{f' (with {budgets})' if budgets else ''}{detail}"
                ) from e

            if progress:
                raise CblTestError(f"{operation} failed mid-transfer on {self._hostname}{progress}: {e}") from e

            raise CblTestError(f"{operation} failed to reach {self._hostname}: {e}") from e


class Caddy(_Sidecar):
    """
    The Caddy file server on one Couchbase Server, Sync Gateway or Edge Server host.
    """

    _NAME = "caddy"

    def __init__(self, hostname: str, port: int = CADDY_PORT) -> None:
        """
        Creates the aiohttp session, so it needs a running event loop.

        :param hostname: Host running the Caddy file server
        :param port: Port it listens on, if not :data:`CADDY_PORT`
        """
        super().__init__(hostname, port, _CADDY_TIMEOUT)

    async def list(self, pattern: str | None = None) -> list[str]:
        """
        Lists the files Caddy is serving, omitting directories.  Requires ``file_server
        browse`` in the Caddyfile.

        :param pattern: Optional regex to filter filenames by (e.g. 'sgcollect_info.*redacted.zip')
        :return: The matching filenames
        :raises CblTestError: If directory browsing is not enabled, or the listing cannot be parsed
        :raises CblTimeoutError: If the transfer stops making progress
        """
        try:
            content = await self._send_request("get", "/", "List directory", headers={"Accept": "application/json"})
        except CblHttpError as e:
            if e.code != 404:
                raise
            raise CblTestError(
                "Directory browsing endpoint not found. Ensure Caddy is configured with 'file_server browse'"
            ) from e

        try:
            listing = loads(content)
        except ValueError as e:
            raise CblTestError(f"Failed to parse Caddy JSON response: {e}") from e

        files = [
            entry["name"]
            for entry in listing
            if isinstance(entry, dict) and "name" in entry and not entry.get("is_dir", False)
        ]
        if pattern:
            files = [f for f in files if re.search(pattern, f)]

        cbl_info(f"Found {len(files)} files via Caddy browse" + (f" matching '{pattern}'" if pattern else ""))
        return files


class Shell2Http(_Sidecar):
    """
    The shell2http runner on one Couchbase Server, Sync Gateway or Edge Server host.
    """

    _NAME = "shell2http"

    # A failing script prints what went wrong, and one that cats a log prints the log, so the
    # budget is set to hold a real one rather than the first few lines of it.
    _ERROR_BODY_LIMIT = 64 * 1024

    def __init__(self, hostname: str, port: int = SHELL2HTTP_PORT) -> None:
        """
        Creates the aiohttp session, so it needs a running event loop.

        :param hostname: Host running the shell2http sidecar
        :param port: Port it listens on, if not :data:`SHELL2HTTP_PORT`
        """
        super().__init__(hostname, port, _SHELL2HTTP_TIMEOUT)

    async def get(self, endpoint: str, timeout: float | None = None) -> str:
        """
        Calls an endpoint that takes no body.

        :param endpoint: Endpoint path, including any query string (e.g. '/start-sgw?config=x')
        :param timeout: Total timeout in seconds, if the session default is too generous
        :return: What the script printed
        """
        return await self._send_request("get", endpoint, f"GET {endpoint}", timeout=timeout)

    async def post(
        self, endpoint: str, data: str | JSONSerializable | None = None, timeout: float | None = None
    ) -> str:
        """
        Calls an endpoint, handing the script a body on its standard input.

        :param endpoint: Endpoint path, including any query string
        :param data: Request body: text as it is, a JSON object serialized
        :param timeout: Total timeout in seconds, if the session default is too generous
        :return: What the script printed
        """
        if data is None:
            body, headers = None, None
        elif isinstance(data, JSONSerializable):
            body, headers = data.serialize(), {"Content-Type": "application/json"}
        else:
            body, headers = data, {"Content-Type": "text/plain"}

        return await self._send_request("post", endpoint, f"POST {endpoint}", body, headers, timeout)
