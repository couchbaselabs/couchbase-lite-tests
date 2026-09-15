"""
The Caddy sidecar that serves files alongside Sync Gateway and Edge Server.

Every AWS-provisioned SGW and Edge Server host runs a Caddy file server on :data:`DEFAULT_PORT`,
which is how the framework retrieves whole files from the host -- ``sg_debug.log``, an
sgcollect archive, an Edge Server audit log -- without needing SSH.
"""

import re
from collections.abc import AsyncGenerator
from contextlib import aclosing
from json import loads
from pathlib import Path
from types import TracebackType
from typing import Self

import aiofiles
from aiohttp import ClientError, ClientSession, ClientTimeout
from opentelemetry.trace import get_tracer

from cbltest.api.error import CblTestError, CblTimeoutError
from cbltest.logging import cbl_info
from cbltest.utils import describe_transfer, is_sidecar_reachable
from cbltest.version import VERSION

_tracer = get_tracer(__name__, VERSION)

DEFAULT_PORT: int = 20000
"""The port the Caddy file server listens on."""

# Caddy serves whole files, whose size grows with the length of the run, so no total duration
# is both generous enough for a big one and tight enough to catch a wedged server.  The tight
# budget is sock_read, on the gap between chunks; the total is only a backstop against a server
# dribbling just fast enough to keep resetting it.  Immutable, so it is the session default.
_TIMEOUT = ClientTimeout(total=10 * 60, connect=30, sock_read=60)

_CHUNK_SIZE = 64 * 1024


