"""
The Caddy sidecar that serves files alongside Sync Gateway and Edge Server.

Every AWS-provisioned SGW and Edge Server host runs a Caddy file server on :data:`DEFAULT_PORT`,
which is how the framework retrieves whole files from the host -- ``sg_debug.log``, an
sgcollect archive, an Edge Server audit log -- without needing SSH.
"""

import re
from json import loads
from pathlib import Path
from types import TracebackType
from typing import Self

from aiohttp import ClientError, ClientTimeout
from opentelemetry.trace import get_tracer

from cbltest.api.error import CblTestError
from cbltest.httpclient import AsyncHTTPClient
from cbltest.logging import cbl_info
from cbltest.utils import is_sidecar_reachable
from cbltest.version import VERSION

_tracer = get_tracer(__name__, VERSION)

DEFAULT_PORT: int = 20000
"""The port the Caddy file server listens on."""

# Caddy serves whole files, whose size grows with the length of the run, so no total duration
# is both generous enough for a big one and tight enough to catch a wedged server.  The tight
# budget is sock_read, on the gap between chunks; the total is only a backstop against a server
# dribbling just fast enough to keep resetting it.  Immutable, so it is the session default.
_TIMEOUT = ClientTimeout(total=10 * 60, connect=30, sock_read=60)


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
        self.__session = AsyncHTTPClient(timeout=_TIMEOUT)

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
        url = self.url(filename)
        with _tracer.start_as_current_span(
            "caddy_request", attributes={"cbl.caddy.url": url, "cbl.caddy.operation": f"Download {filename}"}
        ):
            written = await self.__session.stream_download("get", url, destination)

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
        url = self.url()
        with _tracer.start_as_current_span(
            "caddy_request", attributes={"cbl.caddy.url": url, "cbl.caddy.operation": "List directory"}
        ):
            try:
                resp = await self.__session.get(url, headers={"Accept": "application/json"})
                async with resp:
                    if resp.status == 404:
                        raise CblTestError(
                            "Directory browsing endpoint not found. "
                            "Ensure Caddy is configured with 'file_server browse'"
                        )
                    if resp.status != 200:
                        raise CblTestError(
                            f"List directory failed at {url}: HTTP {resp.status} - {await resp.read_error_detail()}"
                        )
                    content = await resp.read()
            except ClientError as e:
                raise CblTestError(f"Network error listing {url}: {e}") from e

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
