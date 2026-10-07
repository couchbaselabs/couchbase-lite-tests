"""
Calls to the shell2http sidecar that runs management scripts on Couchbase Server, Sync
Gateway and Edge Server hosts.
"""

from aiohttp import ClientTimeout
from aiohttp.client import DEFAULT_TIMEOUT
from yarl import URL

from cbltest.api.error import CblRemoteBadResponseError
from cbltest.httpclient import AsyncHTTPClient
from cbltest.httplog import get_next_writer
from cbltest.logging import cbl_error
from cbltest.utils import SHELL2HTTP_PORT

# Header in which shell2http reports the script's exit code, -1 if a signal killed it.
_EXIT_CODE_HEADER = "X-Shell2http-Exit-Code"

# Total HTTP timeout in seconds for a call that names none, aiohttp's default.
DEFAULT_SHELL2HTTP_TIMEOUT: float = 300


def shell2http_timeout(path: str, timeout: float) -> tuple[str, ClientTimeout]:
    """
    The path and HTTP timeouts for a shell2http call that gets `timeout` seconds in total.
    The host kills the script at 95% of that, so a script that runs too long still returns
    its output, as a 500.

    :param path: Sidecar path, which may already carry a query string
    :param timeout: Total HTTP timeout in seconds
    :return: The path with the host's timeout added, and the timeouts to send the request with
    """
    budgets = ClientTimeout(total=timeout, sock_connect=DEFAULT_TIMEOUT.sock_connect)
    return str(URL(path).update_query(timeout=f"{timeout * 0.95:g}")), budgets


class Shell2HttpClient:
    """
    A session on the shell2http sidecar of one host.  Each call is recorded in the HTTP log,
    and any failure is logged, so the script's output survives even when a caller catches
    the error.  Owns the session, so close it.
    """

    def __init__(
        self,
        role: str,
        hostname: str,
        port: int = SHELL2HTTP_PORT,
        error: type[CblRemoteBadResponseError] = CblRemoteBadResponseError,
    ) -> None:
        """
        :param role: What the host runs, for the logs, e.g. "Sync Gateway"
        :param hostname: The host the sidecar runs on
        :param port: The port the sidecar listens on
        :param error: What to raise when a script fails
        """
        self.__label = f"{role} sidecar [{hostname}]"
        self.__error = error
        self.__session = AsyncHTTPClient(f"http://{hostname}:{port}")

    def __str__(self) -> str:
        return self.__label

    @property
    def closed(self) -> bool:
        """Whether the session is closed"""
        return self.__session.closed

    async def close(self) -> None:
        """Closes the session.  Safe to call more than once."""
        await self.__session.close()

    async def call(
        self,
        method: str,
        path: str,
        *,
        data: str | None = None,
        content_type: str | None = None,
        timeout: float = DEFAULT_SHELL2HTTP_TIMEOUT,
    ) -> str:
        """
        Call a sidecar endpoint, raising unless the script succeeded.  shell2http answers 200
        for a script that a signal killed, so the exit code decides, not only the status.

        :param method: HTTP method to use
        :param path: Sidecar path, which may already carry a query string
        :param data: Request body, for the endpoints that take one
        :param content_type: Content-Type of `data`
        :param timeout: Total HTTP timeout in seconds, see :func:`shell2http_timeout`
        :return: The script's output
        """
        headers = {"Content-Type": content_type} if content_type is not None else None
        path, budgets = shell2http_timeout(path, timeout)
        request = f"{method.upper()} {path}"
        writer = get_next_writer()
        writer.write_begin(f"{self} -> {request}", data or "")
        with writer.record_failure(f"{self} <- {request}"):
            async with await self.__session.request(method, path, data=data, headers=headers, timeout=budgets) as resp:
                # A sidecar echoes raw files back, so one odd byte must not fail the whole call.
                body = await resp.text(errors="replace")
                exit_code = resp.headers.get(_EXIT_CODE_HEADER)

        # No exit code means no script ran, e.g. for a path the sidecar does not serve.
        outcome = f"{resp.status} (exit code {exit_code})"
        writer.write_end(f"{self} <- {request} {outcome}", body)
        if not resp.ok or exit_code != "0":
            cbl_error(f"{self}: {request} returned {outcome}:\n{body}", include_stack=False)
            raise self.__error(resp.status, f"{self}: {request} returned {outcome}", body=body)

        return body