class Caddy:
    """
    The Caddy file server on one Sync Gateway or Edge Server host.

    Owns an aiohttp session, so close it or use it as an async context manager.
    """

    def __init__(self, hostname: str, port: int = DEFAULT_PORT) -> None:
        """
        Creates the aiohttp session, so it needs a running event loop.

        :param hostname: Host running the Caddy file server
        :param port: Port it listens on, if not :data:`DEFAULT_PORT`
        """
        self.__hostname = hostname
        self.__port = port
        # One aiohttp session for every request, so connections are reused and the timeouts
        # above apply in one place.
        self.__session = ClientSession(timeout=_TIMEOUT)

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
        """Closes the aiohttp session this Caddy requests on.  Safe to call more than once."""
        if not self.__session.closed:
            await self.__session.close()

    @property
    def hostname(self) -> str:
        """Gets the host whose Caddy this is"""
        return self.__hostname

    @property
    def port(self) -> int:
        """Gets the port this Caddy is served on"""
        return self.__port

    def url(self, filename: str = "") -> str:
        """
        Builds the URL Caddy serves a file at.

        :param filename: Path relative to Caddy's root; empty for the directory itself
        :return: The full URL
        """
        return f"http://{self.__hostname}:{self.__port}/{filename}"

    def is_reachable(self, timeout: float = 1.0) -> bool:
        """
        Whether this host's Caddy is answering at all.  Synchronous, so a constructor can call it.

        :param timeout: Seconds to wait before deciding nothing is listening
        :return: True if Caddy answered
        """
        return is_sidecar_reachable(self.__hostname, self.__port, timeout)

    async def download(self, filename: str, local_path: str | Path) -> Path:
        """
        Downloads a file to local disk, creating the parent directory if needed.  Writes each
        chunk as it arrives, so a file larger than memory still transfers, and keeps the bytes
        as they are, so it suits archives as well as text.

        :param filename: Path relative to Caddy's root (e.g. 'sgcollectinfo-xxx-redacted.zip')
        :param local_path: Local path to write the file to
        :return: The local path the file was written to
        :raises FileNotFoundError: If the file doesn't exist
        :raises CblTimeoutError: If the transfer stops making progress
        :raises CblTestError: For other HTTP or network errors
        """
        destination = Path(local_path)
        written = 0
        url = self.url(filename)
        operation = f"Download {filename}"
        with _tracer.start_as_current_span(
            "caddy_request", attributes={"cbl.caddy.url": url, "cbl.caddy.operation": operation}
        ):
            async with aclosing(self._stream(url, operation)) as stream:
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

        cbl_info(f"Successfully downloaded {filename} to {destination} ({written} bytes)")
        return destination

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
            content = await self._request(self.url(), "List directory", headers={"Accept": "application/json"})
        except FileNotFoundError as e:
            raise CblTestError(
                "Directory browsing endpoint not found. Ensure Caddy is configured with 'file_server browse'"
            ) from e

        try:
            listing = loads(content.decode("utf-8"))
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

    async def _request(self, url: str, operation: str, headers: dict[str, str] | None = None) -> bytes:
        """
        Fetches one whole response into memory.  Only for bodies known to be small, such as a
        directory listing; anything file-sized belongs in :meth:`_stream`.

        :param url: Full Caddy URL to request
        :param operation: Description of the operation, used in error messages
        :param headers: Optional HTTP headers to include in the request
        :return: The response body
        :raises FileNotFoundError: If the resource returns 404
        :raises CblTimeoutError: If the transfer stalls, or exceeds the total budget
        :raises CblTestError: For other HTTP or network errors
        """
        with _tracer.start_as_current_span(
            "caddy_request", attributes={"cbl.caddy.url": url, "cbl.caddy.operation": operation}
        ):
            chunks = [chunk async for chunk in self._stream(url, operation, headers)]

        return b"".join(chunks)

    async def _stream(self, url: str, operation: str, headers: dict[str, str] | None = None) -> AsyncGenerator[bytes]:
        """
        Yields the response body in chunks, so a caller never needs the whole file at once.
        Yields nothing but a 200's body, since any other status raises.  The caller owns the
        span, since a generator suspends between chunks.

        :param url: Full Caddy URL to request
        :param operation: Description of the operation, used in error messages
        :param headers: Optional HTTP headers to include in the request
        :return: The response body, chunk by chunk
        :raises FileNotFoundError: If the resource returns 404
        :raises CblTimeoutError: If the transfer stalls, or exceeds the total budget
        :raises CblTestError: For other HTTP or network errors
        """
        # Tracked across the whole transfer so a failure can report how far it got.
        received = 0
        expected: int | None = None
        try:
            async with self.__session.get(url, headers=headers) as response:
                if response.status == 404:
                    raise FileNotFoundError(f"{operation} not found at {url}")
                if response.status != 200:
                    # An error page can be arbitrarily large, and its body goes in the
                    # message, so keep only the head of it, as bytes if it is not text.
                    body = await response.content.read(4 * 1024)
                    received += len(body)
                    try:
                        detail = body.decode("utf-8")
                    except UnicodeDecodeError:
                        detail = f"binary body of {len(body)} bytes, starting {body[:200]!r}"

                    raise CblTestError(f"{operation} failed: HTTP {response.status} - {detail}")

                expected = response.content_length
                async for chunk in response.content.iter_chunked(_CHUNK_SIZE):
                    received += len(chunk)
                    yield chunk

        # Must precede ClientError, which aiohttp's timeouts subclass, or it never runs.  A
        # total timeout raises a bare TimeoutError that stringifies to "", so lead with the
        # URL, the progress and the budgets, and append its own text only if it has any.
        except TimeoutError as e:
            detail = f": {e}" if str(e) else ""
            # The aiohttp session's own budgets, so the message stays true to what expired.
            budgets = self.__session.timeout
            raise CblTimeoutError(
                f"{operation} timed out at {url} after receiving {describe_transfer(received, expected)} "
                f"(connect {budgets.connect}s, read-chunk {budgets.sock_read}s, total {budgets.total}s){detail}"
            ) from e
        except ClientError as e:
            raise CblTestError(
                f"Network error during {operation} at {url} after receiving "
                f"{describe_transfer(received, expected)}: {e}"
            ) from e
