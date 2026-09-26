"""Shared aiohttp client setup."""

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Any, Self, Unpack, cast

import aiofiles
from aiohttp import BaseConnector, ClientError, ClientResponse, ClientSession, ClientTimeout
from aiohttp.client import DEFAULT_TIMEOUT
from aiohttp.typedefs import LooseHeaders, Query, StrOrURL
from yarl import URL

from cbltest.api.error import CblTestError, CblTimeoutError

if TYPE_CHECKING:
    # Private to aiohttp, so import it only for type checking, where a rename cannot break imports.
    from aiohttp.client import _RequestOptions

_CHUNK_SIZE = 64 * 1024


class AsyncHTTPClient:
    """
    An aiohttp session whose timeouts name the request that timed out, how far it got and
    the budgets that applied.  Owns the session, so close it or use it as an async context manager.
    """

    def __init__(
        self,
        base_url: StrOrURL | None = None,
        *,
        headers: LooseHeaders | None = None,
        connector: BaseConnector | None = None,
        timeout: ClientTimeout = DEFAULT_TIMEOUT,
    ) -> None:
        """
        Creates the aiohttp session, so it needs a running event loop.

        :param base_url: Base URL that relative request paths resolve against
        :param headers: Headers to send with every request
        :param connector: Connector to use, for example one with an SSL context
        :param timeout: Default timeouts for every request
        """
        self.__base_url = URL(base_url) if base_url is not None else None
        self.__session = ClientSession(
            base_url,
            headers=headers,
            connector=connector,
            timeout=timeout,
            response_class=_DescribedResponse,
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    @property
    def closed(self) -> bool:
        """Whether the session is closed"""
        return self.__session.closed

    async def close(self) -> None:
        """Closes the session.  Safe to call more than once."""
        await self.__session.close()

    async def request(self, method: str, url: StrOrURL, **kwargs: "Unpack[_RequestOptions]") -> "_DescribedResponse":
        """
        Sends a request and returns once the response headers arrive.  Read the body, or use
        the response as an async context manager, to release the connection.

        :param method: HTTP method to use
        :param url: URL to request, relative to the base URL if one was given
        :param kwargs: Passed through to `ClientSession.request`
        """
        # Resolved as aiohttp resolves it, where None means no budgets at all.
        if "timeout" not in kwargs:
            budgets = self.__session.timeout
        elif isinstance(timeout := kwargs["timeout"], ClientTimeout):
            budgets = timeout
        elif isinstance(timeout, int | float):
            budgets = ClientTimeout(total=timeout)
        else:
            budgets = ClientTimeout()

        def describe() -> str:
            return f"{method.upper()} {self.__full_url(url, kwargs.get('params'))}"

        start = time.monotonic()
        with _describe_timeout(describe, start, budgets, lambda: "waiting for the response"):
            resp = cast(_DescribedResponse, await self.__session.request(method, url, **kwargs))

        resp.track(describe, start, budgets)
        return resp

    async def get(self, url: StrOrURL, **kwargs: "Unpack[_RequestOptions]") -> "_DescribedResponse":
        """Sends a GET request.  See :meth:`request`."""
        return await self.request("get", url, **kwargs)

    async def post(self, url: StrOrURL, **kwargs: "Unpack[_RequestOptions]") -> "_DescribedResponse":
        """Sends a POST request.  See :meth:`request`."""
        return await self.request("post", url, **kwargs)

    async def stream_download(
        self,
        method: str,
        uri: StrOrURL,
        filename: Path,
        *,
        headers: LooseHeaders | None = None,
        params: Query = None,
    ) -> int:
        """
        Downloads a response body to `filename`, creating its parent directory if needed.  Writes
        each chunk as it arrives, so a file larger than memory still transfers.  Opens the file
        only after the first chunk arrives, and deletes it if the transfer fails.

        :param method: HTTP method to use
        :param uri: URL to request, relative to the base URL if one was given
        :param filename: Local path to write the body to
        :param headers: Optional HTTP headers to include in the request
        :param params: Optional query parameters
        :return: The number of bytes written
        :raises FileNotFoundError: If the resource returns 404
        :raises CblTimeoutError: If the transfer stalls, or exceeds the total budget
        :raises CblTestError: For any other status, or a network error
        """
        written = 0
        resp: _DescribedResponse | None = None
        try:
            resp = await self.request(method, uri, headers=headers, params=params)
            async with resp:
                if resp.status == 404:
                    raise FileNotFoundError(f"{resp.description} returned 404")
                if resp.status != 200:
                    raise CblTestError(
                        f"{resp.description} returned HTTP {resp.status} - {await resp.read_error_detail()}"
                    )

                chunks = resp.content.iter_chunked(_CHUNK_SIZE)
                with resp.describe_body_timeout():
                    first = await anext(chunks, b"")
                    filename.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        async with aiofiles.open(filename, "wb") as f:
                            await f.write(first)
                            written += len(first)
                            async for chunk in chunks:
                                await f.write(chunk)
                                written += len(chunk)
                    except BaseException:
                        # A file left half written is worse than none, since a caller cannot
                        # tell that it is incomplete.
                        filename.unlink(missing_ok=True)
                        raise
        except ClientError as e:
            if resp is None:
                raise CblTestError(f"Network error during {method.upper()} {self.__full_url(uri, params)}: {e}") from e
            raise CblTestError(f"Network error during {resp.description} after {resp.body_progress()}: {e}") from e

        return written

    def __full_url(self, url: StrOrURL, params: Query) -> URL:
        full = URL(url)
        if self.__base_url is not None and not full.absolute:
            full = self.__base_url.join(full)
        return full.extend_query(params) if params else full


def _describe_transfer(received: int, expected: int | None) -> str:
    """
    Describes how much of a response body arrived, for error messages on a transfer that
    did not finish.

    :param received: Bytes actually read so far
    :param expected: Bytes the response promised via Content-Length, or None if it did not say
    :return: Something like "12.3 MiB of 40.0 MiB (31%)", or "12.3 MiB of unknown total"
    """

    def size(n: int) -> str:
        if n < 1024:
            return f"{n} B"
        exponent = min((n.bit_length() - 1) // 10, 3)
        return f"{n / 1024**exponent:.1f} {('KiB', 'MiB', 'GiB')[exponent - 1]}"

    if expected is None:
        return f"{size(received)} of unknown total"
    if expected == 0:
        return f"{size(received)} of 0 B"
    return f"{size(received)} of {size(expected)} ({received * 100 // expected}%)"


def _describe_budgets(budgets: ClientTimeout) -> str:
    parts = [
        f"{name} {value}s"
        for name, value in (
            ("total", budgets.total),
            ("connect", budgets.connect),
            ("sock_connect", budgets.sock_connect),
            ("sock_read", budgets.sock_read),
        )
        if value is not None
    ]
    return f" ({', '.join(parts)})" if parts else ""


@contextmanager
def _describe_timeout(
    describe: Callable[[], str], start: float, budgets: ClientTimeout, phase: Callable[[], str]
) -> Iterator[None]:
    """
    Raise aiohttp's bare TimeoutError, which stringifies to "", as a `CblTimeoutError` naming
    the request `describe()`, `phase()`, the step it was on, and the budgets that applied.
    """
    try:
        yield
    except TimeoutError as e:
        detail = f": {e}" if str(e) else ""
        raise CblTimeoutError(
            f"{describe()} timed out after {time.monotonic() - start:.1f}s {phase()}"
            f"{_describe_budgets(budgets)}{detail}"
        ) from e


class _DescribedResponse(ClientResponse):
    """Covers the body read, which happens after `AsyncHTTPClient.request` returns."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.__describe: Callable[[], str] = lambda: f"{self.method} {self.url}"
        self.__start = time.monotonic()
        self.__budgets = ClientTimeout()

    def track(self, describe: Callable[[], str], start: float, budgets: ClientTimeout) -> None:
        """Records the request as `AsyncHTTPClient.request` sent it, for timeout messages."""
        self.__describe = describe
        self.__start = start
        self.__budgets = budgets

    @property
    def description(self) -> str:
        """The method and URL of the request, as sent"""
        return self.__describe()

    def body_progress(self) -> str:
        """How much of the body arrived, for example: received 3 B of 10 B (30%)"""
        return f"received {_describe_transfer(self.content.total_raw_bytes, self.content_length)}"

    @contextmanager
    def describe_body_timeout(self) -> Iterator[None]:
        """Raises a timeout while reading the body as a `CblTimeoutError` that names the request."""
        with _describe_timeout(
            self.__describe, self.__start, self.__budgets, lambda: f"reading the body, {self.body_progress()}"
        ):
            yield

    async def read(self) -> bytes:
        with self.describe_body_timeout():
            return await super().read()

    async def read_error_detail(self) -> str:
        """
        Reads the head of an error page for a message.  A page can be arbitrarily large, so this
        keeps only the first 4 KiB, and describes the bytes if they are not text.
        """
        with self.describe_body_timeout():
            body = await self.content.read(4 * 1024)
        try:
            return body.decode("utf-8")
        except UnicodeDecodeError:
            return f"binary body of {len(body)} bytes, starting {body[:200]!r}"
