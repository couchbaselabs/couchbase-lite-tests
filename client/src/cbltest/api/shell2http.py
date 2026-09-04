"""
The shell2http sidecar that runs shell scripts on a host alongside the service it manages.

Every AWS-provisioned Couchbase Server, Sync Gateway and Edge Server host runs shell2http on
:data:`DEFAULT_PORT`, which is how the framework does the things no REST API covers -- stopping
a service, restarting it on another config, writing a certificate, adding a firewall rule --
without needing SSH.
"""

from types import TracebackType
from typing import Self

from aiohttp import ClientError, ClientSession, ClientTimeout
from opentelemetry.trace import get_tracer

from cbltest.api.error import CblTestError, CblTimeoutError
from cbltest.api.jsonserializable import JSONSerializable
from cbltest.httplog import get_next_writer
from cbltest.utils import is_sidecar_reachable
from cbltest.version import VERSION

_tracer = get_tracer(__name__, VERSION)

DEFAULT_PORT: int = 20001
"""The port the shell2http sidecar listens on."""

# Every endpoint runs a script that starts or stops a service and answers with a line or two,
# so the budget is on the whole call rather than on the body arriving.
_TIMEOUT = ClientTimeout(total=5 * 60, connect=30)


class Shell2Http:
    """
    The shell2http sidecar on one Couchbase Server, Sync Gateway or Edge Server host.

    Owns an aiohttp session, so close it or use it as an async context manager.
    """

    def __init__(self, hostname: str, port: int = DEFAULT_PORT) -> None:
        """
        Creates the aiohttp session, so it needs a running event loop.

        :param hostname: Host running the shell2http sidecar
        :param port: Port it listens on, if not :data:`DEFAULT_PORT`
        """
        self.__hostname = hostname
        self.__port = port
        self.__session = ClientSession(f"http://{hostname}:{port}", timeout=_TIMEOUT)

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
        """Closes the aiohttp session this sidecar calls on.  Safe to call more than once."""
        if not self.__session.closed:
            await self.__session.close()

    @property
    def closed(self) -> bool:
        """Whether this sidecar's session has been closed"""
        return self.__session.closed

    def is_reachable(self, timeout: float = 1.0) -> bool:
        """
        Whether this host's shell2http is answering at all.  Synchronous, so a constructor
        can call it.

        :param timeout: Seconds to wait before deciding nothing is listening
        :return: True if shell2http answered
        """
        return is_sidecar_reachable(self.__hostname, self.__port, timeout)

    async def get(self, endpoint: str, timeout: float | None = None) -> str:
        """
        Calls an endpoint that takes no body.

        :param endpoint: Endpoint path, including any query string (e.g. '/start-sgw?config=x')
        :param timeout: Total timeout in seconds, if the session default is too generous
        :return: What the script printed
        """
        return await self._send_request("get", endpoint, timeout=timeout)

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
        return await self._send_request("post", endpoint, data, timeout)

    async def _send_request(
        self,
        method: str,
        endpoint: str,
        data: str | JSONSerializable | None = None,
        timeout: float | None = None,
    ) -> str:
        """
        Calls one endpoint and records the exchange in the HTTP log.

        :param method: HTTP method the endpoint answers on
        :param endpoint: Endpoint path, including any query string
        :param data: Request body, for the endpoints that take one
        :param timeout: Total timeout in seconds, if the session default is too generous
        :return: What the script printed
        :raises CblTimeoutError: If the script does not answer in time
        :raises CblTestError: If the script fails, or the host cannot be reached
        """
        if data is None:
            body, headers = None, None
        elif isinstance(data, JSONSerializable):
            body, headers = data.serialize(), {"Content-Type": "application/json"}
        else:
            body, headers = data, {"Content-Type": "text/plain"}

        # aiohttp falls back to the session default only when the argument is absent, so an
        # override restates the connect budget rather than dropping it.
        budget = _TIMEOUT if timeout is None else ClientTimeout(total=timeout, connect=_TIMEOUT.connect)
        label = f"{method.upper()} {endpoint}"
        writer = get_next_writer()
        writer.write_begin(f"shell2http [{self.__hostname}] -> {label}", body or "")
        with _tracer.start_as_current_span(
            "shell2http_request",
            attributes={
                "cbl.shell2http.url": f"http://{self.__hostname}:{self.__port}{endpoint}",
                "cbl.shell2http.method": method,
            },
        ):
            try:
                async with self.__session.request(
                    method,
                    endpoint,
                    data=body,
                    headers=headers,
                    timeout=budget,
                ) as response:
                    text = await response.text()
                    status = response.status
                    ok = response.ok

            # Must precede ClientError, which aiohttp's timeouts subclass, or it never runs.
            # A total timeout stringifies to "", so its own text is appended only if it has any.
            except TimeoutError as e:
                detail = f": {e}" if str(e) else ""
                message = f"{label} timed out on {self.__hostname} after {budget.total}s{detail}"
                writer.write_error(message)
                raise CblTimeoutError(message) from e
            except ClientError as e:
                message = f"{label} failed to reach {self.__hostname}: {e}"
                writer.write_error(message)
                raise CblTestError(message) from e

        writer.write_end(f"shell2http [{self.__hostname}] <- {label} {status}", text)
        if not ok:
            raise CblTestError(f"{label} failed on {self.__hostname}: {status} - {text}")
        return text
